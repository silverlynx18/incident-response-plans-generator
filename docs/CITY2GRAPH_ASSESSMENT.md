# City2Graph assessment for ARPL

Date: 2026-10-09. Branch: `development/arpl-next-stage`.

**Scope:** source/metadata assessment only. No package installation, dependency change, runtime replacement or live-app change. Findings below are not runtime compatibility results.

**User clarification:** ARPL's routing is proprietary and the central project capability. Preserve it as the source of truth; evaluate City2Graph only for roadmap-aligned supporting integration. Isochrones and unrelated analytics are out of scope. GTFS is an explicit priority, beginning with the roadmap's D2 ingestion/validation/overlay stage, not an automatic replacement of the routing algorithm.

## Summary

City2Graph can complement ARPL and replace selected spatial/graph plumbing. It is not a ready replacement for the OSM downloader, incident-closure rules or the existing detour solver. Evaluate a small adapter against the real saved road graph before adopting it.

The most promising initial use is **relationships between roads, route corridors, signals, schools and other zones**, followed by consistent graph/GeoDataFrame handling. Transit aggregation is useful later. GNN features are not needed for the current workflow.

## Version and environment

- Published PyPI release: **1.0.0**, uploaded 2026-08-01; Python **>=3.12,<3.15**; BSD-3-Clause.
- Reviewed release source: `v1.0.0`, Git tag SHA `0685448e595323808cd6861312b0e4ec2d82afdd`. Upstream main separately inspected at `8c34b040d2acac034eaa1bc4ce99146fe3b92af1`; do not assume main and the published release are identical.
- Current local ARPL interpreter is Python 3.13.2, which meets the declared floor. The README's general Python 3.10 floor would no longer cover a City2Graph-enabled build. Cloud interpreter/build support still requires verification.
- Existing local versions of GeoPandas, pandas, Shapely, NetworkX, pyproj, DuckDB and geopy meet the declared minimums by metadata. SciPy, momepy, libpysal, rustworkx and overturemaps are not installed in the inspected test environment. This is not a resolver or clean-install check.
- Base installation does **not** require Torch. Its mandatory dependencies still include DuckDB, SciPy, libpysal, momepy, rustworkx and Overture Maps, so adopting one utility is not cost-free in startup/deployment footprint.
- Upstream security policy supports 1.0.x and documents optional Torch dependency concerns. No independent vulnerability audit was performed. Preserve BSD copyright/license notices; the authors also request citation of their paper.

## Replacement map

| Current ARPL responsibility | City2Graph candidate | Assessment |
| --- | --- | --- |
| Polygon -> complete OSM road network | `data.load_overture_data`, boundary geocoding | **Keep current loader.** Built-in downloaded data targets Overture; that is not guaranteed OSM-only data and would change the existing requirement. Boundary geocoding also adds Nominatim requests where shapefiles already work. |
| Graph cleanup, inferred speeds and penalties | Generic graph/spatial utilities | **Keep current rules.** City2Graph does not supply ARPL's speed, incident-ref, turn-penalty, rejection or ranking policy. A replacement needs explicit semantics, not a library swap. |
| Signals/assets associated with route corridors or zones | `group_nodes`, `bridge_nodes`, `fixed_radius_graph` | **Strong candidate for selected association plumbing and future typed asset graphs.** `group_nodes` links polygons/points and includes boundary points by default. Construct the intended metric route buffer first; point-to-point radius graphs are not themselves route-buffer searches. Existing GeoPandas joins may be sufficient for a narrow fix. |
| Graph <-> geometry representation for maps/exports | `nx_to_gdf`, `gdf_to_nx` | **Candidate with identity adapter.** Supports directed multigraphs when explicitly requested, but defaults are unsuitable for road routing and node relabeling needs handling. OSMnx's current conversion already preserves road IDs; replacement must demonstrate a concrete benefit. |
| Geographic clipping/component filtering | `clip_graph`, `remove_isolated_components` | **Not a blind replacement.** Geometric clipping, outer-neighbor handling and generic component helpers are not the same as the existing buffered OSMnx graph-building sequence. They could support explicit future area operations after parity checks. |
| Reachable area / distance-limited analysis | `filter_graph_by_distance`, `create_isochrone` | **Out of scope by user instruction.** API inventory only, not a proposed feature or existing-slider replacement. |
| Street/turn relationships and urban networks | `dual_graph`, `movement_to_movement_graph` | **Research candidate for G1 and movement representation.** Edge adjacency alone does not establish a legal directed vehicle turn; retain one-way restrictions, edge identity and approved turn policy. |
| Repeated shortest-path calculations | `nx_to_rx`, `rx_to_nx` and rustworkx | **Benchmark candidate, not yet a replacement.** Could accelerate computation, but conversion overhead and exact directed/keyed routing must be tested. First remove redundant per-pair searches with existing NetworkX if that meets the need. |
| Future transit ingestion/summary | `load_gtfs`, `load_gbfs`, `travel_summary_graph` | **Good D2 candidate.** Summary edges represent aggregate stop-to-stop service, not road detours or a timetable-dependent multimodal router. D3 still needs separate routing requirements. |
| Response-plan library, review state and durable storage | None directly | **Not supplied.** DuckDB used by transit loading is not an ARPL plan database/lifecycle implementation. |
| Current previews and export formats | Generic `plot_graph` / graph utilities | **Do not replace now.** Generic plotting is not the existing A/B, incident, asset, route-review and seven-format export contract, nor a tile-policy solution. |

## Specific adapter risks found in release source

1. **Defaults:** `gdf_to_nx(..., multigraph=False, directed=False)` produces a simple undirected graph by default. ARPL requires directed `(u,v,key)` road identity; both flags must be explicit when converting.
2. **Node IDs:** conversion relabels nodes to integer positions and retains prior IDs as `_original_index`. It is not an identity-preserving drop-in. Restore/map original OSM IDs before passing it into current incident/routing/state code; test parallel keys and original metadata too.
3. **Undirected helpers:** `canonicalize_edges` deliberately merges reciprocal directions into unordered pairs. It is useful for undirected analysis, not the operational road graph. Generic clipping/component outputs call conversions whose defaults require scrutiny.
4. **Graph positions:** reachability code reads `pos`; ordinary OSMnx graphs commonly have `x/y`. An adapter must supply positions/CRS without mutating the original graph or performing planar distance in longitude degrees.
5. **Rustworkx return conversion:** release `rx_to_nx` uses the original edge payload dictionary and pops `__nx_edge_key__`. That changes the source Rustworkx payload during conversion. Treat repeated round-trips/source immutability as a required test; do not promise reversible key preservation merely from the documentation.
6. **Transit network dependency:** `load_gtfs` executes `INSTALL spatial; LOAD spatial` in DuckDB. A local ZIP input can therefore require a separate extension download unless already provisioned. Corporate network trust and cloud startup must be checked; do not assume offline operation.

These are source-level behavior observations, not new upstream issues or locally reproduced City2Graph failures. No issue/PR was opened against upstream.

## Small proof-of-concept to approve next

Following the user's clarification, GTFS D2 is the priority candidate. Choose one approved agency feed, validate stops/routes/calendars/service times and display it without altering proprietary road routing. The graph/asset adapter experiment below remains a separate option, not the automatic next task.

Use an isolated research environment on this branch, with `city2graph==1.0.0` base only. Do not modify production `requirements.txt` or the loader yet.

1. Read the genuine saved Richmond OSM graph; do not download a new network or replace it with generated roads.
2. Test graph -> GeoDataFrames -> graph conversion with explicit directed/multigraph flags and original-ID restoration. Assert unchanged directed edge keys, node IDs, geometry, CRS, source metadata, scalar weights and shortest-path results; source graph must remain unchanged.
3. Test one existing asset layer against a metric route corridor using `group_nodes`. Compare associations with a GeoPandas reference, including boundary points and multipart geometry. Keep asset relations separate from driveable edges.
4. Measure installation footprint, import/RSS cost and execution time on the supported local/cloud environment. Reject adoption if it adds substantial overhead without reducing code or providing a roadmap capability.

**Decision gate:** adopt only the proven adapter/helper, or retain existing GeoPandas/OSMnx if simpler. A future rustworkx or GTFS experiment is separate; no automatic GNN, Overture, visualization-engine or database migration.

Routing acceleration has no measured gain yet. Current `get_detour` performs a targeted Dijkstra search for every start/end pair; one search per start covering its requested ends may avoid repetition without new libraries. A Rustworkx backend is a separate benchmark and must preserve closures, costs, identities and the agreed equal-cost route-selection behavior. Fewer search invocations do not imply the same-factor latency reduction, and neither option speeds network downloads or tiles. No routing code was changed by this research.

## Roadmap alignment

Existing Work Wiki references: `Roadmap.md`, `ARPL Development Roadmap.md`, `ARPL Technical Reference.md`, and `ARPL User Guide.md`.

- B1/B2: keyed identity, route correctness and input immutability are prerequisites for replacement.
- B3/B5/A2: precise metric geometry and consistent assets/exports are the nearest potential utility benefits.
- G1: dual/movement representations may help urban/unreferenced-network work after baseline validation.
- D2/D3: evaluate GTFS ingestion separately from operational transit/bus routing.
- P1-P3: no storage/backend or plan-lifecycle decision is made by this assessment.

## Primary sources

- [PyPI release metadata](https://pypi.org/pypi/city2graph/1.0.0/json)
- [Release package configuration](https://github.com/c2g-dev/city2graph/blob/v1.0.0/pyproject.toml)
- [Graph conversion and Rustworkx](https://github.com/c2g-dev/city2graph/blob/v1.0.0/city2graph/utils/conversion.py)
- [Topology and clipping](https://github.com/c2g-dev/city2graph/blob/v1.0.0/city2graph/utils/topology.py)
- [Asset/zone proximity relationships](https://github.com/c2g-dev/city2graph/blob/v1.0.0/city2graph/proximity.py)
- [Reachability/isochrones](https://github.com/c2g-dev/city2graph/blob/v1.0.0/city2graph/utils/spatial.py)
- [Transit loading and service summaries](https://github.com/c2g-dev/city2graph/blob/v1.0.0/city2graph/transportation.py)
- [Built-in data sources](https://github.com/c2g-dev/city2graph/blob/v1.0.0/city2graph/data.py)
- [Security policy](https://github.com/c2g-dev/city2graph/blob/v1.0.0/SECURITY.md), [license](https://github.com/c2g-dev/city2graph/blob/v1.0.0/LICENSE)
