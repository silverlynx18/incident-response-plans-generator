"""
Detour service for ARPL (Automated Route Planning & Logistics).
Handles detour calculation, route evaluation, and analysis operations.
"""

import networkx as nx
from typing import Dict, List, Any, Optional, Tuple
import streamlit as st
from datetime import datetime
import numpy as np
from shapely.geometry import Point
from shapely.ops import nearest_points

from database import DatabaseManager
import detour_utils as du


class DetourService:
    """Service for detour analysis operations."""

    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize detour service.

        Args:
            db_manager: Database manager instance
        """
        self.db_manager = db_manager

    def select_incident_edge(self, graph: nx.Graph, incident_location: Tuple[float, float]) -> Optional[Dict[str, Any]]:
        """
        Select incident edge from graph based on location.

        Args:
            graph: NetworkX graph
            incident_location: (longitude, latitude) of incident location

        Returns:
            Incident edge information or None if failed
        """
        try:
            # Convert location to Point
            incident_point = Point(incident_location[0], incident_location[1])

            # Find nearest edge
            nearest_edge = None
            min_distance = float('inf')

            for edge in graph.edges():
                if 'geometry' in graph.edges[edge] and graph.edges[edge]['geometry'] is not None:
                    edge_geom = graph.edges[edge]['geometry']
                    distance = incident_point.distance(edge_geom)

                    if distance < min_distance:
                        min_distance = distance
                        nearest_edge = edge

            if nearest_edge is None:
                st.error("No suitable edge found near incident location")
                return None

            # Get edge information
            edge_data = graph.edges[nearest_edge]

            incident_info = {
                'edge': nearest_edge,
                'start_node': nearest_edge[0],
                'end_node': nearest_edge[1],
                'geometry': edge_data.get('geometry'),
                'highway_type': edge_data.get('highway', 'unknown'),
                'name': edge_data.get('name', 'Unnamed Road'),
                'ref': edge_data.get('ref', ''),
                'length': edge_data.get('length', 0),
                'maxspeed': edge_data.get('maxspeed', ''),
                'distance_to_incident': min_distance,
                'selected_at': datetime.now().isoformat()
            }

            return incident_info

        except Exception as e:
            st.error(f"Failed to select incident edge: {str(e)}")
            return None

    def calculate_detours(self, graph: nx.Graph, incident_edge: Tuple[int, int],
                         analysis_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate detour routes for incident.

        Args:
            graph: NetworkX graph
            incident_edge: Incident edge tuple
            analysis_params: Analysis parameters

        Returns:
            Detour analysis results
        """
        try:
            start_time = datetime.now()

            # Extract parameters
            n_turn_nodes = analysis_params.get('n_turn_nodes', 5)
            sector_angle_deg = analysis_params.get('sector_angle_deg', 180)
            sector_radius_m = analysis_params.get('sector_radius_m', 3000)
            min_travel_time_s = analysis_params.get('min_travel_time_s', 90)
            max_travel_time_s = analysis_params.get('max_travel_time_s', 1800)
            max_detour_routes = analysis_params.get('max_detour_routes', 10)

            # Get surrounding turn nodes
            turn_nodes = du.get_surrounding_turns(
                graph, incident_edge, n_turn_nodes
            )

            if not turn_nodes:
                return {
                    'success': False,
                    'error': 'No turn nodes found',
                    'detour_results': {},
                    'generation_time': 0
                }

            # Generate incident graph
            incident_graph = du.generate_incident_graph(graph, incident_edge)

            # Calculate detours
            detour_results = {}
            start_nodes = turn_nodes.get('start_nodes', [])
            end_nodes = turn_nodes.get('end_nodes', [])

            for start_node in start_nodes:
                for end_node in end_nodes:
                    if start_node != end_node:
                        route_key = (start_node, end_node)

                        try:
                            detour_result = du.get_detour(
                                incident_graph, incident_edge,
                                start_node, end_node,
                                min_travel_time_s, max_travel_time_s
                            )
                            detour_results[route_key] = detour_result
                        except Exception as e:
                            detour_results[route_key] = (False, f"Error: {str(e)}", 0, [])

            # Limit results
            if len(detour_results) > max_detour_routes:
                # Sort by validity and travel time
                sorted_results = sorted(
                    detour_results.items(),
                    key=lambda x: (x[1][0], x[1][1] if isinstance(x[1][1], (int, float)) else float('inf'))
                )
                detour_results = dict(sorted_results[:max_detour_routes])

            # Calculate generation time
            generation_time = (datetime.now() - start_time).total_seconds()

            # Get impacted arterials
            try:
                sector_polygon = du.create_sector(
                    graph.nodes[incident_edge[0]]['geometry'] if 'geometry' in graph.nodes[incident_edge[0]] else Point(0, 0),
                    0, sector_radius_m, sector_angle_deg
                )
                impacted_arterials = du.get_impacted_arterials(
                    graph, sector_polygon, incident_edge
                )
            except:
                impacted_arterials = []

            results = {
                'success': True,
                'detour_results': detour_results,
                'turn_nodes': turn_nodes,
                'impacted_arterials': impacted_arterials,
                'incident_edge': incident_edge,
                'analysis_params': analysis_params,
                'generation_time': generation_time,
                'valid_detours': len([v for v in detour_results.values() if v[0]]),
                'total_detours': len(detour_results),
                'calculated_at': datetime.now().isoformat()
            }

            return results

        except Exception as e:
            st.error(f"Failed to calculate detours: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'detour_results': {},
                'generation_time': 0
            }

    def evaluate_route(self, route_key: Tuple[int, int], evaluation_status: str,
                      notes: str = None) -> bool:
        """
        Evaluate a route (accept/reject).

        Args:
            route_key: Route key tuple
            evaluation_status: 'accepted', 'rejected', or 'pending'
            notes: Optional evaluation notes

        Returns:
            True if successful, False otherwise
        """
        try:
            # This would save route evaluation to database
            # For now, just return success
            st.info(f"Route {route_key} evaluated as {evaluation_status}")
            if notes:
                st.info(f"Notes: {notes}")
            return True

        except Exception as e:
            st.error(f"Failed to evaluate route: {str(e)}")
            return False

    def get_detour_results(self, session_id: int = None) -> Dict[str, Any]:
        """Get detour analysis results."""
        try:
            if session_id:
                # Load from database
                session_data = self.db_manager.load_analysis_session(session_id)
                if session_data:
                    return {
                        'detour_results': session_data.get('detour_results', {}),
                        'session_id': session_id,
                        'loaded_from_db': True
                    }

            # Return current session results
            return {
                'detour_results': st.session_state.get('detour_results', {}),
                'session_id': None,
                'loaded_from_db': False
            }

        except Exception as e:
            st.error(f"Failed to get detour results: {str(e)}")
            return {'detour_results': {}}

    def analyze_route_quality(self, detour_results: Dict) -> Dict[str, Any]:
        """Analyze quality of detour routes."""
        try:
            if not detour_results:
                return {'error': 'No detour results to analyze'}

            valid_routes = [v for v in detour_results.values() if v[0]]
            invalid_routes = [v for v in detour_results.values() if not v[0]]

            analysis = {
                'total_routes': len(detour_results),
                'valid_routes': len(valid_routes),
                'invalid_routes': len(invalid_routes),
                'success_rate': len(valid_routes) / len(detour_results) * 100 if detour_results else 0,
                'travel_times': [],
                'route_lengths': [],
                'invalid_reasons': {}
            }

            # Analyze valid routes
            for route_key, (is_valid, travel_time, freeflow_time, path) in valid_routes:
                if is_valid and isinstance(travel_time, (int, float)):
                    analysis['travel_times'].append(travel_time)
                    analysis['route_lengths'].append(len(path) if path else 0)

            # Analyze invalid routes
            for route_key, (is_valid, reason, *_) in invalid_routes:
                if not is_valid:
                    reason_str = str(reason)
                    analysis['invalid_reasons'][reason_str] = analysis['invalid_reasons'].get(reason_str, 0) + 1

            # Calculate statistics
            if analysis['travel_times']:
                analysis['avg_travel_time'] = np.mean(analysis['travel_times'])
                analysis['min_travel_time'] = np.min(analysis['travel_times'])
                analysis['max_travel_time'] = np.max(analysis['travel_times'])
                analysis['std_travel_time'] = np.std(analysis['travel_times'])

            if analysis['route_lengths']:
                analysis['avg_route_length'] = np.mean(analysis['route_lengths'])
                analysis['min_route_length'] = np.min(analysis['route_lengths'])
                analysis['max_route_length'] = np.max(analysis['route_lengths'])

            return analysis

        except Exception as e:
            st.error(f"Failed to analyze route quality: {str(e)}")
            return {'error': str(e)}

    def get_route_statistics(self, detour_results: Dict) -> Dict[str, Any]:
        """Get statistics for detour routes."""
        try:
            if not detour_results:
                return {'error': 'No detour results available'}

            stats = {
                'total_routes': len(detour_results),
                'valid_routes': 0,
                'invalid_routes': 0,
                'avg_travel_time': 0,
                'min_travel_time': float('inf'),
                'max_travel_time': 0,
                'route_types': {},
                'invalid_reasons': {}
            }

            travel_times = []

            for route_key, (is_valid, travel_time, freeflow_time, path) in detour_results.items():
                if is_valid:
                    stats['valid_routes'] += 1
                    if isinstance(travel_time, (int, float)):
                        travel_times.append(travel_time)
                        stats['min_travel_time'] = min(stats['min_travel_time'], travel_time)
                        stats['max_travel_time'] = max(stats['max_travel_time'], travel_time)
                else:
                    stats['invalid_routes'] += 1
                    reason = str(travel_time)
                    stats['invalid_reasons'][reason] = stats['invalid_reasons'].get(reason, 0) + 1

            if travel_times:
                stats['avg_travel_time'] = np.mean(travel_times)

            if stats['min_travel_time'] == float('inf'):
                stats['min_travel_time'] = 0

            return stats

        except Exception as e:
            st.error(f"Failed to get route statistics: {str(e)}")
            return {'error': str(e)}

    def validate_analysis_parameters(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate analysis parameters."""
        validation = {
            'is_valid': True,
            'issues': [],
            'warnings': [],
            'recommendations': []
        }

        # Check required parameters
        required_params = ['n_turn_nodes', 'sector_angle_deg', 'sector_radius_m',
                          'min_travel_time_s', 'max_travel_time_s', 'max_detour_routes']

        for param in required_params:
            if param not in params:
                validation['issues'].append(f"Missing required parameter: {param}")
                validation['is_valid'] = False

        if not validation['is_valid']:
            return validation

        # Validate parameter ranges
        if params['n_turn_nodes'] < 1 or params['n_turn_nodes'] > 20:
            validation['warnings'].append("n_turn_nodes should be between 1 and 20")

        if params['sector_angle_deg'] < 30 or params['sector_angle_deg'] > 360:
            validation['warnings'].append("sector_angle_deg should be between 30 and 360")

        if params['sector_radius_m'] < 500 or params['sector_radius_m'] > 10000:
            validation['warnings'].append("sector_radius_m should be between 500 and 10000 meters")

        if params['min_travel_time_s'] >= params['max_travel_time_s']:
            validation['issues'].append("min_travel_time_s must be less than max_travel_time_s")
            validation['is_valid'] = False

        if params['max_detour_routes'] < 1 or params['max_detour_routes'] > 50:
            validation['warnings'].append("max_detour_routes should be between 1 and 50")

        # Performance recommendations
        if params['sector_radius_m'] > 5000:
            validation['recommendations'].append("Large sector radius may impact performance")

        if params['max_detour_routes'] > 20:
            validation['recommendations'].append("Large number of detour routes may impact performance")

        return validation
