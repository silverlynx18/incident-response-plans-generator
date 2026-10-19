"""
Session management utilities for ARPL (Automated Route Planning & Logistics).
Handles saving, loading, and managing analysis sessions.
"""

import os
import json
import pickle
import tempfile
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
import streamlit as st
import networkx as nx
from shapely.wkt import dumps, loads


class SessionManager:
    """Manages analysis session persistence and retrieval."""

    def __init__(self, sessions_dir: str = "saved_sessions"):
        """
        Initialize session manager.

        Args:
            sessions_dir: Directory to store session files
        """
        self.sessions_dir = sessions_dir
        self._ensure_sessions_dir()

    def _ensure_sessions_dir(self):
        """Create sessions directory if it doesn't exist."""
        if not os.path.exists(self.sessions_dir):
            os.makedirs(self.sessions_dir)

    def save_session(self, session_name: str, session_state: Dict[str, Any]) -> bool:
        """
        Save current analysis session to disk.

        Args:
            session_name: Name for the session
            session_state: Streamlit session state dictionary

        Returns:
            True if successful, False otherwise
        """
        try:
            # Create session data structure
            session_data = {
                'metadata': {
                    'name': session_name,
                    'created_at': datetime.now().isoformat(),
                    'app_version': 'ARPL v2.0',
                    'description': self._generate_session_description(session_state)
                },
                'analysis_data': self._extract_analysis_data(session_state),
                'ui_state': self._extract_ui_state(session_state)
            }

            # Save to JSON file
            session_file = os.path.join(self.sessions_dir, f"{session_name}.json")
            with open(session_file, 'w') as f:
                json.dump(session_data, f, indent=2, default=self._json_serializer)

            # Save graph separately as pickle (if exists)
            if session_state.get('graph'):
                graph_file = os.path.join(self.sessions_dir, f"{session_name}_graph.pkl")
                with open(graph_file, 'wb') as f:
                    pickle.dump(session_state['graph'], f)

            return True

        except Exception as e:
            st.error(f"Failed to save session: {str(e)}")
            return False

    def load_session(self, session_name: str) -> Optional[Dict[str, Any]]:
        """
        Load analysis session from disk.

        Args:
            session_name: Name of the session to load

        Returns:
            Session data dictionary or None if failed
        """
        try:
            session_file = os.path.join(self.sessions_dir, f"{session_name}.json")
            graph_file = os.path.join(self.sessions_dir, f"{session_name}_graph.pkl")

            if not os.path.exists(session_file):
                st.error(f"Session file not found: {session_name}")
                return None

            # Load session data
            with open(session_file, 'r') as f:
                session_data = json.load(f)

            # Load graph if exists
            if os.path.exists(graph_file):
                with open(graph_file, 'rb') as f:
                    session_data['analysis_data']['graph'] = pickle.load(f)

            return session_data

        except Exception as e:
            st.error(f"Failed to load session: {str(e)}")
            return None

    def list_saved_sessions(self) -> List[Dict[str, Any]]:
        """
        List all saved sessions with metadata.

        Returns:
            List of session metadata dictionaries
        """
        sessions = []

        try:
            for filename in os.listdir(self.sessions_dir):
                if filename.endswith('.json') and not filename.endswith('_graph.pkl'):
                    session_name = filename[:-5]  # Remove .json extension
                    session_file = os.path.join(self.sessions_dir, filename)

                    try:
                        with open(session_file, 'r') as f:
                            session_data = json.load(f)

                        sessions.append({
                            'name': session_name,
                            'created_at': session_data.get('metadata', {}).get('created_at', 'Unknown'),
                            'description': session_data.get('metadata', {}).get('description', 'No description'),
                            'jurisdiction': session_data.get('analysis_data', {}).get('selected_jurisdiction_name', 'Unknown'),
                            'incident_edge': session_data.get('analysis_data', {}).get('selected_incident_edge', 'Unknown'),
                            'detour_count': len(session_data.get('analysis_data', {}).get('detour_results', {}))
                        })
                    except Exception as e:
                        # Skip corrupted session files
                        continue

            # Sort by creation date (newest first)
            sessions.sort(key=lambda x: x['created_at'], reverse=True)

        except Exception as e:
            st.error(f"Failed to list sessions: {str(e)}")

        return sessions

    def delete_session(self, session_name: str) -> bool:
        """
        Delete a saved session.

        Args:
            session_name: Name of the session to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            session_file = os.path.join(self.sessions_dir, f"{session_name}.json")
            graph_file = os.path.join(self.sessions_dir, f"{session_name}_graph.pkl")

            if os.path.exists(session_file):
                os.remove(session_file)

            if os.path.exists(graph_file):
                os.remove(graph_file)

            return True

        except Exception as e:
            st.error(f"Failed to delete session: {str(e)}")
            return False

    def restore_session_to_state(self, session_data: Dict[str, Any]) -> bool:
        """
        Restore session data to Streamlit session state.

        Args:
            session_data: Loaded session data

        Returns:
            True if successful, False otherwise
        """
        try:
            analysis_data = session_data.get('analysis_data', {})
            ui_state = session_data.get('ui_state', {})

            # Restore analysis data
            for key, value in analysis_data.items():
                if key == 'graph' and value:
                    # Graph is already loaded as NetworkX object
                    st.session_state[key] = value
                elif key == 'selected_polygon_wkt' and value:
                    # Convert WKT back to geometry if needed
                    st.session_state[key] = value
                else:
                    st.session_state[key] = value

            # Restore UI state
            for key, value in ui_state.items():
                st.session_state[key] = value

            # Set flags to indicate session was loaded
            st.session_state['session_loaded'] = True
            st.session_state['loaded_session_name'] = session_data.get('metadata', {}).get('name', 'Unknown')

            return True

        except Exception as e:
            st.error(f"Failed to restore session: {str(e)}")
            return False

    def _extract_analysis_data(self, session_state: Dict[str, Any]) -> Dict[str, Any]:
        """Extract analysis-related data from session state."""
        analysis_keys = [
            'selected_state_name', 'selected_jurisdiction_name', 'selected_jurisdiction_type',
            'selected_incident_edge', 'selected_edge_key', 'selected_polygon_wkt',
            'selected_polygon_bounds', 'jurisdiction_bounds',
            'detour_results', 'detour_selections', 'detour_generation_time',
            'analysis_params', 'n_turn_nodes', 'sector_angle_deg', 'sector_radius_m',
            'min_travel_time_s', 'max_travel_time_s', 'max_detour_routes',
            'performance_mode', 'data_download_status', 'downloaded_data'
        ]

        analysis_data = {}
        for key in analysis_keys:
            if key in session_state:
                value = session_state[key]
                # Convert NetworkX graph to WKT for JSON serialization
                if key == 'graph' and value:
                    analysis_data[key] = self._graph_to_serializable(value)
                else:
                    analysis_data[key] = value

        return analysis_data

    def _extract_ui_state(self, session_state: Dict[str, Any]) -> Dict[str, Any]:
        """Extract UI-related state from session state."""
        ui_keys = [
            'display_mode', 'show_network', 'show_incident', 'show_detours',
            'show_turn_nodes', 'show_impacted_arterials', 'map_center',
            'map_zoom', 'selected_route_for_comparison'
        ]

        ui_state = {}
        for key in ui_keys:
            if key in session_state:
                ui_state[key] = session_state[key]

        return ui_state

    def _generate_session_description(self, session_state: Dict[str, Any]) -> str:
        """Generate a description for the session."""
        jurisdiction = session_state.get('selected_jurisdiction_name', 'Unknown')
        incident = session_state.get('selected_incident_edge', 'Unknown')
        detour_count = len(session_state.get('detour_results', {}))

        return f"Analysis for {jurisdiction} with {detour_count} detour routes"

    def _json_serializer(self, obj):
        """Custom JSON serializer for non-serializable objects."""
        if hasattr(obj, 'isoformat'):  # datetime objects
            return obj.isoformat()
        elif hasattr(obj, '__dict__'):  # custom objects
            return obj.__dict__
        else:
            return str(obj)

    def _graph_to_serializable(self, graph: nx.Graph) -> Dict[str, Any]:
        """Convert NetworkX graph to serializable format."""
        try:
            # For now, just store basic graph info
            # In a full implementation, you might want to store as GraphML
            return {
                'nodes': len(graph.nodes()),
                'edges': len(graph.edges()),
                'graph_type': type(graph).__name__,
                'note': 'Graph data stored separately as pickle file'
            }
        except Exception:
            return {'error': 'Could not serialize graph'}


def create_session_manager() -> SessionManager:
    """Create and return a SessionManager instance."""
    return SessionManager()


# Convenience functions for Streamlit integration
def save_current_session(session_name: str) -> bool:
    """Save current Streamlit session state."""
    manager = create_session_manager()
    return manager.save_session(session_name, st.session_state)


def load_session_by_name(session_name: str) -> bool:
    """Load session by name into current Streamlit session state."""
    manager = create_session_manager()
    session_data = manager.load_session(session_name)
    if session_data:
        return manager.restore_session_to_state(session_data)
    return False


def get_saved_sessions() -> List[Dict[str, Any]]:
    """Get list of all saved sessions."""
    manager = create_session_manager()
    return manager.list_saved_sessions()


def delete_session_by_name(session_name: str) -> bool:
    """Delete session by name."""
    manager = create_session_manager()
    return manager.delete_session(session_name)
