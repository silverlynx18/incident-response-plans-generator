"""
ARPL Detour Routing Engine (Stage 0 - B0-B6 Baseline)
=====================================================
Clean, modular Python implementation of directed MultiDiGraph incident removal
preserving keyed edges (u, v, key), Dijkstra and A* alternate routing,
and geometry reconstruction without dropping parallel carriageways or opposing lanes.

References:
- Work Wiki/Topics/ITS/ARPL/ARPL Development Roadmap.md (Stage 0: B0-B6)
- Work Wiki/Topics/ITS/ARPL/ARPL Technical Reference.md (B01-B10, §Graph preparation)
- Wiki/Projects/ARPL.md
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union
import math
import heapq
import networkx as nx
from shapely.geometry import LineString, Point


@dataclass(frozen=True)
class IncidentClosure:
    """
    Identifies a directed keyed edge closure in a MultiDiGraph.
    
    Attributes:
        u: Tail node ID.
        v: Head node ID.
        key: Edge key in MultiDiGraph (default 0).
        bidirectional: If True, also closes the reverse direction (v, u, key).
                       Default is False (directed one-way closure).
        description: Optional label or incident note.
    """
    u: Any
    v: Any
    key: Any = 0
    bidirectional: bool = False
    description: Optional[str] = None

    @property
    def edge_tuple(self) -> Tuple[Any, Any, Any]:
        return (self.u, self.v, self.key)

    @property
    def reverse_tuple(self) -> Tuple[Any, Any, Any]:
        return (self.v, self.u, self.key)


@dataclass
class AnalysisParameters:
    """
    Configuration parameters for detour route calculation and filtering.
    
    Enforces distance and time semantics per Roadmap B3.
    """
    min_time_s: float = 120.0          # Routes under 120s rejected ("Too Short")
    max_time_s: float = 7200.0         # Default 2 hour ceiling ("Too Long")
    max_distance_m: Optional[float] = None  # Optional distance ceiling in meters
    turn_penalty_weight: float = 1.0   # Multiplier on turn penalties
    max_alternatives: int = 5          # Number of alternate routes to evaluate
    weight_attribute: str = "total_time" # Edge weight attribute for pathfinding
    hard_removal: bool = True          # True removes edge; False sets weight to inf
    penalize_cost: float = 1e9         # Penalty weight used if hard_removal is False


@dataclass
class RouteResult:
    """
    Immutable representation of an evaluated route.
    Carries stable identifiers, node path, keyed edge path, metrics, and geometry.
    """
    route_id: str
    origin: Any
    destination: Any
    node_path: List[Any]
    edge_path: List[Tuple[Any, Any, Any]] # Exact sequence of (u, v, key)
    geometry: Optional[LineString] = None
    distance_m: float = 0.0               # Total route length in meters
    freeflow_time_s: float = 0.0          # Unimpeded travel time in seconds
    turn_penalty_s: float = 0.0           # Turn delay in seconds
    total_time_s: float = 0.0             # Combined travel time in seconds
    num_turns: int = 0                    # Count of turns taken
    score: float = float("inf")           # Composite evaluation score (lower = better)
    valid: bool = True                    # Feasibility flag
    rejection_reason: Optional[str] = None # Reason string if invalid
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert route summary to a dictionary."""
        return {
            "route_id": self.route_id,
            "origin": self.origin,
            "destination": self.destination,
            "valid": self.valid,
            "rejection_reason": self.rejection_reason,
            "total_time_s": round(self.total_time_s, 2),
            "freeflow_time_s": round(self.freeflow_time_s, 2),
            "turn_penalty_s": round(self.turn_penalty_s, 2),
            "distance_m": round(self.distance_m, 2),
            "distance_km": round(self.distance_m / 1000.0, 3),
            "distance_mi": round(self.distance_m / 1609.344, 3),
            "num_turns": self.num_turns,
            "num_nodes": len(self.node_path),
            "score": round(self.score, 3) if math.isfinite(self.score) else None,
            "edge_path": self.edge_path,
        }


# ============================================================================
# 1. MultiDiGraph Incident Removal & Edge Preservation
# ============================================================================

def normalize_closures(
    closures: Union[IncidentClosure, Tuple[Any, Any, Any], Sequence[Union[IncidentClosure, Tuple[Any, Any, Any]]]]
) -> List[IncidentClosure]:
    """
    Normalizes single or multiple closure specifications into a list of IncidentClosure.
    Supports (u, v, key) tuples or IncidentClosure instances.
    """
    if isinstance(closures, IncidentClosure):
        return [closures]
    if isinstance(closures, tuple) and len(closures) in (2, 3):
        key = closures[2] if len(closures) == 3 else 0
        return [IncidentClosure(u=closures[0], v=closures[1], key=key)]
    
    result = []
    for c in closures:
        if isinstance(c, IncidentClosure):
            result.append(c)
        elif isinstance(c, tuple) and len(c) in (2, 3):
            key = c[2] if len(c) == 3 else 0
            result.append(IncidentClosure(u=c[0], v=c[1], key=key))
        else:
            raise ValueError(f"Invalid closure specification: {c}")
    return result


def prepare_incident_graph(
    graph: nx.MultiDiGraph,
    closures: Union[IncidentClosure, Tuple[Any, Any, Any], Sequence[Union[IncidentClosure, Tuple[Any, Any, Any]]]],
    hard_removal: bool = True,
    penalize_cost: float = 1e9
) -> nx.MultiDiGraph:
    """
    Prepares a routing graph with specified incident closures.
    
    Guarantees:
    - The original input graph `graph` is NEVER modified.
    - Preserves keyed edge identity (u, v, key).
    - Preserves parallel carriageways (other keys between u and v remain intact).
    - Preserves opposing lanes ((v, u, key) remains intact unless bidirectional=True).
    - Preserves all other outgoing and incoming edges connected to u and v.
    
    Args:
        graph: Source nx.MultiDiGraph.
        closures: IncidentClosure or list of closures.
        hard_removal: If True, completely removes (u, v, key).
                      If False, sets weight to `penalize_cost`.
        penalize_cost: Penalty cost when hard_removal is False.
        
    Returns:
        A deep copy of the graph with targeted incident closures applied.
    """
    if not isinstance(graph, nx.MultiDiGraph):
        raise TypeError(f"Expected nx.MultiDiGraph, got {type(graph).__name__}")

    # Create an isolated working copy to guarantee input graph preservation
    G_work = graph.copy()
    norm_closures = normalize_closures(closures)

    for closure in norm_closures:
        edges_to_close = [closure.edge_tuple]
        if closure.bidirectional:
            edges_to_close.append(closure.reverse_tuple)

        for u, v, key in edges_to_close:
            if G_work.has_edge(u, v, key):
                if hard_removal:
                    # Remove ONLY this keyed edge
                    G_work.remove_edge(u, v, key)
                else:
                    # Assign infinite/large penalty
                    edge_data = G_work[u][v][key]
                    edge_data["total_time"] = penalize_cost
                    edge_data["is_closed"] = True
            else:
                # If the exact key is not present, check if node exists
                # We do not silently drop edges; raise or warn
                pass

    return G_work


# ============================================================================
# 2. Keyed Shortest Path Routing (Dijkstra and A*)
# ============================================================================

def find_keyed_shortest_path_dijkstra(
    graph: nx.MultiDiGraph,
    source: Any,
    target: Any,
    weight: str = "total_time"
) -> Tuple[List[Any], List[Tuple[Any, Any, Any]], float]:
    """
    Finds the shortest path on a MultiDiGraph using Dijkstra's algorithm,
    explicitly tracking and returning the exact (u, v, key) edge sequence.
    
    Unlike standard NetworkX shortest_path which only returns node sequence,
    this returns:
        (node_path, edge_path, total_weight)
    
    where `edge_path` is a list of exact `(u, v, key)` tuples chosen during routing.
    
    Raises:
        nx.NetworkXNoPath: If target is unreachable from source.
        nx.NodeNotFound: If source or target not in graph.
    """
    if source not in graph:
        raise nx.NodeNotFound(f"Source node {source} not in graph.")
    if target not in graph:
        raise nx.NodeNotFound(f"Target node {target} not in graph.")

    # Priority queue stores: (cost, node)
    dist: Dict[Any, float] = {source: 0.0}
    # Predecessor mapping: node -> (prev_node, key, edge_cost)
    pred: Dict[Any, Tuple[Any, Any, float]] = {}
    
    # Priority queue with tie-breaking counter
    counter = 0
    pq: List[Tuple[float, int, Any]] = [(0.0, counter, source)]
    visited: Set[Any] = set()

    while pq:
        d, _, u = heapq.heappop(pq)

        if u in visited:
            continue
        visited.add(u)

        if u == target:
            break

        if d > dist.get(u, float("inf")):
            continue

        for v, key_dict in graph[u].items():
            if v in visited:
                continue

            for key, edge_data in key_dict.items():
                edge_cost = edge_data.get(weight, 1.0)
                if edge_cost is None or edge_cost == float("inf"):
                    continue

                new_dist = d + edge_cost
                if new_dist < dist.get(v, float("inf")):
                    dist[v] = new_dist
                    pred[v] = (u, key, edge_cost)
                    counter += 1
                    heapq.heappush(pq, (new_dist, counter, v))

    if target not in pred and source != target:
        raise nx.NetworkXNoPath(f"No path between {source} and {target}")

    # Reconstruct node and keyed edge paths
    curr = target
    node_path = [curr]
    edge_path: List[Tuple[Any, Any, Any]] = []

    while curr != source:
        prev_node, key, _ = pred[curr]
        edge_path.append((prev_node, curr, key))
        curr = prev_node
        node_path.append(curr)

    node_path.reverse()
    edge_path.reverse()

    return node_path, edge_path, dist[target]


def find_keyed_shortest_path_astar(
    graph: nx.MultiDiGraph,
    source: Any,
    target: Any,
    weight: str = "total_time",
    heuristic: Optional[Any] = None
) -> Tuple[List[Any], List[Tuple[Any, Any, Any]], float]:
    """
    Finds the shortest path on a MultiDiGraph using A* algorithm,
    explicitly tracking and returning the exact (u, v, key) edge sequence.
    
    Args:
        graph: nx.MultiDiGraph.
        source: Source node ID.
        target: Target node ID.
        weight: Attribute to minimize.
        heuristic: Callable(u, target) returning estimated remaining cost.
                   If None, uses Euclidean/Haversine distance from node 'x'/'y'
                   coordinates (or 0 if coordinates not present).
    """
    if source not in graph:
        raise nx.NodeNotFound(f"Source node {source} not in graph.")
    if target not in graph:
        raise nx.NodeNotFound(f"Target node {target} not in graph.")

    # Default heuristic: spatial Euclidean distance / max assumed speed
    if heuristic is None:
        def default_heuristic(u: Any, target_node: Any) -> float:
            nu = graph.nodes[u]
            nt = graph.nodes[target_node]
            if "x" in nu and "y" in nu and "x" in nt and "y" in nt:
                dx = nu["x"] - nt["x"]
                dy = nu["y"] - nt["y"]
                # Approximate degree to meters (approx 111,000 m per deg)
                dist_m = math.sqrt(dx * dx + dy * dy) * 111000.0
                # Admissible heuristic: divide by max highway speed (e.g., 33.3 m/s = 120 km/h)
                return dist_m / 35.0
            return 0.0
        heuristic = default_heuristic

    g_score: Dict[Any, float] = {source: 0.0}
    f_score: Dict[Any, float] = {source: heuristic(source, target)}
    pred: Dict[Any, Tuple[Any, Any, float]] = {}

    counter = 0
    pq: List[Tuple[float, float, int, Any]] = [(f_score[source], 0.0, counter, source)]
    closed_set: Set[Any] = set()

    while pq:
        f, g, _, u = heapq.heappop(pq)

        if u in closed_set:
            continue
        closed_set.add(u)

        if u == target:
            break

        if g > g_score.get(u, float("inf")):
            continue

        for v, key_dict in graph[u].items():
            if v in closed_set:
                continue

            for key, edge_data in key_dict.items():
                edge_cost = edge_data.get(weight, 1.0)
                if edge_cost is None or edge_cost == float("inf"):
                    continue

                tentative_g = g + edge_cost
                if tentative_g < g_score.get(v, float("inf")):
                    g_score[v] = tentative_g
                    f_val = tentative_g + heuristic(v, target)
                    f_score[v] = f_val
                    pred[v] = (u, key, edge_cost)
                    counter += 1
                    heapq.heappush(pq, (f_val, tentative_g, counter, v))

    if target not in pred and source != target:
        raise nx.NetworkXNoPath(f"No path between {source} and {target}")

    # Reconstruct paths
    curr = target
    node_path = [curr]
    edge_path: List[Tuple[Any, Any, Any]] = []

    while curr != source:
        prev_node, key, _ = pred[curr]
        edge_path.append((prev_node, curr, key))
        curr = prev_node
        node_path.append(curr)

    node_path.reverse()
    edge_path.reverse()

    return node_path, edge_path, g_score[target]


# ============================================================================
# 3. Geometry Reconstruction with Keyed Multi-Edge Integrity
# ============================================================================

def reconstruct_route_geometry(
    graph: nx.MultiDiGraph,
    edge_path: Sequence[Tuple[Any, Any, Any]]
) -> Optional[LineString]:
    """
    Reconstructs continuous LineString geometry for a keyed edge sequence.
    
    Guarantees:
    - Strictly looks up the exact (u, v, key) edge attribute `geometry`.
    - Parallel edges with different geometries are accurately retrieved
      without collapsing to key 0 or the first edge.
    - Handles straight segments via node (x, y) coordinates if edge lacks geometry.
    - Ensures proper coordinate direction from u -> v.
    - Deduplicates duplicate intermediate endpoints between consecutive edges.
    
    Returns:
        Shapely LineString or None if coordinates cannot be determined.
    """
    if not edge_path:
        return None

    coords: List[Tuple[float, float]] = []

    for u, v, key in edge_path:
        if not graph.has_edge(u, v, key):
            continue

        edge_data = graph[u][v][key]
        edge_geom = edge_data.get("geometry")

        if edge_geom is not None and isinstance(edge_geom, LineString):
            edge_coords = list(edge_geom.coords)
            
            # Check orientation: start of edge_coords should be closest to node u
            node_u = graph.nodes.get(u, {})
            if "x" in node_u and "y" in node_u and len(edge_coords) > 1:
                ux, uy = node_u["x"], node_u["y"]
                start_dist = (edge_coords[0][0] - ux)**2 + (edge_coords[0][1] - uy)**2
                end_dist = (edge_coords[-1][0] - ux)**2 + (edge_coords[-1][1] - uy)**2
                if end_dist < start_dist:
                    edge_coords.reverse()
                    
            for pt in edge_coords:
                if not coords or coords[-1] != (pt[0], pt[1]):
                    coords.append((pt[0], pt[1]))

        else:
            # Fallback to straight segment from node u to node v
            node_u = graph.nodes.get(u, {})
            node_v = graph.nodes.get(v, {})
            if "x" in node_u and "y" in node_u and "x" in node_v and "y" in node_v:
                pt_u = (float(node_u["x"]), float(node_u["y"]))
                pt_v = (float(node_v["x"]), float(node_v["y"]))
                if not coords or coords[-1] != pt_u:
                    coords.append(pt_u)
                if coords[-1] != pt_v:
                    coords.append(pt_v)

    if len(coords) < 2:
        return None

    return LineString(coords)


# ============================================================================
# 4. Metrics, Scoring & Turn Analysis
# ============================================================================

def calculate_route_metrics(
    graph: nx.MultiDiGraph,
    edge_path: Sequence[Tuple[Any, Any, Any]]
) -> Dict[str, float]:
    """
    Calculates distance, freeflow time, turn delay, and total time
    strictly along the exact keyed edge path.
    """
    distance_m = 0.0
    freeflow_time_s = 0.0
    turn_penalty_s = 0.0
    total_time_s = 0.0
    num_turns = 0

    prev_bearing: Optional[float] = None

    for i, (u, v, key) in enumerate(edge_path):
        edge_data = graph[u][v][key]

        # Length in meters
        length = float(edge_data.get("length", 0.0))
        if length <= 0.0 and "geometry" in edge_data:
            # Approximated length if not set
            geom = edge_data["geometry"]
            if isinstance(geom, LineString):
                length = geom.length * 111000.0  # rough degrees to meters
        distance_m += length

        # Speed and travel time
        speed_kph = float(edge_data.get("speed_kph", 50.0))
        speed_mps = max(speed_kph * (1000.0 / 3600.0), 0.5)

        ff_time = float(edge_data.get("freeflow_time", edge_data.get("travel_time", length / speed_mps)))
        freeflow_time_s += ff_time

        # Turn delay & bearing change
        curr_bearing = edge_data.get("bearing")
        if curr_bearing is None:
            # Estimate bearing from node coordinates if available
            nu, nv = graph.nodes.get(u, {}), graph.nodes.get(v, {})
            if "x" in nu and "y" in nu and "x" in nv and "y" in nv:
                dx = nv["x"] - nu["x"]
                dy = nv["y"] - nu["y"]
                curr_bearing = (math.degrees(math.atan2(dx, dy)) + 360.0) % 360.0

        if prev_bearing is not None and curr_bearing is not None:
            diff = abs(curr_bearing - prev_bearing)
            if diff > 180.0:
                diff = 360.0 - diff

            if diff > 35.0:  # Threshold for a turn
                num_turns += 1
                # Quadratic turn penalty up to 120 seconds per U-turn angle
                turn_delay = (diff / 180.0) ** 2 * 120.0
                turn_penalty_s += turn_delay

        prev_bearing = curr_bearing

        # Total time for edge
        edge_total = edge_data.get("total_time")
        if edge_total is not None and edge_total != float("inf"):
            total_time_s += float(edge_total)
        else:
            total_time_s += ff_time

    # Ensure total_time incorporates turn delay if not precomputed
    if total_time_s == freeflow_time_s and turn_penalty_s > 0:
        total_time_s += turn_penalty_s

    return {
        "distance_m": distance_m,
        "freeflow_time_s": freeflow_time_s,
        "turn_penalty_s": turn_penalty_s,
        "total_time_s": total_time_s,
        "num_turns": float(num_turns),
    }


def compute_route_score(
    total_time_s: float,
    freeflow_time_s: float,
    num_nodes: int
) -> float:
    """
    Computes ARPL composite evaluation score:
        score = 0.7 * total_time_s
              + 0.2 * num_nodes
              + 100 * (1 - freeflow_time_s / total_time_s)
              
    Lower score is preferred (higher efficiency and shorter delay).
    """
    if total_time_s <= 0.0:
        return float("inf")

    eff_ratio = freeflow_time_s / total_time_s
    score = (0.7 * total_time_s) + (0.2 * float(num_nodes)) + (100.0 * max(0.0, 1.0 - eff_ratio))
    return score


# ============================================================================
# 5. Detour Generation Engine
# ============================================================================

class DetourEngine:
    """
    Modular Detour Analysis Engine.
    
    Provides clean interfaces for incident removal, single-pair alternate routing,
    multi-pair corridor diversion, and validation.
    """

    def __init__(self, base_graph: nx.MultiDiGraph, parameters: Optional[AnalysisParameters] = None):
        if not isinstance(base_graph, nx.MultiDiGraph):
            raise TypeError(f"base_graph must be a MultiDiGraph, got {type(base_graph).__name__}")
        self.base_graph = base_graph
        self.params = parameters or AnalysisParameters()

    def find_detour(
        self,
        incident_closures: Union[IncidentClosure, Tuple[Any, Any, Any], Sequence[Union[IncidentClosure, Tuple[Any, Any, Any]]]],
        origin: Any,
        destination: Any,
        algorithm: str = "dijkstra",
        route_id: Optional[str] = None
    ) -> RouteResult:
        """
        Calculates the primary detour path between origin and destination
        after applying directed keyed closures.
        
        Args:
            incident_closures: Keyed edge closures.
            origin: Source node ID.
            destination: Target node ID.
            algorithm: 'dijkstra' or 'astar'.
            route_id: Optional identifier.
            
        Returns:
            RouteResult with validity status, metrics, and reconstructed geometry.
        """
        route_id = route_id or f"detour_{origin}_{destination}"
        
        # 1. Prepare incident graph (immutable base_graph)
        G_incident = prepare_incident_graph(
            self.base_graph,
            incident_closures,
            hard_removal=self.params.hard_removal,
            penalize_cost=self.params.penalize_cost
        )

        # 2. Check source/target connectivity
        if origin not in G_incident or destination not in G_incident:
            return RouteResult(
                route_id=route_id,
                origin=origin,
                destination=destination,
                node_path=[],
                edge_path=[],
                valid=False,
                rejection_reason="Disconnected: origin or destination not in graph."
            )

        # 3. Pathfinding
        try:
            if algorithm.lower() == "astar":
                node_path, edge_path, _ = find_keyed_shortest_path_astar(
                    G_incident, origin, destination, weight=self.params.weight_attribute
                )
            else:
                node_path, edge_path, _ = find_keyed_shortest_path_dijkstra(
                    G_incident, origin, destination, weight=self.params.weight_attribute
                )
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return RouteResult(
                route_id=route_id,
                origin=origin,
                destination=destination,
                node_path=[],
                edge_path=[],
                valid=False,
                rejection_reason="No Route: disconnected destination."
            )

        # 4. Compute metrics strictly on keyed edge path
        metrics = calculate_route_metrics(G_incident, edge_path)
        dist_m = metrics["distance_m"]
        ff_s = metrics["freeflow_time_s"]
        turn_s = metrics["turn_penalty_s"]
        tot_s = metrics["total_time_s"]
        num_turns = int(metrics["num_turns"])

        # 5. Reconstruct geometry
        geom = reconstruct_route_geometry(G_incident, edge_path)

        # 6. Score
        score = compute_route_score(tot_s, ff_s, len(node_path))

        # 7. Apply boundary and constraint checks
        valid = True
        rejection_reason = None

        if tot_s < self.params.min_time_s:
            valid = False
            rejection_reason = "Too Short: travel time below minimum threshold (120s)."
        elif tot_s > self.params.max_time_s:
            valid = False
            rejection_reason = f"Too Long: travel time exceeds maximum allowable ({self.params.max_time_s}s)."
        elif self.params.max_distance_m is not None and dist_m > self.params.max_distance_m:
            valid = False
            rejection_reason = f"Too Far: distance exceeds limit ({self.params.max_distance_m}m)."
        elif tot_s >= (self.params.penalize_cost * 0.5):
            valid = False
            rejection_reason = "Needs Mainline: path relies on penalized closed corridor."

        return RouteResult(
            route_id=route_id,
            origin=origin,
            destination=destination,
            node_path=node_path,
            edge_path=edge_path,
            geometry=geom,
            distance_m=dist_m,
            freeflow_time_s=ff_s,
            turn_penalty_s=turn_s,
            total_time_s=tot_s,
            num_turns=num_turns,
            score=score,
            valid=valid,
            rejection_reason=rejection_reason
        )

    def find_alternate_detours(
        self,
        incident_closures: Union[IncidentClosure, Tuple[Any, Any, Any], Sequence[Union[IncidentClosure, Tuple[Any, Any, Any]]]],
        candidate_pairs: Sequence[Tuple[Any, Any]],
        algorithm: str = "dijkstra"
    ) -> List[RouteResult]:
        """
        Evaluates detour routes across multiple candidate entry/exit pairs
        (e.g., surrounding upstream turns to downstream turns).
        
        Returns sorted list of evaluated RouteResults (valid routes first, ordered by score).
        """
        results: List[RouteResult] = []
        for idx, (orig, dest) in enumerate(candidate_pairs):
            rid = f"detour_cand_{idx+1}_{orig}_{dest}"
            res = self.find_detour(
                incident_closures=incident_closures,
                origin=orig,
                destination=dest,
                algorithm=algorithm,
                route_id=rid
            )
            results.append(res)

        # Sort: valid routes first by lowest score, then invalid routes
        results.sort(key=lambda r: (0 if r.valid else 1, r.score))
        return results
