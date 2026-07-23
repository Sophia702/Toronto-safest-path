import sys
from pathlib import Path

import folium
import networkx as nx
import streamlit as st
import streamlit.components.v1 as components
from streamlit_searchbox import st_searchbox

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.geocoding import GeocodingServiceError, search_addresses
from src.routing import build_walk_graph, find_route
from src.scoring import build_explanation, compute_safety_score

st.set_page_config(page_title="Toronto Safest Path", layout="wide")

st.title("Toronto Safest Path")
st.write("Find a safer walking route from one address to another.")


def _search_addresses(query: str):
    try:
        results = search_addresses(query)
    except GeocodingServiceError:
        st.session_state["address_lookup_error"] = True
        return []
    st.session_state["address_lookup_error"] = False
    return results


start_coords = st_searchbox(
    _search_addresses,
    key="start_address_search",
    placeholder="Start address",
    label="Start address",
    debounce=400,
)
end_coords = st_searchbox(
    _search_addresses,
    key="end_address_search",
    placeholder="End address",
    label="End address",
    debounce=400,
)
avoid_dark = st.checkbox("Avoid dark streets")

if st.button("Find route"):
    if st.session_state.get("address_lookup_error"):
        st.error("Address lookup is temporarily unavailable. Please try again in a moment.")
    elif not start_coords or not end_coords:
        st.warning("Please select both addresses from the suggestions.")
    else:
        graph = build_walk_graph()
        try:
            route, summary = find_route(graph, start_coords, end_coords, avoid_dark=avoid_dark)
        except (ValueError, nx.NetworkXNoPath) as exc:
            st.error(f"Could not compute a route: {exc}")
        else:
            score = compute_safety_score(
                summary["distance_m"],
                summary["crime_penalty"],
                summary["traffic_penalty"],
                summary["lighting_penalty"],
            )
            explanation = build_explanation(
                summary["crime_penalty"],
                summary["traffic_penalty"],
                avoid_dark,
            )

            st.success("Route found")
            st.metric("Safety score", f"{score:.1f}/100")
            st.write(f"Approximate walking distance: {summary['distance_m'] / 1000:.1f} km")
            st.write(explanation)

            with st.expander("Route breakdown"):
                st.write(f"- Distance contribution: {summary['distance_m'] / 1000:.1f} km")
                st.write(f"- Average crime exposure per block: {summary['crime_penalty']:.1f}")
                st.write(f"- Average traffic exposure per block: {summary['traffic_penalty']:.1f}")
                st.write(f"- Average lighting penalty per block: {summary['lighting_penalty']:.1f}")

            if len(route) > 1:
                route_coords = [(graph.nodes[node]["y"], graph.nodes[node]["x"]) for node in route]
                route_map = folium.Map(location=route_coords[len(route_coords) // 2], zoom_start=15)
                folium.PolyLine(route_coords, color="red", weight=5).add_to(route_map)
                folium.Marker(
                    [start_coords[0], start_coords[1]],
                    tooltip="Start",
                    icon=folium.Icon(color="green"),
                ).add_to(route_map)
                folium.Marker(
                    [end_coords[0], end_coords[1]],
                    tooltip="End",
                    icon=folium.Icon(color="red"),
                ).add_to(route_map)
                components.html(route_map.get_root().render(), height=500)
