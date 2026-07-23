import unittest
from unittest.mock import MagicMock, patch

import networkx as nx
from fastapi.testclient import TestClient

import src.api as api
from src.geocoding import GeocodingServiceError


class ApiAddressesTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app)

    def test_get_addresses_returns_results(self):
        with patch("src.api.search_addresses", return_value=[("123 Main St, Toronto", (43.65, -79.38))]):
            response = self.client.get("/api/addresses", params={"q": "123 Main"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"results": [{"label": "123 Main St, Toronto", "lat": 43.65, "lon": -79.38}]},
        )

    def test_get_addresses_maps_service_error_to_503(self):
        with patch("src.api.search_addresses", side_effect=GeocodingServiceError("boom")):
            response = self.client.get("/api/addresses", params={"q": "123 Main"})
        self.assertEqual(response.status_code, 503)

    def test_get_addresses_short_query_returns_empty_without_calling_geocoder(self):
        # Uses the real search_addresses - its own <3-char short-circuit means
        # this never touches the network, so it's safe to leave unpatched.
        response = self.client.get("/api/addresses", params={"q": "ab"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"results": []})


class ApiRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app)
        self.graph = nx.Graph()
        self.graph.add_node("a", x=-79.38, y=43.65)
        self.graph.add_node("b", x=-79.37, y=43.65)
        self.request_body = {
            "start_lat": 43.65,
            "start_lon": -79.38,
            "end_lat": 43.65,
            "end_lon": -79.37,
            "avoid_dark": False,
        }

    def test_post_route_returns_expected_shape(self):
        summary = {"distance_m": 1000.0, "crime_penalty": 20.0, "traffic_penalty": 10.0, "lighting_penalty": 0.0}
        with patch("src.api._get_weighted_graph", return_value=self.graph), patch(
            "src.api.find_route", return_value=(["a", "b"], summary)
        ):
            response = self.client.post("/api/route", json=self.request_body)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["distance_m"], 1000.0)
        self.assertIn("safety_score", body)
        self.assertIn("explanation", body)
        self.assertEqual(body["breakdown"]["crime"], {"value": 20.0, "cap": 80.0})
        self.assertEqual(body["breakdown"]["traffic"], {"value": 10.0, "cap": 80.0})
        self.assertEqual(body["breakdown"]["lighting"], {"value": 0.0, "cap": 25.0})
        self.assertEqual(body["route"], [[43.65, -79.38], [43.65, -79.37]])

    def test_post_route_maps_value_error_to_400(self):
        with patch("src.api._get_weighted_graph", return_value=self.graph), patch(
            "src.api.find_route", side_effect=ValueError("same node")
        ):
            response = self.client.post("/api/route", json=self.request_body)
        self.assertEqual(response.status_code, 400)

    def test_post_route_maps_no_path_to_404(self):
        with patch("src.api._get_weighted_graph", return_value=self.graph), patch(
            "src.api.find_route", side_effect=nx.NetworkXNoPath("no path")
        ):
            response = self.client.post("/api/route", json=self.request_body)
        self.assertEqual(response.status_code, 404)


class GraphCacheTests(unittest.TestCase):
    def setUp(self):
        api._base_graph = None
        api._weighted_graphs = {}

    def tearDown(self):
        api._base_graph = None
        api._weighted_graphs = {}

    def test_get_weighted_graph_builds_base_graph_only_once(self):
        base_graph = MagicMock()
        base_graph.copy.return_value = MagicMock()
        with patch("src.api.build_walk_graph", return_value=base_graph) as mock_build, patch(
            "src.api.attach_safety_weights", side_effect=lambda graph, avoid_dark: graph
        ):
            api._get_weighted_graph(False)
            api._get_weighted_graph(False)
            api._get_weighted_graph(True)

        mock_build.assert_called_once()

    def test_get_weighted_graph_caches_separately_per_avoid_dark(self):
        base_graph = MagicMock()
        base_graph.copy.side_effect = lambda: MagicMock()
        with patch("src.api.build_walk_graph", return_value=base_graph), patch(
            "src.api.attach_safety_weights", side_effect=lambda graph, avoid_dark: graph
        ):
            graph_false = api._get_weighted_graph(False)
            graph_true = api._get_weighted_graph(True)

        self.assertIsNot(graph_false, graph_true)


if __name__ == "__main__":
    unittest.main()
