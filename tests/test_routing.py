import unittest

import networkx as nx
import pandas as pd

from src.routing import attach_safety_weights


class RoutingTests(unittest.TestCase):
    def test_attach_safety_weights_uses_additive_formula_for_edge_cost(self):
        graph = nx.Graph()
        graph.add_node("a", x=-79.38, y=43.65)
        graph.add_node("b", x=-79.37, y=43.65)
        graph.add_edge("a", "b", length=1000.0, lit="yes")

        crime_df = {
            "lat": [43.65],
            "lon": [-79.38],
        }
        traffic_df = {
            "latitude": [43.65],
            "longitude": [-79.38],
            "vehicle_volume": [50],
            "foot_volume": [20],
        }

        graph = attach_safety_weights(
            graph,
            crime_df=pd.DataFrame(crime_df),
            traffic_df=pd.DataFrame(traffic_df),
            avoid_dark=False,
        )

        edge = graph["a"]["b"]
        expected_cost = 1000.0 + edge["crime_penalty"] + edge["traffic_penalty"] + edge["lighting_penalty"]
        self.assertAlmostEqual(edge["cost"], expected_cost)


if __name__ == "__main__":
    unittest.main()
