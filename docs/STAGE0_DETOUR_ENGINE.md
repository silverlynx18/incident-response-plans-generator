# ARPL (Automated Route Planning & Logistics) - Stage 0 Baseline

This repository implements the **Stage 0 Concrete Development Backlog (B0–B6)** for the ARPL (Automated Route Planning & Logistics) system, following the specifications defined in:
- `Work Wiki/Topics/ITS/ARPL/ARPL Development Roadmap.md`
- `Work Wiki/Topics/ITS/ARPL/ARPL Technical Reference.md`
- `Wiki/Projects/ARPL.md`

Stage 0 establishes a verified, mathematically reproducible routing, incident removal, and geospatial export baseline. It eliminates historical bugs related to unkeyed multi-edge collapse, opposing-lane dropping, serialization size limits, and unhandled disconnected routing.

---

## Stage 0 Backlog Alignment (B0–B6)

| Backlog ID | Roadmap Specification | Implementation Touchpoint | Verification |
|---|---|---|---|
| **B0** | Target environment reconciliation & geospatial driver verification | `detour_engine.py`, `export_pipeline.py` (EPSG:4326, Shapely, Pyogrio/GeoPandas) | Unit tests run cleanly on standard Python 3.9+ GIS runtime |
| **B1** | Characterize routing using small directed `MultiDiGraph` fixtures | `tests/test_routing_baseline.py` | Known shortest paths, disconnected pairs, edge removal preservation |
| **B2** | Correct incident identity/removal preserving keyed edges `(u, v, key)` | `detour_engine.py:prepare_incident_graph` | Parallel carriageways and opposing lanes survive incident removal |
| **B3** | Enforce total distance and time semantics (<120s floor, >max ceiling) | `detour_engine.py:AnalysisParameters` | Total detour route length enforced; boundary condition unit tests |
| **B4** | Stable analysis and route identity; separate no-route from errors | `detour_engine.py:RouteResult` | Disconnected pairs return `valid=False` without empty list crashes |
| **B5** | Multi-format export pipeline without unkeyed geometry collapse | `export_pipeline.py` | GeoJSON, zipped ESRI Shapefiles (10-char DBF safe), and CSV summaries |
| **B6** | End-to-end reproducible baseline suite | Full `unittest` test suite | 14 test cases green, validating routing, metrics, and multi-format exports |

---

## Key Technical Solutions

### 1. Directed MultiDiGraph Keyed Edge Preservation (`detour_engine.py`)
In OpenStreetMap and transportation networks, multi-lane divided highways, parallel collector/distributor roads, and express/local lanes share origin and destination nodes but possess distinct keys `(u, v, key)` and geometries.

- **Immutability:** `prepare_incident_graph` performs a deep working copy. The base network graph is never mutated.
- **Keyed Incident Removal:** Incident closures specify `(u, v, key)`. Closing `(u, v, 0)` removes only that specific edge key. Parallel edge `(u, v, 1)` and opposing edge `(v, u, 0)` remain intact and routable.
- **Keyed Routing (Dijkstra and A*):** `find_keyed_shortest_path_dijkstra` and `find_keyed_shortest_path_astar` track predecessor edges `(prev_node, curr_node, key)` to guarantee that the exact lowest-cost edge key is returned in the path sequence.
- **Curved Geometry Reconstruction:** `reconstruct_route_geometry` queries the specific `(u, v, key)` edge's `geometry` attribute, orientation-correcting vertex orders and stitching continuous `LineString`s without loss of curvature.
- **Turn Penalties & Dynamic Metrics:** Quadratic turn penalties up to 120s per U-turn angle are calculated from bearing changes.
- **ARPL Composite Scoring:**
  $$\text{score} = 0.7 \cdot \text{total\_time\_s} + 0.2 \cdot \text{num\_nodes} + 100 \cdot \left(1 - \frac{\text{freeflow\_time\_s}}{\text{total\_time\_s}}\right)$$
  Deterministic ranking orders valid routes by lowest score.

### 2. Multi-Format Export Pipeline (`export_pipeline.py`)
Provides consistent, cross-verified outputs:
- **GeoJSON (`export_to_geojson`):** `FeatureCollection` with true `LineString` route geometries, incident closure metadata, and operational properties.
- **ESRI Shapefile (`export_to_shapefile`):** Packaged into a `.zip` archive containing `.shp`, `.shx`, `.dbf`, `.prj`, and `.cpg` files. Attribute names are truncated to $\le 10$ characters (e.g. `tot_time_s`, `ff_time_s`, `dist_m`, `rej_reason`) to adhere to the DBF standard.
- **CSV Summaries (`export_to_csv`):** Tabular export of route metrics, validity flags, rejection reasons, and edge sequences.
- **Batch Export (`export_all_formats`):** Generates all three formats in a single unified call.

### 3. Streamlit Configuration (`config.toml` & `.streamlit/config.toml`)
- **`maxMessageSize = 500`:** Eliminates `Streamlit MessageSizeError` caused by serializing large metropolitan MPO boundaries and road graphs.
- **`enableCORS = false` / `enableXsrfProtection = false`:** Prevents cross-origin browser stalls when running locally, in enterprise proxies, or in headless environments.
- **Theme Standardization:** Applies `#E61E28` red accent color matching project design standards (`Decisions/2025-10-02 PDF for Management UI (ARPL)`).
- **In-Memory Caching & Runner:** Configured for `fastReruns = true` and headless execution.

---

## File Structure

```text
work/projects/arpl/
├── config.toml                     # Streamlit configuration root
├── .streamlit/
│   └── config.toml                 # Streamlit auto-discovery config
├── detour_engine.py                # Directed MultiDiGraph routing engine
├── export_pipeline.py              # GeoJSON, Shapefile, and CSV exporter
├── tests/
│   ├── __init__.py
│   ├── test_routing_baseline.py    # Routing, parallel edge, and boundary tests
│   └── test_export_pipeline.py     # GeoJSON, Shapefile, CSV export tests
└── README.md                       # Stage 0 documentation and verification guide
```

---

## Running the Unit Test Suite

Run the full baseline test suite using Python's built-in `unittest` runner:

```bash
cd /Users/owenmartin/Documents/Gemini-export/work/projects/arpl
python3 -m unittest discover -s tests -p "test_*.py" -v
```

### Verified Test Cases (14/14 Green)
1. `test_known_shortest_path_dijkstra`: Validates exact cost, node sequence, and keyed edges on known graph.
2. `test_known_shortest_path_astar`: Validates optimal A* path matches Dijkstra with admissible heuristic.
3. `test_disconnected_pairs`: Validates graceful `valid=False` rejection when destination is unreachable.
4. `test_edge_removal_preserves_input_graph`: Validates base graph immutability during incident preparation.
5. `test_multidigraph_parallel_edge_integrity`: Validates parallel carriageway survival and opposing lane preservation.
6. `test_corridor_diversion_when_both_parallel_lanes_closed`: Validates arterial diversion when all parallel links are closed.
7. `test_keyed_geometry_reconstruction`: Validates retention of distinct curved LineStrings across parallel edges.
8. `test_time_and_distance_boundaries`: Validates <120s floor ("Too Short"), >max ceiling ("Too Long"), and distance bounds.
9. `test_scoring_ranking`: Validates deterministic ARPL composite route scoring.
10. `test_geojson_export`: Validates GeoJSON FeatureCollection generation, geometry, and properties.
11. `test_shapefile_export`: Validates ESRI Shapefile generation, DBF field truncation, and `.zip` archiving.
12. `test_csv_export`: Validates tabular metrics and summary columns.
13. `test_export_all_formats`: Validates batch export across all three formats.
14. `test_empty_route_export`: Validates resilience when exporting empty or rejected route sets.

---

## Quickstart Usage Example

```python
import networkx as nx
from shapely.geometry import LineString
from detour_engine import DetourEngine, IncidentClosure, AnalysisParameters
from export_pipeline import export_all_formats

# 1. Initialize a MultiDiGraph
G = nx.MultiDiGraph()
G.add_node("A", x=-77.036, y=38.897)
G.add_node("B", x=-77.026, y=38.897)
G.add_node("C", x=-77.016, y=38.897)

# Parallel lanes between A and B
G.add_edge("A", "B", key=0, length=1000, speed_kph=72, total_time=50.0, freeflow_time=50.0,
           geometry=LineString([(-77.036, 38.897), (-77.031, 38.898), (-77.026, 38.897)]))
G.add_edge("A", "B", key=1, length=1200, speed_kph=48, total_time=90.0, freeflow_time=90.0,
           geometry=LineString([(-77.036, 38.897), (-77.031, 38.896), (-77.026, 38.897)]))
G.add_edge("B", "C", key=0, length=2000, speed_kph=72, total_time=100.0, freeflow_time=100.0)

# 2. Configure engine with Stage 0 baseline parameters
params = AnalysisParameters(min_time_s=120.0, max_time_s=3600.0)
engine = DetourEngine(G, params)

# 3. Simulate incident on mainline express lane (A -> B, key 0)
closure = IncidentClosure(u="A", v="B", key=0, description="Crash blocking Express NB")

# 4. Route detour: Automatically diverts via parallel frontage lane (A -> B, key 1)
result = engine.find_detour(closure, origin="A", destination="C")

print(f"Route Valid: {result.valid}")
print(f"Edge Path: {result.edge_path}")       # [('A', 'B', 1), ('B', 'C', 0)]
print(f"Distance: {result.distance_m} m")      # 3200 m
print(f"Total Time: {result.total_time_s} s")  # 190.0 s
print(f"Score: {result.score:.2f}")

# 5. Export across all formats
export_all_formats([result], output_dir="./exports", base_name="incident_diversion")
```
