"""
Sidebar component for ARPL (Automated Route Planning & Logistics).
Manages the sidebar UI and user interactions.
"""

import streamlit as st
from typing import Dict, List, Any, Optional
from datetime import datetime

from backend import get_arpl_api


class SidebarManager:
    """Manages the sidebar UI and user interactions."""

    def __init__(self):
        """Initialize sidebar manager."""
        self.api = get_arpl_api()

    def render(self):
        """Render the complete sidebar."""
        with st.sidebar:
            st.title("🚧 ARPL v2.0")
            st.markdown("---")

            # Data Status Section
            self._render_data_status()

            # Jurisdiction Selection Section
            self._render_jurisdiction_selection()

            # Analysis Parameters Section
            self._render_analysis_parameters()

            # Actions Section
            self._render_actions()

            # Session Management Section
            self._render_session_management()

            # Export Section
            self._render_export_section()

            # Debug Information Section
            self._render_debug_info()

    def _render_data_status(self):
        """Render data status section."""
        st.header("📊 Data Status")

        # Check data availability
        data_stats = self.api.get_data_statistics()

        col1, col2 = st.columns(2)
        with col1:
            st.metric("TIGER Data", data_stats.get('tiger_data', {}).get('total_files', 0))
        with col2:
            st.metric("Custom Data", data_stats.get('custom_data', {}).get('total_files', 0))

        # Show warnings if needed
        if data_stats.get('tiger_data', {}).get('total_files', 0) == 0:
            st.warning("No TIGER data available. Download data to begin analysis.")

    def _render_jurisdiction_selection(self):
        """Render jurisdiction selection section."""
        st.header("🗺️ Jurisdiction Selection")

        # State selection
        states = self.api.get_available_jurisdictions('STATE')
        state_names = [state['name'] for state in states]

        selected_state = st.selectbox(
            "Select State:",
            [""] + state_names,
            key="state_selection"
        )

        if selected_state:
            st.session_state.selected_state_name = selected_state

            # Jurisdiction type selection
            jurisdiction_type = st.selectbox(
                "Jurisdiction Type:",
                ["County", "Urban Area", "MPO"],
                key="jurisdiction_type_selection"
            )

            # Map jurisdiction type to dataset
            dataset_map = {
                "County": "COUNTY",
                "Urban Area": "UAC20",
                "MPO": "MPO"
            }

            dataset = dataset_map.get(jurisdiction_type, "COUNTY")

            # Get jurisdictions for selected state
            jurisdictions = self.api.get_available_jurisdictions(dataset)
            state_jurisdictions = [
                j for j in jurisdictions
                if j.get('state', '').lower() == selected_state.lower()
            ]

            if state_jurisdictions:
                jurisdiction_names = [j['name'] for j in state_jurisdictions]

                selected_jurisdiction = st.selectbox(
                    f"Select {jurisdiction_type}:",
                    [""] + jurisdiction_names,
                    key="jurisdiction_selection"
                )

                if selected_jurisdiction:
                    st.session_state.selected_jurisdiction_name = selected_jurisdiction
                    st.session_state.selected_jurisdiction_type = jurisdiction_type.lower()

                    # Show jurisdiction info
                    jurisdiction_info = next(
                        (j for j in state_jurisdictions if j['name'] == selected_jurisdiction),
                        None
                    )

                    if jurisdiction_info:
                        st.info(f"Area: {jurisdiction_info.get('area_sq_km', 0):.1f} km²")
            else:
                st.warning(f"No {jurisdiction_type} data available for {selected_state}")

    def _render_analysis_parameters(self):
        """Render analysis parameters section."""
        st.header("⚙️ Analysis Parameters")

        # Performance mode
        performance_mode = st.selectbox(
            "Performance Mode:",
            ["Fast", "Balanced", "Complete"],
            index=1,
            key="performance_mode"
        )
        st.session_state.performance_mode = performance_mode

        # Analysis presets
        presets = self.api.get_analysis_presets()
        preset_names = list(presets.keys())

        selected_preset = st.selectbox(
            "Analysis Preset:",
            [""] + preset_names,
            key="analysis_preset"
        )

        if selected_preset:
            if st.button("Apply Preset", key="apply_preset"):
                self.api.apply_analysis_preset(selected_preset)
                st.rerun()

        # Custom parameters
        with st.expander("Custom Parameters", expanded=False):
            col1, col2 = st.columns(2)

            with col1:
                n_turn_nodes = st.slider(
                    "Turn Nodes",
                    min_value=1,
                    max_value=20,
                    value=st.session_state.get('n_turn_nodes', 5),
                    key="n_turn_nodes"
                )
                st.session_state.n_turn_nodes = n_turn_nodes

                sector_angle = st.slider(
                    "Sector Angle (degrees)",
                    min_value=30,
                    max_value=360,
                    value=st.session_state.get('sector_angle_deg', 180),
                    key="sector_angle_deg"
                )
                st.session_state.sector_angle_deg = sector_angle

                sector_radius = st.slider(
                    "Sector Radius (meters)",
                    min_value=500,
                    max_value=10000,
                    value=st.session_state.get('sector_radius_m', 3000),
                    key="sector_radius_m"
                )
                st.session_state.sector_radius_m = sector_radius

            with col2:
                min_travel_time = st.slider(
                    "Min Travel Time (seconds)",
                    min_value=30,
                    max_value=600,
                    value=st.session_state.get('min_travel_time_s', 90),
                    key="min_travel_time_s"
                )
                st.session_state.min_travel_time_s = min_travel_time

                max_travel_time = st.slider(
                    "Max Travel Time (seconds)",
                    min_value=300,
                    max_value=7200,
                    value=st.session_state.get('max_travel_time_s', 1800),
                    key="max_travel_time_s"
                )
                st.session_state.max_travel_time_s = max_travel_time

                max_detour_routes = st.slider(
                    "Max Detour Routes",
                    min_value=1,
                    max_value=50,
                    value=st.session_state.get('max_detour_routes', 10),
                    key="max_detour_routes"
                )
                st.session_state.max_detour_routes = max_detour_routes

    def _render_actions(self):
        """Render actions section."""
        st.header("🎯 Actions")

        # Prepare network button
        if st.button("🌐 Prepare Network", key="prepare_network", type="primary"):
            if self._validate_jurisdiction_selection():
                self._prepare_network()
            else:
                st.error("Please select a jurisdiction first")

        # Find detours button
        if st.button("🔍 Find Detours", key="find_detours", type="primary"):
            if self._validate_analysis_ready():
                self._find_detours()
            else:
                st.error("Please prepare network and select incident first")

        # Reset button
        if st.button("🔄 Reset All", key="reset_all"):
            self._reset_session()

    def _render_session_management(self):
        """Render session management section."""
        st.header("💾 Session Management")

        # Save session
        with st.expander("💾 Save Current Session", expanded=False):
            session_name = st.text_input(
                "Session Name:",
                placeholder="e.g., Highway 101 Analysis",
                key="save_session_name"
            )

            if st.button("💾 Save Session", key="save_session_btn"):
                if session_name:
                    session_id = self.api.save_analysis_session(session_name, st.session_state)
                    if session_id:
                        st.success(f"Session saved with ID: {session_id}")
                    else:
                        st.error("Failed to save session")
                else:
                    st.error("Please enter a session name")

        # Load session
        with st.expander("📂 Load Saved Session", expanded=False):
            sessions = self.api.list_analysis_sessions(limit=20)

            if sessions:
                session_options = {
                    f"{s['session_name']} ({s['created_at'][:10]})": s['id']
                    for s in sessions
                }

                selected_session = st.selectbox(
                    "Select Session:",
                    [""] + list(session_options.keys()),
                    key="load_session_select"
                )

                if selected_session and st.button("📂 Load Session", key="load_session_btn"):
                    session_id = session_options[selected_session]
                    if self.api.load_analysis_session(session_id):
                        st.success("Session loaded successfully")
                        st.rerun()
                    else:
                        st.error("Failed to load session")
            else:
                st.info("No saved sessions available")

    def _render_export_section(self):
        """Render export section."""
        st.header("📤 Export Results")

        if st.session_state.get('detour_results'):
            export_formats = self.api.get_available_export_formats()
            format_names = [fmt['name'] for fmt in export_formats]

            selected_format = st.selectbox(
                "Export Format:",
                format_names,
                key="export_format_select"
            )

            if st.button("📥 Download Export", key="download_export"):
                if selected_format:
                    format_key = next(
                        fmt['key'] for fmt in export_formats
                        if fmt['name'] == selected_format
                    )

                    export_data = self.api.export_results(format_key)
                    if export_data:
                        filename = f"arpl_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format_key}"
                        st.download_button(
                            label=f"📥 Download {selected_format}",
                            data=export_data,
                            file_name=filename,
                            mime="application/octet-stream"
                        )
                    else:
                        st.error("Export failed")
        else:
            st.info("Complete analysis to enable export")

    def _render_debug_info(self):
        """Render debug information section."""
        with st.expander("🔍 Debug Information", expanded=False):
            # System info
            system_info = self.api.get_system_info()

            st.subheader("System Status")
            st.json({
                'database_health': system_info.get('database_health', {}).get('status', 'unknown'),
                'data_sources': len(system_info.get('data_statistics', {})),
                'export_formats': len(system_info.get('available_export_formats', [])),
                'system_time': system_info.get('system_time', 'unknown')
            })

            # Session state info
            st.subheader("Session State")
            session_keys = list(st.session_state.keys())
            st.write(f"Keys: {len(session_keys)}")

            if st.checkbox("Show Session State", key="show_session_state"):
                st.json({k: str(v)[:100] + "..." if len(str(v)) > 100 else v
                        for k, v in st.session_state.items()})

    def _validate_jurisdiction_selection(self) -> bool:
        """Validate jurisdiction selection."""
        return (
            st.session_state.get('selected_jurisdiction_name') and
            st.session_state.get('selected_jurisdiction_type') and
            st.session_state.get('selected_state_name')
        )

    def _validate_analysis_ready(self) -> bool:
        """Validate that analysis is ready to run."""
        return (
            self._validate_jurisdiction_selection() and
            st.session_state.get('graph') is not None and
            st.session_state.get('selected_incident_edge') is not None
        )

    def _prepare_network(self):
        """Prepare network for analysis."""
        try:
            with st.spinner("Preparing network..."):
                network_info = self.api.prepare_network(
                    st.session_state.selected_jurisdiction_name,
                    st.session_state.selected_jurisdiction_type,
                    st.session_state.selected_state_name
                )

                if network_info:
                    st.session_state.graph = network_info['graph']
                    st.session_state.network_info = network_info
                    st.success(f"Network prepared: {network_info['node_count']} nodes, {network_info['edge_count']} edges")
                else:
                    st.error("Failed to prepare network")
        except Exception as e:
            st.error(f"Network preparation failed: {str(e)}")

    def _find_detours(self):
        """Find detour routes."""
        try:
            with st.spinner("Calculating detours..."):
                analysis_params = {
                    'n_turn_nodes': st.session_state.get('n_turn_nodes', 5),
                    'sector_angle_deg': st.session_state.get('sector_angle_deg', 180),
                    'sector_radius_m': st.session_state.get('sector_radius_m', 3000),
                    'min_travel_time_s': st.session_state.get('min_travel_time_s', 90),
                    'max_travel_time_s': st.session_state.get('max_travel_time_s', 1800),
                    'max_detour_routes': st.session_state.get('max_detour_routes', 10),
                    'performance_mode': st.session_state.get('performance_mode', 'Balanced')
                }

                results = self.api.calculate_detours(
                    st.session_state.graph,
                    st.session_state.selected_incident_edge,
                    analysis_params
                )

                if results.get('success'):
                    st.session_state.detour_results = results['detour_results']
                    st.session_state.detour_analysis = results
                    st.success(f"Found {results['valid_detours']} valid detours out of {results['total_detours']} total")
                else:
                    st.error(f"Detour calculation failed: {results.get('error', 'Unknown error')}")
        except Exception as e:
            st.error(f"Detour calculation failed: {str(e)}")

    def _reset_session(self):
        """Reset session state."""
        # Clear session state
        for key in list(st.session_state.keys()):
            if key not in ['arpl_api']:  # Keep API instance
                del st.session_state[key]

        st.success("Session reset successfully")
        st.rerun()
