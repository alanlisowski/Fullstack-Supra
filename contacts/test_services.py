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

    def test_fetch_weather_reads_current_block(self):
        with patch("contacts.services.requests.get") as get:
            get.return_value.raise_for_status.return_value = None
            get.return_value.json.return_value = {
                "current": {"temperature_2m": 20, "relative_humidity_2m": 55, "wind_speed_10m": 5},
            }
            result = services.fetch_weather(1.0, 2.0)
            self.assertEqual(result, {"temperature": 20, "humidity": 55, "windspeed": 5})

    def test_fetch_weather_bad_payload_returns_none(self):
        with patch("contacts.services.requests.get") as get:
            get.return_value.raise_for_status.return_value = None
            get.return_value.json.return_value = {"current": {}}
            self.assertIsNone(services.fetch_weather(1.0, 2.0))

    def test_request_failure_returns_none(self):
        with patch("contacts.services.requests.get", side_effect=services.requests.RequestException):
            self.assertIsNone(services.geocode_city("x"))
            self.assertIsNone(services.fetch_weather(1.0, 2.0))
            self.assertIsNone(services.get_city_weather("x"))
