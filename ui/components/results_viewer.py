"""
Results viewer component for ARPL (Automated Route Planning & Logistics).
Displays analysis results and route evaluations.
"""

import streamlit as st
import pandas as pd
from typing import Dict, List, Any, Optional
from datetime import datetime

from backend import get_arpl_api


class ResultsViewer:
    """Displays analysis results and route evaluations."""

    def __init__(self):
        """Initialize results viewer."""
        self.api = get_arpl_api()

    def render(self):
        """Render the results viewer."""
        st.header("📊 Analysis Results")

        # Check if results are available
        if not st.session_state.get('detour_results'):
            st.info("Complete analysis to view results")
            return

        # Display results summary
        self._render_results_summary()

        # Display route gallery
        self._render_route_gallery()

        # Display detailed metrics
        self._render_detailed_metrics()

    def _render_results_summary(self):
        """Render results summary."""
        detour_results = st.session_state.get('detour_results', {})
        detour_analysis = st.session_state.get('detour_analysis', {})

        if not detour_results:
            return

        # Calculate summary statistics
        total_routes = len(detour_results)
        valid_routes = len([v for v in detour_results.values() if v[0]])
        invalid_routes = total_routes - valid_routes
        success_rate = (valid_routes / total_routes * 100) if total_routes > 0 else 0

        # Display summary metrics
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Routes", total_routes)

        with col2:
            st.metric("Valid Routes", valid_routes)

        with col3:
            st.metric("Invalid Routes", invalid_routes)

        with col4:
            st.metric("Success Rate", f"{success_rate:.1f}%")

        # Display analysis info
        if detour_analysis:
            col5, col6 = st.columns(2)

            with col5:
                st.metric("Generation Time", f"{detour_analysis.get('generation_time', 0):.1f}s")

            with col6:
                st.metric("Turn Nodes", len(detour_analysis.get('turn_nodes', {}).get('start_nodes', [])) +
                         len(detour_analysis.get('turn_nodes', {}).get('end_nodes', [])))

    def _render_route_gallery(self):
        """Render route gallery with navigation."""
        detour_results = st.session_state.get('detour_results', {})

        if not detour_results:
            return

        st.subheader("🛣️ Route Gallery")

        # Initialize route selection if not exists
        if 'selected_route_index' not in st.session_state:
            st.session_state.selected_route_index = 0

        # Get route list
        route_list = list(detour_results.items())
        total_routes = len(route_list)

        if total_routes == 0:
            st.info("No routes to display")
            return

        # Route navigation
        col1, col2, col3, col4, col5 = st.columns([1, 1, 2, 1, 1])

        with col1:
            if st.button("⏮️ First", key="first_route"):
                st.session_state.selected_route_index = 0
                st.rerun()

        with col2:
            if st.button("⬅️ Previous", key="prev_route"):
                if st.session_state.selected_route_index > 0:
                    st.session_state.selected_route_index -= 1
                    st.rerun()

        with col3:
            current_route = route_list[st.session_state.selected_route_index]
            route_key, (is_valid, travel_time, freeflow_time, path) = current_route

            st.write(f"**Route {st.session_state.selected_route_index + 1} of {total_routes}**")
            st.write(f"Edge: {route_key}")

        with col4:
            if st.button("➡️ Next", key="next_route"):
                if st.session_state.selected_route_index < total_routes - 1:
                    st.session_state.selected_route_index += 1
                    st.rerun()

        with col5:
            if st.button("⏭️ Last", key="last_route"):
                st.session_state.selected_route_index = total_routes - 1
                st.rerun()

        # Display current route details
        self._render_route_details(current_route)

        # Route evaluation controls
        self._render_route_evaluation(current_route)

    def _render_route_details(self, route_data: tuple):
        """Render detailed information for current route."""
        route_key, (is_valid, travel_time, freeflow_time, path) = route_data

        st.subheader("📋 Route Details")

        # Route status
        col1, col2 = st.columns(2)

        with col1:
            if is_valid:
                st.success("✅ Valid Route")
            else:
                st.error("❌ Invalid Route")

        with col2:
            if isinstance(travel_time, (int, float)):
                st.metric("Travel Time", f"{travel_time:.1f}s")
            else:
                st.write(f"**Status:** {travel_time}")

        # Route metrics
        if is_valid and isinstance(travel_time, (int, float)):
            col3, col4, col5 = st.columns(3)

            with col3:
                st.metric("Travel Time", f"{travel_time:.1f}s")

            with col4:
                if isinstance(freeflow_time, (int, float)):
                    st.metric("Freeflow Time", f"{freeflow_time:.1f}s")
                else:
                    st.metric("Freeflow Time", "N/A")

            with col5:
                if path:
                    st.metric("Route Length", f"{len(path)} nodes")
                else:
                    st.metric("Route Length", "N/A")

        # Route path information
        if path and len(path) > 0:
            st.subheader("🗺️ Route Path")

            # Display path as expandable list
            with st.expander("View Route Path", expanded=False):
                for i, node in enumerate(path):
                    st.write(f"{i+1}. Node {node}")

        # Route analysis
        if is_valid and isinstance(travel_time, (int, float)) and isinstance(freeflow_time, (int, float)):
            self._render_route_analysis(travel_time, freeflow_time, path)

    def _render_route_analysis(self, travel_time: float, freeflow_time: float, path: List):
        """Render route analysis metrics."""
        st.subheader("📈 Route Analysis")

        # Calculate metrics
        delay_time = travel_time - freeflow_time if freeflow_time > 0 else 0
        delay_percentage = (delay_time / freeflow_time * 100) if freeflow_time > 0 else 0

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Delay Time", f"{delay_time:.1f}s")

        with col2:
            st.metric("Delay Percentage", f"{delay_percentage:.1f}%")

        with col3:
            if path:
                avg_time_per_node = travel_time / len(path)
                st.metric("Avg Time/Node", f"{avg_time_per_node:.1f}s")

        # Performance assessment
        if delay_percentage < 10:
            st.success("🟢 Excellent: Minimal delay")
        elif delay_percentage < 25:
            st.info("🟡 Good: Acceptable delay")
        elif delay_percentage < 50:
            st.warning("🟠 Fair: Moderate delay")
        else:
            st.error("🔴 Poor: Significant delay")

    def _render_route_evaluation(self, route_data: tuple):
        """Render route evaluation controls."""
        route_key, (is_valid, travel_time, freeflow_time, path) = route_data

        st.subheader("⭐ Route Evaluation")

        # Initialize route evaluations if not exists
        if 'route_evaluations' not in st.session_state:
            st.session_state.route_evaluations = {}

        current_evaluation = st.session_state.route_evaluations.get(route_key, 'pending')

        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("✅ Accept Route", key="accept_route", type="primary"):
                st.session_state.route_evaluations[route_key] = 'accepted'
                st.success("Route accepted!")
                st.rerun()

        with col2:
            if st.button("❌ Reject Route", key="reject_route"):
                st.session_state.route_evaluations[route_key] = 'rejected'
                st.error("Route rejected!")
                st.rerun()

        with col3:
            if st.button("⏸️ Mark Pending", key="pending_route"):
                st.session_state.route_evaluations[route_key] = 'pending'
                st.info("Route marked as pending")
                st.rerun()

        # Display current evaluation status
        if current_evaluation == 'accepted':
            st.success(f"✅ Route {route_key} is ACCEPTED")
        elif current_evaluation == 'rejected':
            st.error(f"❌ Route {route_key} is REJECTED")
        else:
            st.info(f"⏸️ Route {route_key} is PENDING")

        # Evaluation notes
        notes_key = f"route_notes_{route_key}"
        notes = st.text_area(
            "Evaluation Notes:",
            value=st.session_state.get(notes_key, ""),
            key=notes_key,
            placeholder="Add notes about this route..."
        )

        if notes:
            st.session_state[notes_key] = notes

    def _render_detailed_metrics(self):
        """Render detailed analysis metrics."""
        detour_results = st.session_state.get('detour_results', {})

        if not detour_results:
            return

        st.subheader("📊 Detailed Metrics")

        # Create metrics table
        metrics_data = []

        for route_key, (is_valid, travel_time, freeflow_time, path) in detour_results.items():
            metrics_data.append({
                'Route': str(route_key),
                'Status': 'Valid' if is_valid else 'Invalid',
                'Travel Time (s)': f"{travel_time:.1f}" if isinstance(travel_time, (int, float)) else str(travel_time),
                'Freeflow Time (s)': f"{freeflow_time:.1f}" if isinstance(freeflow_time, (int, float)) else "N/A",
                'Route Length': len(path) if path else 0,
                'Evaluation': st.session_state.get('route_evaluations', {}).get(route_key, 'Pending')
            })

        if metrics_data:
            df = pd.DataFrame(metrics_data)
            st.dataframe(df, use_container_width=True)

            # Summary statistics
            valid_routes = [r for r in detour_results.values() if r[0]]
            if valid_routes:
                travel_times = [r[1] for r in valid_routes if isinstance(r[1], (int, float))]

                if travel_times:
                    col1, col2, col3, col4 = st.columns(4)

                    with col1:
                        st.metric("Avg Travel Time", f"{sum(travel_times) / len(travel_times):.1f}s")

                    with col2:
                        st.metric("Min Travel Time", f"{min(travel_times):.1f}s")

                    with col3:
                        st.metric("Max Travel Time", f"{max(travel_times):.1f}s")

                    with col4:
                        st.metric("Std Deviation", f"{pd.Series(travel_times).std():.1f}s")

    def get_accepted_routes(self) -> List[tuple]:
        """Get list of accepted routes."""
        detour_results = st.session_state.get('detour_results', {})
        route_evaluations = st.session_state.get('route_evaluations', {})

        accepted_routes = []
        for route_key, route_data in detour_results.items():
            if route_evaluations.get(route_key) == 'accepted':
                accepted_routes.append((route_key, route_data))

        return accepted_routes

    def get_evaluation_summary(self) -> Dict[str, int]:
        """Get evaluation summary."""
        route_evaluations = st.session_state.get('route_evaluations', {})

        summary = {
            'accepted': 0,
            'rejected': 0,
            'pending': 0
        }

        for evaluation in route_evaluations.values():
            if evaluation in summary:
                summary[evaluation] += 1

        # Count pending routes (not yet evaluated)
        detour_results = st.session_state.get('detour_results', {})
        total_routes = len(detour_results)
        evaluated_routes = len(route_evaluations)
        summary['pending'] += (total_routes - evaluated_routes)

        return summary
