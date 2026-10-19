"""
Export service for ARPL (Automated Route Planning & Logistics).
Handles all export functionality including PDF, geospatial, and tabular formats.
"""

from typing import Dict, List, Any, Optional
import streamlit as st
from datetime import datetime

from database import DatabaseManager
from export_utils import (
    create_export_data, PDFReportGenerator,
    GeospatialExporter, TabularExporter
)


class ExportService:
    """Service for export operations."""

    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize export service.

        Args:
            db_manager: Database manager instance
        """
        self.db_manager = db_manager

        # Available export formats
        self.export_formats = {
            'pdf_report': {
                'name': 'PDF Report',
                'description': 'Comprehensive analysis report with charts and maps',
                'mime_type': 'application/pdf',
                'extension': 'pdf'
            },
            'geojson': {
                'name': 'GeoJSON',
                'description': 'Geospatial data in GeoJSON format',
                'mime_type': 'application/geo+json',
                'extension': 'geojson'
            },
            'kml': {
                'name': 'KML',
                'description': 'Google Earth compatible format',
                'mime_type': 'application/vnd.google-earth.kml+xml',
                'extension': 'kml'
            },
            'shapefile': {
                'name': 'Shapefile',
                'description': 'ESRI Shapefile format (ZIP)',
                'mime_type': 'application/zip',
                'extension': 'zip'
            },
            'geopackage': {
                'name': 'GeoPackage',
                'description': 'SQLite-based geospatial format',
                'mime_type': 'application/geopackage+sqlite3',
                'extension': 'gpkg'
            },
            'excel': {
                'name': 'Excel',
                'description': 'Microsoft Excel workbook with multiple sheets',
                'mime_type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'extension': 'xlsx'
            },
            'csv': {
                'name': 'CSV',
                'description': 'Comma-separated values format',
                'mime_type': 'text/csv',
                'extension': 'csv'
            }
        }

    def get_available_export_formats(self) -> List[Dict[str, str]]:
        """Get list of available export formats."""
        return [
            {
                'key': key,
                'name': info['name'],
                'description': info['description'],
                'mime_type': info['mime_type'],
                'extension': info['extension']
            }
            for key, info in self.export_formats.items()
        ]

    def export_results(self, export_format: str, session_id: int = None) -> Optional[bytes]:
        """
        Export analysis results in specified format.

        Args:
            export_format: Export format key
            session_id: Session ID (optional, uses current session if None)

        Returns:
            Export data as bytes or None if failed
        """
        try:
            # Get export data
            export_data = self._get_export_data(session_id)
            if not export_data:
                st.error("No data available for export")
                return None

            # Route to appropriate exporter
            if export_format == 'pdf_report':
                return self.generate_pdf_report(session_id)
            elif export_format in ['geojson', 'kml', 'shapefile', 'geopackage']:
                return self.export_geospatial_data(export_format, session_id)
            elif export_format in ['excel', 'csv']:
                return self.export_tabular_data(export_format, session_id)
            else:
                st.error(f"Unsupported export format: {export_format}")
                return None

        except Exception as e:
            st.error(f"Export failed: {str(e)}")
            return None

    def generate_pdf_report(self, session_id: int = None) -> Optional[bytes]:
        """Generate PDF report."""
        try:
            export_data = self._get_export_data(session_id)
            if not export_data:
                return None

            generator = PDFReportGenerator(export_data)
            return generator.generate_report()

        except Exception as e:
            st.error(f"PDF generation failed: {str(e)}")
            return None

    def export_geospatial_data(self, format_type: str, session_id: int = None) -> Optional[bytes]:
        """Export geospatial data."""
        try:
            export_data = self._get_export_data(session_id)
            if not export_data:
                return None

            exporter = GeospatialExporter(export_data)

            if format_type == 'geojson':
                return exporter.export_geojson()
            elif format_type == 'kml':
                return exporter.export_kml()
            elif format_type == 'shapefile':
                return exporter.export_shapefile()
            elif format_type == 'geopackage':
                return exporter.export_geopackage()
            else:
                st.error(f"Unsupported geospatial format: {format_type}")
                return None

        except Exception as e:
            st.error(f"Geospatial export failed: {str(e)}")
            return None

    def export_tabular_data(self, format_type: str, session_id: int = None) -> Optional[bytes]:
        """Export tabular data."""
        try:
            export_data = self._get_export_data(session_id)
            if not export_data:
                return None

            exporter = TabularExporter(export_data)

            if format_type == 'excel':
                return exporter.export_excel()
            elif format_type == 'csv':
                return exporter.export_csv()
            else:
                st.error(f"Unsupported tabular format: {format_type}")
                return None

        except Exception as e:
            st.error(f"Tabular export failed: {str(e)}")
            return None

    def _get_export_data(self, session_id: int = None) -> Optional[Dict[str, Any]]:
        """Get export data from session or database."""
        try:
            if session_id:
                # Load from database
                session_data = self.db_manager.load_analysis_session(session_id)
                if session_data:
                    return create_export_data(session_data)
            else:
                # Use current session state
                return create_export_data(st.session_state)

            return None

        except Exception as e:
            st.error(f"Failed to get export data: {str(e)}")
            return None

    def get_export_filename(self, export_format: str, session_id: int = None,
                           custom_name: str = None) -> str:
        """Generate export filename."""
        try:
            format_info = self.export_formats.get(export_format, {})
            extension = format_info.get('extension', 'txt')

            # Generate base name
            if custom_name:
                base_name = custom_name
            else:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                base_name = f"arpl_analysis_{timestamp}"

            return f"{base_name}.{extension}"

        except Exception as e:
            st.error(f"Failed to generate filename: {str(e)}")
            return f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

    def validate_export_data(self, export_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate export data."""
        validation = {
            'is_valid': True,
            'issues': [],
            'warnings': [],
            'recommendations': []
        }

        # Check required fields
        required_fields = ['jurisdiction_name', 'detour_results']
        for field in required_fields:
            if field not in export_data:
                validation['issues'].append(f"Missing required field: {field}")
                validation['is_valid'] = False

        # Check detour results
        detour_results = export_data.get('detour_results', {})
        if not detour_results:
            validation['warnings'].append("No detour results available for export")
        else:
            valid_detours = [v for v in detour_results.values() if v[0]]
            if not valid_detours:
                validation['warnings'].append("No valid detour routes available for export")

        # Check metadata
        if not export_data.get('analysis_params'):
            validation['warnings'].append("No analysis parameters available")

        if not export_data.get('incident_info'):
            validation['warnings'].append("No incident information available")

        return validation

    def get_export_preview(self, export_format: str, session_id: int = None) -> Dict[str, Any]:
        """Get export preview information."""
        try:
            export_data = self._get_export_data(session_id)
            if not export_data:
                return {'error': 'No data available for preview'}

            validation = self.validate_export_data(export_data)

            preview = {
                'format': export_format,
                'format_info': self.export_formats.get(export_format, {}),
                'data_summary': {
                    'jurisdiction': export_data.get('jurisdiction_name', 'Unknown'),
                    'total_routes': len(export_data.get('detour_results', {})),
                    'valid_routes': len([v for v in export_data.get('detour_results', {}).values() if v[0]]),
                    'incident_edge': export_data.get('incident_info', {}).get('edge', 'Unknown')
                },
                'validation': validation,
                'estimated_size': self._estimate_export_size(export_format, export_data),
                'preview_available': export_format in ['csv', 'geojson']
            }

            return preview

        except Exception as e:
            return {'error': str(e)}

    def _estimate_export_size(self, export_format: str, export_data: Dict[str, Any]) -> str:
        """Estimate export file size."""
        try:
            detour_results = export_data.get('detour_results', {})
            num_routes = len(detour_results)

            # Rough size estimates based on format
            size_estimates = {
                'pdf_report': num_routes * 50 + 500,  # KB
                'geojson': num_routes * 5 + 50,
                'kml': num_routes * 3 + 30,
                'shapefile': num_routes * 10 + 100,
                'geopackage': num_routes * 8 + 80,
                'excel': num_routes * 2 + 20,
                'csv': num_routes * 1 + 10
            }

            estimated_kb = size_estimates.get(export_format, 100)

            if estimated_kb < 1024:
                return f"{estimated_kb:.0f} KB"
            else:
                return f"{estimated_kb / 1024:.1f} MB"

        except:
            return "Unknown"

    def batch_export(self, export_formats: List[str], session_id: int = None) -> Dict[str, Optional[bytes]]:
        """Export in multiple formats."""
        results = {}

        for format_type in export_formats:
            try:
                results[format_type] = self.export_results(format_type, session_id)
            except Exception as e:
                st.error(f"Batch export failed for {format_type}: {str(e)}")
                results[format_type] = None

        return results

    def get_export_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get export history."""
        try:
            # This would query export history from database
            # For now, return empty list
            return []
        except Exception as e:
            st.error(f"Failed to get export history: {str(e)}")
            return []
