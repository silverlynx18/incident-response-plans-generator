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
import leafmap.foliumap as leafmap
import folium
import base64
from shapely.wkt import loads, dumps
from shapely.geometry import LineString
import osmnx as ox
import networkx as nx
from datetime import datetime
from pathlib import Path
from io import BytesIO

def generate_layer_color(layer_name):
    """Generate a consistent color for a layer based on its name."""
    random.seed(hash(layer_name))
    colors = ['blue', 'green', 'purple', 'orange', 'pink', 'darkred', 'lightblue',
              'darkgreen', 'cadetblue', 'darkpurple', 'lightgreen', 'lightred']
    return random.choice(colors)

st.set_page_config(layout="wide")

# --- Helper Functions ----
def clean_gdf_for_map(gdf):
    """
    Clean a GeoDataFrame to remove non-serializable columns for map display.
    """
    if gdf is None or gdf.empty:
        return gdf

    clean_gdf = gdf.copy()

    # Convert Timestamp columns to strings
    for col in clean_gdf.columns:
        if col != 'geometry':
            try:
                if clean_gdf[col].dtype == 'datetime64[ns]':
                    clean_gdf[col] = clean_gdf[col].astype(str)
                elif len(clean_gdf) > 0 and 'Timestamp' in str(type(clean_gdf[col].iloc[0])):
                    clean_gdf[col] = clean_gdf[col].astype(str)
                elif clean_gdf[col].dtype in ['object', 'category']:
                    # Try to convert to string, if it fails, drop the column
                    try:
                        clean_gdf[col] = clean_gdf[col].astype(str)
                    except:
                        clean_gdf = clean_gdf.drop(columns=[col])
            except Exception:
                # If we can't handle this column, drop it
                try:
                    clean_gdf = clean_gdf.drop(columns=[col])
                except:
                    pass

    return clean_gdf

def create_traffic_signal_icon():
    """
    Create a custom traffic signal icon from SVG file.
    Returns a Folium DivIcon with the traffic signal SVG.
    """
    try:
        # Read the SVG file
        svg_path = "trafficsignal.svg"
        if os.path.exists(svg_path):
            with open(svg_path, 'r') as f:
                svg_content = f.read()

            # Encode SVG to base64 for use in HTML
            svg_b64 = base64.b64encode(svg_content.encode('utf-8')).decode('utf-8')

            # Create HTML for the icon
            icon_html = f"""
            <div style="width: 20px; height: 20px;">
                <img src="data:image/svg+xml;base64,{svg_b64}"
                     style="width: 100%; height: 100%;" />
            </div>
            """

            return folium.DivIcon(
                html=icon_html,
                icon_size=(20, 20),
                icon_anchor=(10, 10),
                popup_anchor=(0, -10)
            )
        else:
            # Fallback to a simple colored circle if SVG not found
            return folium.Icon(color="orange", icon="info-sign")
    except Exception as e:
        # Fallback to default icon if there's any error
        return folium.Icon(color="orange", icon="info-sign")

def is_traffic_signal_data(layer_name, gdf):
    """
    Determine if the data represents traffic signals based on layer name or data content.
    """
    layer_name_lower = layer_name.lower()

    # Check layer name for traffic signal keywords
    traffic_keywords = ['traffic', 'signal', 'light', 'intersection', 'stop']
    if any(keyword in layer_name_lower for keyword in traffic_keywords):
        return True

    # Check column names for traffic signal indicators
    if not gdf.empty:
        columns_lower = [col.lower() for col in gdf.columns]
        traffic_columns = ['traffic', 'signal', 'light', 'intersection', 'stop', 'type']
        if any(keyword in ' '.join(columns_lower) for keyword in traffic_columns):
            return True

    return False
def save_session_data():
    """Save custom jurisdictions and additional data to local files for persistence."""
    import json
    import pickle
    from pathlib import Path

    # Create data directory if it doesn't exist
    data_dir = Path("session_data")
    data_dir.mkdir(exist_ok=True)

    try:
        # Save custom jurisdictions
        custom_jurisdictions = st.session_state.get('custom_jurisdictions', {})
        with open(data_dir / "custom_jurisdictions.json", 'w') as f:
            # Convert GeoDataFrames to WKT for JSON serialization
            serializable_data = {}
            for name, gdf in custom_jurisdictions.items():
                if hasattr(gdf, 'to_wkt'):
                    serializable_data[name] = {
                        'wkt': gdf.to_wkt(),
                        'crs': str(gdf.crs) if gdf.crs else None,
                        'columns': list(gdf.columns)
                    }
            json.dump(serializable_data, f, indent=2)

        # Save additional data
        additional_data = st.session_state.get('additional_data', {})
        with open(data_dir / "additional_data.json", 'w') as f:
            # Convert GeoDataFrames to WKT for JSON serialization
            serializable_data = {}
            for name, gdf in additional_data.items():
                if hasattr(gdf, 'to_wkt'):
                    serializable_data[name] = {
                        'wkt': gdf.to_wkt(),
                        'crs': str(gdf.crs) if gdf.crs else None,
                        'columns': list(gdf.columns)
                    }
            json.dump(serializable_data, f, indent=2)

    except Exception as e:
        st.error(f"Failed to save session data: {str(e)}")

def load_session_data():
    """Load custom jurisdictions and additional data from local files."""
    import json
    from pathlib import Path
    from shapely.wkt import loads

    data_dir = Path("session_data")

    try:
        # Load custom jurisdictions
        custom_jurisdictions_file = data_dir / "custom_jurisdictions.json"
        if custom_jurisdictions_file.exists():
            with open(custom_jurisdictions_file, 'r') as f:
                data = json.load(f)
                for name, info in data.items():
                    try:
                        # Reconstruct GeoDataFrame from WKT
                        gdf = gpd.GeoDataFrame.from_wkt(info['wkt'])
                        if info.get('crs'):
                            gdf.crs = info['crs']
                        st.session_state.custom_jurisdictions[name] = gdf
                    except Exception as e:
                        st.warning(f"Failed to load custom jurisdiction '{name}': {e}")

        # Load additional data
        additional_data_file = data_dir / "additional_data.json"
        if additional_data_file.exists():
            with open(additional_data_file, 'r') as f:
                data = json.load(f)
                for name, info in data.items():
                    try:
                        # Reconstruct GeoDataFrame from WKT
                        gdf = gpd.GeoDataFrame.from_wkt(info['wkt'])
                        if info.get('crs'):
                            gdf.crs = info['crs']
                        st.session_state.additional_data[name] = gdf
                    except Exception as e:
                        st.warning(f"Failed to load additional data '{name}': {e}")

    except Exception as e:
        st.warning(f"Failed to load session data: {str(e)}")

# --- Configuration for Local File Paths ---
SHAPEFILE_PATHS = {
    "states": "data/cb_2018_us_state_500k",
    "counties": "data/tiger_2018_counties",
    "mpos": "data/BTS_MPO",
    "ua": "data/tiger_2018_urban_areas",
}

# --- Initialize Session State ---
# CRITICAL: Ensure each user starts with a clean session
# Use a unique session identifier to prevent cross-user contamination
if 'session_id' not in st.session_state:
    import uuid
    st.session_state.session_id = str(uuid.uuid4())
    # Force reset all selection-related state for new sessions
    st.session_state.selected_state_name = None
    st.session_state.selected_jurisdiction_name = None
    st.session_state.selected_polygon_wkt = None
    st.session_state.selected_polygon_bounds = None

default_state = {
    'graph': None, 'selected_state_name': None, 'selected_jurisdiction_name': None,
    'selected_polygon_wkt': None, 'selected_polygon_bounds': None, 'zoom_to_selection': False,
    'selected_edge_key': "", 'detour_results': None,
    'show_counties': True, 'show_mpos': True, 'show_urban_areas': True, 'show_custom_jurisdictions': True,
    'display_mode': 'selection',
    'custom_jurisdictions': {}, 'additional_data': {}
}

# Setup state
if 'setup_complete' not in st.session_state:
    st.session_state.setup_complete = False

# Initialize default state - but NEVER override None values for selections if they're already None
# This ensures clean state for each user
for key, value in default_state.items():
    if key not in st.session_state:
        st.session_state[key] = value
    # CRITICAL: Force reset selection state if it seems corrupted or from another session
    elif key in ['selected_state_name', 'selected_jurisdiction_name', 'selected_polygon_wkt']:
        # Only keep the value if it's explicitly set by the current user
        # If it's set but we don't have a valid session, reset it
        if not hasattr(st.session_state, 'session_id'):
            st.session_state[key] = None

# Ensure custom data structures are properly initialized
if 'custom_jurisdictions' not in st.session_state:
    st.session_state.custom_jurisdictions = {}
if 'additional_data' not in st.session_state:
    st.session_state.additional_data = {}

# Load persisted session data on startup - but ONLY custom jurisdictions and additional data
# NEVER load state/jurisdiction selections from files (they should be user-specific)
if 'session_data_loaded' not in st.session_state:
    # Only load custom jurisdictions and additional data, not selections
    load_session_data()
    st.session_state.session_data_loaded = True
    # After loading, ensure selections are still None for new users
    if 'selected_state_name' not in st.session_state or st.session_state.selected_state_name is None:
        # This is a new user - ensure clean state
        st.session_state.selected_state_name = None
        st.session_state.selected_jurisdiction_name = None
        st.session_state.selected_polygon_wkt = None
        st.session_state.selected_polygon_bounds = None

# Ensure critical session state variables are preserved
critical_vars = [
    'selected_state_name', 'selected_jurisdiction_name', 'selected_polygon_wkt',
    'selected_polygon_bounds', 'custom_jurisdictions', 'additional_data',
    'performance_mode', 'setup_complete'
]
for var in critical_vars:
    if var not in st.session_state:
        if var == 'selected_polygon_bounds':
            st.session_state[var] = None
        elif var in ['custom_jurisdictions', 'additional_data']:
            st.session_state[var] = {}
        elif var == 'setup_complete':
            st.session_state[var] = False
        else:
            st.session_state[var] = None

# --- Helper Functions ---
def get_best_name_field(gdf):
    """
    Automatically detect the best field to use for polygon names.
    Prioritizes fields with alphabetical characters and common naming patterns.
    """
    if gdf is None or gdf.empty:
        return None

    # Priority order for field names (case-insensitive)
    priority_fields = [
        'name', 'district_name', 'county_name', 'mpo_name', 'area_name',
        'jurisdiction_name', 'region_name', 'zone_name', 'division_name',
        'id', 'district_id', 'county_id', 'mpo_id', 'area_id',
        'label', 'title', 'description', 'identifier'
    ]

    # Check for exact matches first (case-insensitive)
    for priority_field in priority_fields:
        for col in gdf.columns:
            if col.lower() == priority_field.lower():
                # Check if the field has meaningful string values
                if gdf[col].dtype == 'object' and not gdf[col].isna().all():
                    # Check if values contain alphabetical characters
                    sample_values = gdf[col].dropna().astype(str).head(10)
                    if any(any(c.isalpha() for c in str(val)) for val in sample_values):
                        return col

    # If no priority field found, look for any string column with alphabetical content
    for col in gdf.columns:
        if gdf[col].dtype == 'object' and not gdf[col].isna().all():
            sample_values = gdf[col].dropna().astype(str).head(10)
            if any(any(c.isalpha() for c in str(val)) for val in sample_values):
                return col

    return None

def create_polygon_options(gdf, name_field=None):
    """
    Create user-friendly options for polygon selection.
    Returns a list of (display_text, index) tuples.
    """
    if gdf is None or gdf.empty:
        return []

    # Auto-detect name field if not provided
    if name_field is None:
        name_field = get_best_name_field(gdf)

    options = []
    for idx, row in gdf.iterrows():
        if name_field and name_field in gdf.columns:
            # Use the descriptive field
            name_value = str(row[name_field]) if pd.notna(row[name_field]) else f"Feature {idx}"
            display_text = f"{name_value} (Index: {idx})"
        else:
            # Fall back to index-based naming
            display_text = f"Feature {idx}"

        options.append((display_text, idx))

    return options

@st.cache_resource
def load_all_shapefiles():
    """Loads all shapefiles from local directories at once and stores them."""
    gdfs = {}
    gdfs["states"] = load_local_shapefile(SHAPEFILE_PATHS["states"], "States")
    gdfs["counties"] = load_local_shapefile(SHAPEFILE_PATHS["counties"], "Counties")
    gdfs["mpos"] = load_local_shapefile(SHAPEFILE_PATHS["mpos"], "MPOs")
    gdfs["ua"] = load_local_shapefile(SHAPEFILE_PATHS["ua"], "Urban Areas")
    return gdfs

def load_local_shapefile(path, description):
    """Helper to load a single shapefile."""
    if not os.path.isdir(path):
        st.warning(f"Directory for {description} not found: '{path}'")
        return None
    shp_files = [f for f in os.listdir(path) if f.endswith('.shp')]
    if not shp_files:
        st.warning(f"No .shp file found in '{path}'.")
        return None
    try:
        gdf = gpd.read_file(os.path.join(path, shp_files[0]))
        if gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)
        return gdf
    except Exception as e:
        st.error(f"Error reading {description}: {e}")
    return None

@st.cache_resource
def load_and_prepare_graph_from_polygon(polygon_wkt, performance_mode="Fast"):
    polygon = loads(polygon_wkt)
    with st.spinner("Downloading network from OpenStreetMap..."):
        if performance_mode == "Fast":
            # Fast mode: major roads only (no express lanes)
            custom_filter = '["highway"~"motorway|trunk|primary|secondary|trunk_link|primary_link|secondary_link"]'
            graph = ox.graph_from_polygon(
                polygon,
                network_type="drive",
                simplify=True,
                custom_filter=custom_filter,
                retain_all=False
            )
        elif performance_mode == "Balanced":
            # Balanced mode: most roads (no express lanes)
            custom_filter = '["highway"~"motorway|trunk|primary|secondary|tertiary|trunk_link|primary_link|secondary_link|tertiary_link|residential|unclassified"]'
            graph = ox.graph_from_polygon(
                polygon,
                network_type="drive",
                simplify=True,
                custom_filter=custom_filter,
                retain_all=False
            )
        else:  # Complete
            # Complete mode: all roads
            graph = ox.graph_from_polygon(polygon, network_type="drive", simplify=True)
    with st.spinner("Cleaning and preparing graph..."):
        graph_clean = du.clean_graph(graph)
        graph_prepared = du.prepare_graph(graph_clean)
    return graph_prepared

def process_shapefile_upload(uploaded_files):
    """
    Process uploaded shapefile(s) - handles both ZIP and individual files.

    Args:
        uploaded_files: Single file or list of files from st.file_uploader

    Returns:
        GeoDataFrame or None if processing failed
    """
    # Ensure uploaded_files is a list
    if not isinstance(uploaded_files, list):
        uploaded_files = [uploaded_files]

    # Check if any file is a ZIP
    zip_files = [f for f in uploaded_files if f.name.endswith('.zip')]

    if zip_files:
        # Process ZIP file
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_file = zip_files[0]  # Use first ZIP file
            st.info(f"📦 Processing ZIP file: {zip_file.name}")

            try:
                with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                    # List contents for debugging
                    file_list = zip_ref.namelist()
                    st.info(f"📁 ZIP contains {len(file_list)} files")

                    zip_ref.extractall(temp_dir)

                # Find .shp file
                shp_files = list(Path(temp_dir).rglob('*.shp'))

                if not shp_files:
                    st.error("❌ No .shp file found in ZIP archive")
                    st.info("💡 Make sure your ZIP file contains a .shp file")
                    return None

                if len(shp_files) > 1:
                    st.warning(f"⚠️ Multiple .shp files found ({len(shp_files)}). Using the first one: {shp_files[0].name}")

                try:
                    gdf = gpd.read_file(shp_files[0])
                    st.success(f"✅ Successfully loaded {len(gdf)} features from ZIP file")

                    # Convert CRS if needed
                    if gdf.crs and gdf.crs.to_epsg() != 4326:
                        st.info(f"🔄 Converting CRS from {gdf.crs} to EPSG:4326")
                        gdf = gdf.to_crs(epsg=4326)

                    return gdf

                except Exception as e:
                    st.error(f"❌ Error reading shapefile from ZIP: {str(e)}")
                    return None

            except zipfile.BadZipFile:
                st.error("❌ Invalid ZIP file format")
                return None
            except Exception as e:
                st.error(f"❌ Error processing ZIP file: {str(e)}")
                return None

    else:
        # Process individual files
        st.info(f"📁 Processing {len(uploaded_files)} individual files")

        with tempfile.TemporaryDirectory() as temp_dir:
            # Save all uploaded files to temp directory
            for uploaded_file in uploaded_files:
                file_path = Path(temp_dir) / uploaded_file.name
                with open(file_path, 'wb') as f:
                    f.write(uploaded_file.getbuffer())

            # Find .shp file
            shp_files = list(Path(temp_dir).glob('*.shp'))

            if not shp_files:
                st.error("❌ No .shp file found in uploaded files")
                st.info("💡 Make sure you've uploaded a .shp file")
                return None

            if len(shp_files) > 1:
                st.warning(f"⚠️ Multiple .shp files found ({len(shp_files)}). Using the first one: {shp_files[0].name}")

            # Check for required components
            base_name = shp_files[0].stem
            required_extensions = ['.shx', '.dbf']
            missing = []

            for ext in required_extensions:
                if not (Path(temp_dir) / f"{base_name}{ext}").exists():
                    missing.append(ext)

            if missing:
                st.warning(f"⚠️ Missing required files: {', '.join(missing)}")
                st.info("💡 A complete shapefile requires .shp, .shx, and .dbf files")
                st.info("💡 Consider uploading as a ZIP file to ensure all components are included")
                return None

            try:
                gdf = gpd.read_file(shp_files[0])
                st.success(f"✅ Successfully loaded {len(gdf)} features from individual files")

                # Convert CRS if needed
                if gdf.crs and gdf.crs.to_epsg() != 4326:
                    st.info(f"🔄 Converting CRS from {gdf.crs} to EPSG:4326")
                    gdf = gdf.to_crs(epsg=4326)

                return gdf

            except Exception as e:
                st.error(f"❌ Error reading shapefile: {str(e)}")
                return None

# --- Setup Functions ---
def show_setup_wizard():
    """Single-page setup with dropdown selections."""
    st.title("🚦 Traffic Detour Finder - Setup")

    st.markdown("""
    Welcome to the Traffic Detour Finder! Configure your analysis environment below.
    """)

    # Create two main columns
    col1, col2 = st.columns([1, 1])

    with col1:
        st.header("📍 Jurisdiction Selection")

        # Load default shapefiles
        all_gdfs = load_all_shapefiles()

        if all_gdfs["states"] is None:
            st.error("States shapefile is required to run the app.")
            st.stop()

        # State selection
        state_names = ["Virginia"]

        # CRITICAL: Always start with no selection for new users
        # Only use existing selection if it was explicitly set by the current user
        current_state = st.session_state.get('selected_state_name')
        default_index = 0  # Always default to empty selection

        # Only use existing state if session_id exists (user has interacted)
        if current_state and current_state in state_names and 'session_id' in st.session_state:
            # Check if this is a valid user selection (not from a previous session)
            # Only use it if the session was properly initialized
            if st.session_state.get('session_id'):
                default_index = state_names.index(current_state)
            else:
                # Reset to no selection for new/unknown sessions
                default_index = 0
                st.session_state.selected_state_name = None

        selected_state = st.selectbox("Select State:", state_names, key="setup_state", index=default_index)

        if selected_state:
            # Jurisdiction type
            juris_type = st.radio(
                "Jurisdiction Type:",
                ["County", "MPO", "Urban Area", "Custom"],
                horizontal=True,
                key="setup_juris_type"
            )

            # Get jurisdictions based on type
            if juris_type == "Custom":
                # Show custom uploaded jurisdictions
                if st.session_state.get('custom_jurisdictions'):
                    custom_names = list(st.session_state.custom_jurisdictions.keys())
                    selected_juris = st.selectbox("Select Custom Jurisdiction:", [""] + custom_names, key="setup_custom_juris")

                    if selected_juris:
                        # Get polygon from custom jurisdiction
                        custom_data = st.session_state.custom_jurisdictions[selected_juris]
                        # Allow user to select specific polygon if multiple
                        if len(custom_data['gdf']) > 1:
                            # Create user-friendly polygon options
                            polygon_options = create_polygon_options(custom_data['gdf'])
                            if polygon_options:
                                # Get current selection if it exists
                                current_selection = st.session_state.get('selected_custom_polygon_option')
                                default_index = 0
                                if current_selection:
                                    try:
                                        default_index = next(i for i, opt in enumerate(polygon_options) if opt[0] == current_selection)
                                    except StopIteration:
                                        default_index = 0

                                selected_option = st.selectbox(
                                    "Select Polygon:",
                                    options=[opt[0] for opt in polygon_options],
                                    key="setup_poly_idx",
                                    index=default_index
                                )
                                # Store the selection for next time (use the same variable name as main app)
                                st.session_state.selected_custom_polygon_option = selected_option
                                # Find the corresponding index
                                selected_idx = next(opt[1] for opt in polygon_options if opt[0] == selected_option)
                                selected_poly = custom_data['gdf'].iloc[selected_idx].geometry
                            else:
                                # Fallback to simple index selection
                                current_idx = st.session_state.get('selected_setup_polygon_idx', 0)
                                poly_idx = st.selectbox("Select Polygon:", range(len(custom_data['gdf'])), key="setup_poly_idx", index=current_idx)
                                st.session_state.selected_setup_polygon_idx = poly_idx
                                selected_poly = custom_data['gdf'].iloc[poly_idx].geometry
                        else:
                            selected_poly = custom_data['gdf'].iloc[0].geometry

                        # Store selection
                        st.session_state.selected_polygon_wkt = dumps(selected_poly)
                        st.session_state.selected_jurisdiction_name = f"Custom: {selected_juris}"
                        bounds = selected_poly.bounds
                        st.session_state.selected_polygon_bounds = [[bounds[1], bounds[0]], [bounds[3], bounds[2]]]
                else:
                    st.warning("⚠️ No custom jurisdictions uploaded. Use the upload section below.")
            else:
                # Standard TIGER jurisdiction selection
                @st.cache_data
                def get_jurisdictions_in_state(_state_name, _session_id=None):
                    """
                    Get jurisdictions for a state.
                    Include session_id in cache key to ensure proper isolation.
                    """
                    _state_geom = all_gdfs["states"][all_gdfs["states"]['NAME'] == _state_name].iloc[0].geometry
                    jurisdictions = {}
                    if all_gdfs["counties"] is not None:
                        jurisdictions['county'] = sorted(all_gdfs["counties"][all_gdfs["counties"].intersects(_state_geom)]['NAME'].tolist())
                    if all_gdfs["mpos"] is not None:
                        jurisdictions['mpo'] = sorted(all_gdfs["mpos"][all_gdfs["mpos"].intersects(_state_geom)]['MPO_NAME'].tolist())
                    if all_gdfs["ua"] is not None:
                        jurisdictions['ua'] = sorted(all_gdfs["ua"][all_gdfs["ua"].intersects(_state_geom)]['NAME10'].tolist())
                    return jurisdictions

                # Include session_id in cache key to ensure proper session isolation
                session_id = st.session_state.get('session_id', 'default')
                jurisdictions = get_jurisdictions_in_state(selected_state, session_id)

                if juris_type == "County" and 'county' in jurisdictions:
                    selected_juris = st.selectbox("Select County:", [""] + jurisdictions['county'], key="setup_county")
                    if selected_juris:
                        gdf_map = all_gdfs["counties"]
                        name_col = 'NAME'
                elif juris_type == "MPO" and 'mpo' in jurisdictions:
                    selected_juris = st.selectbox("Select MPO:", [""] + jurisdictions['mpo'], key="setup_mpo")
                    if selected_juris:
                        gdf_map = all_gdfs["mpos"]
                        name_col = 'MPO_NAME'
                elif juris_type == "Urban Area" and 'ua' in jurisdictions:
                    selected_juris = st.selectbox("Select Urban Area:", [""] + jurisdictions['ua'], key="setup_ua")
                    if selected_juris:
                        gdf_map = all_gdfs["ua"]
                        name_col = 'NAME10'

                if selected_juris and 'gdf_map' in locals() and selected_state:
                    # CRITICAL: Filter by state first to avoid matching jurisdictions with same name in different states
                    state_geom = all_gdfs["states"][all_gdfs["states"]['NAME'] == selected_state].iloc[0].geometry

                    # Filter by state first, then by name
                    state_filtered_gdf = gdf_map[gdf_map.intersects(state_geom)]
                    name_matches = state_filtered_gdf[state_filtered_gdf[name_col] == selected_juris]

                    if not name_matches.empty:
                        selected_series = name_matches.iloc[0]
                        st.session_state.selected_polygon_wkt = dumps(selected_series.geometry)
                        bounds = selected_series.geometry.bounds
                        st.session_state.selected_polygon_bounds = [[bounds[1], bounds[0]], [bounds[3], bounds[2]]]
                        # Store jurisdiction name in the format expected by main app dropdown
                        if juris_type == "Custom":
                            st.session_state.selected_jurisdiction_name = f"Custom: {selected_juris}"
                        else:
                            st.session_state.selected_jurisdiction_name = f"{juris_type}: {selected_juris}"
                        # Also store the state to ensure consistency
                        st.session_state.selected_state_name = selected_state
                    else:
                        st.error(f"❌ {selected_juris} not found in {selected_state}. Please select a different jurisdiction.")
                        st.session_state.selected_jurisdiction_name = None
                        st.session_state.selected_polygon_wkt = None
                        st.session_state.selected_polygon_bounds = None

    with col2:
        st.header("📁 Data Upload")

        # Custom jurisdiction upload
        st.subheader("Custom Jurisdictions (Optional)")
        st.info("💡 Upload polygon shapefiles to define custom analysis boundaries")
        st.caption("📦 **Supported formats:** ZIP files containing shapefiles, or individual .shp/.shx/.dbf/.prj/.cpg files")

        uploaded_jurisdiction_files = st.file_uploader(
            "Upload Jurisdiction Shapefile:",
            type=['zip', 'shp', 'shx', 'dbf', 'prj', 'cpg'],
            accept_multiple_files=True,
            help="Upload a ZIP file containing shapefile components, or upload individual shapefile files (.shp, .shx, .dbf, .prj, .cpg)",
            key="jurisdiction_uploader"
        )

        if uploaded_jurisdiction_files and st.button("📥 Process Jurisdiction Files", key="setup_process_juris"):
            result = process_shapefile_upload(uploaded_jurisdiction_files)
            if result is not None and not result.empty:
                # Validate polygon geometry
                geom_types = result.geometry.type.unique()
                if not all(gtype in ['Polygon', 'MultiPolygon'] for gtype in geom_types):
                    st.error("❌ Only polygon geometries accepted for jurisdictions")
                else:
                    # Validate and fix geometry
                    invalid_count = 0
                    for idx, geom in enumerate(result.geometry):
                        if not geom.is_valid:
                            invalid_count += 1
                            # Try to fix invalid geometry
                            fixed_geom = geom.buffer(0)
                            if fixed_geom.is_valid:
                                result.geometry.iloc[idx] = fixed_geom
                                st.info(f"🔧 Fixed invalid geometry for feature {idx}")
                            else:
                                st.warning(f"⚠️ Could not fix invalid geometry for feature {idx}")

                    if invalid_count > 0:
                        st.info(f"🔧 Fixed {invalid_count} invalid geometries")

                    # Store the processed result in session state
                    st.session_state.temp_processed_jurisdiction = result
                    st.success("✅ Jurisdiction processed successfully! Enter a name and save it.")

        # Show save interface if we have a processed jurisdiction
        if st.session_state.get('temp_processed_jurisdiction') is not None:
            st.info("📋 Ready to save processed jurisdiction")
            layer_name = st.text_input("Jurisdiction Name:", value="Custom Jurisdiction", key="setup_juris_name")
            if st.button("💾 Save Jurisdiction", key="setup_save_juris"):
                if 'custom_jurisdictions' not in st.session_state:
                    st.session_state.custom_jurisdictions = {}
                st.session_state.custom_jurisdictions[layer_name] = {
                    'gdf': st.session_state.temp_processed_jurisdiction,
                    'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                # Clear the temporary processed jurisdiction
                del st.session_state.temp_processed_jurisdiction
                # Save to persistent storage
                save_session_data()
                st.success(f"✅ Saved '{layer_name}'")
                st.rerun()

        # Additional data upload
        st.subheader("Additional Data (Optional)")
        st.info("💡 Upload point/line data for proximity analysis in exports")
        st.caption("📦 **Supported formats:** ZIP files containing shapefiles, or individual .shp/.shx/.dbf/.prj/.cpg files")

        uploaded_data_files = st.file_uploader(
            "Upload Additional Shapefiles:",
            type=['zip', 'shp', 'shx', 'dbf', 'prj', 'cpg'],
            accept_multiple_files=True,
            help="Upload a ZIP file containing shapefile components, or upload individual shapefile files (.shp, .shx, .dbf, .prj, .cpg)",
            key="data_uploader"
        )

        if uploaded_data_files and st.button("📥 Process Data Files", key="setup_process_data"):
            result = process_shapefile_upload(uploaded_data_files)
            if result is not None and not result.empty:
                # Store the processed result in session state
                st.session_state.temp_processed_data = result
                st.success("✅ Data processed successfully! Enter a name and save it.")

        # Show save interface if we have processed data
        if st.session_state.get('temp_processed_data') is not None:
            st.info("📋 Ready to save processed data")
            layer_name = st.text_input("Data Layer Name:", value="Additional Data", key="setup_data_name")
            if st.button("💾 Save Data Layer", key="setup_save_data"):
                if 'additional_data' not in st.session_state:
                    st.session_state.additional_data = {}
                st.session_state.additional_data[layer_name] = {
                    'gdf': st.session_state.temp_processed_data,
                    'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                # Automatically make the layer visible by default
                st.session_state[f"show_layer_{layer_name}"] = True
                # Clear the temporary processed data
                del st.session_state.temp_processed_data
                # Save to persistent storage
                save_session_data()
                st.success(f"✅ Saved '{layer_name}'")
                st.rerun()

    # Display uploaded data
    if st.session_state.get('custom_jurisdictions') or st.session_state.get('additional_data'):
        st.header("📋 Uploaded Data Summary")

        if st.session_state.get('custom_jurisdictions'):
            st.subheader("Custom Jurisdictions:")
            for name, data in st.session_state.custom_jurisdictions.items():
                col1, col2, col3 = st.columns([2, 1, 1])
                col1.write(f"• **{name}**")
                col2.write(f"{len(data['gdf'])} polygon(s)")
                if col3.button("🗑️", key=f"setup_del_juris_{name}"):
                    del st.session_state.custom_jurisdictions[name]
                    st.rerun()

        if st.session_state.get('additional_data'):
            st.subheader("Additional Data:")
            for name, data in st.session_state.additional_data.items():
                col1, col2, col3 = st.columns([2, 1, 1])
                col1.write(f"• **{name}**")
                col2.write(f"{len(data['gdf'])} feature(s)")
                if col3.button("🗑️", key=f"setup_del_data_{name}"):
                    del st.session_state.additional_data[name]
                    st.rerun()

    # Network preparation and launch
    st.header("🚀 Ready to Launch")

    if st.session_state.get('selected_polygon_wkt'):
        st.success(f"✅ Jurisdiction selected: {st.session_state.selected_jurisdiction_name}")

        # Performance mode selection
        performance_mode = st.selectbox(
            "Performance Mode:",
            ["Fast", "Balanced", "Complete"],
            index=0,
            help="Fast: Major roads only | Balanced: Most roads | Complete: All roads",
            key="setup_performance"
        )

        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("🚀 Launch Application", type="primary", use_container_width=True):
                # Store performance preference
                st.session_state.performance_mode = performance_mode

                # Ensure polygon selection is properly transferred
                if st.session_state.get('selected_custom_polygon_option'):
                    st.session_state.selected_custom_polygon_option = st.session_state.selected_custom_polygon_option

                # Load and prepare network
                with st.spinner("Preparing network..."):
                    st.session_state.graph = load_and_prepare_graph_from_polygon(
                        st.session_state.selected_polygon_wkt,
                        performance_mode
                    )

                # Mark setup as complete
                st.session_state.setup_complete = True
                st.success("✅ Setup complete! Launching application...")
                st.rerun()
    else:
        st.warning("⚠️ Please select a jurisdiction to continue.")

# --- Main Application Logic ---
if not st.session_state.setup_complete:
    show_setup_wizard()
    st.stop()

# Main UI only loads after setup completion
st.title("🚦 Traffic Detour Finder V1.6.1")

# --- Sidebar UI ---
with st.sidebar:
    st.header("1. Data Configuration")

    # Show loaded data summary
    st.success("✅ Setup Complete")

    with st.expander("📊 Data Summary", expanded=False):
        st.write("**Loaded Jurisdictions:**")
        all_gdfs = load_all_shapefiles()
        st.write(f"• States: {len(all_gdfs['states'])} features")
        if all_gdfs['counties'] is not None:
            st.write(f"• Counties: {len(all_gdfs['counties'])} features")
        if all_gdfs['mpos'] is not None:
            st.write(f"• MPOs: {len(all_gdfs['mpos'])} features")
        if all_gdfs['ua'] is not None:
            st.write(f"• Urban Areas: {len(all_gdfs['ua'])} features")

        # Show custom uploaded shapefiles
        if st.session_state.get('additional_data'):
            st.write("**Custom Data Layers:**")
            for name, data in st.session_state.additional_data.items():
                st.write(f"• {name}: {len(data['gdf'])} features")


    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 Restart Setup"):
            st.session_state.setup_complete = False
            st.rerun()

    with col2:
        if st.button("🗑️ Reset Session", help="Clear all selections, detour routes, and reset to initial state"):
            # Clear all session state except setup completion and session_id
            keys_to_clear = [
                'graph', 'selected_state_name', 'selected_jurisdiction_name',
                'selected_polygon_wkt', 'selected_polygon_bounds', 'zoom_to_selection',
                'selected_edge_key', 'detour_results', 'all_valid_detours',
                'detour_selections', 'accepted_detours', 'show_all_routes',
                'performance_mode', 'zoom_to_incident', 'analysis_recorded',
                'state_selector', 'setup_state'  # Clear selectbox keys
            ]

            for key in keys_to_clear:
                if key in st.session_state:
                    del st.session_state[key]

            # Reset to default values - ensure selections are None
            for key, value in default_state.items():
                st.session_state[key] = value

            # Force reset selection state to None
            st.session_state.selected_state_name = None
            st.session_state.selected_jurisdiction_name = None
            st.session_state.selected_polygon_wkt = None
            st.session_state.selected_polygon_bounds = None

            st.success("✅ Session reset! All selections and detour routes cleared.")
            st.rerun()


    st.divider()

    # Area Selection section
    st.header("2. Area Selection")

    # Load shapefiles for area selection
    all_gdfs = load_all_shapefiles()
    gdf_states = all_gdfs["states"]
    gdf_counties = all_gdfs["counties"]
    gdf_mpos = all_gdfs["mpos"]
    gdf_ua = all_gdfs["ua"]

    # Extract state name from selected jurisdiction if available
    # CRITICAL: Only auto-detect state if not already selected
    # The main jurisdiction loading code (below) will filter by selected state
    current_state_name = None
    if st.session_state.selected_jurisdiction_name and not st.session_state.selected_state_name:
        # Parse the jurisdiction name to extract state
        # Format: "County: Name" or "MPO: Name" or "Urban Area: Name" or "Custom: Name"
        if "County:" in st.session_state.selected_jurisdiction_name:
            # For counties, we need to find which state it belongs to
            county_name = st.session_state.selected_jurisdiction_name.replace("County: ", "")
            if gdf_counties is not None:
                county_row = gdf_counties[gdf_counties['NAME'] == county_name]
                if not county_row.empty:
                    # Find intersecting state - use first match (may have duplicates)
                    county_geom = county_row.iloc[0].geometry
                    intersecting_states = gdf_states[gdf_states.intersects(county_geom)]
                    if not intersecting_states.empty:
                        current_state_name = intersecting_states.iloc[0]['NAME']
        elif "MPO:" in st.session_state.selected_jurisdiction_name:
            # For MPOs, find intersecting state
            mpo_name = st.session_state.selected_jurisdiction_name.replace("MPO: ", "")
            if gdf_mpos is not None:
                mpo_row = gdf_mpos[gdf_mpos['MPO_NAME'] == mpo_name]
                if not mpo_row.empty:
                    mpo_geom = mpo_row.iloc[0].geometry
                    intersecting_states = gdf_states[gdf_states.intersects(mpo_geom)]
                    if not intersecting_states.empty:
                        current_state_name = intersecting_states.iloc[0]['NAME']
        elif "Urban Area:" in st.session_state.selected_jurisdiction_name:
            # For urban areas, find intersecting state
            ua_name = st.session_state.selected_jurisdiction_name.replace("Urban Area: ", "")
            if gdf_ua is not None:
                ua_row = gdf_ua[gdf_ua['NAME10'] == ua_name]
                if not ua_row.empty:
                    ua_geom = ua_row.iloc[0].geometry
                    intersecting_states = gdf_states[gdf_states.intersects(ua_geom)]
                    if not intersecting_states.empty:
                        current_state_name = intersecting_states.iloc[0]['NAME']
        elif "Custom:" in st.session_state.selected_jurisdiction_name:
            # For custom jurisdictions, find intersecting state(s) from the polygon
            custom_name = st.session_state.selected_jurisdiction_name.replace("Custom: ", "")
            if (st.session_state.get('custom_jurisdictions') and
                custom_name in st.session_state.custom_jurisdictions and
                st.session_state.selected_polygon_wkt):
                try:
                    from shapely.wkt import loads
                    custom_poly = loads(st.session_state.selected_polygon_wkt)
                    if gdf_states is not None:
                        intersecting_states = gdf_states[gdf_states.intersects(custom_poly)]
                        if not intersecting_states.empty:
                            # Use the state with the largest intersection area
                            max_area = 0
                            best_state = None
                            for idx, state_row in intersecting_states.iterrows():
                                intersection = state_row.geometry.intersection(custom_poly)
                                area = intersection.area
                                if area > max_area:
                                    max_area = area
                                    best_state = state_row['NAME']
                            if best_state:
                                current_state_name = best_state
                except Exception as e:
                    # If we can't determine state from custom jurisdiction, that's okay
                    # User can manually select state
                    pass

    # Set the current state in session state if we found it
    if current_state_name and not st.session_state.selected_state_name:
        st.session_state.selected_state_name = current_state_name

    # Get state names - handle case where shapefiles might not be loaded
    if gdf_states is not None and not gdf_states.empty:
        state_names = [""] + sorted(gdf_states['NAME'].tolist())
    else:
        state_names = [""]
        if not st.session_state.get('shapefile_warning_shown', False):
            st.warning("⚠️ State shapefiles not loaded. Please check data configuration.")
            st.session_state.shapefile_warning_shown = True

    def on_state_change():
        # CRITICAL: Clear jurisdiction when state changes
        st.session_state.selected_jurisdiction_name = None
        st.session_state.selected_polygon_wkt = None
        st.session_state.selected_polygon_bounds = None
        st.session_state.display_mode = 'selection'
        # Clear any cached jurisdiction data
        if 'jurisdiction_selector' in st.session_state:
            del st.session_state['jurisdiction_selector']
        # Mark that state changed to trigger cache invalidation
        st.session_state.state_changed = True

    # CRITICAL: Ensure state selector always starts with no selection for new users
    # Calculate default index safely
    current_state = st.session_state.get('selected_state_name')
    default_index = 0  # Always default to empty selection

    # Only use existing state if it's a valid user selection from current session
    if current_state and current_state in state_names:
        # Verify this is from the current session, not a stale value
        if 'session_id' in st.session_state and st.session_state.get('session_id'):
            default_index = state_names.index(current_state)
        else:
            # Reset to no selection for new/unknown sessions
            default_index = 0
            st.session_state.selected_state_name = None
    else:
        # No valid state selected, ensure it's None
        st.session_state.selected_state_name = None

    selected_state_name = st.selectbox(
        "Select a State (or click map)", state_names, key="state_selector",
        index=default_index,
        help="Select a state here or click it directly on the map to begin.",
        on_change=on_state_change
    )

    # Update session state when user makes a selection
    # CRITICAL: If state changed, immediately clear jurisdiction
    if selected_state_name and selected_state_name != "":
        if st.session_state.selected_state_name != selected_state_name:
            # State changed - clear all jurisdiction-related state
            st.session_state.selected_state_name = selected_state_name
            st.session_state.selected_jurisdiction_name = None
            st.session_state.selected_polygon_wkt = None
            st.session_state.selected_polygon_bounds = None
            # Clear jurisdiction selector widget state
            if 'jurisdiction_selector' in st.session_state:
                del st.session_state['jurisdiction_selector']
    else:
        # User selected empty option - clear the state
        if st.session_state.selected_state_name is not None:
            st.session_state.selected_state_name = None
            st.session_state.selected_jurisdiction_name = None
            st.session_state.selected_polygon_wkt = None
            st.session_state.selected_polygon_bounds = None

    @st.cache_data
    def get_jurisdictions_in_state(_state_name, _session_id=None):
        """
        Get jurisdictions for a state.
        Include session_id in cache key to ensure proper isolation.
        """
        if not _state_name:
            return {}
        try:
            _state_geom = gdf_states[gdf_states['NAME'] == _state_name].iloc[0].geometry
            jurisdictions = {}
            if gdf_counties is not None:
                jurisdictions['county'] = sorted(gdf_counties[gdf_counties.intersects(_state_geom)]['NAME'].tolist())
            if gdf_mpos is not None:
                jurisdictions['mpo'] = sorted(gdf_mpos[gdf_mpos.intersects(_state_geom)]['MPO_NAME'].tolist())
            if gdf_ua is not None:
                jurisdictions['ua'] = sorted(gdf_ua[gdf_ua.intersects(_state_geom)]['NAME10'].tolist())
            return jurisdictions
        except (IndexError, KeyError):
            # State not found, return empty
            return {}

    # CRITICAL: Ensure jurisdiction options are cleared when state changes
    # Check if state actually changed by comparing with previous state
    if 'previous_state_name' not in st.session_state:
        st.session_state.previous_state_name = None

    # If state changed, clear jurisdiction and force rebuild
    if (st.session_state.selected_state_name != st.session_state.previous_state_name and
        st.session_state.previous_state_name is not None):
        # State changed - clear jurisdiction
        st.session_state.selected_jurisdiction_name = None
        st.session_state.selected_polygon_wkt = None
        st.session_state.selected_polygon_bounds = None
        # Clear the jurisdiction selector widget state
        if 'jurisdiction_selector' in st.session_state:
            del st.session_state['jurisdiction_selector']

    # Update previous state name
    st.session_state.previous_state_name = st.session_state.selected_state_name

    jurisdiction_options = {"": ""}

    # Always show jurisdiction layer toggles, even if no state is selected
    # This allows users to see custom jurisdictions and prepare for state selection
    st.subheader("Toggle Jurisdiction Layers")
    st.session_state.show_counties = st.checkbox("Counties", key="show_counties_checkbox", value=st.session_state.show_counties)
    st.session_state.show_mpos = st.checkbox("MPOs", key="show_mpos_checkbox", value=st.session_state.show_mpos)
    st.session_state.show_urban_areas = st.checkbox("Urban Areas", key="show_urban_areas_checkbox", value=st.session_state.show_urban_areas)

    # Add custom jurisdictions toggle
    if st.session_state.get('custom_jurisdictions'):
        st.session_state.show_custom_jurisdictions = st.checkbox("Custom Jurisdictions", key="show_custom_jurisdictions_checkbox", value=st.session_state.get('show_custom_jurisdictions', True))

    # Only populate standard jurisdictions if a state is selected
    if st.session_state.selected_state_name:
        # Include session_id in cache key to ensure proper session isolation
        session_id = st.session_state.get('session_id', 'default')
        cached_jurisdictions = get_jurisdictions_in_state(st.session_state.selected_state_name, session_id)

        if st.session_state.show_counties and 'county' in cached_jurisdictions:
            for name in cached_jurisdictions['county']:
                jurisdiction_options[f"County: {name}"] = ('county', name)
        if st.session_state.show_mpos and 'mpo' in cached_jurisdictions:
            for name in cached_jurisdictions['mpo']:
                jurisdiction_options[f"MPO: {name}"] = ('mpo', name)
        if st.session_state.show_urban_areas and 'ua' in cached_jurisdictions:
            for name in cached_jurisdictions['ua']:
                jurisdiction_options[f"Urban Area: {name}"] = ('ua', name)
    else:
        # If no state selected, show a message
        if not jurisdiction_options or len(jurisdiction_options) == 1:  # Only has empty option
            st.info("ℹ️ Select a state above to see standard jurisdictions (Counties, MPOs, Urban Areas)")

    # Add custom jurisdictions if available and toggle is enabled (always available, regardless of state)
    if st.session_state.get('custom_jurisdictions') and st.session_state.get('show_custom_jurisdictions', True):
        for name in st.session_state.custom_jurisdictions.keys():
            jurisdiction_options[f"Custom: {name}"] = ('custom', name)


    # CRITICAL: Calculate jurisdiction selector index safely
    # Only use existing jurisdiction if it matches the CURRENT state
    current_jurisdiction = st.session_state.get('selected_jurisdiction_name')
    jurisdiction_default_index = 0

    # Only use existing jurisdiction if:
    # 1. It exists in the current options (for current state)
    # 2. For custom jurisdictions, always allow them (no state required)
    # 3. For standard jurisdictions, state must be set
    if current_jurisdiction and current_jurisdiction in jurisdiction_options:
        # Custom jurisdictions don't require state
        if "Custom:" in current_jurisdiction:
            jurisdiction_default_index = list(jurisdiction_options.keys()).index(current_jurisdiction)
        # Standard jurisdictions require state
        elif st.session_state.selected_state_name:
            jurisdiction_default_index = list(jurisdiction_options.keys()).index(current_jurisdiction)
        else:
            # Standard jurisdiction selected but no state - clear it
            st.session_state.selected_jurisdiction_name = None
            st.session_state.selected_polygon_wkt = None
            st.session_state.selected_polygon_bounds = None
    elif current_jurisdiction:
        # Jurisdiction not in current options - clear it
        st.session_state.selected_jurisdiction_name = None
        st.session_state.selected_polygon_wkt = None
        st.session_state.selected_polygon_bounds = None

    # Use state name in key to force reset when state changes
    jurisdiction_selector_key = f"jurisdiction_selector_{st.session_state.selected_state_name or 'none'}"

    # Allow jurisdiction selection even if no state is selected (for custom jurisdictions)
    # But show a helpful message if only standard jurisdictions are available
    has_custom_jurisdictions = any("Custom:" in opt for opt in jurisdiction_options.keys())
    is_disabled = not st.session_state.selected_state_name and not has_custom_jurisdictions

    selected_jurisdiction_key = st.selectbox(
        "Select a Jurisdiction",
        options=list(jurisdiction_options.keys()),
        key=jurisdiction_selector_key,
        disabled=is_disabled,
        index=jurisdiction_default_index,
        help="Select a jurisdiction. Custom jurisdictions are always available. Standard jurisdictions require a state selection."
    )

    if selected_jurisdiction_key:
        juris_type, juris_name = jurisdiction_options[selected_jurisdiction_key]
        # Update session state to match the dropdown key format
        if st.session_state.selected_jurisdiction_name != selected_jurisdiction_key:
            st.session_state.selected_jurisdiction_name = selected_jurisdiction_key
        if juris_type == 'custom':
            # Handle custom jurisdiction
            custom_data = st.session_state.custom_jurisdictions[juris_name]
            if len(custom_data['gdf']) > 1:
                # Create user-friendly polygon options
                polygon_options = create_polygon_options(custom_data['gdf'])
                if polygon_options:
                    # Get current selection if it exists
                    current_selection = st.session_state.get('selected_custom_polygon_option')
                    default_index = 0
                    if current_selection:
                        try:
                            default_index = next(i for i, opt in enumerate(polygon_options) if opt[0] == current_selection)
                        except StopIteration:
                            default_index = 0

                    selected_option = st.selectbox(
                        "Select Polygon:",
                        options=[opt[0] for opt in polygon_options],
                        key="custom_poly_selector",
                        index=default_index
                    )
                    # Store the selection for next time
                    st.session_state.selected_custom_polygon_option = selected_option
                    # Find the corresponding index
                    selected_idx = next(opt[1] for opt in polygon_options if opt[0] == selected_option)
                    selected_poly = custom_data['gdf'].iloc[selected_idx].geometry
                else:
                    # Fallback to simple index selection
                    current_idx = st.session_state.get('selected_custom_polygon_idx', 0)
                    poly_idx = st.selectbox("Select Polygon:", range(len(custom_data['gdf'])), key="custom_poly_selector", index=current_idx)
                    st.session_state.selected_custom_polygon_idx = poly_idx
                    selected_poly = custom_data['gdf'].iloc[poly_idx].geometry
            else:
                selected_poly = custom_data['gdf'].iloc[0].geometry
            st.session_state.selected_polygon_wkt = dumps(selected_poly)
            bounds = selected_poly.bounds
            st.session_state.selected_polygon_bounds = [[bounds[1], bounds[0]], [bounds[3], bounds[2]]]
            st.session_state.selected_jurisdiction_name = selected_jurisdiction_key
        else:
            # Handle standard jurisdictions
            # CRITICAL: Filter by state first to avoid matching jurisdictions with same name in different states
            if not st.session_state.selected_state_name:
                st.error("❌ Please select a state first")
                st.session_state.selected_jurisdiction_name = None
                st.session_state.selected_polygon_wkt = None
            else:
                gdf_map = {'county': gdf_counties, 'mpo': gdf_mpos, 'ua': gdf_ua}
                name_col_map = {'county': 'NAME', 'mpo': 'MPO_NAME', 'ua': 'NAME10'}
                target_gdf = gdf_map.get(juris_type)
                if target_gdf is not None:
                    # Get state geometry to filter jurisdictions
                    state_geom = gdf_states[gdf_states['NAME'] == st.session_state.selected_state_name].iloc[0].geometry

                    # CRITICAL: Filter by state first, then by name
                    # This ensures we only get jurisdictions from the selected state
                    state_filtered_gdf = target_gdf[target_gdf.intersects(state_geom)]

                    # Now find by name within the state-filtered set
                    name_matches = state_filtered_gdf[state_filtered_gdf[name_col_map[juris_type]] == juris_name]

                    if not name_matches.empty:
                        selected_series = name_matches.iloc[0]
                        st.session_state.selected_polygon_wkt = dumps(selected_series.geometry)
                        bounds = selected_series.geometry.bounds
                        st.session_state.selected_polygon_bounds = [[bounds[1], bounds[0]], [bounds[3], bounds[2]]]
                        st.session_state.selected_jurisdiction_name = selected_jurisdiction_key
                    else:
                        st.error(f"❌ {juris_name} not found in {st.session_state.selected_state_name}. Please select a different jurisdiction.")
                        st.session_state.selected_jurisdiction_name = None
                        st.session_state.selected_polygon_wkt = None
                        st.session_state.selected_polygon_bounds = None
                else:
                    st.error(f"❌ Could not load {juris_type} data")
                    st.session_state.selected_jurisdiction_name = None
                    st.session_state.selected_polygon_wkt = None
    else:
        st.session_state.selected_polygon_wkt = None
        st.session_state.selected_jurisdiction_name = None

    st.subheader("3. Actions")

    # Performance Mode Selector
    performance_mode = st.selectbox(
        "Performance Mode",
        ["Fast", "Balanced", "Complete"],
        index=0,
        help="Fast: Major roads only | Balanced: Most roads | Complete: All roads"
    )

    col1, col2 = st.columns(2)

    def set_zoom_flag():
        st.session_state.zoom_to_selection = True

    col1.button("Zoom to Selection", key="zoom_button", use_container_width=True,
                disabled=st.session_state.selected_polygon_wkt is None, on_click=set_zoom_flag)

    if col2.button("Prepare Network", key="prepare_button", use_container_width=True, type="primary", disabled=st.session_state.selected_polygon_wkt is None):
        with st.spinner("Loading network from OSM..."):
            try:
                # Get the selected polygon
                if st.session_state.selected_polygon_wkt:
                    poly_geom = loads(st.session_state.selected_polygon_wkt)

                    # Validate polygon geometry
                    if not poly_geom.is_valid:
                        st.warning("⚠️ Invalid polygon geometry detected. Attempting to fix...")
                        poly_geom = poly_geom.buffer(0)  # Fix invalid geometry
                        if not poly_geom.is_valid:
                            st.error("❌ Could not fix invalid polygon geometry. Please check your custom jurisdiction data.")
                            st.stop()

                    # Check polygon size (area in square degrees)
                    area_deg2 = poly_geom.area
                    area_km2 = area_deg2 * 111.32 * 111.32  # Rough conversion to km²

                    if area_km2 > 10000:  # Larger than 10,000 km²
                        st.warning(f"⚠️ Large area detected ({area_km2:.0f} km²). This may take a while to download...")
                    elif area_km2 < 1:  # Smaller than 1 km²
                        st.warning(f"⚠️ Small area detected ({area_km2:.2f} km²). Network may be sparse...")

                    # Check polygon bounds
                    bounds = poly_geom.bounds
                    st.info(f"📍 Polygon bounds: ({bounds[0]:.4f}, {bounds[1]:.4f}) to ({bounds[2]:.4f}, {bounds[3]:.4f})")

                    # Use OSMnx to load network with proper highway filtering
                    # Set timeout for large areas
                    import signal

                    def timeout_handler(signum, frame):
                        raise TimeoutError("Network download timed out")

                    # Set 5 minute timeout for network download
                    signal.signal(signal.SIGALRM, timeout_handler)
                    signal.alarm(300)  # 5 minutes

                    try:
                        if performance_mode == "Fast":
                            # Fast mode: major roads only (no express lanes)
                            custom_filter = '["highway"~"motorway|trunk|primary|secondary|trunk_link|primary_link|secondary_link"]'
                            G = ox.graph_from_polygon(
                                poly_geom,
                                network_type="drive",
                                simplify=True,
                                custom_filter=custom_filter,
                                retain_all=False
                            )
                        elif performance_mode == "Balanced":
                            # Balanced mode: most roads (no express lanes)
                            custom_filter = '["highway"~"motorway|trunk|primary|secondary|tertiary|trunk_link|primary_link|secondary_link|tertiary_link|residential|unclassified"]'
                            G = ox.graph_from_polygon(
                                poly_geom,
                                network_type="drive",
                                simplify=True,
                                custom_filter=custom_filter,
                                retain_all=False
                            )
                        else:  # Complete
                            # Complete mode: all roads
                            G = ox.graph_from_polygon(
                                poly_geom,
                                network_type="drive",
                                simplify=True
                            )
                    finally:
                        signal.alarm(0)  # Cancel the alarm

                    # Check if graph is empty
                    if len(G.nodes()) == 0:
                        st.error("❌ No network data found for this area. The polygon may be in an area without road data or may be too small.")
                        st.stop()

                    # Clean and prepare the graph for detour analysis
                    with st.spinner("Preparing graph for detour analysis..."):
                        G_clean = du.clean_graph(G)
                        G_prepared = du.prepare_graph(G_clean)

                    st.session_state.graph = G_prepared
                    st.session_state.performance_mode = performance_mode
                    st.success(f"✅ Network prepared: {len(G_prepared.nodes())} nodes, {len(G_prepared.edges())} edges")
                    st.rerun()

            except TimeoutError as e:
                st.error(f"⏰ Network download timed out: {str(e)}")
                st.error("💡 This might be due to:")
                st.error("• Area too large for network download")
                st.error("• Slow internet connection")
                st.error("• OSM server issues")
                st.error("• Try using 'Fast' performance mode for large areas")
            except Exception as e:
                st.error(f"❌ Error preparing network: {str(e)}")
                st.error("💡 This might be due to:")
                st.error("• Invalid polygon geometry")
                st.error("• Area too large or too small")
                st.error("• Network connectivity issues")
                st.error("• OSM data availability in this region")

    # Jurisdiction Selection Map Access
    st.subheader("🗺️ Jurisdiction Selection Map")
    if st.button("📋 Show Jurisdiction Selection Map", help="Click to expand the jurisdiction selection map"):
        st.session_state.show_jurisdiction_map = True

    if st.session_state.get('show_jurisdiction_map', False):
        with st.expander("🗺️ Jurisdiction Selection Map", expanded=True):

            # Create the selection map
            m = leafmap.Map(location=[39.8283, -98.5795], zoom_start=4, height=400)

            # Add base map
            m.add_basemap("CartoDB.Positron")

            # Add states layer with click functionality
            if gdf_states is not None:
                m.add_gdf(
                    clean_gdf_for_map(gdf_states),
                    layer_name="States",
                    style={
                        "color": "gray",
                        "weight": 1,
                        "fillColor": "#add8e6",
                        "fillOpacity": 0.6
                    },
                    info_mode="on_click"
                )

            # Highlight selected state
            if st.session_state.selected_state_name and gdf_states is not None:
                state_series = gdf_states[gdf_states['NAME'] == st.session_state.selected_state_name].iloc[0]
                state_gdf = gpd.GeoDataFrame([1], geometry=[state_series.geometry], crs=gdf_states.crs)
                m.add_gdf(
                    clean_gdf_for_map(state_gdf),
                    layer_name="Selected State",
                    style={
                        "color": "red",
                        "weight": 3,
                        "fillColor": "lightblue",
                        "fillOpacity": 0.3
                    },
                    info_mode="on_click"
                )

            # Add jurisdiction layers based on toggles
            if st.session_state.selected_state_name:
                state_geom = gdf_states[gdf_states['NAME'] == st.session_state.selected_state_name].iloc[0].geometry

                if st.session_state.show_counties and gdf_counties is not None:
                    counties_in_state = gdf_counties[gdf_counties.intersects(state_geom)]
                    if not counties_in_state.empty:
                        m.add_gdf(
                            clean_gdf_for_map(counties_in_state),
                            layer_name="Counties",
                            style={
                                "color": "blue",
                                "weight": 1,
                                "fillColor": "lightblue",
                                "fillOpacity": 0.4
                            },
                            info_mode="on_click"
                        )

                if st.session_state.show_mpos and gdf_mpos is not None:
                    mpos_in_state = gdf_mpos[gdf_mpos.intersects(state_geom)]
                    if not mpos_in_state.empty:
                        m.add_gdf(
                            clean_gdf_for_map(mpos_in_state),
                            layer_name="MPOs",
                            style={
                                "color": "green",
                                "weight": 1,
                                "fillColor": "lightgreen",
                                "fillOpacity": 0.4
                            },
                            info_mode="on_click"
                        )

                if st.session_state.show_urban_areas and gdf_ua is not None:
                    ua_in_state = gdf_ua[gdf_ua.intersects(state_geom)]
                    if not ua_in_state.empty:
                        m.add_gdf(
                            clean_gdf_for_map(ua_in_state),
                            layer_name="Urban Areas",
                            style={
                                "color": "purple",
                                "weight": 1,
                                "fillColor": "lightpink",
                                "fillOpacity": 0.4
                            },
                            info_mode="on_click"
                        )

            # Add custom jurisdictions to map (only if toggle is enabled)
            if st.session_state.get('custom_jurisdictions') and st.session_state.get('show_custom_jurisdictions', True):
                for name, data in st.session_state.custom_jurisdictions.items():
                    gdf = data['gdf']
                    if not gdf.empty:
                        m.add_gdf(
                            clean_gdf_for_map(gdf),
                            layer_name=f"Custom: {name}",
                            style={
                                "color": "orange",
                                "weight": 2,
                                "fillColor": "orange",
                                "fillOpacity": 0.3
                            },
                            info_mode="on_click"
                        )

            # Highlight selected jurisdiction
            if st.session_state.selected_polygon_wkt:
                poly_geom = loads(st.session_state.selected_polygon_wkt)
                selected_gdf = gpd.GeoDataFrame([1], geometry=[poly_geom], crs=gdf_states.crs)
                m.add_gdf(
                    clean_gdf_for_map(selected_gdf),
                    layer_name="Selected Jurisdiction",
                    style={
                        "color": "red",
                        "weight": 4,
                        "fillColor": "red",
                        "fillOpacity": 0.2
                    },
                    info_mode="on_click"
                )

            # Display the map with click handling
            map_component = m.to_streamlit()

            # Handle map clicks for jurisdiction selection
            try:
                if map_component:
                    last_clicked = m.st_last_click(map_component)

                    if last_clicked and isinstance(last_clicked, dict) and 'layer_name' in last_clicked:
                        layer_name = last_clicked['layer_name']

                        if layer_name == "States" and 'NAME' in last_clicked:
                            clicked_state = last_clicked['NAME']
                            if clicked_state != st.session_state.selected_state_name:
                                st.session_state.selected_state_name = clicked_state
                                st.session_state.selected_jurisdiction_name = None
                                st.session_state.selected_polygon_wkt = None
                                st.success(f"🗺️ Selected state: {clicked_state}")
                                st.rerun()

                        elif layer_name == "Counties" and 'NAME' in last_clicked:
                            clicked_county = last_clicked['NAME']
                            jurisdiction_key = f"County: {clicked_county}"
                            if jurisdiction_key != st.session_state.selected_jurisdiction_name:
                                st.session_state.selected_jurisdiction_name = jurisdiction_key
                                county_geom = gdf_counties[gdf_counties['NAME'] == clicked_county].iloc[0].geometry
                                st.session_state.selected_polygon_wkt = dumps(county_geom)
                                bounds = county_geom.bounds
                                st.session_state.selected_polygon_bounds = [[bounds[1], bounds[0]], [bounds[3], bounds[2]]]
                                st.success(f"🗺️ Selected county: {clicked_county}")
                                st.rerun()

                        elif layer_name == "MPOs" and 'MPO_NAME' in last_clicked:
                            clicked_mpo = last_clicked['MPO_NAME']
                            jurisdiction_key = f"MPO: {clicked_mpo}"
                            if jurisdiction_key != st.session_state.selected_jurisdiction_name:
                                st.session_state.selected_jurisdiction_name = jurisdiction_key
                                mpo_geom = gdf_mpos[gdf_mpos['MPO_NAME'] == clicked_mpo].iloc[0].geometry
                                st.session_state.selected_polygon_wkt = dumps(mpo_geom)
                                bounds = mpo_geom.bounds
                                st.session_state.selected_polygon_bounds = [[bounds[1], bounds[0]], [bounds[3], bounds[2]]]
                                st.success(f"🗺️ Selected MPO: {clicked_mpo}")
                                st.rerun()

                        elif layer_name == "Urban Areas" and 'NAME10' in last_clicked:
                            clicked_ua = last_clicked['NAME10']
                            jurisdiction_key = f"Urban Area: {clicked_ua}"
                            if jurisdiction_key != st.session_state.selected_jurisdiction_name:
                                st.session_state.selected_jurisdiction_name = jurisdiction_key
                                ua_geom = gdf_ua[gdf_ua['NAME10'] == clicked_ua].iloc[0].geometry
                                st.session_state.selected_polygon_wkt = dumps(ua_geom)
                                bounds = ua_geom.bounds
                                st.session_state.selected_polygon_bounds = [[bounds[1], bounds[0]], [bounds[3], bounds[2]]]
                                st.success(f"🗺️ Selected urban area: {clicked_ua}")
                                st.rerun()

                        elif layer_name.startswith("Custom:") and 'geometry' in last_clicked:
                            custom_name = layer_name.replace("Custom: ", "")
                            jurisdiction_key = f"Custom: {custom_name}"
                            if jurisdiction_key != st.session_state.selected_jurisdiction_name:
                                st.session_state.selected_jurisdiction_name = jurisdiction_key
                                custom_data = st.session_state.custom_jurisdictions[custom_name]
                                clicked_geom = last_clicked['geometry']
                                for idx, row in custom_data['gdf'].iterrows():
                                    if row.geometry.equals(clicked_geom):
                                        st.session_state.selected_polygon_wkt = dumps(row.geometry)
                                        bounds = row.geometry.bounds
                                        st.session_state.selected_polygon_bounds = [[bounds[1], bounds[0]], [bounds[3], bounds[2]]]
                                        break
                                st.success(f"🗺️ Selected custom jurisdiction: {custom_name}")
                                st.rerun()
            except Exception as e:
                    pass

    st.divider()

    # Additional Data Layers section
    st.header("📊 Additional Data Layers")


    if st.session_state.get('additional_data'):
        st.info("💡 These layers are automatically displayed on the network map and filtered to show only features inside the selected jurisdiction. Used for proximity analysis in exports.")

        # Add legend for additional data layers
        st.subheader("🎨 Layer Legend")
        col1, col2 = st.columns([1, 3])
        with col1:
            st.markdown("**Point Data:**")
            st.markdown("**Traffic Signals:**")
            st.markdown("**Line/Polygon Data:**")
        with col2:
            st.markdown("🚦 Custom traffic signal icon")
            st.markdown("🚦 Traffic signal icon")
    else:
        st.info("💡 No additional data layers loaded. Upload shapefiles in the setup wizard to add them here.")

    if st.session_state.get('additional_data'):
        for name, data in st.session_state.additional_data.items():
            gdf = data['gdf']
            geom_types = gdf.geometry.geom_type.unique()

            with st.expander(f"📁 {name} ({len(gdf)} features)", expanded=False):
                col1, col2 = st.columns([3, 1])

                with col1:
                    st.write(f"**Layer Info:**")
                    st.write(f"• Features: {len(gdf)}")
                    st.write(f"• Geometry Types: {', '.join(geom_types)}")
                    st.write(f"• CRS: {gdf.crs}")

                    # Show first few rows
                    st.write("**Data Preview:**")
                    # Convert geometry to WKT for display to avoid PyArrow issues
                    display_gdf = gdf.copy()
                    if 'geometry' in display_gdf.columns:
                        display_gdf['geometry'] = display_gdf['geometry'].apply(lambda x: str(x)[:50] + "..." if len(str(x)) > 50 else str(x))
                    st.dataframe(display_gdf.head(), use_container_width=True)

                    # Show geometry bounds
                    if len(gdf) > 0:
                        bounds = gdf.total_bounds
                        st.write(f"**Bounds:** ({bounds[0]:.4f}, {bounds[1]:.4f}) to ({bounds[2]:.4f}, {bounds[3]:.4f})")

                with col2:
                    if st.button(f"🗑️ Delete", key=f"delete_additional_{name}"):
                        del st.session_state.additional_data[name]
                        st.success(f"Deleted {name}")
                        st.rerun()

                    # Hide/Show layer on map toggle (default is visible)
                    if st.button(f"👁️ Hide from Map" if st.session_state.get(f"show_layer_{name}", True) else f"🗺️ Show on Map", key=f"show_map_{name}"):
                        st.session_state[f"show_layer_{name}"] = not st.session_state.get(f"show_layer_{name}", True)
                        st.rerun()

                    if st.session_state.get(f"show_layer_{name}", True):
                        st.success("✅ Visible on map")
                    else:
                        st.info("👁️ Hidden from map")

    st.divider()

    # Analysis section
    st.header("4. Analysis")

    def get_edge_options(_graph):
        if not _graph:
            return {"": None}

        edge_options = {"": None}
        # Convert OSMnx graph to GeoDataFrame
        _, edges_gdf = ox.graph_to_gdfs(_graph)

        # Sort by OSMID
        if 'osmid' in edges_gdf.columns:
            # Handle OSMID lists and sort
            edges_gdf['osmid_str'] = edges_gdf['osmid'].apply(
                lambda x: ', '.join(map(str, x)) if isinstance(x, list) else str(x)
            )
            edges_gdf = edges_gdf.sort_values(by="osmid_str")

        for idx, row in edges_gdf.iterrows():
            u, v, k = idx
            osmid = row.get('osmid', 'N/A')
            if isinstance(osmid, list):
                osmid = ', '.join(map(str, osmid))

            name = row.get('name', "Unnamed Road")
            if isinstance(name, list):
                name = '; '.join(name)

            highway = row.get('highway', 'unknown')
            if isinstance(highway, list):
                highway = '; '.join(highway)

            key = f"OSMID: {osmid} | {name} ({highway})"
            edge_options[key] = (u, v, k)

        return edge_options

    # Edge selection
    edge_options_dict = get_edge_options(st.session_state.graph)
    edge_option_keys = list(edge_options_dict.keys())

    # Data status
    if st.session_state.graph:
        st.success(f"✅ Graph loaded: {len(st.session_state.graph.nodes())} nodes, {len(st.session_state.graph.edges())} edges")
    else:
        st.info("📊 No network data loaded")

    def update_random_edge():
        if len(edge_option_keys) > 1:
            st.session_state.selected_edge_key = random.choice(edge_option_keys[1:])

    # Incident edge selection
    st.selectbox("Select Incident Edge", options=edge_option_keys, key="selected_edge_key",
        disabled=st.session_state.graph is None, help="Select the road link (by OSMID) where the incident occurred.")

    # Show current selection
    if st.session_state.selected_edge_key:
        st.info(f"📍 **Selected Incident:** {st.session_state.selected_edge_key}")

        # Add confirm button for feedback
        if st.button("🎯 Confirm Incident Link", disabled=st.session_state.graph is None):
            st.session_state.zoom_to_incident = True
            st.success(f"✅ Incident link confirmed: {st.session_state.selected_edge_key}")
            st.rerun()

    # Analysis parameters
    st.subheader("Detour Parameters")
    max_detour_distance = st.slider("Max Detour Distance (km):", 1, 50, 10)
    max_detour_time = st.slider("Max Detour Time (minutes):", 5, 120, 30)
    max_alternatives = st.slider("Max Alternatives:", 1, 20, 5)

    # Export parameters
    st.subheader("Export Settings")
    buffer_miles = st.slider("Buffer Distance for Points (miles):", 0.1, 2.0, 0.1, 0.1)


    st.divider()

    # Action buttons
    st.header("5. Actions")

    def update_random_edge():
        if len(edge_option_keys) > 1:
            st.session_state.selected_edge_key = random.choice(edge_option_keys[1:])
            st.rerun()

    b_col1, b_col2 = st.columns(2)
    b_col1.button("Pick Random Edge", key="random_edge_picker_button", use_container_width=True,
                  disabled=st.session_state.graph is None, on_click=update_random_edge)
    find_detours_button = b_col2.button("Find Detours", key="find_detours_button", type="primary", use_container_width=True,
                                        disabled=(st.session_state.graph is None or not st.session_state.selected_edge_key))

# --- Main Panel ---
# Network Selection Map (for area selection) - Collapsible when incident edge is selected
if not st.session_state.get('selected_edge_key'):
    # Only show the Network Selection Map when no incident edge is selected
    with st.expander("🗺️ Network Selection Map", expanded=True):

        # Create the selection map
        m = leafmap.Map(location=[39.8283, -98.5795], zoom_start=4, height=400)

        # Add base map
        m.add_basemap("CartoDB.Positron")

        # Load shapefiles for the selection map
        all_gdfs = load_all_shapefiles()
        gdf_states = all_gdfs["states"]
        gdf_counties = all_gdfs["counties"]
        gdf_mpos = all_gdfs["mpos"]
        gdf_ua = all_gdfs["ua"]

        # Add states layer with click functionality
        if gdf_states is not None:
            m.add_gdf(
                clean_gdf_for_map(gdf_states),
                layer_name="States",
                style={
                    "color": "gray",
                    "weight": 1,
                    "fillColor": "#add8e6",
                    "fillOpacity": 0.6
                },
                info_mode="on_click"
            )

        # Highlight selected state
        if st.session_state.selected_state_name and gdf_states is not None:
            state_series = gdf_states[gdf_states['NAME'] == st.session_state.selected_state_name].iloc[0]
            state_gdf = gpd.GeoDataFrame([1], geometry=[state_series.geometry], crs=gdf_states.crs)
            m.add_gdf(
                clean_gdf_for_map(state_gdf),
                layer_name="Selected State",
                style={
                    "color": "red",
                    "weight": 3,
                    "fillColor": "lightblue",
                    "fillOpacity": 0.3
                },
                info_mode="on_click"
            )

        # Add jurisdiction layers based on toggles
        if st.session_state.selected_state_name:
            state_geom = gdf_states[gdf_states['NAME'] == st.session_state.selected_state_name].iloc[0].geometry

            if st.session_state.show_counties and gdf_counties is not None:
                counties_in_state = gdf_counties[gdf_counties.intersects(state_geom)]
                if not counties_in_state.empty:
                    m.add_gdf(
                        clean_gdf_for_map(counties_in_state),
                        layer_name="Counties",
                        style={
                            "color": "blue",
                            "weight": 1,
                            "fillColor": "lightblue",
                            "fillOpacity": 0.4
                        },
                        info_mode="on_click"
                    )

            if st.session_state.show_mpos and gdf_mpos is not None:
                mpos_in_state = gdf_mpos[gdf_mpos.intersects(state_geom)]
                if not mpos_in_state.empty:
                    m.add_gdf(
                        clean_gdf_for_map(mpos_in_state),
                        layer_name="MPOs",
                        style={
                            "color": "green",
                            "weight": 1,
                            "fillColor": "lightgreen",
                            "fillOpacity": 0.4
                        },
                        info_mode="on_click"
                    )

            if st.session_state.show_urban_areas and gdf_ua is not None:
                ua_in_state = gdf_ua[gdf_ua.intersects(state_geom)]
                if not ua_in_state.empty:
                    m.add_gdf(
                        clean_gdf_for_map(ua_in_state),
                        layer_name="Urban Areas",
                        style={
                            "color": "purple",
                            "weight": 1,
                            "fillColor": "lightpink",
                            "fillOpacity": 0.4
                        },
                        info_mode="on_click"
                    )

        # Add custom jurisdictions to map (only if toggle is enabled)
        if st.session_state.get('custom_jurisdictions') and st.session_state.get('show_custom_jurisdictions', True):
            for name, data in st.session_state.custom_jurisdictions.items():
                gdf = data['gdf']
                if not gdf.empty:
                    m.add_gdf(
                        clean_gdf_for_map(gdf),
                        layer_name=f"Custom: {name}",
                        style={
                            "color": "orange",
                            "weight": 2,
                            "fillColor": "orange",
                            "fillOpacity": 0.3
                        },
                        info_mode="on_click"
                    )

        # Highlight selected jurisdiction
        if st.session_state.selected_polygon_wkt:
            poly_geom = loads(st.session_state.selected_polygon_wkt)
            selected_gdf = gpd.GeoDataFrame([1], geometry=[poly_geom], crs=gdf_states.crs)
            m.add_gdf(
                clean_gdf_for_map(selected_gdf),
                layer_name="Selected Jurisdiction",
                style={
                    "color": "red",
                    "weight": 4,
                    "fillColor": "red",
                    "fillOpacity": 0.2
                },
                info_mode="on_click"
            )

        # Display the map with click handling
        map_component = m.to_streamlit()

        # Handle map clicks for jurisdiction selection
        try:
            if map_component:
                last_clicked = m.st_last_click(map_component)

                if last_clicked and isinstance(last_clicked, dict) and 'layer_name' in last_clicked:
                    layer_name = last_clicked['layer_name']

                    if layer_name == "States" and 'NAME' in last_clicked:
                        clicked_state = last_clicked['NAME']
                        if clicked_state != st.session_state.selected_state_name:
                            st.session_state.selected_state_name = clicked_state
                            st.session_state.selected_jurisdiction_name = None
                            st.session_state.selected_polygon_wkt = None
                            st.success(f"🗺️ Selected state: {clicked_state}")
                            st.rerun()

                    elif layer_name == "Counties" and 'NAME' in last_clicked:
                        clicked_county = last_clicked['NAME']
                        jurisdiction_key = f"County: {clicked_county}"
                        if jurisdiction_key != st.session_state.selected_jurisdiction_name:
                            st.session_state.selected_jurisdiction_name = jurisdiction_key
                            county_geom = gdf_counties[gdf_counties['NAME'] == clicked_county].iloc[0].geometry
                            st.session_state.selected_polygon_wkt = dumps(county_geom)
                            bounds = county_geom.bounds
                            st.session_state.selected_polygon_bounds = [[bounds[1], bounds[0]], [bounds[3], bounds[2]]]
                            st.success(f"🗺️ Selected county: {clicked_county}")
                            st.rerun()

                    elif layer_name == "MPOs" and 'MPO_NAME' in last_clicked:
                        clicked_mpo = last_clicked['MPO_NAME']
                        jurisdiction_key = f"MPO: {clicked_mpo}"
                        if jurisdiction_key != st.session_state.selected_jurisdiction_name:
                            st.session_state.selected_jurisdiction_name = jurisdiction_key
                            mpo_geom = gdf_mpos[gdf_mpos['MPO_NAME'] == clicked_mpo].iloc[0].geometry
                            st.session_state.selected_polygon_wkt = dumps(mpo_geom)
                            bounds = mpo_geom.bounds
                            st.session_state.selected_polygon_bounds = [[bounds[1], bounds[0]], [bounds[3], bounds[2]]]
                            st.success(f"🗺️ Selected MPO: {clicked_mpo}")
                            st.rerun()

                    elif layer_name == "Urban Areas" and 'NAME10' in last_clicked:
                        clicked_ua = last_clicked['NAME10']
                        jurisdiction_key = f"Urban Area: {clicked_ua}"
                        if jurisdiction_key != st.session_state.selected_jurisdiction_name:
                            st.session_state.selected_jurisdiction_name = jurisdiction_key
                            ua_geom = gdf_ua[gdf_ua['NAME10'] == clicked_ua].iloc[0].geometry
                            st.session_state.selected_polygon_wkt = dumps(ua_geom)
                            bounds = ua_geom.bounds
                            st.session_state.selected_polygon_bounds = [[bounds[1], bounds[0]], [bounds[3], bounds[2]]]
                            st.success(f"🗺️ Selected urban area: {clicked_ua}")
                            st.rerun()

                    elif layer_name.startswith("Custom:") and 'geometry' in last_clicked:
                        custom_name = layer_name.replace("Custom: ", "")
                        jurisdiction_key = f"Custom: {custom_name}"
                        if jurisdiction_key != st.session_state.selected_jurisdiction_name:
                            st.session_state.selected_jurisdiction_name = jurisdiction_key
                            custom_data = st.session_state.custom_jurisdictions[custom_name]
                            clicked_geom = last_clicked['geometry']
                            for idx, row in custom_data['gdf'].iterrows():
                                if row.geometry.equals(clicked_geom):
                                    st.session_state.selected_polygon_wkt = dumps(row.geometry)
                                    bounds = row.geometry.bounds
                                    st.session_state.selected_polygon_bounds = [[bounds[1], bounds[0]], [bounds[3], bounds[2]]]
                                    break
                            st.success(f"🗺️ Selected custom jurisdiction: {custom_name}")
                            st.rerun()
        except Exception as e:
                pass

        # Zoom to selection if requested
        if st.session_state.get('zoom_to_selection') and st.session_state.selected_polygon_bounds:
            st.info("📍 Zooming to selected area...")
            st.session_state.zoom_to_selection = False

else:
    # Show collapsed state when incident edge is selected
    st.info("🗺️ **Network Selection Map** is collapsed because an incident edge is selected. Clear the incident edge to expand the map.")

st.divider()

# Network Graph View (for loaded networks)
st.header("🗺️ Network Graph View")

if st.session_state.graph:
    G = st.session_state.graph

    # Convert OSMnx graph to GeoDataFrames
    nodes, edges = ox.graph_to_gdfs(G)

    # Clean up any problematic data types for display
    for col in edges.columns:
        if any(isinstance(val, set) for val in edges[col]):
            edges[col] = edges[col].apply(lambda x: str(x) if isinstance(x, set) else x)

    # Compute map center
    map_center = [edges.unary_union.centroid.y, edges.unary_union.centroid.x]

    # Create Leafmap instance
    m = leafmap.Map(
        location=map_center,
        zoom_start=12,
        height=500,
        width="100%"
    )

    # Add base map
    m.add_basemap("CartoDB.Positron")

    # For very large graphs, sample edges to avoid locking the UI
    render_edges = edges
    if len(edges) > 75000:
        render_edges = edges.sample(n=75000, random_state=42)

    # Add network edges as GeoJSON layer
    m.add_gdf(
        clean_gdf_for_map(render_edges),
        layer_name="Network Roads",
        style={
            "color": "#333333",
            "weight": 2,
            "opacity": 0.8
        },
        info_mode="on_click"
    )

    # Add jurisdiction outline
    if st.session_state.selected_polygon_wkt:
        poly_geom = loads(st.session_state.selected_polygon_wkt)
        # Create GeoDataFrame for jurisdiction
        jurisdiction_gdf = gpd.GeoDataFrame([1], geometry=[poly_geom], crs=edges.crs)

        m.add_gdf(
            clean_gdf_for_map(jurisdiction_gdf),
            layer_name="Jurisdiction Outline",
            style={
                "color": "red",
                "weight": 3,
                "fillColor": "none",
                "opacity": 1.0
            },
            info_mode="on_click"
        )

        # Fit map to jurisdiction bounds
        bounds = poly_geom.bounds
        m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])

    # Add incident edge highlighting
    if (st.session_state.selected_edge_key and
        st.session_state.selected_edge_key in edge_options_dict and
        edge_options_dict[st.session_state.selected_edge_key] is not None):
        incident_edge = edge_options_dict[st.session_state.selected_edge_key]
        if G.has_edge(*incident_edge):
            # Get the edge geometry
            edge_data = G.get_edge_data(*incident_edge)
            if edge_data and 'geometry' in edge_data:
                edge_geom = edge_data['geometry']

                # Add incident edge as GeoJSON
                incident_gdf = gpd.GeoDataFrame([1], geometry=[edge_geom], crs=edges.crs)
                m.add_gdf(
                    clean_gdf_for_map(incident_gdf),
                    layer_name="Incident Edge",
                    style={
                        "color": "red",
                        "weight": 6,
                        "opacity": 0.8
                    },
                    info_mode="on_click"
                )


                # Zoom to incident if requested
                if st.session_state.get('zoom_to_incident', False):
                    bounds = edge_geom.bounds
                    m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
                    st.session_state.zoom_to_incident = False

    # Add accepted detour routes with varying colors
    if 'accepted_detours' in st.session_state and st.session_state.accepted_detours:
        # Color palette for detour routes (avoiding red, yellow, green)
        route_colors = ['blue', 'purple', 'pink', 'lightblue', 'darkblue',
                       'magenta', 'cyan', 'darkviolet', 'indigo', 'teal', 'navy',
                       'aqua', 'fuchsia', 'silver', 'gray', 'darkgray', 'lightgray',
                       'black', 'darkmagenta', 'mediumpurple']

        # Convert to list to get index for color assignment
        routes_list = list(st.session_state.accepted_detours.items())

        for route_idx, (route_key, route_data) in enumerate(routes_list):
            # Try multiple ways to get the path
            path = None
            if 'data' in route_data and len(route_data['data']) >= 4:
                _, _, _, path = route_data['data']
            elif 'path' in route_data:
                path = route_data['path']

            if path and len(path) > 1:
                # Create path geometry
                path_coords = []
                for i in range(len(path) - 1):
                    if G.has_edge(path[i], path[i+1]):
                        edge_data = G.get_edge_data(path[i], path[i+1])
                        if edge_data:
                            # Handle edge_data structure (NetworkX can return dict with keys or direct dict)
                            edge_attrs = None
                            if isinstance(edge_data, dict):
                                # Check if it's a dict of edge keys (multi-edge case like {0: {...}, 1: {...}})
                                # or a direct edge attributes dict
                                if len(edge_data) > 0:
                                    first_key = next(iter(edge_data.keys()))
                                    # If keys are integers (0, 1, 2...), it's multi-edge format
                                    if isinstance(first_key, int):
                                        edge_attrs = edge_data[first_key]
                                    # Otherwise, it's direct edge attributes
                                    elif 'geometry' in edge_data or 'osmid' in edge_data:
                                        edge_attrs = edge_data
                                    else:
                                        # Try to get first value
                                        edge_attrs = next(iter(edge_data.values()))
                                else:
                                    edge_attrs = edge_data
                            else:
                                edge_attrs = edge_data

                            # Try to get geometry from edge
                            edge_geom = None
                            if edge_attrs:
                                if isinstance(edge_attrs, dict) and 'geometry' in edge_attrs:
                                    edge_geom = edge_attrs['geometry']
                                elif hasattr(edge_attrs, 'geometry'):
                                    edge_geom = edge_attrs.geometry

                            if edge_geom and hasattr(edge_geom, 'coords'):
                                # Use edge geometry coordinates
                                path_coords.extend(list(edge_geom.coords))
                            else:
                                # Fallback to node coordinates if edge geometry not available
                                if path[i] in G.nodes and path[i+1] in G.nodes:
                                    u_node = G.nodes[path[i]]
                                    v_node = G.nodes[path[i+1]]
                                    if 'x' in u_node and 'y' in u_node and 'x' in v_node and 'y' in v_node:
                                        path_coords.append((u_node['x'], u_node['y']))
                                        path_coords.append((v_node['x'], v_node['y']))

                if path_coords and len(path_coords) > 1:
                    # Create a line from the path coordinates
                    try:
                        detour_line = LineString(path_coords)
                        detour_gdf = gpd.GeoDataFrame([1], geometry=[detour_line], crs=edges.crs)

                        # Assign color based on route index
                        route_color = route_colors[route_idx % len(route_colors)]

                        m.add_gdf(
                            clean_gdf_for_map(detour_gdf),
                            layer_name=f"Detour Route {route_key}",
                            style={
                                "color": route_color,
                                "weight": 4,
                                "opacity": 0.7
                            },
                            info_mode="on_click"
                        )
                    except Exception as e:
                        # If LineString creation fails, try with simplified coordinates
                        st.warning(f"Could not display route {route_key} on map: {str(e)}")

    # Add additional data layers if they're toggled to show - TEMPORARILY DISABLED
    # Display additional data layers on the map
    if st.session_state.get('additional_data'):
        for name, data in st.session_state.additional_data.items():
            if st.session_state.get(f"show_layer_{name}", True):
                gdf = data['gdf']

                # Filter to only show features inside the selected jurisdiction
                if st.session_state.selected_polygon_wkt:
                    try:
                        from shapely.wkt import loads
                        selected_polygon = loads(st.session_state.selected_polygon_wkt)

                        # Ensure both geometries are in the same CRS
                        if gdf.crs is None:
                            gdf = gdf.set_crs('EPSG:4326')

                        # Create a GeoDataFrame for the selected polygon
                        polygon_gdf = gpd.GeoDataFrame([1], geometry=[selected_polygon], crs=gdf.crs)

                        # For Point geometries, use within() to ensure they're actually inside
                        # For other geometries, use intersects() to include those that cross boundaries
                        geometry_types = gdf.geometry.geom_type.unique()
                        has_points = any(geom_type in ['Point', 'MultiPoint'] for geom_type in geometry_types)

                        if has_points:
                            # Use within() for points to ensure they're inside the polygon
                            filtered_gdf = gdf[gdf.geometry.within(selected_polygon)]
                        else:
                            # Use intersects() for lines/polygons that may cross boundaries
                            filtered_gdf = gdf[gdf.geometry.intersects(selected_polygon)]

                        if len(filtered_gdf) == 0:
                            continue  # Skip if no features intersect

                        gdf = filtered_gdf

                    except Exception as e:
                        st.warning(f"⚠️ Could not filter {name} by jurisdiction: {str(e)}")
                        # Continue with unfiltered data if filtering fails

                # Style based on geometry type
                if any(gtype in ['Point', 'MultiPoint'] for gtype in gdf.geometry.geom_type.unique()):
                    # Point data - use individual markers with custom styling
                    try:
                        # Check if this is traffic signal data to use custom icon
                        is_traffic = is_traffic_signal_data(name, gdf)
                        if is_traffic:
                            # Use individual markers with traffic signal icon
                            for idx, row in gdf.iterrows():
                                point = row.geometry
                                if hasattr(point, 'y') and hasattr(point, 'x'):
                                    icon = create_traffic_signal_icon()
                                    m.add_marker(
                                        location=[point.y, point.x],
                                        popup=f"{name}: Feature {idx}",
                                        icon=icon
                                    )
                        else:
                            # Non-traffic signal data - use colored dots (random color per layer)
                            layer_color = generate_layer_color(name)
                            for idx, row in gdf.iterrows():
                                point = row.geometry
                                if hasattr(point, 'y') and hasattr(point, 'x'):
                                    folium.CircleMarker(
                                        location=[point.y, point.x],
                                        radius=5,
                                        color=layer_color,
                                        fill=True,
                                        fillColor=layer_color,
                                        fillOpacity=0.8,
                                        weight=2,
                                        popup=f"{name}: Feature {idx}"
                                    ).add_to(m)
                    except Exception as e:
                        st.warning(f"⚠️ Could not add styled points for {name}: {str(e)}")
                        # Fallback to individual markers with custom icons
                        try:
                            for idx, row in gdf.iterrows():
                                point = row.geometry
                                if hasattr(point, 'y') and hasattr(point, 'x'):
                                    # Use custom traffic signal icon if this is traffic signal data
                                    if is_traffic_signal_data(name, gdf):
                                        icon = create_traffic_signal_icon()
                                        m.add_marker(
                                            location=[point.y, point.x],
                                            popup=f"{name}: Feature {idx}",
                                            icon=icon
                                        )
                                    else:
                                        # Use colored circle marker for non-traffic data
                                        layer_color = generate_layer_color(name)
                                        folium.CircleMarker(
                                            location=[point.y, point.x],
                                            radius=5,
                                            color=layer_color,
                                            fill=True,
                                            fillColor=layer_color,
                                            fillOpacity=0.8,
                                            weight=2,
                                            popup=f"{name}: Feature {idx}"
                                        ).add_to(m)
                        except Exception as e2:
                            st.warning(f"⚠️ Could not add individual markers for {name}: {str(e2)}")
                            # Final fallback - simple markers with custom traffic signal icon
                            for idx, row in gdf.iterrows():
                                point = row.geometry
                                if hasattr(point, 'y') and hasattr(point, 'x'):
                                    # Use custom traffic signal icon if this is traffic signal data
                                    if is_traffic_signal_data(name, gdf):
                                        icon = create_traffic_signal_icon()
                                        m.add_marker(
                                            location=[point.y, point.x],
                                            popup=f"{name}: Feature {idx}",
                                            icon=icon
                                        )
                                    else:
                                        # Use colored circle marker for non-traffic data
                                        layer_color = generate_layer_color(name)
                                        folium.CircleMarker(
                                            location=[point.y, point.x],
                                            radius=5,
                                            color=layer_color,
                                            fill=True,
                                            fillColor=layer_color,
                                            fillOpacity=0.8,
                                            weight=2,
                                            popup=f"{name}: Feature {idx}"
                                        ).add_to(m)
                else:
                    # Line/Polygon data - use GeoJSON with thinner lines
                    # Clean the GeoDataFrame to remove non-serializable columns
                    clean_gdf = gdf.copy()

                    # Convert Timestamp columns to strings
                    for col in clean_gdf.columns:
                        if clean_gdf[col].dtype == 'datetime64[ns]' or 'Timestamp' in str(type(clean_gdf[col].iloc[0])) if len(clean_gdf) > 0 else False:
                            clean_gdf[col] = clean_gdf[col].astype(str)

                    # Remove any other problematic columns
                    problematic_types = ['object', 'category']
                    for col in clean_gdf.columns:
                        if col != 'geometry' and clean_gdf[col].dtype in problematic_types:
                            try:
                                # Try to convert to string, if it fails, drop the column
                                clean_gdf[col] = clean_gdf[col].astype(str)
                            except:
                                clean_gdf = clean_gdf.drop(columns=[col])

                    m.add_gdf(
                        clean_gdf_for_map(clean_gdf),
                        layer_name=f"Additional: {name}",
                        style={
                            "color": "purple",
                            "weight": 1,
                            "opacity": 0.6
                        },
                        info_mode="on_click"
                    )

    # Add incident edge marker LAST so it appears on top of all other elements
    if (st.session_state.selected_edge_key and
        st.session_state.selected_edge_key in edge_options_dict and
        edge_options_dict[st.session_state.selected_edge_key] is not None):
        incident_edge = edge_options_dict[st.session_state.selected_edge_key]
        if incident_edge and len(incident_edge) >= 2:
            u, v = incident_edge[0], incident_edge[1]
            if st.session_state.graph.has_edge(u, v):
                # Get edge data safely - handle both 2-tuple and 3-tuple edge formats
                try:
                    # Try to get edge data with key if it exists
                    edge_data = st.session_state.graph.get_edge_data(u, v)
                    if edge_data:
                        # Get the first edge data (in case of multiple edges between same nodes)
                        edge_attrs = next(iter(edge_data.values())) if isinstance(edge_data, dict) else edge_data
                        edge_geom = edge_attrs.get('geometry')

                        if edge_geom:
                            # Add marker at center of incident edge
                            center_point = edge_geom.centroid

                            # Create a larger red icon for incident edge
                            incident_icon_html = """
                            <div style="width: 40px; height: 40px; background-color: red; border-radius: 50%; border: 3px solid white; box-shadow: 0 0 10px rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center;">
                                <div style="color: white; font-size: 20px; font-weight: bold;">!</div>
                            </div>
                            """

                            incident_icon = folium.DivIcon(
                                html=incident_icon_html,
                                icon_size=(40, 40),
                                icon_anchor=(20, 20),
                                popup_anchor=(0, -20)
                            )

                            m.add_marker(
                                location=[center_point.y, center_point.x],
                                popup=f"Incident Edge: {st.session_state.selected_edge_key}",
                                icon=incident_icon
                            )
                except Exception as e:
                    # If we can't get the geometry, skip adding the marker
                    st.warning(f"⚠️ Could not add incident edge marker: {str(e)}")

    # Display the map with click handling
    map_component = m.to_streamlit()

    # Handle map clicks for incident edge selection
    # Note: Using a safer approach for click handling
    try:
        if map_component:
            # Get the last clicked object using a safer method
            last_clicked = m.st_last_click(map_component)

            if last_clicked and isinstance(last_clicked, dict) and 'layer_name' in last_clicked:
                layer_name = last_clicked['layer_name']

                # Handle clicks on network roads
                if layer_name == "Network Roads" and 'osmid' in last_clicked:
                    clicked_osmid = last_clicked['osmid']

                    # Find the corresponding edge in our edge options
                    for edge_key, edge_data in edge_options_dict.items():
                        if edge_data and len(edge_data) >= 2:
                            u, v = edge_data[0], edge_data[1]
                            # Check if this edge matches the clicked OSMID
                            if st.session_state.graph.has_edge(u, v):
                                edge_attrs = st.session_state.graph.edges[u, v]
                                if edge_attrs.get('osmid') == clicked_osmid:
                                    # Update the selected edge
                                    st.session_state.selected_edge_key = edge_key
                                    st.success(f"🎯 Selected incident edge: {edge_key}")
                                    st.rerun()
                                    break
    except Exception as e:
        # If click handling fails, just display the map without click functionality
        pass

    # Show map legend organized by layer
    st.markdown("### 🗺️ Map Legend")

    # Network Layer
    st.markdown("**🛣️ Network Layer:**")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("• **Network Roads:** Gray lines")
        st.markdown("• **Incident Location:** Red marker + line")
    with col2:
        st.markdown("• **Detour Routes:** Blue lines")

    # Jurisdiction Layer
    st.markdown("**📍 Jurisdiction Layer:**")
    st.markdown("• **Selected Jurisdiction:** Red outline")

    # Additional Data Layers
    if st.session_state.get('additional_data'):
        st.markdown("**📊 Additional Data Layers:**")
        for name, data in st.session_state.additional_data.items():
            gdf = data['gdf']
            geom_types = gdf.geometry.geom_type.unique()
            if any(gtype in ['Point', 'MultiPoint'] for gtype in geom_types):
                st.markdown(f"• **{name}:** 🔵 Blue dots ({len(gdf)} features)")
            else:
                st.markdown(f"• **{name}:** 🟣 Purple lines ({len(gdf)} features)")

    # Show processing indicator below the map
    with st.spinner("Network graph rendered successfully"):
        st.success("✅ Network graph loaded and displayed above")

st.divider()
st.header("📈 Analysis Results")
if find_detours_button:
    G = st.session_state.graph
    incident_edge = edge_options_dict.get(st.session_state.selected_edge_key)

    if not incident_edge:
        st.error("Please select a valid incident edge.")
        st.stop()
    if not G.has_edge(*incident_edge):
        st.error(f"Edge {incident_edge} not in graph.")
        st.stop()

    with st.spinner("Calculating detours..."):
        # Use the user's detour parameters
        max_detour_distance_m = max_detour_distance * 1000  # Convert km to meters
        max_detour_time_s = max_detour_time * 60  # Convert minutes to seconds

        # Set reasonable minimum time for detours (at least 2 minutes)
        min_detour_time_s = 120  # 2 minutes minimum

        # For motorways, we need to look further to find suitable turn points
        search_distance = max(max_alternatives, 10)  # At least 10 nodes for motorways
        start_nodes, end_nodes, _, _ = du.get_surrounding_turns(G, incident_edge, n=search_distance)

        # Debug information
        st.write(f"**Search Parameters:**")
        st.write(f"- Max detour distance: {max_detour_distance} km")
        st.write(f"- Max detour time: {max_detour_time} minutes")
        st.write(f"- Max alternatives: {max_alternatives}")
        st.write(f"- Search distance: {search_distance} nodes")

        # Find detours using the correct pattern from V1.5.2
        try:
            # Get surrounding turns (start and end nodes)
            start_nodes, end_nodes, _, _ = du.get_surrounding_turns(G, incident_edge, n=search_distance)

            if not start_nodes or not end_nodes:
                st.warning("⚠️ No valid start/end nodes found. Try increasing the search distance.")
                st.stop()

            # Generate incident graph
            G_incident = du.generate_incident_graph(G, incident_edge)

            # Find detours
            detours = du.get_detour(G_incident, incident_edge, start_nodes, end_nodes, min_detour_time_s, max_detour_time_s)

            if detours:
                # Conduct buffer search for each detour route to include points in initial printout
                buffer_miles = st.session_state.get('buffer_distance_miles', 0.1)
                additional_data = st.session_state.get('additional_data', {})

                # Add buffer search results to each detour
                # CRITICAL: Filter additional_data by jurisdiction before buffer search
                filtered_additional_data = {}
                if st.session_state.selected_polygon_wkt:
                    from shapely.wkt import loads
                    selected_polygon = loads(st.session_state.selected_polygon_wkt)

                    for data_name, data in additional_data.items():
                        gdf = data['gdf'].copy()

                        # Ensure CRS is set
                        if gdf.crs is None:
                            gdf = gdf.set_crs('EPSG:4326')

                        # Filter by jurisdiction - use within() for points
                        geometry_types = gdf.geometry.geom_type.unique()
                        has_points = any(geom_type in ['Point', 'MultiPoint'] for geom_type in geometry_types)

                        if has_points:
                            filtered_gdf = gdf[gdf.geometry.within(selected_polygon)]
                        else:
                            filtered_gdf = gdf[gdf.geometry.intersects(selected_polygon)]

                        if not filtered_gdf.empty:
                            filtered_additional_data[data_name] = {'gdf': filtered_gdf}
                else:
                    # No jurisdiction selected, use all data
                    filtered_additional_data = additional_data

                for route_key, route_data in detours.items():
                    if route_data and 'path' in route_data:
                        path = route_data['path']
                        # Conduct buffer search for this route with filtered data
                        buffer_points = du.get_points_in_buffer(
                            G, path, filtered_additional_data, buffer_miles
                        )
                        # Store buffer points with the route
                        route_data['buffer_points'] = buffer_points

                # Store all valid detours for comprehensive analysis
                st.session_state.all_valid_detours = detours
                st.session_state.detour_results = detours
                st.success(f"✅ Found {len(detours)} detour routes!")
            else:
                st.warning("⚠️ No detours found with the current parameters. Try adjusting the search criteria.")

        except Exception as e:
            st.error(f"❌ Error finding detours: {str(e)}")
            st.stop()

# Helper function to safely get incident edge
def get_safe_incident_edge():
    if (st.session_state.selected_edge_key and
        st.session_state.selected_edge_key in edge_options_dict and
        edge_options_dict[st.session_state.selected_edge_key] is not None):
        return edge_options_dict[st.session_state.selected_edge_key]
    return None

# Comprehensive Detour Analysis Section
if st.session_state.get('all_valid_detours'):
    st.subheader(f"Detour Analysis for `{st.session_state.selected_edge_key}`")

    # Get all valid detours
    all_valid_detours = st.session_state.get('all_valid_detours', {})
    if not all_valid_detours:
        st.warning(f"No valid detours found meeting the time criteria (up to {max_detour_time} minutes).")
    else:
        st.info(f"Found {len(all_valid_detours)} valid detour(s). Evaluating and ranking routes...")

        # Rank detours by multiple criteria (travel time, distance, etc.)
        ranked_detours = []
        for (start, end), (valid, total_time, freeflow_time, path) in all_valid_detours.items():
            # Skip if path is None or invalid
            if path is None or not path:
                continue

            # Calculate additional metrics for ranking
            path_length = len(path)  # Number of nodes in path
            time_efficiency = freeflow_time / total_time if total_time > 0 else 0

            # Composite score (lower is better)
            # Weight: travel time (70%), path complexity (20%), time efficiency (10%)
            score = (total_time * 0.7) + (path_length * 0.2) + ((1 - time_efficiency) * 1000 * 0.1)

            ranked_detours.append({
                'route': (start, end),
                'data': (valid, total_time, freeflow_time, path),
                'score': score,
                'path_length': path_length,
                'time_efficiency': time_efficiency
            })

        # Sort by score (best routes first)
        ranked_detours.sort(key=lambda x: x['score'])

        # Show only the best routes (up to max_alternatives) unless user wants to see all
        if st.session_state.get('show_all_routes', False):
            best_routes = ranked_detours
            display_title = f"📊 **All {len(best_routes)} Routes** (ranked by travel time, path complexity, and efficiency)"
        else:
            # Use the user's "Max Alternative Routes" parameter
            num_routes_to_show = min(max_alternatives, len(ranked_detours))
            best_routes = ranked_detours[:num_routes_to_show]
            display_title = f"📊 **Top {len(best_routes)} Best Routes** (ranked by travel time, path complexity, and efficiency)"

        st.success(display_title)

        # Show ranking criteria and options
        col1, col2 = st.columns([3, 1])
        with col1:
            with st.expander("📈 Ranking Criteria", expanded=False):
                st.write("""
                **Routes are ranked using a composite score based on:**
                - **Travel Time (70%)**: Total time including turn penalties
                - **Path Complexity (20%)**: Number of nodes in the route (fewer is better)
                - **Time Efficiency (10%)**: Ratio of freeflow time to total time

                **Lower scores indicate better routes.**
                """)

                # Show some statistics
                all_scores = [r['score'] for r in ranked_detours]
                all_times = [r['data'][1]/60 for r in ranked_detours]  # Convert to minutes
                st.write(f"**Statistics:**")
                st.write(f"- Score range: {min(all_scores):.1f} - {max(all_scores):.1f}")
                st.write(f"- Time range: {min(all_times):.1f} - {max(all_times):.1f} minutes")
                st.write(f"- Total routes evaluated: {len(ranked_detours)}")

        with col2:
            if st.button("📋 Show All Routes", help="View all evaluated routes"):
                st.session_state.show_all_routes = not st.session_state.get('show_all_routes', False)
                st.rerun()

        # Initialize session state for detour management
        if 'detour_selections' not in st.session_state:
            st.session_state.detour_selections = {}

        # Detour management section
        st.subheader("📋 Detour Management")

        # Create columns for each detour with Accept/Reject buttons
        for i, route_info in enumerate(best_routes):
            (start, end) = route_info['route']
            (valid, total_time, freeflow_time, path) = route_info['data']
            score = route_info['score']
            path_length = route_info['path_length']
            time_efficiency = route_info['time_efficiency']

            # Show route info and buttons on the side
            col1, col2, col3, col4 = st.columns([4, 1, 1, 1])

            with col1:
                st.write(f"**Route {i+1}:** {start}→{end} ({total_time/60:.1f} min) | Score: {score:.1f} | Nodes: {path_length}")

            with col2:
                # Check current status
                current_status = st.session_state.detour_selections.get(f"route_{i}", {}).get('status', 'none')

                if current_status == 'accepted':
                    st.success("✅ Accepted")
                else:
                    if st.button("✅ Accept", key=f"accept_{i}"):
                        # Accept and update UI immediately
                        st.session_state.detour_selections[f"route_{i}"] = {
                            'status': 'accepted',
                            'route': (start, end),
                            'data': (valid, total_time, freeflow_time, path)
                        }
                        st.rerun()

            with col3:
                # Check current status
                current_status = st.session_state.detour_selections.get(f"route_{i}", {}).get('status', 'none')

                if current_status == 'rejected':
                    st.error("❌ Rejected")
                else:
                    if st.button("❌ Reject", key=f"reject_{i}"):
                        # Reject and update UI immediately
                        st.session_state.detour_selections[f"route_{i}"] = {
                            'status': 'rejected',
                            'route': (start, end),
                            'data': (valid, total_time, freeflow_time, path)
                        }
                        st.rerun()

            with col4:
                if st.button("📊 Hide", key=f"hide_{i}"):
                    st.session_state[f"hide_route_{i}"] = not st.session_state.get(f"hide_route_{i}", False)
                    st.rerun()

            # Show the map by default (unless hidden)
            if not st.session_state.get(f"hide_route_{i}", False):
                with st.expander(f"🗺️ Detour: {start}→{end} ({total_time/60:.1f} min)", expanded=True):
                    try:
                        # Create layout with route details on left and expanded map on right
                        col1, col2 = st.columns([1, 2])

                        with col1:
                            st.subheader("📋 Route Details")
                            # Extract route information for table
                            route_info = du.extract_route_info(st.session_state.graph, path)

                            # Create route IDs table
                            route_data = []
                            for i, route_id in enumerate(route_info['route_ids']):
                                route_data.append({
                                    'Segment': i + 1,
                                    'Route ID': route_id,
                                    'Highway Type': route_info['highways'][0] if route_info['highways'] else 'unknown'
                                })

                            if route_data:
                                st.dataframe(route_data, use_container_width=True)
                            else:
                                st.info("No route data available")

                        with col2:
                            # Get incident edge for plotting
                            incident_edge = edge_options_dict.get(st.session_state.selected_edge_key)

                            if not incident_edge:
                                st.error("❌ No incident edge found for plotting")
                            else:
                                # Generate the detour plot without additional data for fast preview
                                try:
                                    fig = du.plot_detour(
                                        st.session_state.graph,
                                        path,
                                        incident_edge,
                                        buffer_points=[]  # Empty buffer points for fast preview
                                    )
                                    st.pyplot(fig)
                                    plt.close(fig)
                                except Exception as e:
                                    st.error(f"❌ Error plotting detour: {str(e)}")
                                    st.write(f"Debug info - incident_edge: {incident_edge}")
                                    st.write(f"Debug info - path length: {len(path) if path else 'None'}")
                    except Exception as e:
                        st.error(f"Error plotting detour: {e}")

        # Evaluate All button
        accepted_routes = [k for k, v in st.session_state.detour_selections.items() if v['status'] == 'accepted']
        if accepted_routes:
            st.divider()
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                # Buffer search toggle above Evaluate All button
                enable_buffer_search = st.checkbox(
                    "Enable Buffer Search for Detour Analysis",
                    value=st.session_state.get('enable_buffer_search', False),
                    help="Conduct buffer search to find nearby points for each detour route. Disable for faster analysis."
                )
                st.session_state.enable_buffer_search = enable_buffer_search

                if st.button("🎯 Evaluate All Accepted Routes", key="evaluate_all", type="primary"):
                    # Prepare accepted routes for analysis only (no export)
                    st.session_state.accepted_detours = {}

                    # Get buffer search settings
                    buffer_miles = st.session_state.get('buffer_distance_miles', 0.1)
                    additional_data = st.session_state.get('additional_data', {})
                    enable_buffer_search = st.session_state.get('enable_buffer_search', False)

                    with st.spinner(f"Analyzing {len(accepted_routes)} accepted routes..."):
                        for route_key in accepted_routes:
                            route_data = st.session_state.detour_selections[route_key]

                            # Conduct buffer search if enabled and additional data exists
                            buffer_points = []
                            if enable_buffer_search and additional_data:
                                try:
                                    # Get the path from the route data - try multiple ways
                                    path = None
                                    if 'data' in route_data and len(route_data['data']) >= 4:
                                        _, _, _, path = route_data['data']
                                    elif 'path' in route_data:
                                        path = route_data['path']

                                    if path:
                                        # CRITICAL: Filter additional_data by jurisdiction before buffer search
                                        # This ensures buffer search only looks within the selected jurisdiction
                                        filtered_additional_data = {}
                                        if st.session_state.selected_polygon_wkt:
                                            from shapely.wkt import loads
                                            selected_polygon = loads(st.session_state.selected_polygon_wkt)

                                            for data_name, data in additional_data.items():
                                                gdf = data['gdf'].copy()

                                                # Ensure CRS is set
                                                if gdf.crs is None:
                                                    gdf = gdf.set_crs('EPSG:4326')

                                                # Filter by jurisdiction - use within() for points
                                                geometry_types = gdf.geometry.geom_type.unique()
                                                has_points = any(geom_type in ['Point', 'MultiPoint'] for geom_type in geometry_types)

                                                if has_points:
                                                    filtered_gdf = gdf[gdf.geometry.within(selected_polygon)]
                                                else:
                                                    filtered_gdf = gdf[gdf.geometry.intersects(selected_polygon)]

                                                if not filtered_gdf.empty:
                                                    filtered_additional_data[data_name] = {'gdf': filtered_gdf}
                                        else:
                                            # No jurisdiction selected, use all data
                                            filtered_additional_data = additional_data

                                        buffer_points = du.get_points_in_buffer(
                                            st.session_state.graph, path, filtered_additional_data, buffer_miles
                                        )
                                except Exception as e:
                                    st.warning(f"⚠️ Buffer search failed for route {route_key}: {str(e)}")
                                    buffer_points = []

                            # Add buffer search results to route data
                            route_data['buffer_points'] = buffer_points
                            route_data['buffer_miles'] = buffer_miles

                            # Ensure path is accessible both ways
                            if 'data' in route_data and len(route_data['data']) >= 4:
                                _, _, _, path = route_data['data']
                                route_data['path'] = path  # Also store as 'path' for easier access

                            st.session_state.accepted_detours[route_key] = route_data

                    # Show analysis summary
                    # CRITICAL: Deduplicate points across routes to get unique count
                    # A point can be within buffer of multiple routes, so we count it only once
                    all_buffer_points = []
                    seen_points = set()  # Track unique points by (x, y, id) tuple

                    for route in st.session_state.accepted_detours.values():
                        route_buffer_points = route.get('buffer_points', [])
                        for point in route_buffer_points:
                            # Create unique identifier for point
                            point_key = (round(point.get('x', 0), 6), round(point.get('y', 0), 6), str(point.get('id', '')))
                            if point_key not in seen_points:
                                seen_points.add(point_key)
                                all_buffer_points.append(point)

                    unique_buffer_count = len(all_buffer_points)
                    total_buffer_points = sum(len(route.get('buffer_points', [])) for route in st.session_state.accepted_detours.values())

                    if enable_buffer_search and additional_data:
                        st.success(f"✅ {len(accepted_routes)} accepted routes analyzed!")
                        st.info(f"📍 Found {unique_buffer_count} unique points within {buffer_miles} miles (total: {total_buffer_points} across all routes)")
                    else:
                        st.success(f"✅ {len(accepted_routes)} accepted routes analyzed!")
                        if not enable_buffer_search:
                            st.info("💡 Enable buffer search in Export Settings to include point analysis")

                    # Set analysis complete flag
                    st.session_state.analysis_complete = True
                    st.rerun()

# Export section - only show after analysis is complete
if (st.session_state.get('analysis_complete', False) and
    'accepted_detours' in st.session_state and
    st.session_state.accepted_detours):
    st.divider()
    st.header("📤 Export Results")

    st.write(f"**Accepted Routes:** {len(st.session_state.accepted_detours)}")

    # Show buffer search summary if available
    # CRITICAL: Deduplicate points across routes to get unique count
    all_buffer_points = []
    seen_points = set()  # Track unique points by (x, y, id) tuple

    for route in st.session_state.accepted_detours.values():
        route_buffer_points = route.get('buffer_points', [])
        for point in route_buffer_points:
            # Create unique identifier for point
            point_key = (round(point.get('x', 0), 6), round(point.get('y', 0), 6), str(point.get('id', '')))
            if point_key not in seen_points:
                seen_points.add(point_key)
                all_buffer_points.append(point)

    unique_buffer_count = len(all_buffer_points)
    total_buffer_points = sum(len(route.get('buffer_points', [])) for route in st.session_state.accepted_detours.values())

    if unique_buffer_count > 0:
        buffer_miles = list(st.session_state.accepted_detours.values())[0].get('buffer_miles', 0.1)
        st.info(f"📍 Buffer search completed: Found {unique_buffer_count} unique points within {buffer_miles} miles (total: {total_buffer_points} across all routes)")

    # Export format selection
    st.subheader("Select Export Format")
    export_format = st.selectbox(
        "Choose export format:",
        ["PDF Report", "GeoJSON", "KML", "KMZ", "Shapefile", "Excel", "CSV"],
        key="export_format_select"
    )

    # Import export utilities
    try:
        from export_utils_v1_5_6 import (
            export_to_pdf, export_to_geojson, export_to_kml,
            export_to_shapefile, export_to_excel, export_to_csv
        )

        # Export button
        if st.button(f"📄 Export {export_format}", key="export_button", type="primary"):
            incident_edge = get_safe_incident_edge()
            buffer_miles = st.session_state.get('buffer_distance_miles', 0.1)

            try:
                if export_format == "PDF Report":
                    if incident_edge:
                        with st.spinner("Generating PDF report..."):
                            pdf_data = export_to_pdf(
                                st.session_state.graph,
                                st.session_state.accepted_detours,
                                incident_edge,
                                st.session_state.get('additional_data', {}),
                                buffer_miles,
                                include_maps=True
                            )
                            if pdf_data:
                                st.download_button(
                                    label="Download PDF",
                                    data=pdf_data,
                                    file_name=f"detour_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                                    mime="application/pdf"
                                )
                                st.success("✅ PDF report generated successfully!")
                            else:
                                st.warning("No data to export")
                    else:
                        st.error("❌ No incident edge selected for PDF export")

                elif export_format == "GeoJSON":
                    with st.spinner("Generating GeoJSON..."):
                        geojson_data = export_to_geojson(
                            st.session_state.graph,
                            st.session_state.accepted_detours,
                            edge_options_dict.get(st.session_state.selected_edge_key),
                            st.session_state.get('additional_data', {}),
                            buffer_miles
                        )
                        if geojson_data:
                            st.download_button(
                                label="Download GeoJSON",
                                data=geojson_data,
                                file_name=f"detour_routes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.geojson",
                                mime="application/json"
                            )
                            st.success("✅ GeoJSON export generated successfully!")
                        else:
                            st.warning("No routes to export")

                elif export_format == "KML":
                    with st.spinner("Generating KML..."):
                        kml_data = export_to_kml(
                            st.session_state.graph,
                            st.session_state.accepted_detours,
                            edge_options_dict.get(st.session_state.selected_edge_key),
                            st.session_state.get('additional_data', {}),
                            buffer_miles
                        )
                        if kml_data:
                            st.download_button(
                                label="Download KML",
                                data=kml_data,
                                file_name=f"detour_routes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.kml",
                                mime="application/vnd.google-earth.kml+xml"
                            )
                            st.success("✅ KML export generated successfully!")
                        else:
                            st.warning("No routes to export")

                elif export_format == "KMZ":
                    with st.spinner("Generating KMZ (compressed KML)..."):
                        # Generate KML first, then compress to KMZ
                        kml_data = export_to_kml(
                            st.session_state.graph,
                            st.session_state.accepted_detours,
                            edge_options_dict.get(st.session_state.selected_edge_key),
                            st.session_state.get('additional_data', {}),
                            buffer_miles
                        )
                        if kml_data:
                            # Create KMZ (ZIP with KML inside)
                            import zipfile
                            from io import BytesIO

                            kmz_buffer = BytesIO()
                            with zipfile.ZipFile(kmz_buffer, 'w', zipfile.ZIP_DEFLATED) as kmz_file:
                                kmz_file.writestr("doc.kml", kml_data)
                            kmz_buffer.seek(0)

                            st.download_button(
                                label="Download KMZ",
                                data=kmz_buffer.getvalue(),
                                file_name=f"detour_routes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.kmz",
                                mime="application/vnd.google-earth.kmz"
                            )
                            st.success("✅ KMZ export generated successfully!")
                        else:
                            st.warning("No routes to export")

                elif export_format == "Shapefile":
                    with st.spinner("Generating Shapefile..."):
                        try:
                            shp_data = export_to_shapefile(
                                st.session_state.graph,
                                st.session_state.accepted_detours,
                                edge_options_dict.get(st.session_state.selected_edge_key),
                                st.session_state.get('additional_data', {}),
                                buffer_miles
                            )
                            if shp_data:
                                st.download_button(
                                    label="Download Shapefile",
                                    data=shp_data,
                                    file_name=f"detour_routes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                                    mime="application/zip"
                                )
                                st.success("✅ Shapefile export generated successfully!")
                            else:
                                st.warning("No routes to export")
                        except Exception as e:
                            st.error(f"Shapefile export failed: {str(e)}")

                elif export_format == "Excel":
                    with st.spinner("Generating Excel..."):
                        try:
                            excel_data = export_to_excel(
                                st.session_state.graph,
                                st.session_state.accepted_detours,
                                edge_options_dict.get(st.session_state.selected_edge_key),
                                st.session_state.get('additional_data', {}),
                                buffer_miles
                            )
                            if excel_data:
                                st.download_button(
                                    label="Download Excel",
                                    data=excel_data,
                                    file_name=f"detour_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                                )
                                st.success("✅ Excel export generated successfully!")
                            else:
                                st.warning("No routes to export")
                        except Exception as e:
                            st.error(f"Excel export failed: {str(e)}")

                elif export_format == "CSV":
                    with st.spinner("Generating CSV..."):
                        try:
                            csv_data = export_to_csv(
                                st.session_state.graph,
                                st.session_state.accepted_detours,
                                edge_options_dict.get(st.session_state.selected_edge_key),
                                st.session_state.get('additional_data', {}),
                                buffer_miles
                            )
                            if csv_data:
                                st.download_button(
                                    label="Download CSV",
                                    data=csv_data,
                                    file_name=f"detour_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                    mime="text/csv"
                                )
                                st.success("✅ CSV export generated successfully!")
                            else:
                                st.warning("No routes to export")
                        except Exception as e:
                            st.error(f"CSV export failed: {str(e)}")

            except Exception as e:
                st.error(f"Export failed: {str(e)}")

    except ImportError as e:
        st.error(f"Export utilities not available: {e}")
        st.info("Please ensure export_utils_v1_5_6.py is in the same directory.")
