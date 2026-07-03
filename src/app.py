import folium
import osmnx as ox
import streamlit as st
import streamlit.components.v1 as components

from src.geocoding import geocode_address
from src.routing import build_walk_graph, find_route
from src.scoring import build_explanation, compute_safety_score

st.set_page_config(page_title="Toronto Safest Path", layout="wide")

st.title("Toronto Safest Path")
st.write("Find a safer walking route from one address to another.")

start_address = st.text_input("Start address")
end_address = st.text_input("End address")
avoid_dark = st.checkbox("Avoid dark streets")

if st.button("Find route"):
    if not start_address or not end_address:
        st.warning("Please enter both addresses.")
    else:
        start_coords = geocode_address(start_address)
        end_coords = geocode_address(end_address)

        if not start_coords or not end_coords:
            st.error("Could not geocode one or both addresses.")
        else:
            graph = build_walk_graph()
            route, summary = find_route(graph, start_coords, end_coords, avoid_dark=avoid_dark)
            score = compute_safety_score(
                summary["distance_m"],
                summary["crime_penalty"],
                summary["traffic_penalty"],
                summary["lighting_penalty"],
            )
            explanation = build_explanation(summary["crime_penalty"], summary["traffic_penalty"], avoid_dark)

            st.success("Route found")
            st.metric("Safety score", f"{score:.1f}/100")
            st.write(f"Approximate walking distance: {summary['distance_m'] / 1000:.1f} km")
            st.write(explanation)

            if len(route) > 1:
                route_map = ox.plot_route_folium(graph, route, route_color="red", route_width=5)
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
