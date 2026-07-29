"""Weather lookup for contact cities: geocode -> forecast, both cached."""
import logging

import requests
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Nominatim rejects requests with no User-Agent (403), so we always identify ourselves.
USER_AGENT = "supra-contacts/1.0"

TIMEOUT = 5
GEOCODE_TTL = 60 * 60 * 24 * 7  # coordinates don't change; cache a week
GEOCODE_MISS_TTL = 60 * 60  # typo'd city: don't hammer the API every page load
WEATHER_TTL = 60 * 30

_GEOCODE_MISS = "__miss__"  # cache.get pickles values, so identity won't survive a round-trip; compare by value


class CityNotFound(Exception):
    """The geocoder answered, and the place does not exist.

    Permanent for a given spelling: the user mistyped. Worth caching and worth
    telling them about, since only they can fix it.
    """


class WeatherUnavailable(Exception):
    """An upstream service failed to answer.

    Transient and not the user's fault, so it is never cached — the next
    request should try again.
    """


def geocode_city(city: str) -> tuple[float, float]:
    key = f"geo:{city}"
    cached = cache.get(key)
    if cached is not None:
        if cached == _GEOCODE_MISS:
            raise CityNotFound(city)
        return cached

    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": city, "format": "json", "limit": 1},
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        results = resp.json()
    except requests.RequestException as exc:
        logger.warning("geocode_city: request failed for %r", city)
        raise WeatherUnavailable("geocoding service unreachable") from exc

    if not results:
        cache.set(key, _GEOCODE_MISS, GEOCODE_MISS_TTL)
        raise CityNotFound(city)

    coords = (float(results[0]["lat"]), float(results[0]["lon"]))
    cache.set(key, coords, GEOCODE_TTL)
    return coords


def fetch_weather(lat: float, lon: float) -> dict:
    try:
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                # The legacy "current_weather=true" block carries no humidity,
                # which forced a fragile lookup into the hourly series by
                # timestamp. The "current=" parameter returns all three values
                # we need directly, so there is nothing to match up.
                "current": "temperature_2m,relative_humidity_2m,wind_speed_10m",
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        logger.warning("fetch_weather: request failed for %s,%s", lat, lon)
        raise WeatherUnavailable("weather service unreachable") from exc

    try:
        current = data["current"]
        return {
            "temperature": current["temperature_2m"],
            "humidity": current["relative_humidity_2m"],
            "windspeed": current["wind_speed_10m"],
        }
    except KeyError as exc:
        # An unexpected payload shape must not be cached or rendered as a
        # half-filled row; treat it the same as a failed request.
        logger.warning("fetch_weather: unexpected payload for %s,%s", lat, lon)
        raise WeatherUnavailable("unexpected weather payload") from exc


def get_city_weather(city: str) -> dict:
    """Current conditions for a city.

    Raises CityNotFound if the place doesn't exist, WeatherUnavailable if a
    service is down. Callers need to tell those apart: one is a typo the user
    should fix, the other is nothing they can act on.
    """
    normalized = city.strip().casefold()
    key = f"weather:{normalized}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    weather = fetch_weather(*geocode_city(normalized))
    cache.set(key, weather, WEATHER_TTL)
    return weather
