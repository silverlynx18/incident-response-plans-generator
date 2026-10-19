"""
Unit tests for ARPL core routing and detour calculation algorithms.
"""

import pytest
import math
import networkx as nx
from shapely.geometry import LineString
from pyproj import Transformer

from arpl.core import detour_utils as du

class TestDetourCoreAlgorithms:
    """Test geometric and graph helper functions in detour_utils."""

    def test_calculate_linestring_length(self):
        """Test calculating line string distance in meters with coordinate projection."""
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
        # Line spanning 0.01 degrees (~1.1 km)
        line = LineString([(-77.0369, 38.9072), (-77.0369, 38.9172)])
        length_m = du.calculate_linestring_length(line, transformer=transformer)
        assert length_m > 1000
        assert length_m < 1500

    def test_bearing_calculation(self):
        """Test geographic bearing calculations with (lon, lat) inputs."""
        pointA = (-77.0, 38.0)
        pointB = (-77.0, 39.0)  # Due North
        b_north = du.bearing(pointA, pointB)
        assert abs(b_north - 0.0) < 1.0 or abs(b_north - 360.0) < 1.0

        pointEast = (-76.0, 38.0)  # Due East
        b_east = du.bearing(pointA, pointEast)
        assert abs(b_east - 90.0) < 2.0

    def test_bearing_diff(self):
        """Test angular differences between bearings."""
        assert du.bearing_diff(10, 350) == 20
        assert du.bearing_diff(0, 180) == 180
        assert du.bearing_diff(90, 100) == 10

    def test_normalize_speed_to_kph(self):
        """Test speed string normalization."""
        assert du.normalize_speed_to_kph("25 mph") == 25 * 1.60934
        assert du.normalize_speed_to_kph("60 km/h") == 60.0
        assert du.normalize_speed_to_kph("45", default_unit="mph") == 45 * 1.60934
        assert du.normalize_speed_to_kph("50") == 50.0

    def test_synthetic_graph_detour(self):
        """Test finding detours on a synthetic road network."""
        # Create a simple diamond network:
        # 1 -> 2 (incident edge)
        # 1 -> 3 -> 2 (detour edge)
        G = nx.MultiDiGraph()
        G.graph['crs'] = 'EPSG:4326'

        G.add_node(1, x=-77.00, y=38.00)
        G.add_node(2, x=-77.00, y=38.02)
        G.add_node(3, x=-77.01, y=38.01)

        # Incident edge
        G.add_edge(1, 2, key=0, length=2000, travel_time=120, total_time=120, ref='US-1', start_bearing=0, end_bearing=0)
        # Alternate path
        G.add_edge(1, 3, key=0, length=1500, travel_time=90, total_time=90, ref='Alt-1', start_bearing=315, end_bearing=315)
        G.add_edge(3, 2, key=0, length=1500, travel_time=90, total_time=90, ref='Alt-1', start_bearing=45, end_bearing=45)

        detours = du.get_detour(G, incident_edge=(1, 2, 0), start_nodes=[1], end_nodes=[2], traveltime_min=30, traveltime_max=600)
        assert len(detours) > 0
        assert (1, 2) in detours
        is_valid, total_time, freeflow, path = detours[(1, 2)]
        assert is_valid is True
        assert path == [1, 3, 2]
        assert freeflow == 180
