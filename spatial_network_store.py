"""
Spatial Network Store & Partitioning Engine for ARPL.
Solves the monolithic whole-state memory bloat and multi-user session collision.
Partitions road networks into spatial bounding tiles, providing isolated, fast subgraphs
for emergency incident polygons without loading entire state networks into shared RAM.
"""

import os
import hashlib
import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Set
import networkx as nx
from shapely.geometry import Polygon, box, Point
from shapely.wkt import loads as load_wkt

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / "data" / "spatial_tiles"


class SpatialNetworkStore:
    """
    Manages spatial partitioning and caching of road networks.
    Extracts isolated subgraphs intersecting an incident corridor or bounding polygon
    with an expansion buffer for diversion routing.
    """

    def __init__(self, cache_dir: Optional[Path] = None, buffer_meters: float = 3000.0):
        self.cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.buffer_meters = buffer_meters
        # Approximate degree conversion for buffer at mid-latitudes
        self.deg_buffer = buffer_meters / 111320.0

    def compute_bounds_hash(self, minx: float, miny: float, maxx: float, maxy: float) -> str:
        """Generates a deterministic hash for a bounding box."""
        key = f"{round(minx, 4)}_{round(miny, 4)}_{round(maxx, 4)}_{round(maxy, 4)}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def extract_subgraph_in_bounds(
        self,
        base_graph: nx.MultiDiGraph,
        minx: float,
        miny: float,
        maxx: float,
        maxy: float,
        apply_buffer: bool = True
    ) -> nx.MultiDiGraph:
        """
        Extracts all nodes and directed edges within the bounding box plus buffer.
        Returns a fresh, isolated MultiDiGraph.
        """
        buf = self.deg_buffer if apply_buffer else 0.0
        bbox_poly = box(minx - buf, miny - buf, maxx + buf, maxy + buf)

        selected_nodes: Set[Any] = set()
        for node, data in base_graph.nodes(data=True):
            x = data.get("x")
            y = data.get("y")
            if x is not None and y is not None:
                if bbox_poly.contains(Point(x, y)):
                    selected_nodes.add(node)

        # Create fresh isolated subgraph
        subgraph = base_graph.subgraph(selected_nodes).copy()
        logger.info(
            f"Extracted spatial subgraph: {subgraph.number_of_nodes()} nodes, "
            f"{subgraph.number_of_edges()} edges (buffer: {self.buffer_meters}m)"
        )
        return subgraph

    def extract_subgraph_for_incident_edges(
        self,
        base_graph: nx.MultiDiGraph,
        incident_edges: List[Tuple[Any, ...]],
        buffer_meters: Optional[float] = None
    ) -> nx.MultiDiGraph:
        """
        Calculates the bounding envelope of all incident edges and extracts
        the diversion corridor subgraph.
        """
        if not incident_edges:
            return base_graph.copy()

        xs = []
        ys = []
        for edge in incident_edges:
            u, v = edge[0], edge[1]
            if u in base_graph.nodes:
                u_data = base_graph.nodes[u]
                if "x" in u_data and "y" in u_data:
                    xs.append(u_data["x"])
                    ys.append(u_data["y"])
            if v in base_graph.nodes:
                v_data = base_graph.nodes[v]
                if "x" in v_data and "y" in v_data:
                    xs.append(v_data["x"])
                    ys.append(v_data["y"])

        if not xs or not ys:
            return base_graph.copy()

        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)

        buf = (buffer_meters / 111320.0) if buffer_meters else self.deg_buffer
        return self.extract_subgraph_in_bounds(base_graph, minx, miny, maxx, maxy, apply_buffer=True)
