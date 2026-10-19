"""
Core API functions for ARPL (Automated Route Planning & Logistics).
Provides high-level API for all application functionality.
"""

from typing import Dict, List, Any, Optional, Tuple
import streamlit as st
from datetime import datetime

from .services.network_service import NetworkService
from .services.detour_service import DetourService
from .services.export_service import ExportService
from .services.data_service import DataService
from database import DatabaseManager
from user_preferences import UserPreferencesManager


class ARPLAPI:
    """Main API class for ARPL application."""

    def __init__(self):
        """Initialize ARPL API with all services."""
        self.db_manager = DatabaseManager()
        self.preferences_manager = UserPreferencesManager()
        self.network_service = NetworkService(self.db_manager)
        self.detour_service = DetourService(self.db_manager)
        self.export_service = ExportService(self.db_manager)
        self.data_service = DataService(self.db_manager)

    # Jurisdiction and Data Management

    def get_available_jurisdictions(self, dataset: str = 'COUNTY', year: str = None) -> List[Dict[str, Any]]:
        """Get list of available jurisdictions."""
        return self.data_service.get_available_jurisdictions(dataset, year)

    def load_jurisdiction_data(self, jurisdiction_name: str, jurisdiction_type: str,
                              state_name: str) -> Optional[Dict[str, Any]]:
        """Load jurisdiction boundary data."""
        return self.data_service.load_jurisdiction_data(jurisdiction_name, jurisdiction_type, state_name)

    def download_tiger_data(self, dataset: str, year: str = None) -> Optional[str]:
        """Download TIGER data."""
        return self.data_service.download_tiger_data(dataset, year)

    def get_tiger_year_info(self, year: str) -> Dict[str, Any]:
        """Get TIGER year information."""
        return self.data_service.get_tiger_year_info(year)

    def get_available_tiger_years(self) -> List[Dict[str, Any]]:
        """Get available TIGER years."""
        return self.data_service.get_available_tiger_years()

    # Network Management

    def prepare_network(self, jurisdiction_name: str, jurisdiction_type: str,
                       state_name: str, area_polygon_shp=None,
                       osm_nodes_shp=None, osm_edges_shp=None) -> Optional[Dict[str, Any]]:
        """Prepare network for analysis."""
        return self.network_service.prepare_network(
            jurisdiction_name, jurisdiction_type, state_name,
            area_polygon_shp, osm_nodes_shp, osm_edges_shp
        )

    def get_network_info(self, jurisdiction_name: str, jurisdiction_type: str,
                        state_name: str) -> Optional[Dict[str, Any]]:
        """Get network information."""
        return self.network_service.get_network_info(jurisdiction_name, jurisdiction_type, state_name)

    def cache_network(self, jurisdiction_name: str, jurisdiction_type: str,
                     state_name: str, graph) -> bool:
        """Cache network data."""
        return self.network_service.cache_network(jurisdiction_name, jurisdiction_type, state_name, graph)

    def load_cached_network(self, jurisdiction_name: str, jurisdiction_type: str,
                           state_name: str):
        """Load cached network."""
        return self.network_service.load_cached_network(jurisdiction_name, jurisdiction_type, state_name)

    # Incident and Detour Analysis

    def select_incident_edge(self, graph, incident_location: Tuple[float, float]) -> Optional[Dict[str, Any]]:
        """Select incident edge from graph."""
        return self.detour_service.select_incident_edge(graph, incident_location)

    def calculate_detours(self, graph, incident_edge: Tuple[int, int],
                         analysis_params: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate detour routes."""
        return self.detour_service.calculate_detours(graph, incident_edge, analysis_params)

    def evaluate_route(self, route_key: Tuple[int, int], evaluation_status: str,
                      notes: str = None) -> bool:
        """Evaluate a route (accept/reject)."""
        return self.detour_service.evaluate_route(route_key, evaluation_status, notes)

    def get_detour_results(self, session_id: int = None) -> Dict[str, Any]:
        """Get detour analysis results."""
        return self.detour_service.get_detour_results(session_id)

    # Export Functionality

    def export_results(self, export_format: str, session_id: int = None) -> Optional[bytes]:
        """Export analysis results."""
        return self.export_service.export_results(export_format, session_id)

    def get_available_export_formats(self) -> List[Dict[str, str]]:
        """Get available export formats."""
        return self.export_service.get_available_export_formats()

    def generate_pdf_report(self, session_id: int = None) -> Optional[bytes]:
        """Generate PDF report."""
        return self.export_service.generate_pdf_report(session_id)

    def export_geospatial_data(self, format_type: str, session_id: int = None) -> Optional[bytes]:
        """Export geospatial data."""
        return self.export_service.export_geospatial_data(format_type, session_id)

    def export_tabular_data(self, format_type: str, session_id: int = None) -> Optional[bytes]:
        """Export tabular data."""
        return self.export_service.export_tabular_data(format_type, session_id)

    # Session Management

    def save_analysis_session(self, session_name: str, session_data: Dict[str, Any]) -> Optional[int]:
        """Save analysis session."""
        return self.db_manager.save_analysis_session(session_data)

    def load_analysis_session(self, session_id: int) -> Optional[Dict[str, Any]]:
        """Load analysis session."""
        return self.db_manager.load_analysis_session(session_id)

    def list_analysis_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List analysis sessions."""
        return self.db_manager.list_analysis_sessions(limit)

    def delete_analysis_session(self, session_id: int) -> bool:
        """Delete analysis session."""
        return self.db_manager.delete_analysis_session(session_id)

    # User Preferences

    def get_user_preference(self, key: str, default: Any = None) -> Any:
        """Get user preference."""
        return self.preferences_manager.get_preference(key, default)

    def set_user_preference(self, key: str, value: Any) -> bool:
        """Set user preference."""
        return self.preferences_manager.set_preference(key, value)

    def get_analysis_presets(self) -> Dict[str, Dict[str, Any]]:
        """Get analysis presets."""
        return self.preferences_manager.get_analysis_presets()

    def apply_analysis_preset(self, preset_name: str) -> bool:
        """Apply analysis preset."""
        preset = self.preferences_manager.get_analysis_presets().get(preset_name)
        if preset:
            for key, value in preset.items():
                st.session_state[key] = value
            return True
        return False

    # Batch Processing

    def start_batch_analysis(self, batch_name: str, incidents: List[Dict[str, Any]],
                            analysis_params: Dict[str, Any], graph) -> str:
        """Start batch analysis."""
        from batch_processor import create_batch_processor
        processor = create_batch_processor()
        return processor.start_batch_analysis(batch_name, incidents, analysis_params, graph)

    def get_batch_results(self, batch_id: str) -> Optional[Dict[str, Any]]:
        """Get batch analysis results."""
        from batch_processor import create_batch_processor
        processor = create_batch_processor()
        return processor.get_batch_results(batch_id)

    def list_batch_analyses(self) -> List[Dict[str, Any]]:
        """List batch analyses."""
        from batch_processor import create_batch_processor
        processor = create_batch_processor()
        return processor.list_batches()

    # Analysis History

    def record_analysis_history(self, history_data: Dict[str, Any]) -> bool:
        """Record analysis in history."""
        return self.db_manager.record_analysis_history(history_data)

    def get_analysis_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get analysis history."""
        return self.db_manager.get_analysis_history(limit)

    # Data Validation and Quality

    def validate_data_quality(self, gdf) -> Dict[str, Any]:
        """Validate data quality."""
        return self.data_service.validate_data_quality(gdf)

    def get_data_statistics(self) -> Dict[str, Any]:
        """Get data statistics."""
        return self.data_service.get_data_statistics()

    # System Information

    def get_system_info(self) -> Dict[str, Any]:
        """Get system information."""
        return {
            'database_health': self.db_manager.get_database_health(),
            'data_statistics': self.get_data_statistics(),
            'user_preferences': self.preferences_manager.get_all_preferences(),
            'available_export_formats': self.get_available_export_formats(),
            'system_time': datetime.now().isoformat()
        }

    def get_database_health(self) -> Dict[str, Any]:
        """Get database health information."""
        return self.db_manager.get_database_health()

    def cleanup_expired_data(self) -> Dict[str, int]:
        """Cleanup expired data."""
        return {
            'expired_caches': self.network_service.cleanup_expired_caches(),
            'expired_sessions': 0  # Would implement session cleanup
        }


def create_arpl_api() -> ARPLAPI:
    """Create and return an ARPLAPI instance."""
    return ARPLAPI()


# Convenience functions for Streamlit integration
def get_arpl_api() -> ARPLAPI:
    """Get or create ARPL API instance."""
    if 'arpl_api' not in st.session_state:
        st.session_state.arpl_api = create_arpl_api()
    return st.session_state.arpl_api


def get_jurisdictions(dataset: str = 'COUNTY', year: str = None) -> List[Dict[str, Any]]:
    """Get available jurisdictions."""
    api = get_arpl_api()
    return api.get_available_jurisdictions(dataset, year)


def prepare_network(jurisdiction_name: str, jurisdiction_type: str, state_name: str) -> Optional[Dict[str, Any]]:
    """Prepare network for analysis."""
    api = get_arpl_api()
    return api.prepare_network(jurisdiction_name, jurisdiction_type, state_name)


def calculate_detours(graph, incident_edge: Tuple[int, int], analysis_params: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate detour routes."""
    api = get_arpl_api()
    return api.calculate_detours(graph, incident_edge, analysis_params)


def export_results(export_format: str) -> Optional[bytes]:
    """Export analysis results."""
    api = get_arpl_api()
    return api.export_results(export_format)


def save_session(session_name: str) -> Optional[int]:
    """Save current analysis session."""
    api = get_arpl_api()
    return api.save_analysis_session(session_name, st.session_state)


def load_session(session_id: int) -> bool:
    """Load analysis session."""
    api = get_arpl_api()
    session_data = api.load_analysis_session(session_id)
    if session_data:
        # Restore session state
        for key, value in session_data.items():
            if key not in ['id', 'created_at', 'updated_at']:
                st.session_state[key] = value
        return True
    return False
