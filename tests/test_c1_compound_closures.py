"""
Unit and regression tests for Package C1: Compound & Multi-Link Closures.
Verifies routing invariants, multi-edge removal, graph immutability,
and prevention of accidental unref'd road blocking.
"""

import pytest
import networkx as nx
from shapely.geometry import LineString, Polygon, Point
import detour_utils as du


@pytest.fixture
def sample_network():
    """
    Creates a synthetic MultiDiGraph with mainline highway and parallel arterial detour:
    Nodes: 0 -> 1 -> 2 -> 3 -> 4 (Mainline, ref="I-95", speed=100)
    Arterial detour: 0 -> 10 -> 20 -> 30 -> 4 (Local arterial, ref=None, speed=50)
    Cross connections: 1 -> 10, 20 -> 2, 3 -> 30
    """
    G = nx.MultiDiGraph()
    G.graph['crs'] = 'EPSG:4326'

    # Mainline coordinates
    coords = {
        0: (-77.0, 38.0),
        1: (-77.0, 38.1),
        2: (-77.0, 38.2),
        3: (-77.0, 38.3),
        4: (-77.0, 38.4),
        10: (-76.9, 38.1),
        20: (-76.9, 38.2),
        30: (-76.9, 38.3)
    }

    for n, (x, y) in coords.items():
        G.add_node(n, x=x, y=y, turns=[])

    # Mainline edges (I-95)
    for u, v in [(0, 1), (1, 2), (2, 3), (3, 4)]:
        geom = LineString([coords[u], coords[v]])
        G.add_edge(u, v, key=0, ref="I-95", highway="motorway",
                   travel_time=60.0, total_time=60.0, length=1000.0,
                   geometry=geom, start_bearing=0.0, end_bearing=0.0)

    # Parallel arterial edges (ref is None - tests that None is not accidentally blocked!)
    for u, v in [(0, 10), (10, 20), (20, 30), (30, 4)]:
        geom = LineString([coords[u], coords[v]])
        G.add_edge(u, v, key=0, ref=None, highway="secondary",
                   travel_time=120.0, total_time=120.0, length=1500.0,
                   geometry=geom, start_bearing=0.0, end_bearing=0.0)

    # Ramps / cross connectors
    G.add_edge(1, 10, key=0, ref=None, highway="motorway_link", travel_time=30.0, total_time=30.0, length=200.0, geometry=LineString([coords[1], coords[10]]), start_bearing=90.0, end_bearing=90.0)
    G.add_edge(30, 3, key=0, ref=None, highway="motorway_link", travel_time=30.0, total_time=30.0, length=200.0, geometry=LineString([coords[30], coords[3]]), start_bearing=270.0, end_bearing=270.0)

    return G


def test_normalize_incident_edges():
    """Verifies normalize_incident_edges handles single and compound inputs."""
    # Single 2-tuple
    assert du.normalize_incident_edges((1, 2)) == [(1, 2)]
    # Single 3-tuple
    assert du.normalize_incident_edges((1, 2, 0)) == [(1, 2, 0)]
    # List of tuples
    assert du.normalize_incident_edges([(1, 2, 0), (2, 3, 0)]) == [(1, 2, 0), (2, 3, 0)]
    # Set of tuples
    normalized = du.normalize_incident_edges({(1, 2, 0), (2, 3, 0)})
    assert len(normalized) == 2
    # None or empty
    assert du.normalize_incident_edges(None) == []
    assert du.normalize_incident_edges([]) == []


def test_single_incident_closure_preserves_unrelated_unrefed_roads(sample_network):
    """
    Regression test for B2/B3:
    Ensures that an incident on an unref'd road does NOT block all other unref'd roads.
    """
    G = sample_network
    unref_edge = (1, 10, 0)
    G_inc = du.generate_incident_graph(G, unref_edge)

    # Unrelated unref'd arterial edge (10, 20) MUST NOT be blocked (total_time < 1e9)
    assert G_inc.edges[(10, 20, 0)]['total_time'] == 120.0
    # Closed edge must be blocked
    assert G_inc.edges[unref_edge]['total_time'] >= 1e9


def test_compound_multi_link_closure(sample_network):
    """
    Package C1 Core Test:
    Closes a 2-segment corridor on I-95: [(1, 2, 0), (2, 3, 0)].
    Verifies that get_detour routes via arterial (0 -> 10 -> 20 -> 30 -> 4)
    and strictly avoids all closed segments.
    """
    G = sample_network
    closed_corridor = [(1, 2, 0), (2, 3, 0)]

    detours = du.get_detour(
        G_input=G,
        incident_edges=closed_corridor,
        start_nodes=[0],
        end_nodes=[4],
        traveltime_min=0,
        traveltime_max=3600
    )

    route_key = (0, 4)
    assert route_key in detours
    status, total_t, freeflow_t, path = detours[route_key]

    assert status is True
    assert path is not None
    # Path must use arterial nodes
    assert 10 in path and 20 in path and 30 in path
    # Path must NOT contain any closed nodes in sequence
    assert (1, 2) not in zip(path[:-1], path[1:])
    assert (2, 3) not in zip(path[:-1], path[1:])

    # Graph immutability: Original graph G still has the closed edges
    assert G.has_edge(1, 2, 0)
    assert G.has_edge(2, 3, 0)


def test_polygon_closure_extraction(sample_network):
    """
    Package C2 Prep Test:
    Verifies get_edges_in_polygon identifies edges intersecting a bounding box polygon.
    """
    G = sample_network
    # Bounding polygon covering node 2 and its adjacent edges
    poly = Polygon([
        (-77.05, 38.15),
        (-76.95, 38.15),
        (-76.95, 38.25),
        (-77.05, 38.25)
    ])

    intersected_edges = du.get_edges_in_polygon(G, poly)
    assert len(intersected_edges) > 0

    # Test closing via polygon
    detours = du.get_detour(
        G_input=G,
        incident_edges=intersected_edges,
        start_nodes=[0],
        end_nodes=[4],
        traveltime_min=0,
        traveltime_max=3600
    )

    status, _, _, path = detours[(0, 4)]
    # All paths must avoid the polygon closure
    for u, v in zip(path[:-1], path[1:]):
        assert (u, v, 0) not in intersected_edges
