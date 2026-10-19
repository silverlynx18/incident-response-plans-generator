"""
Export panel component for ARPL (Automated Route Planning & Logistics).
Handles export functionality and file downloads.
"""

import streamlit as st
from typing import Dict, List, Any, Optional
from datetime import datetime

from backend import get_arpl_api


class ExportPanel:
    """Handles export functionality and file downloads."""

    def __init__(self):
        """Initialize export panel."""
        self.api = get_arpl_api()

    def render(self):
        """Render the export panel."""
        st.header("📤 Export Results")

        # Check if results are available
        if not st.session_state.get('detour_results'):
            st.info("Complete analysis to enable export functionality")
            return

        # Display export options
        self._render_export_options()

        # Display export preview
        self._render_export_preview()

        # Display batch export options
        self._render_batch_export()

    def _render_export_options(self):
        """Render export format options."""
        st.subheader("📋 Export Formats")

        # Get available export formats
        export_formats = self.api.get_available_export_formats()

        # Create columns for format selection
        cols = st.columns(2)

        for i, format_info in enumerate(export_formats):
            with cols[i % 2]:
                with st.container():
                    st.markdown(f"**{format_info['name']}**")
                    st.caption(format_info['description'])

                    # Export button for each format
                    if st.button(f"📥 Export {format_info['name']}", key=f"export_{format_info['key']}"):
                        self._export_format(format_info['key'])

    def _render_export_preview(self):
        """Render export preview."""
        st.subheader("👁️ Export Preview")

        # Get export data summary
        detour_results = st.session_state.get('detour_results', {})
        accepted_routes = self._get_accepted_routes()

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Routes", len(detour_results))

        with col2:
            st.metric("Valid Routes", len([v for v in detour_results.values() if v[0]]))

        with col3:
            st.metric("Accepted Routes", len(accepted_routes))

        with col4:
            st.metric("Export Ready", "✅" if accepted_routes else "❌")

        # Show accepted routes
        if accepted_routes:
            st.success(f"✅ {len(accepted_routes)} routes ready for export")

            with st.expander("View Accepted Routes", expanded=False):
                for route_key, route_data in accepted_routes:
                    is_valid, travel_time, freeflow_time, path = route_data
                    st.write(f"**Route {route_key}**: {travel_time:.1f}s travel time")
        else:
            st.warning("⚠️ No routes have been accepted for export")
            st.info("Use the route gallery to accept routes before exporting")

    def _render_batch_export(self):
        """Render batch export options."""
        st.subheader("📦 Batch Export")

        # Get available formats
        export_formats = self.api.get_available_export_formats()
        format_names = [fmt['name'] for fmt in export_formats]

        # Multi-select for batch export
        selected_formats = st.multiselect(
            "Select formats for batch export:",
            format_names,
            default=[],
            key="batch_export_formats"
        )

        if selected_formats and st.button("📦 Export All Formats", key="batch_export"):
            self._batch_export(selected_formats)

    def _export_format(self, format_key: str):
        """Export in specific format."""
        try:
            with st.spinner(f"Preparing {format_key} export..."):
                export_data = self.api.export_results(format_key)

                if export_data:
                    # Generate filename
                    filename = self._generate_filename(format_key)

                    # Get format info
                    export_formats = self.api.get_available_export_formats()
                    format_info = next((fmt for fmt in export_formats if fmt['key'] == format_key), {})

                    # Create download button
                    st.download_button(
                        label=f"📥 Download {format_info.get('name', format_key)}",
                        data=export_data,
                        file_name=filename,
                        mime=format_info.get('mime_type', 'application/octet-stream'),
                        key=f"download_{format_key}_{datetime.now().timestamp()}"
                    )

                    st.success(f"✅ {format_key} export ready for download")
                else:
                    st.error(f"❌ Failed to generate {format_key} export")

        except Exception as e:
            st.error(f"Export failed: {str(e)}")

    def _batch_export(self, format_names: List[str]):
        """Export in multiple formats."""
        try:
            with st.spinner("Preparing batch export..."):
                # Get format keys
                export_formats = self.api.get_available_export_formats()
                format_keys = [
                    fmt['key'] for fmt in export_formats
                    if fmt['name'] in format_names
                ]

                # Export in all formats
                export_results = {}
                for format_key in format_keys:
                    export_data = self.api.export_results(format_key)
                    if export_data:
                        export_results[format_key] = export_data

                # Display download buttons
                if export_results:
                    st.success(f"✅ Batch export completed: {len(export_results)} formats")

                    for format_key, export_data in export_results.items():
                        format_info = next((fmt for fmt in export_formats if fmt['key'] == format_key), {})
                        filename = self._generate_filename(format_key)

                        st.download_button(
                            label=f"📥 Download {format_info.get('name', format_key)}",
                            data=export_data,
                            file_name=filename,
                            mime=format_info.get('mime_type', 'application/octet-stream'),
                            key=f"batch_download_{format_key}_{datetime.now().timestamp()}"
                        )
                else:
                    st.error("❌ Batch export failed")

        except Exception as e:
            st.error(f"Batch export failed: {str(e)}")

    def _generate_filename(self, format_key: str) -> str:
        """Generate filename for export."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        jurisdiction = st.session_state.get('selected_jurisdiction_name', 'unknown')

        # Get file extension
        export_formats = self.api.get_available_export_formats()
        format_info = next((fmt for fmt in export_formats if fmt['key'] == format_key), {})
        extension = format_info.get('extension', 'txt')

        return f"arpl_{jurisdiction}_{format_key}_{timestamp}.{extension}"

    def _get_accepted_routes(self) -> List[tuple]:
        """Get list of accepted routes."""
        detour_results = st.session_state.get('detour_results', {})
        route_evaluations = st.session_state.get('route_evaluations', {})

        accepted_routes = []
        for route_key, route_data in detour_results.items():
            if route_evaluations.get(route_key) == 'accepted':
                accepted_routes.append((route_key, route_data))

        return accepted_routes

    def get_export_statistics(self) -> Dict[str, Any]:
        """Get export statistics."""
        detour_results = st.session_state.get('detour_results', {})
        accepted_routes = self._get_accepted_routes()

        return {
            'total_routes': len(detour_results),
            'valid_routes': len([v for v in detour_results.values() if v[0]]),
            'accepted_routes': len(accepted_routes),
            'export_ready': len(accepted_routes) > 0,
            'available_formats': len(self.api.get_available_export_formats())
        }
