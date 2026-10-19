"""
Session panel component for ARPL (Automated Route Planning & Logistics).
Handles session management and analysis history.
"""

import streamlit as st
from typing import Dict, List, Any, Optional
from datetime import datetime

from backend import get_arpl_api


class SessionPanel:
    """Handles session management and analysis history."""

    def __init__(self):
        """Initialize session panel."""
        self.api = get_arpl_api()

    def render(self):
        """Render the session panel."""
        st.header("💾 Session Management")

        # Session controls
        self._render_session_controls()

        # Analysis history
        self._render_analysis_history()

        # Session statistics
        self._render_session_statistics()

    def _render_session_controls(self):
        """Render session control options."""
        st.subheader("🎛️ Session Controls")

        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("💾 Save Current Session", key="save_current_session", type="primary"):
                self._save_current_session()

        with col2:
            if st.button("📂 Load Session", key="load_session"):
                self._show_load_session_dialog()

        with col3:
            if st.button("🔄 Reset Session", key="reset_session"):
                self._reset_session()

        # Quick save with name
        st.markdown("---")
        session_name = st.text_input(
            "Quick Save Session:",
            placeholder="Enter session name...",
            key="quick_save_name"
        )

        if st.button("💾 Quick Save", key="quick_save") and session_name:
            self._save_session_with_name(session_name)

    def _render_analysis_history(self):
        """Render analysis history."""
        st.subheader("📊 Analysis History")

        # Get analysis history
        history = self.api.get_analysis_history(limit=10)

        if history:
            # Display history table
            for entry in history:
                with st.expander(f"Analysis {entry.get('id', 'Unknown')} - {entry.get('created_at', 'Unknown')[:10]}", expanded=False):
                    col1, col2 = st.columns(2)

                    with col1:
                        st.write(f"**Jurisdiction:** {entry.get('jurisdiction_name', 'Unknown')}")
                        st.write(f"**Type:** {entry.get('jurisdiction_type', 'Unknown')}")
                        st.write(f"**State:** {entry.get('state_name', 'Unknown')}")

                    with col2:
                        st.write(f"**Routes Found:** {entry.get('total_routes', 0)}")
                        st.write(f"**Valid Routes:** {entry.get('valid_routes', 0)}")
                        st.write(f"**Success Rate:** {entry.get('success_rate', 0):.1f}%")

                    # Load session button
                    if st.button(f"📂 Load Session {entry.get('id')}", key=f"load_history_{entry.get('id')}"):
                        self._load_session_by_id(entry.get('id'))
        else:
            st.info("No analysis history available")

    def _render_session_statistics(self):
        """Render session statistics."""
        st.subheader("📈 Session Statistics")

        # Get session statistics
        sessions = self.api.list_analysis_sessions(limit=100)

        if sessions:
            # Calculate statistics
            total_sessions = len(sessions)
            total_routes = sum(s.get('total_routes', 0) for s in sessions)
            total_valid_routes = sum(s.get('valid_routes', 0) for s in sessions)
            avg_success_rate = (total_valid_routes / total_routes * 100) if total_routes > 0 else 0

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("Total Sessions", total_sessions)

            with col2:
                st.metric("Total Routes", total_routes)

            with col3:
                st.metric("Valid Routes", total_valid_routes)

            with col4:
                st.metric("Avg Success Rate", f"{avg_success_rate:.1f}%")

            # Recent sessions
            st.markdown("**Recent Sessions:**")
            for session in sessions[:5]:
                st.write(f"• {session.get('session_name', 'Unnamed')} - {session.get('created_at', 'Unknown')[:10]}")
        else:
            st.info("No session statistics available")

    def _save_current_session(self):
        """Save current session."""
        try:
            # Generate session name
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            jurisdiction = st.session_state.get('selected_jurisdiction_name', 'unknown')
            session_name = f"{jurisdiction}_{timestamp}"

            # Save session
            session_id = self.api.save_analysis_session(session_name, st.session_state)

            if session_id:
                st.success(f"✅ Session saved with ID: {session_id}")
            else:
                st.error("❌ Failed to save session")

        except Exception as e:
            st.error(f"Save failed: {str(e)}")

    def _save_session_with_name(self, session_name: str):
        """Save session with custom name."""
        try:
            session_id = self.api.save_analysis_session(session_name, st.session_state)

            if session_id:
                st.success(f"✅ Session '{session_name}' saved with ID: {session_id}")
            else:
                st.error("❌ Failed to save session")

        except Exception as e:
            st.error(f"Save failed: {str(e)}")

    def _show_load_session_dialog(self):
        """Show load session dialog."""
        st.subheader("📂 Load Session")

        # Get available sessions
        sessions = self.api.list_analysis_sessions(limit=20)

        if sessions:
            # Create session options
            session_options = {
                f"{s['session_name']} ({s['created_at'][:10]})": s['id']
                for s in sessions
            }

            selected_session = st.selectbox(
                "Select Session:",
                [""] + list(session_options.keys()),
                key="load_session_select"
            )

            if selected_session and st.button("📂 Load Selected Session", key="load_selected_session"):
                session_id = session_options[selected_session]
                self._load_session_by_id(session_id)
        else:
            st.info("No saved sessions available")

    def _load_session_by_id(self, session_id: int):
        """Load session by ID."""
        try:
            session_data = self.api.load_analysis_session(session_id)

            if session_data:
                # Restore session state
                for key, value in session_data.items():
                    if key not in ['id', 'created_at', 'updated_at']:
                        st.session_state[key] = value

                st.success("✅ Session loaded successfully")
                st.rerun()
            else:
                st.error("❌ Failed to load session")

        except Exception as e:
            st.error(f"Load failed: {str(e)}")

    def _reset_session(self):
        """Reset current session."""
        if st.button("🔄 Confirm Reset", key="confirm_reset"):
            # Clear session state
            for key in list(st.session_state.keys()):
                if key not in ['arpl_api']:  # Keep API instance
                    del st.session_state[key]

            st.success("✅ Session reset successfully")
            st.rerun()

    def get_session_info(self) -> Dict[str, Any]:
        """Get current session information."""
        return {
            'has_jurisdiction': bool(st.session_state.get('selected_jurisdiction_name')),
            'has_network': bool(st.session_state.get('graph')),
            'has_incident': bool(st.session_state.get('selected_incident_edge')),
            'has_results': bool(st.session_state.get('detour_results')),
            'accepted_routes': len(self._get_accepted_routes()),
            'session_size': len(st.session_state)
        }

    def _get_accepted_routes(self) -> List[tuple]:
        """Get list of accepted routes."""
        detour_results = st.session_state.get('detour_results', {})
        route_evaluations = st.session_state.get('route_evaluations', {})

        accepted_routes = []
        for route_key, route_data in detour_results.items():
            if route_evaluations.get(route_key) == 'accepted':
                accepted_routes.append((route_key, route_data))

        return accepted_routes
