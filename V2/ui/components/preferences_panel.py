"""
Preferences panel component for ARPL (Automated Route Planning & Logistics).
Handles user preferences and settings management.
"""

import streamlit as st
from typing import Dict, List, Any, Optional
from datetime import datetime

from backend import get_arpl_api


class PreferencesPanel:
    """Handles user preferences and settings management."""

    def __init__(self):
        """Initialize preferences panel."""
        self.api = get_arpl_api()

    def render(self):
        """Render the preferences panel."""
        st.header("⚙️ User Preferences")

        # Analysis preferences
        self._render_analysis_preferences()

        # UI preferences
        self._render_ui_preferences()

        # Performance preferences
        self._render_performance_preferences()

        # Export preferences
        self._render_export_preferences()

        # Preset management
        self._render_preset_management()

    def _render_analysis_preferences(self):
        """Render analysis preferences."""
        st.subheader("🔬 Analysis Preferences")

        col1, col2 = st.columns(2)

        with col1:
            # Default turn nodes
            default_turn_nodes = st.slider(
                "Default Turn Nodes",
                min_value=1,
                max_value=20,
                value=self.api.get_user_preference('default_turn_nodes', 5),
                key="pref_turn_nodes"
            )
            self.api.set_user_preference('default_turn_nodes', default_turn_nodes)

            # Default sector angle
            default_sector_angle = st.slider(
                "Default Sector Angle (degrees)",
                min_value=30,
                max_value=360,
                value=self.api.get_user_preference('default_sector_angle', 180),
                key="pref_sector_angle"
            )
            self.api.set_user_preference('default_sector_angle', default_sector_angle)

            # Default sector radius
            default_sector_radius = st.slider(
                "Default Sector Radius (meters)",
                min_value=500,
                max_value=10000,
                value=self.api.get_user_preference('default_sector_radius', 3000),
                key="pref_sector_radius"
            )
            self.api.set_user_preference('default_sector_radius', default_sector_radius)

        with col2:
            # Default travel time constraints
            default_min_travel_time = st.slider(
                "Default Min Travel Time (seconds)",
                min_value=30,
                max_value=600,
                value=self.api.get_user_preference('default_min_travel_time', 90),
                key="pref_min_travel_time"
            )
            self.api.set_user_preference('default_min_travel_time', default_min_travel_time)

            default_max_travel_time = st.slider(
                "Default Max Travel Time (seconds)",
                min_value=300,
                max_value=7200,
                value=self.api.get_user_preference('default_max_travel_time', 1800),
                key="pref_max_travel_time"
            )
            self.api.set_user_preference('default_max_travel_time', default_max_travel_time)

            # Default max detour routes
            default_max_routes = st.slider(
                "Default Max Detour Routes",
                min_value=1,
                max_value=50,
                value=self.api.get_user_preference('default_max_routes', 10),
                key="pref_max_routes"
            )
            self.api.set_user_preference('default_max_routes', default_max_routes)

    def _render_ui_preferences(self):
        """Render UI preferences."""
        st.subheader("🎨 UI Preferences")

        col1, col2 = st.columns(2)

        with col1:
            # Map preferences
            default_map_style = st.selectbox(
                "Default Map Style",
                ["OpenStreetMap", "CartoDB Positron", "CartoDB Dark_Matter"],
                index=["OpenStreetMap", "CartoDB Positron", "CartoDB Dark_Matter"].index(
                    self.api.get_user_preference('default_map_style', 'OpenStreetMap')
                ),
                key="pref_map_style"
            )
            self.api.set_user_preference('default_map_style', default_map_style)

            # Show debug info
            show_debug = st.checkbox(
                "Show Debug Information",
                value=self.api.get_user_preference('show_debug_info', False),
                key="pref_show_debug"
            )
            self.api.set_user_preference('show_debug_info', show_debug)

            # Auto-save sessions
            auto_save = st.checkbox(
                "Auto-save Sessions",
                value=self.api.get_user_preference('auto_save_sessions', True),
                key="pref_auto_save"
            )
            self.api.set_user_preference('auto_save_sessions', auto_save)

        with col2:
            # Results display
            results_per_page = st.slider(
                "Results Per Page",
                min_value=5,
                max_value=50,
                value=self.api.get_user_preference('results_per_page', 10),
                key="pref_results_per_page"
            )
            self.api.set_user_preference('results_per_page', results_per_page)

            # Show route details
            show_route_details = st.checkbox(
                "Show Detailed Route Information",
                value=self.api.get_user_preference('show_route_details', True),
                key="pref_show_route_details"
            )
            self.api.set_user_preference('show_route_details', show_route_details)

            # Show map controls
            show_map_controls = st.checkbox(
                "Show Map Controls",
                value=self.api.get_user_preference('show_map_controls', True),
                key="pref_show_map_controls"
            )
            self.api.set_user_preference('show_map_controls', show_map_controls)

    def _render_performance_preferences(self):
        """Render performance preferences."""
        st.subheader("⚡ Performance Preferences")

        col1, col2 = st.columns(2)

        with col1:
            # Cache preferences
            cache_networks = st.checkbox(
                "Cache Networks",
                value=self.api.get_user_preference('cache_networks', True),
                key="pref_cache_networks"
            )
            self.api.set_user_preference('cache_networks', cache_networks)

            # Cache expiration
            cache_expiration = st.slider(
                "Cache Expiration (days)",
                min_value=1,
                max_value=365,
                value=self.api.get_user_preference('cache_expiration_days', 30),
                key="pref_cache_expiration"
            )
            self.api.set_user_preference('cache_expiration_days', cache_expiration)

            # Max cache size
            max_cache_size = st.slider(
                "Max Cache Size (MB)",
                min_value=100,
                max_value=10000,
                value=self.api.get_user_preference('max_cache_size_mb', 1000),
                key="pref_max_cache_size"
            )
            self.api.set_user_preference('max_cache_size_mb', max_cache_size)

        with col2:
            # Performance mode
            default_performance_mode = st.selectbox(
                "Default Performance Mode",
                ["Fast", "Balanced", "Complete"],
                index=["Fast", "Balanced", "Complete"].index(
                    self.api.get_user_preference('default_performance_mode', 'Balanced')
                ),
                key="pref_performance_mode"
            )
            self.api.set_user_preference('default_performance_mode', default_performance_mode)

            # Parallel processing
            parallel_processing = st.checkbox(
                "Enable Parallel Processing",
                value=self.api.get_user_preference('parallel_processing', True),
                key="pref_parallel_processing"
            )
            self.api.set_user_preference('parallel_processing', parallel_processing)

            # Memory optimization
            memory_optimization = st.checkbox(
                "Enable Memory Optimization",
                value=self.api.get_user_preference('memory_optimization', True),
                key="pref_memory_optimization"
            )
            self.api.set_user_preference('memory_optimization', memory_optimization)

    def _render_export_preferences(self):
        """Render export preferences."""
        st.subheader("📤 Export Preferences")

        col1, col2 = st.columns(2)

        with col1:
            # Default export format
            default_export_format = st.selectbox(
                "Default Export Format",
                ["PDF Report", "GeoJSON", "KML", "Shapefile", "GeoPackage", "Excel", "CSV"],
                index=["PDF Report", "GeoJSON", "KML", "Shapefile", "GeoPackage", "Excel", "CSV"].index(
                    self.api.get_user_preference('default_export_format', 'PDF Report')
                ),
                key="pref_export_format"
            )
            self.api.set_user_preference('default_export_format', default_export_format)

            # Include metadata
            include_metadata = st.checkbox(
                "Include Metadata in Exports",
                value=self.api.get_user_preference('include_metadata', True),
                key="pref_include_metadata"
            )
            self.api.set_user_preference('include_metadata', include_metadata)

            # Include charts
            include_charts = st.checkbox(
                "Include Charts in PDF Reports",
                value=self.api.get_user_preference('include_charts', True),
                key="pref_include_charts"
            )
            self.api.set_user_preference('include_charts', include_charts)

        with col2:
            # Export quality
            export_quality = st.selectbox(
                "Export Quality",
                ["Low", "Medium", "High"],
                index=["Low", "Medium", "High"].index(
                    self.api.get_user_preference('export_quality', 'Medium')
                ),
                key="pref_export_quality"
            )
            self.api.set_user_preference('export_quality', export_quality)

            # Auto-download
            auto_download = st.checkbox(
                "Auto-download Exports",
                value=self.api.get_user_preference('auto_download_exports', False),
                key="pref_auto_download"
            )
            self.api.set_user_preference('auto_download_exports', auto_download)

            # Export history
            keep_export_history = st.checkbox(
                "Keep Export History",
                value=self.api.get_user_preference('keep_export_history', True),
                key="pref_export_history"
            )
            self.api.set_user_preference('keep_export_history', keep_export_history)

    def _render_preset_management(self):
        """Render preset management."""
        st.subheader("🎯 Preset Management")

        # Get available presets
        presets = self.api.get_analysis_presets()

        if presets:
            st.markdown("**Available Presets:**")
            for preset_name, preset_data in presets.items():
                with st.expander(f"Preset: {preset_name}", expanded=False):
                    st.json(preset_data)

                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button(f"Apply {preset_name}", key=f"apply_preset_{preset_name}"):
                            self.api.apply_analysis_preset(preset_name)
                            st.success(f"Applied preset: {preset_name}")
                            st.rerun()

                    with col2:
                        if st.button(f"Edit {preset_name}", key=f"edit_preset_{preset_name}"):
                            st.info("Preset editing would be implemented here")

        # Create custom preset
        st.markdown("**Create Custom Preset:**")
        preset_name = st.text_input("Preset Name:", key="custom_preset_name")

        if preset_name and st.button("Create Preset", key="create_preset"):
            # Create preset from current settings
            preset_data = {
                'n_turn_nodes': st.session_state.get('n_turn_nodes', 5),
                'sector_angle_deg': st.session_state.get('sector_angle_deg', 180),
                'sector_radius_m': st.session_state.get('sector_radius_m', 3000),
                'min_travel_time_s': st.session_state.get('min_travel_time_s', 90),
                'max_travel_time_s': st.session_state.get('max_travel_time_s', 1800),
                'max_detour_routes': st.session_state.get('max_detour_routes', 10),
                'performance_mode': st.session_state.get('performance_mode', 'Balanced')
            }

            # Save preset (would implement in backend)
            st.success(f"Custom preset '{preset_name}' created")

    def get_preferences_summary(self) -> Dict[str, Any]:
        """Get preferences summary."""
        return {
            'analysis_preferences': {
                'default_turn_nodes': self.api.get_user_preference('default_turn_nodes', 5),
                'default_sector_angle': self.api.get_user_preference('default_sector_angle', 180),
                'default_sector_radius': self.api.get_user_preference('default_sector_radius', 3000),
                'default_performance_mode': self.api.get_user_preference('default_performance_mode', 'Balanced')
            },
            'ui_preferences': {
                'default_map_style': self.api.get_user_preference('default_map_style', 'OpenStreetMap'),
                'show_debug_info': self.api.get_user_preference('show_debug_info', False),
                'auto_save_sessions': self.api.get_user_preference('auto_save_sessions', True)
            },
            'performance_preferences': {
                'cache_networks': self.api.get_user_preference('cache_networks', True),
                'cache_expiration_days': self.api.get_user_preference('cache_expiration_days', 30),
                'parallel_processing': self.api.get_user_preference('parallel_processing', True)
            },
            'export_preferences': {
                'default_export_format': self.api.get_user_preference('default_export_format', 'PDF Report'),
                'include_metadata': self.api.get_user_preference('include_metadata', True),
                'export_quality': self.api.get_user_preference('export_quality', 'Medium')
            }
        }
