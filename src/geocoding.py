import ssl
from functools import lru_cache
from typing import List, Optional, Tuple

import certifi
from geopy.geocoders import Nominatim

_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
_geolocator = Nominatim(user_agent="toronto-safest-path", ssl_context=_SSL_CONTEXT)

# Bounding box roughly covering the City of Toronto, as (top-left, bottom-right)
# (lat, lon) corners, used to bias/restrict search results.
TORONTO_VIEWBOX = [(43.855, -79.639), (43.581, -79.116)]


class GeocodingServiceError(Exception):
    """Raised when the upstream geocoding service cannot be reached."""


def geocode_address(address: str, city: str = "Toronto") -> Optional[Tuple[float, float]]:
    """Geocode a single address to (latitude, longitude)."""
    if not address or not str(address).strip():
        return None

    cleaned = str(address).strip()

    candidates = [
        f"{cleaned}, {city}",
        f"{cleaned}, Toronto, Ontario, Canada",
        cleaned,
    ]

    for query in candidates:
        try:
            location = _geolocator.geocode(
                query,
                timeout=20,
                viewbox=TORONTO_VIEWBOX,
                bounded=True,
                country_codes="ca",
            )
            if location is not None:
                return (location.latitude, location.longitude)
        except Exception:
            continue

    return None


@lru_cache(maxsize=256)
def _geocode_query(cleaned: str, limit: int) -> Tuple[Tuple[str, float, float], ...]:
    locations = _geolocator.geocode(
        cleaned,
        exactly_one=False,
        limit=limit,
        viewbox=TORONTO_VIEWBOX,
        bounded=True,
        country_codes="ca",
        timeout=10,
    )
    if not locations:
        return ()
    return tuple((location.address, location.latitude, location.longitude) for location in locations)


def search_addresses(query: str, limit: int = 5) -> List[Tuple[str, Tuple[float, float]]]:
    """Look up Toronto address suggestions for a partial query.

    Returns a list of (display_name, (latitude, longitude)) pairs suitable
    for feeding into an autocomplete widget. Raises GeocodingServiceError if
    the upstream geocoding service cannot be reached.
    """
    cleaned = str(query).strip()
    if len(cleaned) < 3:
        return []

    try:
        results = _geocode_query(cleaned, limit)
    except Exception as exc:
        raise GeocodingServiceError(str(exc)) from exc

    return [(address, (lat, lon)) for address, lat, lon in results]
