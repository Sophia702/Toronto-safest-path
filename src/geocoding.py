from typing import Optional, Tuple

from geopy.geocoders import Nominatim


def geocode_address(address: str, city: str = "Toronto") -> Optional[Tuple[float, float]]:
    """Geocode a single address to (latitude, longitude)."""
    geolocator = Nominatim(user_agent="toronto-safest-path")
    try:
        location = geolocator.geocode(f"{address}, {city}")
        if location is None:
            return None
        return (location.latitude, location.longitude)
    except Exception:
        return None
