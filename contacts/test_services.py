from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase

from contacts import services


class ServicesTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_geocode_caches_hit_and_miss(self):
        with patch("contacts.services.requests.get") as get:
            get.return_value.json.return_value = [{"lat": "1.5", "lon": "2.5"}]
            get.return_value.raise_for_status.return_value = None
            self.assertEqual(services.geocode_city("nowhere"), (1.5, 2.5))
            self.assertEqual(services.geocode_city("nowhere"), (1.5, 2.5))
            self.assertEqual(get.call_count, 1)  # second call hit the cache

        with patch("contacts.services.requests.get") as get:
            get.return_value.json.return_value = []
            get.return_value.raise_for_status.return_value = None
            self.assertIsNone(services.geocode_city("typocity"))
            self.assertIsNone(services.geocode_city("typocity"))
            self.assertEqual(get.call_count, 1)  # negative result also cached

    def test_fetch_weather_matches_humidity_by_hour(self):
        with patch("contacts.services.requests.get") as get:
            get.return_value.raise_for_status.return_value = None
            get.return_value.json.return_value = {
                "current_weather": {"temperature": 20, "windspeed": 5, "time": "2026-07-29T12:00"},
                "hourly": {
                    "time": ["2026-07-29T11:00", "2026-07-29T12:00"],
                    "relative_humidity_2m": [40, 55],
                },
            }
            result = services.fetch_weather(1.0, 2.0)
            self.assertEqual(result, {"temperature": 20, "humidity": 55, "windspeed": 5})

    def test_request_failure_returns_none(self):
        with patch("contacts.services.requests.get", side_effect=services.requests.RequestException):
            self.assertIsNone(services.geocode_city("x"))
            self.assertIsNone(services.fetch_weather(1.0, 2.0))
            self.assertIsNone(services.get_city_weather("x"))
