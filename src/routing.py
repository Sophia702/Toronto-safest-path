from typing import Any, Dict, Tuple

import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd

from src.data_paths import get_data_path

# crime_penalty = risk_score * 40.0 (cap 80.0); traffic_penalty is capped directly.
RISK_SCORE_CAP = 2.0
TRAFFIC_PENALTY_CAP = 80.0
# Raw crime counts are naturally higher anywhere with more foot/bike traffic,
# simply from more people passing through - not necessarily more danger per
# visit. At the busiest locations (foot-traffic percentile -> 1.0), crime_risk
# is divided by up to (1 + FOOT_TRAFFIC_DISCOUNT); at zero foot traffic, it's
# left unchanged. This is deliberately based on pedestrian/bike volume, not
# vehicle volume - vehicle traffic doesn't provide the same "eyes on the
# street" effect and is penalized separately below instead.
FOOT_TRAFFIC_DISCOUNT = 0.5


def build_walk_graph(place: str = "Toronto, Ontario, Canada"):
    """Download and return a walkable street graph for Toronto."""
    return ox.graph_from_place(place, network_type="walk", simplify=True)


def _load_crime_data():
    path = get_data_path("Major_Crime_Indicators_Open_Data_1579054118756352687.csv")
    df = pd.read_csv(path)
    df = df[(df["OCC_YEAR"].notna()) & (pd.to_numeric(df["OCC_YEAR"], errors="coerce") >= 2020)]
    df = df[df["OFFENCE"].fillna("").str.contains("Assault|Robbery", case=False, regex=True)]
    # The raw export repeats some incidents as multiple identical rows (same
    # event, offense, coordinates, and date) - without this, those incidents
    # get counted 2-3x toward local crime risk.
    df = df.drop_duplicates(subset="EVENT_UNIQUE_ID")
    df = df[["LONG_WGS84", "LAT_WGS84"]].dropna()
    df = df.rename(columns={"LONG_WGS84": "lon", "LAT_WGS84": "lat"})
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df = df.dropna()
    # (0, 0) is a placeholder for missing geocoding, not a real Toronto location.
    return df[(df["lon"] != 0) & (df["lat"] != 0)]


def _load_traffic_data():
    path = get_data_path("2020-2029_traffic_volumes.csv")
    df = pd.read_csv(path)
    excluded = {"_id", "count_id", "centreline_type", "centreline_id", "px"}
    # Vehicle volume (cars, trucks, buses) is a pedestrian hazard - more of it
    # means more crossings and closer vehicle exposure, so it's penalized.
    # Foot/bike volume is the opposite: more people around means more "eyes on
    # the street", so it's used only to discount crime risk (see
    # FOOT_TRAFFIC_DISCOUNT), not to penalize the route.
    vehicle_columns = [
        col for col in df.columns if any(token in col for token in ["cars", "truck", "bus"]) and col not in excluded
    ]
    foot_columns = [col for col in df.columns if any(token in col for token in ["peds", "bike"]) and col not in excluded]
    df["vehicle_interval_volume"] = df[vehicle_columns].fillna(0).sum(axis=1)
    df["foot_interval_volume"] = df[foot_columns].fillna(0).sum(axis=1)

    # Each row is a 15-minute interval count, and the same intersection
    # (centreline_id) was often resurveyed on several different dates over
    # 2020-2029 - busier intersections tend to get resurveyed more often, so
    # summing every row ever collected conflates "how busy" with "how many
    # times this location happened to be recounted". Sum within each
    # (location, date) to get that day's total, then average across the
    # location's surveyed dates for one representative daily volume.
    daily_totals = (
        df.groupby(["centreline_id", "count_date"])
        .agg(
            vehicle_volume=("vehicle_interval_volume", "sum"),
            foot_volume=("foot_interval_volume", "sum"),
            longitude=("longitude", "first"),
            latitude=("latitude", "first"),
        )
        .reset_index()
    )
    per_location = (
        daily_totals.groupby("centreline_id")
        .agg(
            vehicle_volume=("vehicle_volume", "mean"),
            foot_volume=("foot_volume", "mean"),
            longitude=("longitude", "first"),
            latitude=("latitude", "first"),
        )
        .reset_index()
    )

    per_location = per_location[["longitude", "latitude", "vehicle_volume", "foot_volume"]].dropna()
    per_location["longitude"] = pd.to_numeric(per_location["longitude"], errors="coerce")
    per_location["latitude"] = pd.to_numeric(per_location["latitude"], errors="coerce")
    return per_location.dropna()


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


def _neighborhood_sum_distribution(bins: pd.DataFrame) -> "np.ndarray":
    """3x3 bin-neighborhood sums for every occupied bin, sorted ascending.

    Used as a reference distribution for percentile-based normalization:
    ranking a raw risk sum against this array (rather than dividing by a fixed
    constant and clipping) keeps relative differences visible even among the
    highest-risk areas, instead of flattening everything above a threshold to
    the same capped value.
    """
    lut = {(lat_b, lon_b): value for lat_b, lon_b, value in zip(bins["lat_bin"], bins["lon_bin"], bins["value"])}
    sums = []
    for lat_b, lon_b in zip(bins["lat_bin"], bins["lon_bin"]):
        total = 0.0
        for dlat in (-1, 0, 1):
            for dlon in (-1, 0, 1):
                total += lut.get((lat_b + dlat, lon_b + dlon), 0.0)
        sums.append(total)
    return np.sort(np.array(sums))


def _percentile_rank(value: float, reference_sorted: "np.ndarray") -> float:
    """Fraction (0-1) of reference_sorted that value is at or above."""
    if len(reference_sorted) == 0:
        return 0.0
    return min(1.0, np.searchsorted(reference_sorted, value, side="right") / len(reference_sorted))


def _percentile_penalty(value: float, reference_sorted: "np.ndarray", cap: float) -> float:
    """Scale value to [0, cap] by its percentile rank within reference_sorted."""
    return cap * _percentile_rank(value, reference_sorted)


def attach_safety_weights(graph, crime_df=None, traffic_df=None, avoid_dark: bool = False) -> Dict[str, Any]:
    """Attach crime, traffic, and lighting-derived costs to graph edges."""
    crime_df = crime_df if crime_df is not None else _load_crime_data()
    traffic_df = traffic_df if traffic_df is not None else _load_traffic_data()

    crime_bins = _prepare_binned_counts(crime_df, "lat", "lon")
    vehicle_bins = _prepare_binned_counts(traffic_df, "latitude", "longitude", value_col="vehicle_volume")
    foot_bins = _prepare_binned_counts(traffic_df, "latitude", "longitude", value_col="foot_volume")
    crime_reference = _neighborhood_sum_distribution(crime_bins)
    vehicle_reference = _neighborhood_sum_distribution(vehicle_bins)
    foot_reference = _neighborhood_sum_distribution(foot_bins)

    for node, data in graph.nodes(data=True):
        lat = data.get("y")
        lon = data.get("x")
        crime_risk = _get_local_score(lat, lon, crime_bins)
        vehicle_risk = _get_local_score(lat, lon, vehicle_bins)
        foot_risk = _get_local_score(lat, lon, foot_bins)
        graph.nodes[node]["crime_risk"] = crime_risk
        graph.nodes[node]["vehicle_risk"] = vehicle_risk
        graph.nodes[node]["foot_risk"] = foot_risk

        foot_percentile = _percentile_rank(foot_risk, foot_reference)
        foot_traffic_adjusted_crime_risk = crime_risk / (1.0 + FOOT_TRAFFIC_DISCOUNT * foot_percentile)
        graph.nodes[node]["risk_score"] = _percentile_penalty(
            foot_traffic_adjusted_crime_risk, crime_reference, RISK_SCORE_CAP
        )

    edge_iter = graph.edges(data=True, keys=True) if graph.is_multigraph() else graph.edges(data=True)
    for edge in edge_iter:
        if graph.is_multigraph():
            u, v, k, data = edge
        else:
            u, v, data = edge

        if "length" not in data:
            continue
        u_risk = graph.nodes[u].get("risk_score", 0.0)
        v_risk = graph.nodes[v].get("risk_score", 0.0)
        avg_risk = (u_risk + v_risk) / 2.0
        avg_vehicle_risk = (graph.nodes[u].get("vehicle_risk", 0.0) + graph.nodes[v].get("vehicle_risk", 0.0)) / 2.0
        traffic_penalty = _percentile_penalty(avg_vehicle_risk, vehicle_reference, TRAFFIC_PENALTY_CAP)
        lighting_penalty = 0.0
        if avoid_dark:
            edge_lit = data.get("lit")
            if edge_lit == "no":
                lighting_penalty = 25.0
            elif edge_lit is None:
                lighting_penalty = 10.0

        data["crime_penalty"] = avg_risk * 40.0
        data["traffic_penalty"] = traffic_penalty
        data["lighting_penalty"] = lighting_penalty

        # Unbounded, per-meter routing weight for Dijkstra. compute_safety_score
        # (src/scoring.py) is a separate, clamped 0-100 formula meant only for
        # the whole-route display score in app.py - it must not be reused here,
        # since its distance term is scaled for a whole trip in km and its
        # clamp would make very different edges indistinguishable.
        data["cost"] = data["length"] + data["crime_penalty"] + data["traffic_penalty"] + data["lighting_penalty"]

    return graph


def find_route(graph, start_coord: Tuple[float, float], end_coord: Tuple[float, float], avoid_dark: bool = False):
    """Find a route between two coordinates using a safety-weighted graph."""
    graph = attach_safety_weights(graph, avoid_dark=avoid_dark)
    start_node = ox.distance.nearest_nodes(graph, start_coord[1], start_coord[0])
    end_node = ox.distance.nearest_nodes(graph, end_coord[1], end_coord[0])
    if start_node == end_node:
        # Both addresses snapped to the same nearest node - either they're
        # genuinely on top of each other, or (more likely) at least one is
        # outside the graph's coverage area and got pulled to its nearest
        # edge. Either way there's no meaningful route to show.
        raise ValueError(
            "Start and end addresses both map to the same point on the street "
            "network. They may be outside the supported area or too close together."
        )
    route = nx.shortest_path(graph, start_node, end_node, weight="cost")

    route_length = 0.0
    crime_penalties = []
    traffic_penalties = []
    lighting_penalties = []
    for u, v in zip(route, route[1:]):
        edge_data = graph[u][v]
        edge = next(iter(edge_data.values()), {})
        route_length += edge.get("length", 0.0)
        crime_penalties.append(edge.get("crime_penalty", 0.0))
        traffic_penalties.append(edge.get("traffic_penalty", 0.0))
        lighting_penalties.append(edge.get("lighting_penalty", 0.0))

    edge_count = len(crime_penalties)

    def _mean(values):
        return sum(values) / edge_count if edge_count else 0.0

    return route, {
        "distance_m": route_length,
        # Average per-block exposure along the route, not a total - crime_penalty
        # and traffic_penalty are capped per edge (see attach_safety_weights), so
        # averaging keeps them on that same bounded scale for compute_safety_score
        # regardless of how many edges the route happens to have. Summing here
        # would make any route of more than a few blocks blow past the 0-100 scale
        # even through low-risk areas.
        "crime_penalty": _mean(crime_penalties),
        "traffic_penalty": _mean(traffic_penalties),
        "lighting_penalty": _mean(lighting_penalties),
    }
