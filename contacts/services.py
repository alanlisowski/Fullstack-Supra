"""Weather lookup for contact cities: geocode -> forecast, both cached."""
import logging
from typing import NamedTuple

import requests
from django.core.cache import cache

logger = logging.getLogger(__name__)


class Place(NamedTuple):
    """A geocoded location, kept with the label Nominatim actually matched.

    Carrying display_name is what lets the UI show *which* place it found:
    "Londo" resolves to a river in the DRC, and without that label the user
    just sees plausible-looking weather for somewhere they never meant.
    """

    lat: float
    lon: float
    display_name: str

# Nominatim rejects requests with no User-Agent (403), so we always identify ourselves.
USER_AGENT = "supra-contacts/1.0"

TIMEOUT = 5
GEOCODE_TTL = 60 * 60 * 24 * 7  # coordinates don't change; cache a week
GEOCODE_MISS_TTL = 60 * 60  # typo'd city: don't hammer the API every page load
WEATHER_TTL = 60 * 30
CANDIDATES_TTL = 60 * 60 * 24  # place names are stable
CANDIDATES_LIMIT = 5

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


def geocode_city(city: str) -> Place:
    key = f"geo:{city}"
    cached = cache.get(key)
    if cached is not None:
        if cached == _GEOCODE_MISS:
            raise CityNotFound(city)
        return cached

    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": city,
                "format": "json",
                "limit": 1,
                # Without this, Nominatim happily matches rivers, mountains and
                # bus stops: "Londo" returns a river in the DRC rather than
                # failing, and the user gets confident weather for the wrong
                # continent. "settlement" covers cities, towns and villages.
                "featureType": "settlement",
            },
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

    top = results[0]
    place = Place(float(top["lat"]), float(top["lon"]), top.get("display_name", city))
    cache.set(key, place, GEOCODE_TTL)
    return place


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


def _candidate_label(display_name: str) -> str:
    """Condense Nominatim's address chain into something pickable.

    "Springfield, Sangamon County, Illinois, United States" becomes
    "Springfield, Illinois, United States" — the region is what tells same-named
    towns apart, so only the middle is dropped.
    """
    parts = [p.strip() for p in display_name.split(",") if p.strip()]
    if len(parts) >= 3:
        label = f"{parts[0]}, {parts[-2]}, {parts[-1]}"
    else:
        label = ", ".join(parts)
    return label[:100]  # Contact.city is CharField(max_length=100)


def find_settlements(city: str) -> list[str]:
    """Places matching this name, most relevant first.

    Used to ask "did you mean?" when a name is ambiguous. Storing the label the
    user picks means the ambiguity is resolved once, at write time, instead of
    being re-guessed on every page load.
    """
    normalized = city.strip().casefold()
    if not normalized:
        return []

    key = f"candidates:{normalized}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": normalized,
                "format": "json",
                "limit": CANDIDATES_LIMIT,
                "featureType": "settlement",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        results = resp.json()
    except requests.RequestException as exc:
        logger.warning("find_settlements: request failed for %r", city)
        raise WeatherUnavailable("geocoding service unreachable") from exc

    labels = []
    for result in results:
        label = _candidate_label(result.get("display_name", ""))
        if label and label not in labels:
            labels.append(label)

    cache.set(key, labels, CANDIDATES_TTL)
    return labels


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

    place = geocode_city(normalized)
    weather = fetch_weather(place.lat, place.lon)
    # Pass the matched place name through so the UI can show what was actually
    # resolved, rather than leaving a near-miss looking authoritative.
    weather["location"] = place.display_name
    cache.set(key, weather, WEATHER_TTL)
    return weather
