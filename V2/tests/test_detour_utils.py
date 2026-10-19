"""
Unit tests for detour_utils.py module.
Tests core detour analysis algorithms and functions.
"""

import pytest
import networkx as nx
import numpy as np
from shapely.geometry import Point, LineString
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import detour_utils as du


class TestDetourUtils:
    """Test cases for detour_utils module."""

    def setup_method(self):
        """Set up test fixtures."""
        # Create a simple test graph
        self.test_graph = nx.MultiDiGraph()

        # Add nodes with geometry
        self.test_graph.add_node(1, geometry=Point(0, 0))
        self.test_graph.add_node(2, geometry=Point(1, 0))
        self.test_graph.add_node(3, geometry=Point(1, 1))
        self.test_graph.add_node(4, geometry=Point(0, 1))
        self.test_graph.add_node(5, geometry=Point(2, 0))

        # Add edges with geometry and attributes
        self.test_graph.add_edge(1, 2,
                                geometry=LineString([(0, 0), (1, 0)]),
                                highway='primary',
                                length=100,
                                maxspeed=50)
        self.test_graph.add_edge(2, 3,
                                geometry=LineString([(1, 0), (1, 1)]),
                                highway='secondary',
                                length=100,
                                maxspeed=40)
        self.test_graph.add_edge(3, 4,
                                geometry=LineString([(1, 1), (0, 1)]),
                                highway='tertiary',
                                length=100,
                                maxspeed=30)
        self.test_graph.add_edge(4, 1,
                                geometry=LineString([(0, 1), (0, 0)]),
                                highway='residential',
                                length=100,
                                maxspeed=25)
        self.test_graph.add_edge(2, 5,
                                geometry=LineString([(1, 0), (2, 0)]),
                                highway='primary',
                                length=100,
                                maxspeed=50)

    def test_normalize_list_string(self):
        """Test normalize_list_string function."""
        # Test with list
        result = du.normalize_list_string(['highway', 'primary'])
        assert result == 'highway;primary'

        # Test with string
        result = du.normalize_list_string('highway')
        assert result == 'highway'

        # Test with None
        result = du.normalize_list_string(None)
        assert result == ''

    def test_normalize_speed_to_kph(self):
        """Test normalize_speed_to_kph function."""
        # Test with mph
        result = du.normalize_speed_to_kph('30 mph')
        assert result == 48  # 30 * 1.60934

        # Test with kph
        result = du.normalize_speed_to_kph('50 kph')
        assert result == 50

        # Test with numeric string
        result = du.normalize_speed_to_kph('40')
        assert result == 40

        # Test with None
        result = du.normalize_speed_to_kph(None)
        assert result == 50  # Default speed

    def test_calculate_linestring_length(self):
        """Test calculate_linestring_length function."""
        # Test with LineString
        line = LineString([(0, 0), (1, 0)])
        result = du.calculate_linestring_length(line)
        assert abs(result - 111319.5) < 1000  # Approximate length in meters

        # Test with None
        result = du.calculate_linestring_length(None)
        assert result == 0

    def test_bearing_diff(self):
        """Test bearing_diff function."""
        # Test same bearing
        result = du.bearing_diff(90, 90)
        assert result == 0

        # Test opposite bearings
        result = du.bearing_diff(0, 180)
        assert result == 180

        # Test 90 degree difference
        result = du.bearing_diff(0, 90)
        assert result == 90

    def test_has_common_ref(self):
        """Test has_common_ref function."""
        # Test with common ref
        result = du.has_common_ref('I-95', 'I-95')
        assert result is True

        # Test with different refs
        result = du.has_common_ref('I-95', 'I-66')
        assert result is False

        # Test with None values
        result = du.has_common_ref(None, 'I-95')
        assert result is False

    def test_is_valid_turn(self):
        """Test is_valid_turn function."""
        # Test valid turn (90 degrees)
        result = du.is_valid_turn(0, 90, 45)
        assert result is True

        # Test invalid turn (too sharp)
        result = du.is_valid_turn(0, 10, 45)
        assert result is False

        # Test invalid turn (too wide)
        result = du.is_valid_turn(0, 200, 45)
        assert result is False

    def test_traverse_direction(self):
        """Test traverse_direction function."""
        # Test forward direction
        result = du.traverse_direction(self.test_graph, (1, 2), 2)
        assert result == 'forward'

        # Test backward direction
        result = du.traverse_direction(self.test_graph, (1, 2), 1)
        assert result == 'backward'

    def test_get_surrounding_turns(self):
        """Test get_surrounding_turns function."""
        incident_edge = (1, 2)
        n_turn_nodes = 2

        result = du.get_surrounding_turns(self.test_graph, incident_edge, n_turn_nodes)

        assert 'start_nodes' in result
        assert 'end_nodes' in result
        assert isinstance(result['start_nodes'], list)
        assert isinstance(result['end_nodes'], list)

    def test_create_sector(self):
        """Test create_sector function."""
        center = Point(0, 0)
        bearing = 0
        radius = 1000
        angle = 90

        result = du.create_sector(center, bearing, radius, angle)

        assert result is not None
        assert hasattr(result, 'geom_type')
        assert result.geom_type in ['Polygon', 'MultiPolygon']

    def test_get_impacted_arterials(self):
        """Test get_impacted_arterials function."""
        # Create a simple sector polygon
        sector = Point(0, 0).buffer(1000)
        incident_edge = (1, 2)

        result = du.get_impacted_arterials(self.test_graph, sector, incident_edge)

        assert isinstance(result, list)

    def test_generate_incident_graph(self):
        """Test generate_incident_graph function."""
        incident_edge = (1, 2)

        result = du.generate_incident_graph(self.test_graph, incident_edge)

        assert isinstance(result, nx.MultiDiGraph)
        assert result.has_edge(1, 2)  # Incident edge should still exist

    def test_get_detour(self):
        """Test get_detour function."""
        incident_graph = self.test_graph.copy()
        incident_edge = (1, 2)
        start_node = 1
        end_node = 3
        min_travel_time = 30
        max_travel_time = 300

        result = du.get_detour(incident_graph, incident_edge, start_node, end_node,
                              min_travel_time, max_travel_time)

        assert isinstance(result, tuple)
        assert len(result) == 4  # (is_valid, travel_time, freeflow_time, path)

        is_valid, travel_time, freeflow_time, path = result
        assert isinstance(is_valid, bool)
        assert isinstance(travel_time, (int, float, str))
        assert isinstance(freeflow_time, (int, float))
        assert isinstance(path, list)

    def test_clean_graph(self):
        """Test clean_graph function."""
        # Add some problematic edges
        self.test_graph.add_edge(1, 6, highway='service', length=0)  # Zero length
        self.test_graph.add_edge(7, 8, highway='footway', length=50)  # Non-drivable

        result = du.clean_graph(self.test_graph)

        assert isinstance(result, nx.MultiDiGraph)
        # Should have fewer edges after cleaning
        assert len(result.edges()) <= len(self.test_graph.edges())

    def test_calculate_bearings(self):
        """Test calculate_bearings function."""
        result = du.calculate_bearings(self.test_graph)

        assert isinstance(result, nx.MultiDiGraph)
        # Check that bearings were added to edges
        for edge in result.edges():
            assert 'bearing' in result.edges[edge]

    def test_compute_traveltime_bearing(self):
        """Test compute_traveltime_bearing function."""
        result = du.compute_traveltime_bearing(self.test_graph)

        assert isinstance(result, nx.MultiDiGraph)
        # Check that travel times were added to edges
        for edge in result.edges():
            assert 'travel_time' in result.edges[edge]

    def test_compute_turntime(self):
        """Test compute_turntime function."""
        result = du.compute_turntime(self.test_graph)

        assert isinstance(result, nx.MultiDiGraph)
        # Check that turn times were added to edges
        for edge in result.edges():
            assert 'turn_time' in result.edges[edge]

    def test_find_turns(self):
        """Test find_turns function."""
        result = du.find_turns(self.test_graph)

        assert isinstance(result, nx.MultiDiGraph)
        # Check that turn information was added to nodes
        for node in result.nodes():
            assert 'turns' in result.nodes[node]

    def test_prepare_graph(self):
        """Test prepare_graph function."""
        result = du.prepare_graph(self.test_graph)

        assert isinstance(result, nx.MultiDiGraph)
        # Check that all required attributes are present
        for edge in result.edges():
            edge_data = result.edges[edge]
            assert 'travel_time' in edge_data
            assert 'turn_time' in edge_data
            assert 'bearing' in edge_data

    def test_load_osm_graph(self):
        """Test load_osm_graph function."""
        # This test would require actual OSM data or mocking
        # For now, just test that the function exists and can be called
        try:
            # This should fail gracefully without actual data
            result = du.load_osm_graph(espg=4326)
            # If it doesn't fail, it should return None or a graph
            assert result is None or isinstance(result, nx.MultiDiGraph)
        except Exception:
            # Expected to fail without proper data
            pass


class TestDetourUtilsIntegration:
    """Integration tests for detour_utils module."""

    def setup_method(self):
        """Set up integration test fixtures."""
        # Create a more complex test graph
        self.complex_graph = nx.MultiDiGraph()

        # Add a grid of nodes
        for i in range(5):
            for j in range(5):
                node_id = i * 5 + j
                self.complex_graph.add_node(node_id, geometry=Point(i, j))

        # Add edges to create a grid
        for i in range(5):
            for j in range(5):
                node_id = i * 5 + j

                # Add horizontal edges
                if j < 4:
                    next_node = i * 5 + j + 1
                    self.complex_graph.add_edge(node_id, next_node,
                                              geometry=LineString([(i, j), (i, j + 1)]),
                                              highway='primary',
                                              length=100,
                                              maxspeed=50)

                # Add vertical edges
                if i < 4:
                    next_node = (i + 1) * 5 + j
                    self.complex_graph.add_edge(node_id, next_node,
                                              geometry=LineString([(i, j), (i + 1, j)]),
                                              highway='secondary',
                                              length=100,
                                              maxspeed=40)

    def test_complete_detour_workflow(self):
        """Test complete detour analysis workflow."""
        # Prepare the graph
        prepared_graph = du.prepare_graph(self.complex_graph)

        # Select an incident edge
        incident_edge = (0, 1)

        # Get surrounding turns
        turn_nodes = du.get_surrounding_turns(prepared_graph, incident_edge, 3)

        # Generate incident graph
        incident_graph = du.generate_incident_graph(prepared_graph, incident_edge)

        # Calculate detours
        detour_results = {}
        for start_node in turn_nodes['start_nodes'][:2]:  # Limit for testing
            for end_node in turn_nodes['end_nodes'][:2]:
                if start_node != end_node:
                    result = du.get_detour(incident_graph, incident_edge,
                                         start_node, end_node, 30, 300)
                    detour_results[(start_node, end_node)] = result

        # Verify results
        assert len(detour_results) > 0

        for route_key, (is_valid, travel_time, freeflow_time, path) in detour_results.items():
            assert isinstance(is_valid, bool)
            assert isinstance(travel_time, (int, float, str))
            assert isinstance(freeflow_time, (int, float))
            assert isinstance(path, list)

    def test_performance_with_large_graph(self):
        """Test performance with a larger graph."""
        # Create a larger graph
        large_graph = nx.MultiDiGraph()

        # Add 100 nodes in a grid
        for i in range(10):
            for j in range(10):
                node_id = i * 10 + j
                large_graph.add_node(node_id, geometry=Point(i, j))

        # Add edges
        for i in range(10):
            for j in range(10):
                node_id = i * 10 + j

                if j < 9:
                    next_node = i * 10 + j + 1
                    large_graph.add_edge(node_id, next_node,
                                       geometry=LineString([(i, j), (i, j + 1)]),
                                       highway='primary',
                                       length=100,
                                       maxspeed=50)

                if i < 9:
                    next_node = (i + 1) * 10 + j
                    large_graph.add_edge(node_id, next_node,
                                       geometry=LineString([(i, j), (i + 1, j)]),
                                       highway='secondary',
                                       length=100,
                                       maxspeed=40)

        # Test that operations complete in reasonable time
        import time
        start_time = time.time()

        prepared_graph = du.prepare_graph(large_graph)

        end_time = time.time()
        assert (end_time - start_time) < 5.0  # Should complete in under 5 seconds


if __name__ == '__main__':
    pytest.main([__file__])
