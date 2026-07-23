import sys
import threading
from pathlib import Path

import networkx as nx
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.geocoding import GeocodingServiceError, search_addresses
from src.routing import attach_safety_weights, build_walk_graph, find_route
from src.scoring import (
    CRIME_PENALTY_MAX,
    LIGHTING_PENALTY_MAX,
    TRAFFIC_PENALTY_MAX,
    build_explanation,
    compute_safety_score,
)

FRONTEND_DIR = PROJECT_ROOT / "frontend"

# Two-tier lazy cache: the raw OSM graph is expensive to download and doesn't
# depend on avoid_dark, so it's built once and copied per weighted variant.
# Each tier has its own lock, always acquired in this order (weighted -> base),
# so concurrent cold-start requests serialize instead of racing or deadlocking.
_base_graph_lock = threading.Lock()
_base_graph = None

_weighted_graph_lock = threading.Lock()
_weighted_graphs: dict = {}


def _get_base_graph():
    global _base_graph
    if _base_graph is None:
        with _base_graph_lock:
            if _base_graph is None:
                _base_graph = build_walk_graph()
    return _base_graph


def _get_weighted_graph(avoid_dark: bool):
    graph = _weighted_graphs.get(avoid_dark)
    if graph is None:
        with _weighted_graph_lock:
            graph = _weighted_graphs.get(avoid_dark)
            if graph is None:
                graph = attach_safety_weights(_get_base_graph().copy(), avoid_dark=avoid_dark)
                _weighted_graphs[avoid_dark] = graph
    return graph


class AddressSuggestion(BaseModel):
    label: str
    lat: float
    lon: float


class AddressSearchResponse(BaseModel):
    results: list[AddressSuggestion]


class RouteRequest(BaseModel):
    start_lat: float = Field(ge=-90, le=90)
    start_lon: float = Field(ge=-180, le=180)
    end_lat: float = Field(ge=-90, le=90)
    end_lon: float = Field(ge=-180, le=180)
    avoid_dark: bool = False


class PenaltyBreakdown(BaseModel):
    value: float
    cap: float


class RouteBreakdown(BaseModel):
    crime: PenaltyBreakdown
    traffic: PenaltyBreakdown
    lighting: PenaltyBreakdown


class RouteResponse(BaseModel):
    distance_m: float
    safety_score: float
    explanation: str
    breakdown: RouteBreakdown
    route: list[tuple[float, float]]


router = APIRouter(prefix="/api")


@router.get("/addresses", response_model=AddressSearchResponse, summary="Search Toronto addresses")
def get_addresses(q: str = "", limit: int = 5):
    try:
        results = search_addresses(q, limit)
    except GeocodingServiceError:
        raise HTTPException(503, "Address lookup is temporarily unavailable. Please try again in a moment.")
    return AddressSearchResponse(
        results=[AddressSuggestion(label=label, lat=lat, lon=lon) for label, (lat, lon) in results]
    )


@router.post("/route", response_model=RouteResponse, summary="Compute the safest walking route")
def post_route(body: RouteRequest):
    graph = _get_weighted_graph(body.avoid_dark)
    try:
        route_nodes, summary = find_route(graph, (body.start_lat, body.start_lon), (body.end_lat, body.end_lon))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except nx.NetworkXNoPath:
        raise HTTPException(404, "No walking route could be found between these two points.")

    score = compute_safety_score(
        summary["distance_m"], summary["crime_penalty"], summary["traffic_penalty"], summary["lighting_penalty"]
    )
    explanation = build_explanation(summary["crime_penalty"], summary["traffic_penalty"], body.avoid_dark)
    route_latlon = [(graph.nodes[n]["y"], graph.nodes[n]["x"]) for n in route_nodes]

    return RouteResponse(
        distance_m=summary["distance_m"],
        safety_score=score,
        explanation=explanation,
        breakdown=RouteBreakdown(
            crime=PenaltyBreakdown(value=summary["crime_penalty"], cap=CRIME_PENALTY_MAX),
            traffic=PenaltyBreakdown(value=summary["traffic_penalty"], cap=TRAFFIC_PENALTY_MAX),
            lighting=PenaltyBreakdown(value=summary["lighting_penalty"], cap=LIGHTING_PENALTY_MAX),
        ),
        route=route_latlon,
    )


app = FastAPI(
    title="Toronto Safest Path API",
    description="Computes walking routes in Toronto weighted by crime and traffic exposure, not just distance.",
)
app.include_router(router)
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
