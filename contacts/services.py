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


def geocode_city(city: str) -> tuple[float, float] | None:
    key = f"geo:{city}"
    cached = cache.get(key)
    if cached is not None:
        return None if cached == _GEOCODE_MISS else cached

    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": city, "format": "json", "limit": 1},
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        results = resp.json()
    except requests.RequestException:
        logger.warning("geocode_city: request failed for %r", city)
        return None

    if not results:
        cache.set(key, _GEOCODE_MISS, GEOCODE_MISS_TTL)
        return None

    coords = (float(results[0]["lat"]), float(results[0]["lon"]))
    cache.set(key, coords, GEOCODE_TTL)
    return coords


def fetch_weather(lat: float, lon: float) -> dict | None:
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
    except requests.RequestException:
        logger.warning("fetch_weather: request failed for %s,%s", lat, lon)
        return None

    try:
        current = data["current"]
        return {
            "temperature": current["temperature_2m"],
            "humidity": current["relative_humidity_2m"],
            "windspeed": current["wind_speed_10m"],
        }
    except KeyError:
        # An unexpected payload shape must not be cached or rendered as a
        # half-filled row; treat it the same as a failed request.
        logger.warning("fetch_weather: unexpected payload for %s,%s", lat, lon)
        return None


def get_city_weather(city: str) -> dict | None:
    normalized = city.strip().casefold()
    key = f"weather:{normalized}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    coords = geocode_city(normalized)
    if coords is None:
        return None

    weather = fetch_weather(*coords)
    if weather is None:
        return None

    cache.set(key, weather, WEATHER_TTL)
    return weather
