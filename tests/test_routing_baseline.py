"""
Unit tests for ARPL Stage 0 Detour Engine Baseline
===================================================
Tests covering:
- Known shortest path and cost calculation (Dijkstra and A*)
- Disconnected origin/destination pairs without unhandled exceptions
- Edge removal preservation (base input graph immutability)
- MultiDiGraph parallel edge integrity (parallel carriageways and opposing lanes)
- Keyed geometry reconstruction preserving curved geometries
- Time and distance boundary constraints (<120s floor, >max ceiling)
- Composite scoring and deterministic ranking

References:
- Work Wiki/Topics/ITS/ARPL/ARPL Development Roadmap.md (§Stage 0: B1, B2, B3)
- Work Wiki/Topics/ITS/ARPL/ARPL Technical Reference.md (B01-B10)
"""

import unittest
import math
import os
import sys

# Ensure parent directory is in sys.path
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import networkx as nx
from shapely.geometry import LineString, Point

from detour_engine import (
    DetourEngine,
    IncidentClosure,
    AnalysisParameters,
    RouteResult,
    prepare_incident_graph,
    find_keyed_shortest_path_dijkstra,
    find_keyed_shortest_path_astar,
    reconstruct_route_geometry,
    calculate_route_metrics,
    compute_route_score
)


class TestRoutingBaseline(unittest.TestCase):

    def setUp(self):
        """
        Creates a synthetic directed MultiDiGraph fixture representing a corridor
        with parallel carriageways, arterial detours, and opposing lanes.
        
        Topology:
          N0 (Start) -----(key 0: mainline express, 1000m, 50s)-----> N1
                     -----(key 1: frontage road,   1200m, 90s)-----> N1
                     <----(key 0: opposing lane,   1000m, 50s)------ N1
                     -----(key 0: off-ramp to arterial, 800m, 60s)-> N2
          
          N1 --------(key 0: mainline cont., 2000m, 100s)----------> N3 (End)
          
          N2 --------(key 0: arterial diversion, 2500m, 150s)------> N3
          
          N4, N5: Disconnected component.
        """
        self.G = nx.MultiDiGraph()

        # Nodes with spatial coordinates (EPSG:4326 mock)
        self.G.add_node("N0", x=-77.0365, y=38.8977)  # Origin
        self.G.add_node("N1", x=-77.0265, y=38.8977)  # Mid mainline
        self.G.add_node("N2", x=-77.0315, y=38.9050)  # North arterial
        self.G.add_node("N3", x=-77.0100, y=38.8977)  # Destination
        self.G.add_node("N4", x=-77.1000, y=38.8000)  # Disconnected node
        self.G.add_node("N5", x=-77.1100, y=38.8000)  # Disconnected node

        # Curved geometry for mainline express (key 0)
        geom_express = LineString([
            (-77.0365, 38.8977),
            (-77.0315, 38.8978),
            (-77.0265, 38.8977)
        ])

        # Distinct curved geometry for frontage road (key 1)
        geom_frontage = LineString([
            (-77.0365, 38.8977),
            (-77.0315, 38.8965),
            (-77.0265, 38.8977)
        ])

        # 1. Parallel edges from N0 -> N1
        # Key 0: Express lane (fast)
        self.G.add_edge(
            "N0", "N1", key=0,
            length=1000.0, speed_kph=72.0, travel_time=50.0, total_time=50.0,
            freeflow_time=50.0, geometry=geom_express, name="I-95 Express NB"
        )
        # Key 1: Frontage road (slower parallel carriageway)
        self.G.add_edge(
            "N0", "N1", key=1,
            length=1200.0, speed_kph=48.0, travel_time=90.0, total_time=90.0,
            freeflow_time=90.0, geometry=geom_frontage, name="I-95 Frontage NB"
        )

        # 2. Opposing lane N1 -> N0 (Southbound)
        self.G.add_edge(
            "N1", "N0", key=0,
            length=1000.0, speed_kph=72.0, travel_time=50.0, total_time=50.0,
            freeflow_time=50.0, name="I-95 SB"
        )

        # 3. Off-ramp to arterial diversion N0 -> N2
        self.G.add_edge(
            "N0", "N2", key=0,
            length=800.0, speed_kph=48.0, travel_time=60.0, total_time=60.0,
            freeflow_time=60.0, name="Exit 1 Ramp"
        )

        # 4. Continuation N1 -> N3
        self.G.add_edge(
            "N1", "N3", key=0,
            length=2000.0, speed_kph=72.0, travel_time=100.0, total_time=100.0,
            freeflow_time=100.0, name="I-95 NB Mainline"
        )

        # 5. Arterial link N2 -> N3
        self.G.add_edge(
            "N2", "N3", key=0,
            length=2500.0, speed_kph=60.0, travel_time=150.0, total_time=150.0,
            freeflow_time=150.0, name="US-1 Arterial"
        )

        # 6. Isolated edge in separate component
        self.G.add_edge(
            "N4", "N5", key=0,
            length=500.0, speed_kph=50.0, travel_time=36.0, total_time=36.0,
            freeflow_time=36.0, name="Isolated Island St"
        )

        # Set up engine with relaxed min_time for test flexibility
        self.params = AnalysisParameters(min_time_s=100.0, max_time_s=1000.0)
        self.engine = DetourEngine(self.G, self.params)

    def test_known_shortest_path_dijkstra(self):
        """
        Verifies Dijkstra finds the exact known optimal path and costs on the unblocked graph.
        Optimal: N0 -> N1 (key 0, 50s) -> N3 (key 0, 100s) = 150s, 3000m.
        """
        node_path, edge_path, total_cost = find_keyed_shortest_path_dijkstra(
            self.G, "N0", "N3", weight="total_time"
        )
        self.assertEqual(node_path, ["N0", "N1", "N3"])
        self.assertEqual(edge_path, [("N0", "N1", 0), ("N1", "N3", 0)])
        self.assertEqual(total_cost, 150.0)

    def test_known_shortest_path_astar(self):
        """
        Verifies A* pathfinding finds the identical optimal path and cost as Dijkstra.
        """
        node_path, edge_path, total_cost = find_keyed_shortest_path_astar(
            self.G, "N0", "N3", weight="total_time"
        )
        self.assertEqual(node_path, ["N0", "N1", "N3"])
        self.assertEqual(edge_path, [("N0", "N1", 0), ("N1", "N3", 0)])
        self.assertAlmostEqual(total_cost, 150.0, places=2)

    def test_disconnected_pairs(self):
        """
        Verifies that querying path between disconnected components (N0 -> N5)
        returns valid=False with an explicit reason, without raising an unhandled exception.
        """
        result = self.engine.find_detour(
            incident_closures=[],
            origin="N0",
            destination="N5"
        )
        self.assertFalse(result.valid)
        self.assertIn("No Route", result.rejection_reason)
        self.assertEqual(result.node_path, [])
        self.assertEqual(result.edge_path, [])
        self.assertIsNone(result.geometry)

    def test_edge_removal_preserves_input_graph(self):
        """
        Verifies that closing an incident edge produces an altered working graph
        while the original base graph `self.G` remains completely intact and unmodified.
        """
        closure = IncidentClosure(u="N0", v="N1", key=0)
        
        # Verify edge exists in base graph
        self.assertTrue(self.G.has_edge("N0", "N1", key=0))
        orig_data = dict(self.G["N0"]["N1"][0])

        # Prepare incident graph
        G_inc = prepare_incident_graph(self.G, closure, hard_removal=True)

        # Edge must be gone in working graph
        self.assertFalse(G_inc.has_edge("N0", "N1", key=0))

        # Base graph MUST still retain the edge and exact attributes
        self.assertTrue(self.G.has_edge("N0", "N1", key=0))
        self.assertEqual(self.G["N0"]["N1"][0]["name"], orig_data["name"])
        self.assertEqual(self.G["N0"]["N1"][0]["total_time"], orig_data["total_time"])

    def test_multidigraph_parallel_edge_integrity(self):
        """
        CRITICAL TEST (Roadmap B1, B2):
        Parallel carriageway integrity:
        Closing (N0, N1, key=0) MUST NOT remove parallel edge (N0, N1, key=1).
        Opposing lane (N1, N0, key=0) MUST NOT be removed.
        Unrelated outgoing edge (N0, N2, key=0) MUST NOT be removed.
        Routing must successfully divert across the parallel carriageway (key=1).
        """
        closure = IncidentClosure(u="N0", v="N1", key=0)
        G_inc = prepare_incident_graph(self.G, closure, hard_removal=True)

        # 1. Key 0 removed, but Key 1 remains
        self.assertFalse(G_inc.has_edge("N0", "N1", key=0))
        self.assertTrue(G_inc.has_edge("N0", "N1", key=1))

        # 2. Opposing lane preserved
        self.assertTrue(G_inc.has_edge("N1", "N0", key=0))

        # 3. Unrelated outgoing link preserved
        self.assertTrue(G_inc.has_edge("N0", "N2", key=0))

        # 4. Detour routing using parallel edge:
        # Cost via parallel frontage road: 90s + 100s = 190s.
        # Cost via arterial diversion: 60s + 150s = 210s.
        # Shortest alternate route MUST choose parallel frontage road (N0, N1, key=1)!
        node_path, edge_path, total_cost = find_keyed_shortest_path_dijkstra(
            G_inc, "N0", "N3", weight="total_time"
        )
        self.assertEqual(node_path, ["N0", "N1", "N3"])
        self.assertEqual(edge_path, [("N0", "N1", 1), ("N1", "N3", 0)])
        self.assertEqual(total_cost, 190.0)

    def test_corridor_diversion_when_both_parallel_lanes_closed(self):
        """
        When both express (key 0) and frontage (key 1) are closed,
        routing must divert to arterial: N0 -> N2 (key 0) -> N3 (key 0) = 210s, 3300m.
        """
        closures = [
            IncidentClosure(u="N0", v="N1", key=0),
            IncidentClosure(u="N0", v="N1", key=1)
        ]
        result = self.engine.find_detour(closures, origin="N0", destination="N3")
        self.assertTrue(result.valid)
        self.assertEqual(result.node_path, ["N0", "N2", "N3"])
        self.assertEqual(result.edge_path, [("N0", "N2", 0), ("N2", "N3", 0)])
        self.assertEqual(result.distance_m, 3300.0)
        self.assertAlmostEqual(result.freeflow_time_s, 210.0, places=1)
        self.assertEqual(result.num_turns, 1)
        self.assertGreater(result.turn_penalty_s, 0.0)
        self.assertAlmostEqual(result.total_time_s, 210.0 + result.turn_penalty_s, places=2)

    def test_keyed_geometry_reconstruction(self):
        """
        Verifies that reconstruct_route_geometry faithfully retrieves the exact
        LineString attached to the chosen keyed edge, preserving distinct curves.
        """
        # When key 0 is routed:
        geom_0 = reconstruct_route_geometry(self.G, [("N0", "N1", 0)])
        self.assertIsNotNone(geom_0)
        self.assertIsInstance(geom_0, LineString)
        # Midpoint of key 0 is (-77.0315, 38.8978)
        self.assertEqual(geom_0.coords[1], (-77.0315, 38.8978))

        # When key 1 is routed:
        geom_1 = reconstruct_route_geometry(self.G, [("N0", "N1", 1)])
        self.assertIsNotNone(geom_1)
        self.assertIsInstance(geom_1, LineString)
        # Midpoint of key 1 is (-77.0315, 38.8965)
        self.assertEqual(geom_1.coords[1], (-77.0315, 38.8965))

        # Geometries must NOT be identical
        self.assertNotEqual(geom_0, geom_1)

    def test_time_and_distance_boundaries(self):
        """
        Verifies Roadmap B3 boundary conditions:
        - Routes with total_time < min_time (e.g. 120s floor) marked invalid ("Too Short").
        - Routes with total_time > max_time marked invalid ("Too Long").
        - Distance ceiling enforced.
        """
        # Strict 120s floor and 180s ceiling
        params = AnalysisParameters(min_time_s=120.0, max_time_s=180.0, max_distance_m=3100.0)
        engine = DetourEngine(self.G, params)

        # 1. Test short trip: N0 -> N1 (key 0) takes 50s (<120s)
        res_short = engine.find_detour([], origin="N0", destination="N1")
        self.assertFalse(res_short.valid)
        self.assertIn("Too Short", res_short.rejection_reason)

        # 2. Test trip exceeding max_time: close N0->N1, diversion takes 210s (>180s)
        closures = [
            IncidentClosure(u="N0", v="N1", key=0),
            IncidentClosure(u="N0", v="N1", key=1)
        ]
        res_long = engine.find_detour(closures, origin="N0", destination="N3")
        self.assertFalse(res_long.valid)
        self.assertIn("Too Long", res_long.rejection_reason)

        # 3. Test distance ceiling: diversion is 3300m (>3100m)
        params_dist = AnalysisParameters(min_time_s=100.0, max_time_s=500.0, max_distance_m=3100.0)
        engine_dist = DetourEngine(self.G, params_dist)
        res_dist = engine_dist.find_detour(closures, origin="N0", destination="N3")
        self.assertFalse(res_dist.valid)
        self.assertIn("Too Far", res_dist.rejection_reason)

    def test_scoring_ranking(self):
        """
        Verifies deterministic ranking via ARPL composite score:
        score = 0.7 * total_time + 0.2 * nodes + 100 * (1 - freeflow_time / total_time)
        Lower is better.
        """
        score_fast = compute_route_score(total_time_s=150.0, freeflow_time_s=150.0, num_nodes=3)
        # When freeflow == total: 0.7 * 150 + 0.2 * 3 + 0 = 105.0 + 0.6 = 105.6
        self.assertAlmostEqual(score_fast, 105.6, places=2)

        score_delayed = compute_route_score(total_time_s=200.0, freeflow_time_s=150.0, num_nodes=3)
        # When delayed: 0.7 * 200 + 0.2 * 3 + 100 * (1 - 150/200) = 140.0 + 0.6 + 25.0 = 165.6
        self.assertAlmostEqual(score_delayed, 165.6, places=2)
        self.assertGreater(score_delayed, score_fast)


if __name__ == "__main__":
    unittest.main()
