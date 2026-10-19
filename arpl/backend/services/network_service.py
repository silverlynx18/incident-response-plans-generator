"""
Network service for ARPL (Automated Route Planning & Logistics).
Handles network loading, caching, and management operations.
"""

import networkx as nx
from typing import Dict, List, Any, Optional, Tuple
import streamlit as st
from datetime import datetime

from database import DatabaseManager
from network_cache import NetworkCache
import detour_utils as du


class NetworkService:
    """Service for network operations."""

    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize network service.

        Args:
            db_manager: Database manager instance
        """
        self.db_manager = db_manager
        self.network_cache = NetworkCache()

    def prepare_network(self, jurisdiction_name: str, jurisdiction_type: str,
                       state_name: str, area_polygon_shp=None,
                       osm_nodes_shp=None, osm_edges_shp=None) -> Optional[Dict[str, Any]]:
        """
        Prepare network for analysis.

        Args:
            jurisdiction_name: Name of jurisdiction
            jurisdiction_type: Type of jurisdiction
            state_name: State name
            area_polygon_shp: Area polygon shapefile
            osm_nodes_shp: OSM nodes shapefile
            osm_edges_shp: OSM edges shapefile

        Returns:
            Network information dictionary or None if failed
        """
        try:
            # Try to load from cache first
            cached_graph = self.network_cache.load_cached_network(
                jurisdiction_name, jurisdiction_type, state_name
            )

            if cached_graph is not None:
                st.info(f"Loaded cached network for {jurisdiction_name}")
                graph = cached_graph
            else:
                # Download and process network
                st.info(f"Downloading network for {jurisdiction_name}...")
                graph = du.load_osm_graph(
                    espg=4326,
                    area_polygon_shp=area_polygon_shp,
                    osm_nodes_shp=osm_nodes_shp,
                    osm_edges_shp=osm_edges_shp
                )

                if graph is None:
                    st.error("Failed to load network")
                    return None

                # Cache the network
                self.network_cache.cache_network(
                    jurisdiction_name, jurisdiction_type, state_name, graph
                )

            # Prepare network information
            network_info = {
                'graph': graph,
                'jurisdiction_name': jurisdiction_name,
                'jurisdiction_type': jurisdiction_type,
                'state_name': state_name,
                'node_count': len(graph.nodes()),
                'edge_count': len(graph.edges()),
                'prepared_at': datetime.now().isoformat(),
                'is_cached': cached_graph is not None
            }

            return network_info

        except Exception as e:
            st.error(f"Failed to prepare network: {str(e)}")
            return None

    def get_network_info(self, jurisdiction_name: str, jurisdiction_type: str,
                        state_name: str) -> Optional[Dict[str, Any]]:
        """Get network information."""
        try:
            graph = self.network_cache.load_cached_network(
                jurisdiction_name, jurisdiction_type, state_name
            )

            if graph is None:
                return None

            return {
                'jurisdiction_name': jurisdiction_name,
                'jurisdiction_type': jurisdiction_type,
                'state_name': state_name,
                'node_count': len(graph.nodes()),
                'edge_count': len(graph.edges()),
                'is_connected': nx.is_weakly_connected(graph),
                'has_geometry': any('geometry' in graph.edges[edge] for edge in graph.edges())
            }

        except Exception as e:
            st.error(f"Failed to get network info: {str(e)}")
            return None

    def cache_network(self, jurisdiction_name: str, jurisdiction_type: str,
                     state_name: str, graph: nx.Graph) -> bool:
        """Cache network data."""
        return self.network_cache.cache_network(
            jurisdiction_name, jurisdiction_type, state_name, graph
        )

    def load_cached_network(self, jurisdiction_name: str, jurisdiction_type: str,
                           state_name: str) -> Optional[nx.Graph]:
        """Load cached network."""
        return self.network_cache.load_cached_network(
            jurisdiction_name, jurisdiction_type, state_name
        )

    def get_cache_statistics(self) -> Dict[str, Any]:
        """Get network cache statistics."""
        return self.network_cache.get_cache_statistics()

    def cleanup_expired_caches(self) -> int:
        """Cleanup expired network caches."""
        return self.network_cache.cleanup_expired_caches()

    def clear_all_caches(self) -> bool:
        """Clear all network caches."""
        return self.network_cache.clear_all_caches()

    def get_cached_networks_list(self) -> List[Dict[str, Any]]:
        """Get list of cached networks."""
        return self.network_cache.get_cached_networks_list()

    def delete_cached_network(self, jurisdiction_name: str, jurisdiction_type: str,
                             state_name: str) -> bool:
        """Delete specific cached network."""
        return self.network_cache.delete_cached_network(
            jurisdiction_name, jurisdiction_type, state_name
        )

    def validate_network(self, graph: nx.Graph) -> Dict[str, Any]:
        """Validate network quality."""
        validation_results = {
            'is_valid': True,
            'node_count': len(graph.nodes()),
            'edge_count': len(graph.edges()),
            'is_connected': nx.is_weakly_connected(graph),
            'has_geometry': False,
            'has_speed_data': False,
            'issues': [],
            'warnings': [],
            'recommendations': []
        }

        try:
            # Check for geometry data
            has_geometry = any('geometry' in graph.edges[edge] for edge in graph.edges())
            validation_results['has_geometry'] = has_geometry

            if not has_geometry:
                validation_results['warnings'].append("Network lacks geometry data")
                validation_results['recommendations'].append("Consider using OSM data with geometry")

            # Check for speed data
            has_speed = any('maxspeed' in graph.edges[edge] for edge in graph.edges())
            validation_results['has_speed_data'] = has_speed

            if not has_speed:
                validation_results['warnings'].append("Network lacks speed limit data")
                validation_results['recommendations'].append("Consider adding speed limit data for accurate travel time calculations")

            # Check connectivity
            if not validation_results['is_connected']:
                validation_results['issues'].append("Network is not connected")
                validation_results['recommendations'].append("Check for isolated components")

            # Check for required attributes
            required_attrs = ['highway', 'length']
            for attr in required_attrs:
                has_attr = any(attr in graph.edges[edge] for edge in graph.edges())
                if not has_attr:
                    validation_results['warnings'].append(f"Network lacks {attr} attribute")

            # Check for null geometries
            null_geometries = 0
            for edge in graph.edges():
                if 'geometry' in graph.edges[edge] and graph.edges[edge]['geometry'] is None:
                    null_geometries += 1

            if null_geometries > 0:
                validation_results['warnings'].append(f"{null_geometries} edges have null geometries")

            validation_results['is_valid'] = len(validation_results['issues']) == 0

        except Exception as e:
            validation_results['is_valid'] = False
            validation_results['issues'].append(f"Validation error: {str(e)}")

        return validation_results

    def simplify_network(self, graph: nx.Graph, simplification_factor: float = 0.1) -> nx.Graph:
        """Simplify network for better performance."""
        try:
            # This would implement network simplification
            # For now, return the original graph
            st.info("Network simplification would be implemented here")
            return graph
        except Exception as e:
            st.error(f"Failed to simplify network: {str(e)}")
            return graph

    def get_network_bounds(self, graph: nx.Graph) -> Optional[Tuple[float, float, float, float]]:
        """Get network bounding box."""
        try:
            bounds = []
            for edge in graph.edges():
                if 'geometry' in graph.edges[edge] and graph.edges[edge]['geometry'] is not None:
                    geom = graph.edges[edge]['geometry']
                    bounds.extend([geom.bounds[0], geom.bounds[1], geom.bounds[2], geom.bounds[3]])

            if bounds:
                return (min(bounds[::4]), min(bounds[1::4]), max(bounds[2::4]), max(bounds[3::4]))

            return None
        except Exception as e:
            st.error(f"Failed to get network bounds: {str(e)}")
            return None
