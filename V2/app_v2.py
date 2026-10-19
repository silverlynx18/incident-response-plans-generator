"""
ARPL V2 - Enhanced Traffic Detour Finder
Production-ready application with database persistence, session management,
batch processing, and enhanced data management.
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
import time

# V2 Imports
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))  # Add parent directory to path

from database import DatabaseManager
from session_manager import SessionManager
from analysis_history import AnalysisHistory
from batch_processor import BatchProcessor
from user_preferences import PreferencesManager
from network_cache import NetworkCache
from data_manager import DataManager
from export_utils import create_export_data, PDFReportGenerator, GeospatialExporter, TabularExporter, BatchExporter

# ==============================================================================
# SECTION 1: CONFIGURATION AND SETUP
# ==============================================================================

st.set_page_config(
    page_title="ARPL V2 - Traffic Detour Finder",
    page_icon="🚦",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🚦 ARPL V2 - Traffic Detour Finder")
st.caption("Enhanced with database persistence, session management, and batch processing")

# ==============================================================================
# SECTION 2: INITIALIZE BACKEND SERVICES
# ==============================================================================

# Initialize database and managers
if 'db_manager' not in st.session_state:
    with st.spinner("Initializing ARPL V2 backend services..."):
        st.session_state.db_manager = DatabaseManager()
        st.session_state.session_manager = SessionManager()
        st.session_state.history = AnalysisHistory(st.session_state.db_manager)
        st.session_state.preferences = PreferencesManager(st.session_state.db_manager)
        st.session_state.network_cache = NetworkCache(st.session_state.db_manager)
        st.session_state.data_manager = DataManager()
        st.session_state.batch_processor = BatchProcessor(st.session_state.db_manager)
        st.session_state.batch_exporter = BatchExporter(st.session_state.db_manager)

# ==============================================================================
# SECTION 3: HELPER FUNCTIONS
# ==============================================================================

@st.cache_resource(ttl=3600)  # 1-hour cache
def load_all_shapefiles():
    """Load all shapefiles using DataManager."""
    dm = DataManager()
    return dm.load_all_shapefiles()

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
def load_and_prepare_graph_from_polygon(polygon_wkt, jurisdiction_name):
    """Load and prepare graph with caching enhancement."""
    cache = st.session_state.network_cache
    cache_key = cache.generate_cache_key(jurisdiction_name, polygon_wkt)

    # Check cache first
    cached_graph = cache.load_network(cache_key)
    if cached_graph:
        st.info("✅ Loaded cached network")
        st.session_state.cache_hit = True
        return cached_graph

    # Otherwise download and prepare
    polygon = loads(polygon_wkt)
    with st.spinner("Downloading network from OpenStreetMap..."):
        graph = ox.graph_from_polygon(polygon, network_type="drive", simplify=True)

    with st.spinner("Cleaning and preparing graph..."):
        graph_clean = du.clean_graph(graph)
        graph_prepared = du.prepare_graph(graph_clean)

    # Cache for future use (30 day expiration)
    cache.save_network(cache_key, graph_prepared, jurisdiction_name, expiration_days=30)
    st.session_state.cache_hit = False
    st.session_state.network_cached = True

    return graph_prepared

def convert_graph_to_graphml(graph):
    """Convert graph to GraphML format."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".graphml") as tmp_file:
        ox.save_graphml(graph, filepath=tmp_file.name)
        tmp_file.seek(0)
        return tmp_file.read()

def simplify_large_graph(graph, max_edges=50000):
    """Simplify graph if too large for visualization."""
    if len(graph.edges()) > max_edges:
        st.warning(f"Large network detected ({len(graph.edges())} edges). Simplifying...")
        graph = graph.copy()
        edges_to_remove = [
            (u, v, k) for u, v, k, d in graph.edges(keys=True, data=True)
            if d.get('highway') in ['service', 'residential', 'footway']
        ]
        graph.remove_edges_from(edges_to_remove)
        st.info(f"Simplified to {len(graph.edges())} edges")
    return graph

# ==============================================================================
# SECTION 4: SESSION STATE INITIALIZATION
# ==============================================================================

# Load user preferences on startup
if not st.session_state.get('preferences_loaded'):
    prefs = st.session_state.preferences.get_all()
    for key, value in prefs.items():
        if key not in st.session_state:
            st.session_state[key] = value
    st.session_state.preferences_loaded = True

# Initialize default state
default_state = {
    'graph': None, 'selected_state_name': None, 'selected_jurisdiction_name': None,
    'selected_polygon_wkt': None, 'selected_polygon_bounds': None, 'zoom_to_selection': False,
    'selected_edge_key': "", 'detour_results': None,
    'show_counties': True, 'show_mpos': True, 'show_urban_areas': True,
    'display_mode': 'selection',
    # V2 additions
    'session_id': None,
    'current_session_name': None,
    'preferences_loaded': False,
    'analysis_recorded': False,
    'batch_results': None,
    'cache_hit': False,
    'network_cached': False
}

for key, value in default_state.items():
    if key not in st.session_state:
        st.session_state[key] = value

# ==============================================================================
# SECTION 5: SIDEBAR UI
# ==============================================================================

with st.sidebar:
    st.header("🚦 ARPL V2")

    # Database health check
    with st.expander("🔍 System Status", expanded=False):
        health = st.session_state.db_manager.health_check()
        if health['status'] == 'healthy':
            st.success("✅ Database: Healthy")
            stats = st.session_state.db_manager.get_database_stats()
            st.info(f"📊 Sessions: {stats['sessions']['total']}, Analyses: {stats['analysis_history']['total']}")
        else:
            st.error("❌ Database: Unhealthy")
            st.error(health.get('error', 'Unknown error'))

    st.divider()

    # V2 Session Management
    st.header("💾 Session Management")
    with st.expander("Save/Load Sessions", expanded=False):
        # Save session
        session_name = st.text_input("Session Name:", key="save_session_name")
        if st.button("💾 Save Current Session"):
            if session_name:
                session_id = st.session_state.session_manager.save_session(
                    session_name, dict(st.session_state)
                )
                if session_id:
                    st.session_state.session_id = session_id
                    st.session_state.current_session_name = session_name
                    st.success(f"Session '{session_name}' saved!")
                else:
                    st.error("Failed to save session")

        # Load session
        sessions = st.session_state.session_manager.list_saved_sessions()
        if sessions:
            session_options = {f"{s['name']} ({s['created_at'][:10]})": s['id']
                             for s in sessions}
            selected = st.selectbox("Load Session:", [""] + list(session_options.keys()))
            if selected and st.button("📂 Load Session"):
                session_id = session_options[selected]
                loaded_state = st.session_state.session_manager.load_session(session_id)
                if loaded_state:
                    for key, value in loaded_state.items():
                        st.session_state[key] = value
                    st.success("Session loaded!")
                    st.rerun()
        else:
            st.info("No saved sessions found")

    st.divider()

    # V2 User Preferences
    st.header("⚙️ Preferences")
    with st.expander("Analysis Defaults", expanded=False):
        prefs = st.session_state.preferences
        default_turns = st.slider("Default turn nodes", 1, 20,
                                  prefs.get('default_turn_nodes', 5))
        default_angle = st.slider("Default sector angle", 30, 360,
                                  prefs.get('default_sector_angle', 180))
        default_max_detour = st.slider("Default max detour length (miles)", 0.5, 5.0,
                                       prefs.get('default_max_detour_length', 2.0))

        if st.button("Save Preferences"):
            prefs.save('default_turn_nodes', default_turns)
            prefs.save('default_sector_angle', default_angle)
            prefs.save('default_max_detour_length', default_max_detour)
            st.success("Preferences saved!")

    st.divider()

    # Data Source Section
    st.header("1. Data Source")
    st.success("✅ Loaded Local Shapefiles (2018)")

    # Advanced: Custom URL Download
    with st.expander("🔗 Advanced: Download from Custom URL", expanded=False):
        st.info("💡 Upload custom geospatial data from any URL")

        custom_url = st.text_input("Enter Data URL:", placeholder="https://services.arcgis.com/.../FeatureServer/2")

        if st.button("Download Custom Data") and custom_url:
            with st.spinner("Downloading custom data..."):
                custom_gdf = st.session_state.data_manager.load_custom_data(custom_url)
                if custom_gdf is not None:
                    st.session_state.custom_data = custom_gdf
                    st.success("✅ Custom data loaded successfully!")
                else:
                    st.error("❌ Failed to load custom data")

    st.divider()

    # Area Selection Section
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

    st.divider()

    # Network Preparation Section
    st.header("3. Network Preparation")

    if st.session_state.selected_polygon_wkt:
        if st.button("🔄 Load Network"):
            with st.spinner("Loading network..."):
                start_time = time.time()
                graph = load_and_prepare_graph_from_polygon(
                    st.session_state.selected_polygon_wkt,
                    st.session_state.selected_jurisdiction_name
                )
                load_time = time.time() - start_time

                if graph:
                    st.session_state.graph = graph
                    st.success(f"✅ Network loaded in {load_time:.2f} seconds")
                    st.info(f"📊 Nodes: {len(graph.nodes())}, Edges: {len(graph.edges())}")
                else:
                    st.error("❌ Failed to load network")

    st.divider()

    # Incident Selection Section
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

    st.divider()

    # Analysis Parameters Section
    st.header("5. Analysis Parameters")

    # Get default values from preferences
    default_turn_nodes = st.session_state.preferences.get('default_turn_nodes', 5)
    default_sector_angle = st.session_state.preferences.get('default_sector_angle', 180)
    default_max_detour = st.session_state.preferences.get('default_max_detour_length', 2.0)

    n_turn_nodes = st.slider("Number of Turn Nodes", 1, 20, default_turn_nodes, key="turn_nodes")
    sector_angle = st.slider("Sector Angle (degrees)", 30, 360, default_sector_angle, key="sector_angle")
    max_detour_length = st.slider("Max Detour Length (miles)", 0.5, 5.0, default_max_detour, key="max_detour")

    # Store analysis parameters
    st.session_state.analysis_params = {
        'n_turn_nodes': n_turn_nodes,
        'sector_angle_deg': sector_angle,
        'sector_radius_m': max_detour_length * 1609.34,  # Convert to meters
        'max_detour_length': max_detour_length
    }

# ==============================================================================
# SECTION 6: MAIN CONTENT AREA
# ==============================================================================

# Main analysis section
if st.session_state.graph and st.session_state.selected_incident_edge:
    st.header("🔍 Detour Analysis")

    col1, col2 = st.columns([3, 1])

    with col1:
        if st.button("🚀 Find Detours", type="primary"):
            with st.spinner("Analyzing detour routes..."):
                start_time = time.time()

                # Run detour analysis
                detour_results = du.find_detour_routes(
                    st.session_state.graph,
                    st.session_state.selected_incident_edge[0],
                    st.session_state.selected_incident_edge[1],
                    turn_nodes=st.session_state.analysis_params['n_turn_nodes'],
                    sector_angle=st.session_state.analysis_params['sector_angle_deg'],
                    max_detour_length=st.session_state.analysis_params['max_detour_length']
                )

                analysis_time = time.time() - start_time
                st.session_state.detour_results = detour_results
                st.session_state.detour_generation_time = analysis_time
                st.session_state.analysis_recorded = False

                st.success(f"✅ Analysis complete in {analysis_time:.2f} seconds")

    with col2:
        if st.session_state.detour_results:
            valid_count = len([v for v in st.session_state.detour_results.values() if v[0]])
            total_count = len(st.session_state.detour_results)
            success_rate = (valid_count / total_count * 100) if total_count > 0 else 0

            st.metric("Valid Routes", valid_count)
            st.metric("Total Routes", total_count)
            st.metric("Success Rate", f"{success_rate:.1f}%")

    # Record analysis in history
    if st.session_state.detour_results and not st.session_state.analysis_recorded:
        results = st.session_state.detour_results
        valid_count = len([v for v in results.values() if v[0]])
        st.session_state.history.record_analysis(
            jurisdiction=st.session_state.selected_jurisdiction_name,
            total_routes=len(results),
            valid_routes=valid_count,
            parameters=st.session_state.analysis_params,
            processing_time_seconds=st.session_state.detour_generation_time
        )
        st.session_state.analysis_recorded = True

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

# ==============================================================================
# SECTION 7: BATCH PROCESSING
# ==============================================================================

with st.expander("🔄 Batch Analysis", expanded=False):
    st.subheader("Process Multiple Incidents")

    if st.session_state.graph:
        # Get edge options for batch processing
        edge_options = []
        for u, v, data in st.session_state.graph.edges(data=True):
            edge_name = data.get('name', 'Unnamed')
            if isinstance(edge_name, list):
                edge_name = edge_name[0] if edge_name else 'Unnamed'
            edge_options.append(f"{u}-{v}: {edge_name}")

        # Limit for UI performance
        if len(edge_options) > 50:
            edge_options = edge_options[:50]
            st.info(f"Showing first 50 edges for batch processing")

        selected_edges = st.multiselect("Select incident edges:", edge_options, key="batch_edges")

        if st.button("Run Batch Analysis") and selected_edges:
            # Parse selected edges
            incident_edges = []
            for edge_str in selected_edges:
                u, v = edge_str.split(':')[0].split('-')
                incident_edges.append((int(u), int(v)))

            # Run batch analysis
            progress_bar = st.progress(0)
            status_text = st.empty()

            def update_progress(current, total):
                progress_bar.progress(current / total)
                status_text.text(f"Processing incident {current}/{total}...")

            batch_results = st.session_state.batch_processor.run_batch_analysis(
                st.session_state.graph,
                incident_edges,
                st.session_state.analysis_params,
                progress_callback=update_progress
            )

            st.session_state.batch_results = batch_results
            st.success(f"Batch analysis complete! Processed {len(incident_edges)} incidents.")

            # Show summary
            st.subheader("Batch Results Summary")
            summary = st.session_state.batch_processor.get_batch_summary(batch_results)

            # Display summary table
            summary_df = pd.DataFrame(summary['summary_table'])
            st.dataframe(summary_df, use_container_width=True)

            # Display overall statistics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Incidents", summary['total_incidents'])
            with col2:
                st.metric("Successful Analyses", summary['overall_stats']['successful_analyses'])
            with col3:
                st.metric("Overall Success Rate", f"{summary['overall_stats']['overall_success_rate']:.1f}%")
            with col4:
                st.metric("Total Time", f"{summary['total_batch_time']:.1f}s")

# ==============================================================================
# SECTION 8: EXPORT FUNCTIONALITY
# ==============================================================================

if st.session_state.detour_results or st.session_state.batch_results:
    st.header("📤 Export Results")

    # Export format selection
    export_formats = ["PDF Report", "GeoJSON", "KML", "Shapefile", "GeoPackage", "Excel", "CSV"]

    if st.session_state.batch_results:
        export_formats.append("Batch Results (JSON)")
        export_formats.append("Batch Results (CSV)")

    selected_format = st.selectbox("Select Export Format:", export_formats)

    if st.button(f"Export as {selected_format}"):
        # Create export data
        export_data = create_export_data(dict(st.session_state))

        try:
            if selected_format == "PDF Report":
                exporter = PDFReportGenerator(export_data, st.session_state.db_manager)
                content = exporter.generate_report()
                st.download_button(
                    "Download PDF Report",
                    content,
                    file_name=f"arpl_detour_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                    mime="application/pdf"
                )

            elif selected_format == "GeoJSON":
                exporter = GeospatialExporter(export_data, st.session_state.db_manager)
                content = exporter.export_geojson()
                st.download_button(
                    "Download GeoJSON",
                    content,
                    file_name=f"detour_routes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.geojson",
                    mime="application/json"
                )

            elif selected_format == "KML":
                exporter = GeospatialExporter(export_data, st.session_state.db_manager)
                content = exporter.export_kml()
                st.download_button(
                    "Download KML",
                    content,
                    file_name=f"detour_routes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.kml",
                    mime="application/vnd.google-earth.kml+xml"
                )

            elif selected_format == "Shapefile":
                exporter = GeospatialExporter(export_data, st.session_state.db_manager)
                content = exporter.export_shapefile()
                st.download_button(
                    "Download Shapefile (ZIP)",
                    content,
                    file_name=f"detour_routes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                    mime="application/zip"
                )

            elif selected_format == "GeoPackage":
                exporter = GeospatialExporter(export_data, st.session_state.db_manager)
                content = exporter.export_geopackage()
                st.download_button(
                    "Download GeoPackage",
                    content,
                    file_name=f"detour_routes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.gpkg",
                    mime="application/geopackage+sqlite3"
                )

            elif selected_format == "Excel":
                exporter = TabularExporter(export_data, st.session_state.db_manager)
                content = exporter.export_excel()
                st.download_button(
                    "Download Excel",
                    content,
                    file_name=f"detour_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            elif selected_format == "CSV":
                exporter = TabularExporter(export_data, st.session_state.db_manager)
                content = exporter.export_csv()
                st.download_button(
                    "Download CSV",
                    content,
                    file_name=f"detour_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )

            elif selected_format == "Batch Results (JSON)":
                content = st.session_state.batch_exporter.export_batch_results(
                    st.session_state.batch_results, 'json'
                )
                st.download_button(
                    "Download Batch Results (JSON)",
                    content,
                    file_name=f"batch_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json"
                )

            elif selected_format == "Batch Results (CSV)":
                content = st.session_state.batch_exporter.export_batch_results(
                    st.session_state.batch_results, 'csv'
                )
                st.download_button(
                    "Download Batch Results (CSV)",
                    content,
                    file_name=f"batch_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )

            st.success("✅ Export ready for download!")

        except Exception as e:
            st.error(f"❌ Export failed: {str(e)}")

# ==============================================================================
# SECTION 9: ANALYSIS HISTORY
# ==============================================================================

with st.expander("📊 Analysis History", expanded=False):
    st.subheader("Recent Analyses")

    history = st.session_state.history.get_history(limit=20)
    if history:
        history_df = pd.DataFrame(history)
        st.dataframe(history_df, use_container_width=True)

        # Statistics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Analyses", len(history))
        with col2:
            avg_success = history_df['success_rate'].mean()
            st.metric("Avg Success Rate", f"{avg_success:.1f}%")
        with col3:
            if st.button("Export History"):
                csv = st.session_state.history.export_to_csv()
                st.download_button("Download CSV", csv, "analysis_history.csv", "text/csv")
    else:
        st.info("No analysis history found")

# ==============================================================================
# SECTION 10: CACHE MANAGEMENT
# ==============================================================================

with st.expander("🗄️ Cache Management", expanded=False):
    st.subheader("Network Cache")

    cache_stats = st.session_state.network_cache.get_cache_stats()
    if cache_stats:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Cached Networks", cache_stats['active_entries'])
        with col2:
            st.metric("Total Size", f"{cache_stats['total_size_mb']} MB")
        with col3:
            st.metric("Expired Entries", cache_stats['expired_entries'])

        if st.button("Clear Expired Cache"):
            cleared = st.session_state.network_cache.clear_expired()
            st.success(f"Cleared {cleared} expired cache entries")
            st.rerun()

        if st.button("Clear All Cache"):
            cleared = st.session_state.network_cache.clear_all()
            st.success(f"Cleared {cleared} cache entries")
            st.rerun()
    else:
        st.info("No cache statistics available")

# ==============================================================================
# SECTION 11: FOOTER
# ==============================================================================

st.divider()
st.caption("ARPL V2 - Enhanced Traffic Detour Finder | Built with Streamlit, NetworkX, and OSMnx")
st.caption("Features: Database persistence, session management, batch processing, network caching")
