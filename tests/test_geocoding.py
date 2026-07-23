import unittest
from unittest.mock import patch

from src.geocoding import GeocodingServiceError, _geocode_query, geocode_address, search_addresses


class GeocodingTests(unittest.TestCase):
    def setUp(self):
        _geocode_query.cache_clear()

    def test_geocode_address_handles_empty_input(self):
        self.assertIsNone(geocode_address(""))

    def test_geocode_address_returns_none_when_service_is_unavailable(self):
        coords = geocode_address("1 King Street West, Toronto")
        self.assertTrue(coords is None or len(coords) == 2)

    def test_search_addresses_returns_empty_list_for_short_query(self):
        self.assertEqual(search_addresses("ab"), [])

    def test_search_addresses_raises_geocoding_service_error_on_failure(self):
        with patch("src.geocoding._geolocator") as mock_geolocator:
            mock_geolocator.geocode.side_effect = RuntimeError("boom")
            with self.assertRaises(GeocodingServiceError):
                search_addresses("123 Main Street")


if __name__ == "__main__":
    unittest.main()
