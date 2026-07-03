from typing import Any, Dict, Tuple

import networkx as nx
import osmnx as ox
import pandas as pd

from src.data_paths import get_data_path


def build_walk_graph(place: str = "Toronto, Ontario, Canada"):
    """Download and return a walkable street graph for Toronto."""
    return ox.graph_from_place(place, network_type="walk", simplify=True)


def _load_crime_data():
    path = get_data_path("Major_Crime_Indicators_Open_Data_1579054118756352687.csv")
    df = pd.read_csv(path)
    df = df[(df["OCC_YEAR"].notna()) & (pd.to_numeric(df["OCC_YEAR"], errors="coerce") >= 2020)]
    df = df[df["OFFENCE"].fillna("").str.contains("Assault|Robbery", case=False, regex=True)]
    df = df[["LONG_WGS84", "LAT_WGS84"]].dropna()
    df = df.rename(columns={"LONG_WGS84": "lon", "LAT_WGS84": "lat"})
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    return df.dropna()


def _load_traffic_data():
    path = get_data_path("2020-2029_traffic_volumes.csv")
    df = pd.read_csv(path)
    traffic_columns = [
        col
        for col in df.columns
        if any(token in col for token in ["peds", "bike", "cars", "bus"])
        and col not in {"_id", "count_id", "centreline_type", "centreline_id", "px"}
    ]
    df["total_volume"] = df[traffic_columns].fillna(0).sum(axis=1)
    df = df[["longitude", "latitude", "total_volume"]].dropna()
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    return df.dropna()


def _prepare_binned_counts(df, lat_col: str, lon_col: str, value_col: str | None = None, step: float = 0.005):
    out = df.copy()
    out["lat_bin"] = (out[lat_col] / step).astype(int)
    out["lon_bin"] = (out[lon_col] / step).astype(int)
    if value_col is None:
        out = out.groupby(["lat_bin", "lon_bin"]).size().reset_index(name="value")
    else:
        out = out.groupby(["lat_bin", "lon_bin"])[value_col].sum().reset_index(name="value")
    return out


def _get_local_score(lat: float, lon: float, bins: pd.DataFrame, step: float = 0.005) -> float:
    base_lat = int(lat / step)
    base_lon = int(lon / step)
    total = 0.0
    for lat_offset in (-1, 0, 1):
        for lon_offset in (-1, 0, 1):
            subset = bins[(bins["lat_bin"] == base_lat + lat_offset) & (bins["lon_bin"] == base_lon + lon_offset)]
            if not subset.empty:
                total += subset["value"].sum()
    return total


def attach_safety_weights(graph, crime_df=None, traffic_df=None, avoid_dark: bool = False) -> Dict[str, Any]:
    """Attach crime, traffic, and lighting-derived costs to graph edges."""
    crime_df = crime_df if crime_df is not None else _load_crime_data()
    traffic_df = traffic_df if traffic_df is not None else _load_traffic_data()

    crime_bins = _prepare_binned_counts(crime_df, "lat", "lon")
    traffic_bins = _prepare_binned_counts(traffic_df, "latitude", "longitude", value_col="total_volume")

    for node, data in graph.nodes(data=True):
        lat = data.get("y")
        lon = data.get("x")
        crime_risk = _get_local_score(lat, lon, crime_bins)
        traffic_risk = _get_local_score(lat, lon, traffic_bins)
        graph.nodes[node]["crime_risk"] = crime_risk
        graph.nodes[node]["traffic_risk"] = traffic_risk
        graph.nodes[node]["risk_score"] = min(2.0, crime_risk / 6.0 + traffic_risk / 1200.0)

    for u, v, k, data in graph.edges(keys=True, data=True):
        if "length" not in data:
            continue
        u_risk = graph.nodes[u].get("risk_score", 0.0)
        v_risk = graph.nodes[v].get("risk_score", 0.0)
        avg_risk = (u_risk + v_risk) / 2.0
        traffic_penalty = (graph.nodes[u].get("traffic_risk", 0.0) + graph.nodes[v].get("traffic_risk", 0.0)) / 2000.0
        lighting_penalty = 0.0
        if avoid_dark:
            edge_lit = data.get("lit")
            if edge_lit == "no":
                lighting_penalty = 25.0
            elif edge_lit is None:
                lighting_penalty = 10.0

        data["cost"] = data["length"] + avg_risk * 40.0 + traffic_penalty + lighting_penalty
        data["crime_penalty"] = avg_risk * 40.0
        data["traffic_penalty"] = traffic_penalty
        data["lighting_penalty"] = lighting_penalty

    return graph


def find_route(graph, start_coord: Tuple[float, float], end_coord: Tuple[float, float], avoid_dark: bool = False):
    """Find a route between two coordinates using a safety-weighted graph."""
    graph = attach_safety_weights(graph, avoid_dark=avoid_dark)
    start_node = ox.distance.nearest_nodes(graph, start_coord[1], start_coord[0])
    end_node = ox.distance.nearest_nodes(graph, end_coord[1], end_coord[0])
    route = nx.shortest_path(graph, start_node, end_node, weight="cost")

    route_length = 0.0
    crime_penalty = 0.0
    traffic_penalty = 0.0
    lighting_penalty = 0.0
    for u, v in zip(route, route[1:]):
        edge_data = graph[u][v]
        edge = next(iter(edge_data.values()), {})
        route_length += edge.get("length", 0.0)
        crime_penalty += edge.get("crime_penalty", 0.0)
        traffic_penalty += edge.get("traffic_penalty", 0.0)
        lighting_penalty += edge.get("lighting_penalty", 0.0)

    return route, {
        "distance_m": route_length,
        "crime_penalty": crime_penalty,
        "traffic_penalty": traffic_penalty,
        "lighting_penalty": lighting_penalty,
    }
