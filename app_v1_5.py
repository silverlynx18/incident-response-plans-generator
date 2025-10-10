"""
ARPL V1.5 - Traffic Detour Finder
Enhanced version with export functionality.
"""

import streamlit as st
import tempfile
import os
import zipfile
import detour_utils as du
import random
import ast
import pandas as pd
import matplotlib.pyplot as plt
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from shapely.wkt import loads, dumps
from shapely.geometry import LineString
import osmnx as ox
import networkx as nx
from datetime import datetime

st.set_page_config(layout="wide")
st.title("🚦 Traffic Detour Finder V1.5")

# --- Configuration for Local File Paths ---
SHAPEFILE_PATHS = {
    "states": "data/cb_2018_us_state_500k",
    "counties": "data/tiger_2018_counties",
    "mpos": "data/BTS_MPO",
    "ua": "data/tiger_2018_urban_areas",
}

# --- Helper Functions ---
@st.cache_resource
def load_all_shapefiles():
    """Loads all shapefiles from local data directory."""
    gdfs = {}
    gdfs["states"] = load_local_shapefile(SHAPEFILE_PATHS["states"], "States")
    gdfs["counties"] = load_local_shapefile(SHAPEFILE_PATHS["counties"], "Counties")
    gdfs["mpos"] = load_local_shapefile(SHAPEFILE_PATHS["mpos"], "MPOs")
    gdfs["ua"] = load_local_shapefile(SHAPEFILE_PATHS["ua"], "Urban Areas")
    return gdfs

def load_local_shapefile(path, description):
    """Helper to load a single shapefile."""
    if not os.path.isdir(path):
        st.sidebar.warning(f"Directory for {description} not found: '{path}'")
        return None
    shp_files = [f for f in os.listdir(path) if f.endswith('.shp')]
    if not shp_files:
        st.sidebar.warning(f"No .shp file found in '{path}'.")
        return None
    try:
        gdf = gpd.read_file(os.path.join(path, shp_files[0]))
        if gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)
        st.sidebar.success(f"Loaded {description}.")
        return gdf
    except Exception as e:
        st.sidebar.error(f"Error reading {description}: {e}")
    return None

@st.cache_resource
def load_and_prepare_graph_from_polygon(polygon_wkt):
    polygon = loads(polygon_wkt)
    with st.spinner("Downloading network from OpenStreetMap..."):
        graph = ox.graph_from_polygon(polygon, network_type="drive", simplify=True)
    with st.spinner("Cleaning and preparing graph..."):
        graph_clean = du.clean_graph(graph)
        graph_prepared = du.prepare_graph(graph_clean)
    return graph_prepared

# --- Initialize Session State ---
default_state = {
    'graph': None, 'selected_state_name': None, 'selected_jurisdiction_name': None,
    'selected_polygon_wkt': None, 'selected_polygon_bounds': None, 'zoom_to_selection': False,
    'selected_edge_key': "", 'detour_results': None,
    'show_counties': True, 'show_mpos': True, 'show_urban_areas': True,
    'display_mode': 'selection'
}
for key, value in default_state.items():
    if key not in st.session_state:
        st.session_state[key] = value

# --- Sidebar UI ---
with st.sidebar:
    st.header("1. Data Source")
    st.success("✅ Loaded Local Shapefiles (2018)")

    st.header("2. Area Selection")

    # Load shapefiles
    gdfs = load_all_shapefiles()

    if gdfs and gdfs.get("states") is not None:
        # State selection
        state_options = gdfs["states"]["NAME"].tolist()
        selected_state = st.selectbox("Select State:", state_options, key="state_select")

        if selected_state:
            st.session_state.selected_state_name = selected_state
            state_gdf = gdfs["states"][gdfs["states"]["NAME"] == selected_state]

            # Jurisdiction type selection
            jurisdiction_type = st.selectbox(
                "Select Jurisdiction Type:",
                ["Counties", "MPOs", "Urban Areas"],
                key="jurisdiction_type_select"
            )

            # Jurisdiction selection based on type
            if jurisdiction_type == "Counties" and gdfs.get("counties") is not None:
                counties_in_state = gdfs["counties"][gdfs["counties"]["STATE_NAME"] == selected_state]
                if not counties_in_state.empty:
                    county_options = counties_in_state["NAME"].tolist()
                    selected_jurisdiction = st.selectbox("Select County:", county_options, key="county_select")
                    if selected_jurisdiction:
                        selected_gdf = counties_in_state[counties_in_state["NAME"] == selected_jurisdiction]
                        st.session_state.selected_jurisdiction_name = selected_jurisdiction
                        st.session_state.selected_jurisdiction_type = "County"

            elif jurisdiction_type == "MPOs" and gdfs.get("mpos") is not None:
                mpos_in_state = gdfs["mpos"][gdfs["mpos"]["STATE"] == selected_state]
                if not mpos_in_state.empty:
                    mpo_options = mpos_in_state["NAME"].tolist()
                    selected_jurisdiction = st.selectbox("Select MPO:", mpo_options, key="mpo_select")
                    if selected_jurisdiction:
                        selected_gdf = mpos_in_state[mpos_in_state["NAME"] == selected_jurisdiction]
                        st.session_state.selected_jurisdiction_name = selected_jurisdiction
                        st.session_state.selected_jurisdiction_type = "MPO"

            elif jurisdiction_type == "Urban Areas" and gdfs.get("ua") is not None:
                ua_in_state = gdfs["ua"][gdfs["ua"]["STATE"] == selected_state]
                if not ua_in_state.empty:
                    ua_options = ua_in_state["NAME"].tolist()
                    selected_jurisdiction = st.selectbox("Select Urban Area:", ua_options, key="ua_select")
                    if selected_jurisdiction:
                        selected_gdf = ua_in_state[ua_in_state["NAME"] == selected_jurisdiction]
                        st.session_state.selected_jurisdiction_name = selected_jurisdiction
                        st.session_state.selected_jurisdiction_type = "Urban Area"

            # Store selected geometry
            if 'selected_gdf' in locals() and not selected_gdf.empty:
                geometry = selected_gdf.iloc[0].geometry
                st.session_state.selected_polygon_wkt = dumps(geometry)
                st.session_state.selected_polygon_bounds = geometry.bounds
                st.session_state.zoom_to_selection = True

    st.header("3. Network Preparation")

    if st.session_state.selected_polygon_wkt:
        if st.button("🔄 Load Network"):
            with st.spinner("Loading network..."):
                graph = load_and_prepare_graph_from_polygon(st.session_state.selected_polygon_wkt)
                if graph:
                    st.session_state.graph = graph
                    st.success("✅ Network loaded")
                    st.info(f"📊 Nodes: {len(graph.nodes())}, Edges: {len(graph.edges())}")
                else:
                    st.error("❌ Failed to load network")

    st.header("4. Incident Selection")

    if st.session_state.graph:
        # Get edge options for incident selection
        edge_options = []
        for u, v, data in st.session_state.graph.edges(data=True):
            edge_name = data.get('name', 'Unnamed')
            if isinstance(edge_name, list):
                edge_name = edge_name[0] if edge_name else 'Unnamed'
            edge_options.append(f"{u}-{v}: {edge_name}")

        # Limit options for UI performance
        if len(edge_options) > 100:
            edge_options = edge_options[:100]
            st.info(f"Showing first 100 edges (total: {len(st.session_state.graph.edges())})")

        selected_edge = st.selectbox("Select Incident Edge:", edge_options, key="edge_select")

        if selected_edge:
            # Parse selected edge
            edge_parts = selected_edge.split(':')[0].split('-')
            if len(edge_parts) == 2:
                u, v = int(edge_parts[0]), int(edge_parts[1])
                st.session_state.selected_incident_edge = (u, v)
                st.session_state.selected_edge_key = selected_edge
                st.success("✅ Incident edge selected")

    st.header("5. Analysis Parameters")

    n_turn_nodes = st.slider("Number of Turn Nodes", 1, 20, 5, key="turn_nodes")
    sector_angle = st.slider("Sector Angle (degrees)", 30, 360, 180, key="sector_angle")
    max_detour_length = st.slider("Max Detour Length (miles)", 0.5, 5.0, 2.0, key="max_detour")

# --- Main Content Area ---
if st.session_state.graph and st.session_state.selected_incident_edge:
    st.header("🔍 Detour Analysis")

    if st.button("🚀 Find Detours", type="primary"):
        with st.spinner("Analyzing detour routes..."):
            # Run detour analysis
            detour_results = du.find_detour_routes(
                st.session_state.graph,
                st.session_state.selected_incident_edge[0],
                st.session_state.selected_incident_edge[1],
                turn_nodes=n_turn_nodes,
                sector_angle=sector_angle,
                max_detour_length=max_detour_length
            )

            st.session_state.detour_results = detour_results
            st.success("✅ Analysis complete")

    # Display results
    if st.session_state.detour_results:
        st.subheader("📊 Analysis Results")

        # Results table
        results_data = []
        for i, ((start, end), (valid, total, freeflow, path)) in enumerate(st.session_state.detour_results.items()):
            results_data.append({
                'Route': f"Route {i+1}",
                'Start': start,
                'End': end,
                'Valid': '✅' if valid else '❌',
                'Total Time (min)': f"{total/60:.1f}" if isinstance(total, (int, float)) else str(total),
                'Freeflow Time (min)': f"{freeflow/60:.1f}" if isinstance(freeflow, (int, float)) else str(freeflow),
                'Nodes': len(path) if path else 0
            })

        results_df = pd.DataFrame(results_data)
        st.dataframe(results_df, use_container_width=True)

        # Map visualization
        if st.session_state.selected_polygon_bounds:
            st.subheader("🗺️ Route Visualization")

            # Create map
            center_lat = (st.session_state.selected_polygon_bounds[1] + st.session_state.selected_polygon_bounds[3]) / 2
            center_lon = (st.session_state.selected_polygon_bounds[0] + st.session_state.selected_polygon_bounds[2]) / 2

            m = folium.Map(
                location=[center_lat, center_lon],
                zoom_start=12,
                tiles='OpenStreetMap'
            )

            # Add jurisdiction boundary
            if st.session_state.selected_polygon_wkt:
                polygon = loads(st.session_state.selected_polygon_wkt)
                folium.GeoJson(
                    dumps(polygon),
                    style_function=lambda x: {'fillColor': 'lightblue', 'color': 'blue', 'weight': 2}
                ).add_to(m)

            # Add incident point
            if st.session_state.selected_incident_edge and st.session_state.graph.has_edge(*st.session_state.selected_incident_edge):
                incident_geom = st.session_state.graph.edges[st.session_state.selected_incident_edge].get('geometry')
                if incident_geom:
                    center = incident_geom.centroid
                    folium.Marker(
                        [center.y, center.x],
                        popup="Incident Location",
                        icon=folium.Icon(color='red', icon='warning-sign')
                    ).add_to(m)

            # Add detour routes
            colors = ['red', 'blue', 'green', 'purple', 'orange', 'darkred', 'lightred', 'beige', 'darkblue', 'darkgreen']
            for i, ((start, end), (valid, total, freeflow, path)) in enumerate(st.session_state.detour_results.items()):
                if valid and path:
                    coords = []
                    for node in path:
                        if node in st.session_state.graph.nodes:
                            coords.append([st.session_state.graph.nodes[node]['y'], st.session_state.graph.nodes[node]['x']])

                    if len(coords) > 1:
                        color = colors[i % len(colors)]
                        folium.PolyLine(
                            coords,
                            color=color,
                            weight=3,
                            popup=f"Route {i+1}: {total/60:.1f} min"
                        ).add_to(m)

            st_folium(m, width=700, height=500)

st.divider()
st.caption("ARPL V1.5 - Traffic Detour Finder | Built with Streamlit, NetworkX, and OSMnx")
