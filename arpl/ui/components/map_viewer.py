"""
Map viewer component for ARPL (Automated Route Planning & Logistics).
Handles interactive map display and user interactions.
"""

import streamlit as st
import folium
import streamlit_folium as st_folium
import geopandas as gpd
import networkx as nx
from typing import Dict, List, Any, Optional, Tuple
from shapely.geometry import Point, LineString
import json

from backend import get_arpl_api


class MapViewer:
    """Handles interactive map display and user interactions."""

    def __init__(self):
        """Initialize map viewer."""
        self.api = get_arpl_api()

    def render(self):
        """Render the interactive map."""
        st.header("🗺️ Interactive Map")

        # Create map
        map_obj = self._create_map()

        # Display map and handle interactions
        map_data = st_folium.st_folium(
            map_obj,
            width=700,
            height=500,
            returned_objects=["last_object_clicked", "last_object_clicked_tooltip"]
        )

        # Handle map interactions
        self._handle_map_interactions(map_data)

        # Display map controls
        self._render_map_controls()

    def _create_map(self) -> folium.Map:
        """Create the base map."""
        # Get map center from session state or use default
        center_lat = st.session_state.get('map_center_lat', 39.8283)
        center_lon = st.session_state.get('map_center_lon', -98.5795)
        zoom_level = st.session_state.get('map_zoom', 4)

        # Create map
        map_obj = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=zoom_level,
            tiles='OpenStreetMap'
        )

        # Add jurisdiction boundary if available
        self._add_jurisdiction_boundary(map_obj)

        # Add road network if available
        self._add_road_network(map_obj)

        # Add incident location if available
        self._add_incident_location(map_obj)

        # Add detour routes if available
        self._add_detour_routes(map_obj)

        # Add turn nodes if available
        self._add_turn_nodes(map_obj)

        # Add impacted arterials if available
        self._add_impacted_arterials(map_obj)

        return map_obj

    def _add_jurisdiction_boundary(self, map_obj: folium.Map):
        """Add jurisdiction boundary to map."""
        if st.session_state.get('jurisdiction_boundary'):
            try:
                boundary = st.session_state.jurisdiction_boundary

                # Convert to GeoJSON
                if hasattr(boundary, '__geo_interface__'):
                    folium.GeoJson(
                        boundary.__geo_interface__,
                        style_function=lambda x: {
                            'fillColor': 'lightblue',
                            'color': 'blue',
                            'weight': 2,
                            'fillOpacity': 0.1
                        },
                        popup=folium.Popup(
                            f"<b>{st.session_state.get('selected_jurisdiction_name', 'Jurisdiction')}</b><br>"
                            f"Type: {st.session_state.get('selected_jurisdiction_type', 'Unknown')}<br>"
                            f"State: {st.session_state.get('selected_state_name', 'Unknown')}",
                            max_width=200
                        )
                    ).add_to(map_obj)
            except Exception as e:
                st.warning(f"Could not add jurisdiction boundary: {e}")

    def _add_road_network(self, map_obj: folium.Map):
        """Add road network to map."""
        if st.session_state.get('graph') and st.session_state.get('show_road_network', True):
            try:
                graph = st.session_state.graph

                # Sample edges for display (limit to avoid performance issues)
                edges_to_show = list(graph.edges())[:1000]  # Limit to 1000 edges

                for edge in edges_to_show:
                    if 'geometry' in graph.edges[edge] and graph.edges[edge]['geometry'] is not None:
                        geom = graph.edges[edge]['geometry']

                        # Get road type for styling
                        highway_type = graph.edges[edge].get('highway', 'unknown')
                        color = self._get_road_color(highway_type)
                        weight = self._get_road_weight(highway_type)

                        # Create polyline
                        if hasattr(geom, 'coords'):
                            coords = list(geom.coords)
                            folium.PolyLine(
                                coords,
                                color=color,
                                weight=weight,
                                opacity=0.7,
                                popup=folium.Popup(
                                    f"<b>Road Segment</b><br>"
                                    f"Type: {highway_type}<br>"
                                    f"Name: {graph.edges[edge].get('name', 'Unnamed')}<br>"
                                    f"Ref: {graph.edges[edge].get('ref', 'N/A')}",
                                    max_width=200
                                )
                            ).add_to(map_obj)
            except Exception as e:
                st.warning(f"Could not add road network: {e}")

    def _add_incident_location(self, map_obj: folium.Map):
        """Add incident location to map."""
        if st.session_state.get('selected_incident_edge'):
            try:
                incident_edge = st.session_state.selected_incident_edge
                graph = st.session_state.graph

                if graph.has_edge(*incident_edge):
                    edge_data = graph.edges[incident_edge]

                    # Get incident point (midpoint of edge)
                    if 'geometry' in edge_data and edge_data['geometry'] is not None:
                        geom = edge_data['geometry']
                        if hasattr(geom, 'interpolate'):
                            incident_point = geom.interpolate(0.5, normalized=True)
                        else:
                            incident_point = geom.centroid

                        # Add incident marker
                        folium.Marker(
                            [incident_point.y, incident_point.x],
                            popup=folium.Popup(
                                f"<b>🚧 Incident Location</b><br>"
                                f"Edge: {incident_edge}<br>"
                                f"Type: {edge_data.get('highway', 'unknown')}<br>"
                                f"Name: {edge_data.get('name', 'Unnamed')}<br>"
                                f"Length: {edge_data.get('length', 0):.1f}m",
                                max_width=200
                            ),
                            icon=folium.Icon(color='red', icon='exclamation-triangle')
                        ).add_to(map_obj)
            except Exception as e:
                st.warning(f"Could not add incident location: {e}")

    def _add_detour_routes(self, map_obj: folium.Map):
        """Add detour routes to map."""
        if st.session_state.get('detour_results') and st.session_state.get('show_detour_routes', True):
            try:
                detour_results = st.session_state.detour_results
                graph = st.session_state.graph

                colors = ['green', 'blue', 'purple', 'orange', 'darkred', 'lightred', 'beige', 'darkblue', 'darkgreen', 'cadetblue']

                for i, (route_key, (is_valid, travel_time, freeflow_time, path)) in enumerate(detour_results.items()):
                    if is_valid and path:
                        color = colors[i % len(colors)]

                        # Create route geometry
                        route_coords = []
                        for j in range(len(path) - 1):
                            start_node = path[j]
                            end_node = path[j + 1]

                            if graph.has_edge(start_node, end_node):
                                edge_data = graph.edges[start_node, end_node]
                                if 'geometry' in edge_data and edge_data['geometry'] is not None:
                                    geom = edge_data['geometry']
                                    if hasattr(geom, 'coords'):
                                        route_coords.extend(list(geom.coords))

                        if route_coords:
                            # Add route polyline
                            folium.PolyLine(
                                route_coords,
                                color=color,
                                weight=4,
                                opacity=0.8,
                                popup=folium.Popup(
                                    f"<b>🛣️ Detour Route</b><br>"
                                    f"Status: {'✅ Valid' if is_valid else '❌ Invalid'}<br>"
                                    f"Travel Time: {travel_time:.1f}s<br>"
                                    f"Freeflow Time: {freeflow_time:.1f}s<br>"
                                    f"Nodes: {len(path)}",
                                    max_width=200
                                )
                            ).add_to(map_obj)
            except Exception as e:
                st.warning(f"Could not add detour routes: {e}")

    def _add_turn_nodes(self, map_obj: folium.Map):
        """Add turn nodes to map."""
        if st.session_state.get('turn_nodes') and st.session_state.get('show_turn_nodes', True):
            try:
                turn_nodes = st.session_state.turn_nodes
                graph = st.session_state.graph

                # Add start turn nodes
                for node in turn_nodes.get('start_nodes', []):
                    if node in graph.nodes:
                        node_data = graph.nodes[node]
                        if 'geometry' in node_data and node_data['geometry'] is not None:
                            geom = node_data['geometry']
                            folium.CircleMarker(
                                [geom.y, geom.x],
                                radius=6,
                                color='green',
                                fill=True,
                                fillColor='lightgreen',
                                popup=folium.Popup(f"<b>🟢 Start Turn Node</b><br>Node: {node}", max_width=150)
                            ).add_to(map_obj)

                # Add end turn nodes
                for node in turn_nodes.get('end_nodes', []):
                    if node in graph.nodes:
                        node_data = graph.nodes[node]
                        if 'geometry' in node_data and node_data['geometry'] is not None:
                            geom = node_data['geometry']
                            folium.CircleMarker(
                                [geom.y, geom.x],
                                radius=6,
                                color='red',
                                fill=True,
                                fillColor='lightcoral',
                                popup=folium.Popup(f"<b>🔴 End Turn Node</b><br>Node: {node}", max_width=150)
                            ).add_to(map_obj)
            except Exception as e:
                st.warning(f"Could not add turn nodes: {e}")

    def _add_impacted_arterials(self, map_obj: folium.Map):
        """Add impacted arterials to map."""
        if st.session_state.get('impacted_arterials') and st.session_state.get('show_impacted_arterials', True):
            try:
                impacted_arterials = st.session_state.impacted_arterials
                graph = st.session_state.graph

                for edge in impacted_arterials:
                    if graph.has_edge(*edge):
                        edge_data = graph.edges[edge]
                        if 'geometry' in edge_data and edge_data['geometry'] is not None:
                            geom = edge_data['geometry']
                            if hasattr(geom, 'coords'):
                                coords = list(geom.coords)
                                folium.PolyLine(
                                    coords,
                                    color='yellow',
                                    weight=3,
                                    opacity=0.6,
                                    popup=folium.Popup(
                                        f"<b>🟡 Impacted Arterial</b><br>"
                                        f"Edge: {edge}<br>"
                                        f"Type: {edge_data.get('highway', 'unknown')}",
                                        max_width=200
                                    )
                                ).add_to(map_obj)
            except Exception as e:
                st.warning(f"Could not add impacted arterials: {e}")

    def _get_road_color(self, highway_type: str) -> str:
        """Get color for road type."""
        color_map = {
            'motorway': 'red',
            'trunk': 'orange',
            'primary': 'blue',
            'secondary': 'green',
            'tertiary': 'purple',
            'residential': 'gray',
            'service': 'lightgray'
        }
        return color_map.get(highway_type, 'black')

    def _get_road_weight(self, highway_type: str) -> int:
        """Get weight for road type."""
        weight_map = {
            'motorway': 4,
            'trunk': 3,
            'primary': 3,
            'secondary': 2,
            'tertiary': 2,
            'residential': 1,
            'service': 1
        }
        return weight_map.get(highway_type, 1)

    def _handle_map_interactions(self, map_data: Dict[str, Any]):
        """Handle map interactions."""
        if map_data.get('last_object_clicked'):
            clicked_data = map_data['last_object_clicked']

            # Handle incident selection
            if clicked_data.get('type') == 'marker':
                # This would handle marker clicks
                pass
            elif clicked_data.get('type') == 'polyline':
                # This would handle road segment clicks
                pass

    def _render_map_controls(self):
        """Render map control options."""
        st.subheader("🎛️ Map Controls")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.session_state.show_road_network = st.checkbox(
                "Show Road Network",
                value=st.session_state.get('show_road_network', True),
                key="show_road_network"
            )

        with col2:
            st.session_state.show_detour_routes = st.checkbox(
                "Show Detour Routes",
                value=st.session_state.get('show_detour_routes', True),
                key="show_detour_routes"
            )

        with col3:
            st.session_state.show_turn_nodes = st.checkbox(
                "Show Turn Nodes",
                value=st.session_state.get('show_turn_nodes', True),
                key="show_turn_nodes"
            )

        col4, col5, col6 = st.columns(3)

        with col4:
            st.session_state.show_impacted_arterials = st.checkbox(
                "Show Impacted Arterials",
                value=st.session_state.get('show_impacted_arterials', True),
                key="show_impacted_arterials"
            )

        with col5:
            if st.button("🎯 Zoom to Jurisdiction", key="zoom_to_jurisdiction"):
                self._zoom_to_jurisdiction()

        with col6:
            if st.button("🔄 Refresh Map", key="refresh_map"):
                st.rerun()

    def _zoom_to_jurisdiction(self):
        """Zoom map to jurisdiction bounds."""
        if st.session_state.get('jurisdiction_boundary'):
            try:
                bounds = st.session_state.jurisdiction_boundary.bounds
                center_lat = (bounds[1] + bounds[3]) / 2
                center_lon = (bounds[0] + bounds[2]) / 2

                st.session_state.map_center_lat = center_lat
                st.session_state.map_center_lon = center_lon
                st.session_state.map_zoom = 10

                st.success("Map zoomed to jurisdiction")
                st.rerun()
            except Exception as e:
                st.error(f"Could not zoom to jurisdiction: {e}")
        else:
            st.warning("No jurisdiction boundary available")
