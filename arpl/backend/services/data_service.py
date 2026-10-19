"""
Data service for ARPL (Automated Route Planning & Logistics).
Handles data loading, validation, and management operations.
"""

import geopandas as gpd
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple
import streamlit as st
from datetime import datetime
from pathlib import Path

from database import DatabaseManager
from data_manager import DataManager
from dot_data_sources import DOTDataSources
from custom_data_upload import CustomDataUploader


class DataService:
    """Service for data operations."""

    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize data service.

        Args:
            db_manager: Database manager instance
        """
        self.db_manager = db_manager
        self.data_manager = DataManager()
        self.dot_sources = DOTDataSources()
        self.custom_uploader = CustomDataUploader()

    def get_available_jurisdictions(self, dataset: str = 'COUNTY', year: str = None) -> List[Dict[str, Any]]:
        """Get list of available jurisdictions."""
        return self.data_manager.get_available_jurisdictions(dataset, year)

    def load_jurisdiction_data(self, jurisdiction_name: str, jurisdiction_type: str,
                              state_name: str) -> Optional[Dict[str, Any]]:
        """Load jurisdiction boundary data."""
        try:
            gdf = self.data_manager.load_tiger_data(jurisdiction_type.upper(), year=None)
            if gdf is None:
                return None

            # Filter for specific jurisdiction
            if jurisdiction_type == 'county':
                filtered = gdf[gdf['NAME'] == jurisdiction_name]
            elif jurisdiction_type == 'state':
                filtered = gdf[gdf['NAME'] == jurisdiction_name]
            elif jurisdiction_type == 'urban_area':
                filtered = gdf[gdf['NAME20'] == jurisdiction_name]
            else:
                return None

            if len(filtered) == 0:
                return None

            return {
                'geometry': filtered.iloc[0].geometry,
                'properties': filtered.iloc[0].to_dict(),
                'bounds': filtered.total_bounds.tolist(),
                'area_sq_km': filtered.iloc[0].geometry.area / 1e6
            }

        except Exception as e:
            st.error(f"Failed to load jurisdiction data: {str(e)}")
            return None

    def download_tiger_data(self, dataset: str, year: str = None) -> Optional[str]:
        """Download TIGER data."""
        return self.data_manager.download_tiger_data(dataset, year)

    def get_tiger_year_info(self, year: str) -> Dict[str, Any]:
        """Get TIGER year information."""
        return self.data_manager.get_tiger_year_info(year)

    def get_available_tiger_years(self) -> List[Dict[str, Any]]:
        """Get available TIGER years."""
        return self.data_manager.get_available_tiger_years()

    def set_preferred_tiger_year(self, year: str) -> bool:
        """Set preferred TIGER year."""
        return self.data_manager.set_preferred_tiger_year(year)

    def get_dot_data_sources(self) -> Dict[str, Dict[str, Any]]:
        """Get available state DOT data sources."""
        return self.dot_sources.get_dot_data_sources()

    def get_available_dot_states(self) -> List[str]:
        """Get list of available state DOT data sources."""
        return self.dot_sources.get_available_states()

    def get_state_dot_datasets(self, state: str) -> List[Dict[str, Any]]:
        """Get available datasets for a state DOT."""
        return self.dot_sources.get_state_datasets(state)

    def download_dot_dataset(self, state: str, dataset: str) -> Optional[str]:
        """Download dataset from state DOT."""
        return self.dot_sources.download_state_dataset(state, dataset)

    def load_dot_dataset(self, state: str, dataset: str) -> Optional[gpd.GeoDataFrame]:
        """Load state DOT dataset."""
        return self.dot_sources.load_state_dataset(state, dataset)

    def validate_data_quality(self, gdf: gpd.GeoDataFrame) -> Dict[str, Any]:
        """Validate data quality."""
        return self.data_manager.validate_data_quality(gdf)

    def get_data_statistics(self) -> Dict[str, Any]:
        """Get data statistics."""
        return self.data_manager.get_data_statistics()

    def upload_custom_data(self, uploaded_file, use_case: str = 'general',
                          custom_name: str = None) -> Optional[Dict[str, Any]]:
        """Upload and process custom data file."""
        return self.custom_uploader.process_and_save_upload(uploaded_file, use_case, custom_name)

    def validate_custom_data(self, uploaded_file, use_case: str = 'general') -> Dict[str, Any]:
        """Validate custom data file."""
        return self.custom_uploader.validate_file(uploaded_file, use_case)

    def list_custom_datasets(self) -> List[Dict[str, Any]]:
        """List all custom datasets."""
        return self.custom_uploader.list_uploaded_datasets()

    def load_custom_dataset(self, filename: str) -> Optional[gpd.GeoDataFrame]:
        """Load custom dataset."""
        return self.custom_uploader.load_dataset(filename)

    def delete_custom_dataset(self, filename: str) -> bool:
        """Delete custom dataset."""
        return self.custom_uploader.delete_dataset(filename)

    def get_custom_data_statistics(self) -> Dict[str, Any]:
        """Get custom data statistics."""
        return self.custom_uploader.get_upload_statistics()

    def get_supported_upload_formats(self) -> List[Dict[str, str]]:
        """Get supported upload formats."""
        formats = []
        for format_name, format_info in self.custom_uploader.supported_formats.items():
            formats.append({
                'name': format_name,
                'description': format_info['description'],
                'extensions': format_info['extensions'],
                'driver': format_info['driver']
            })
        return formats

    def get_geometry_requirements(self, use_case: str) -> List[str]:
        """Get geometry requirements for use case."""
        return self.custom_uploader.geometry_requirements.get(use_case, ['Point', 'LineString', 'Polygon'])

    def cleanup_old_data(self, days_old: int = 30) -> int:
        """Cleanup old data files."""
        return self.data_manager.cleanup_old_data(days_old)

    def get_data_health_report(self) -> Dict[str, Any]:
        """Get comprehensive data health report."""
        try:
            report = {
                'timestamp': datetime.now().isoformat(),
                'tiger_data': self.data_manager.get_data_statistics(),
                'dot_data': self.dot_sources.get_dot_data_summary(),
                'custom_data': self.custom_uploader.get_upload_statistics(),
                'database_health': self.db_manager.get_database_health(),
                'recommendations': []
            }

            # Add recommendations
            if report['custom_data']['total_datasets'] == 0:
                report['recommendations'].append("Consider uploading custom data for specific analysis needs")

            if report['tiger_data'].get('tiger_data', {}).get('total_files', 0) == 0:
                report['recommendations'].append("Download TIGER data for jurisdiction boundaries")

            cache_stats = report['database_health'].get('cache_statistics', {})
            if cache_stats.get('active_caches', 0) == 0:
                report['recommendations'].append("Consider caching networks for better performance")

            return report

        except Exception as e:
            return {'error': str(e), 'timestamp': datetime.now().isoformat()}

    def validate_jurisdiction_selection(self, jurisdiction_name: str, jurisdiction_type: str,
                                       state_name: str) -> Dict[str, Any]:
        """Validate jurisdiction selection."""
        validation = {
            'is_valid': True,
            'issues': [],
            'warnings': [],
            'recommendations': []
        }

        try:
            # Check if jurisdiction data is available
            jurisdiction_data = self.load_jurisdiction_data(jurisdiction_name, jurisdiction_type, state_name)

            if jurisdiction_data is None:
                validation['is_valid'] = False
                validation['issues'].append(f"Jurisdiction '{jurisdiction_name}' not found in {jurisdiction_type} data")
                return validation

            # Check area size
            area_sq_km = jurisdiction_data.get('area_sq_km', 0)
            if area_sq_km > 10000:  # 10,000 sq km
                validation['warnings'].append("Large jurisdiction may impact performance")
                validation['recommendations'].append("Consider using a smaller area or enabling performance mode")

            if area_sq_km < 1:  # 1 sq km
                validation['warnings'].append("Very small jurisdiction may have limited road network")

            # Check if network is cached
            from network_cache import NetworkCache
            cache = NetworkCache()
            cached_network = cache.load_cached_network(jurisdiction_name, jurisdiction_type, state_name)

            if cached_network is None:
                validation['recommendations'].append("Network not cached - first analysis may take longer")
            else:
                validation['recommendations'].append("Network is cached - analysis should be fast")

            return validation

        except Exception as e:
            validation['is_valid'] = False
            validation['issues'].append(f"Validation error: {str(e)}")
            return validation

    def get_data_sources_summary(self) -> Dict[str, Any]:
        """Get summary of all data sources."""
        return {
            'tiger_data': {
                'available_years': self.get_available_tiger_years(),
                'current_year': self.data_manager.current_tiger_year,
                'statistics': self.data_manager.get_data_statistics()
            },
            'dot_data': {
                'available_states': self.get_available_dot_states(),
                'total_sources': len(self.get_available_dot_states()),
                'summary': self.dot_sources.get_dot_data_summary()
            },
            'custom_data': {
                'supported_formats': self.get_supported_upload_formats(),
                'statistics': self.get_custom_data_statistics()
            }
        }
