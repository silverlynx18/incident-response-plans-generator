# ARPL Technical Reference

**Baseline:** repository source at `54a6463ecf3c7e4bed384aae78ad6cc141b6fd2c`, reviewed 2026-10-08. UI title: V1.6.1; entry point: `app_v1_5_6.py`. This is a static implementation assessment. No application runtime, OSM download, or operational validation was performed.

Read the [user guide](ARPL_USER_GUIDE.md) for operation and the [development roadmap](ARPL_DEVELOPMENT_ROADMAP.md) for proposed changes.

## Evidence and provenance

| Source | What it establishes |
|---|---|
| [Application](../app_v1_5_6.py) | Connected UI, imports, session flow, analysis invocation, ranking and export choices |
| [Detour utilities](../detour_utils.py) | Graph transformations, traversal, pathfinding, asset searches, and plotting |
| [Export utilities](../export_utils_v1_5_6.py) | Actual function-based export payloads; older classes are separate code paths |
| [Network loader](../osm_network_loader.py) | Available but disconnected preprocessed-network implementation |
| [Research notebook](../testing_notebook/generalized_detour_solution.ipynb) | Algorithm ancestry; 26 cells containing graph preparation, turn discovery, sector/pathfinding, and shapefile matching |
| [Historical timeline](../COMPLETE_DEVELOPMENT_TIMELINE.md) | Narrative of earlier versions and experiments, not current acceptance evidence |
| Work Wiki `Topics\ITS\ARPL\Roadmap.md` | Desired capabilities and open-data/freight restrictions; source property `ITS/ARPL/Roadmap.md` |
| Work Wiki `Topics\ITS\ARPL DIF.md` | Product exploration: library generator and response tool; market/revenue/client claims remain hypotheses |
| Work Wiki `Topics\AI\Antigravity Comprehensive AI Worklog.md` | Historical July 9 ingestion/map debugging references and reported transcript loss; no recovered implementation detail |

The roadmap contains overlapping drafts. This consolidation retains all six themes and the fuller aim of reusing validated plans, without treating repeated prose as separate features.

Earlier Antigravity, Cursor, and VS Code Copilot conversations were identified by Owen as informative but not useful. The readily available Antigravity summary was consulted; Cursor/VS Code transcripts were not recovered. Copilot session-history searches over seven and ninety days returned no matches. No application conversation databases or credential stores were scanned. A history claim becomes "implemented" only when the current code and later validation support it.

## Architecture and connected data flow

| Component | Responsibility / integration |
|---|---|
| `app_v1_5_6.py` | Top-level Streamlit script: initialization, single-page setup, shapefile processing, area/incident selection, OSM downloads, ranking, route selection, evaluation, map rendering, exports |
| `detour_utils.py` | Reusable algorithm functions called by the app; also contains research helpers not wired into its UI |
| `export_utils_v1_5_6.py` | App imports `export_to_pdf`, `export_to_geojson`, `export_to_kml`, `export_to_shapefile`, `export_to_excel`, `export_to_csv`; KMZ packaging happens in the app |
| `osm_network_loader.py` | Reads metadata and `.pkl.gz` state graphs, merges intersecting states, returns the full merged graph without polygon trimming; no import/call in current app |
| `data` / `session_data` | Packaged boundary shapefiles and metadata/logs; attempted upload persistence in shared local JSON files |

```text
Boundary shapefiles / custom polygon + optional asset shapefiles
  -> show_setup_wizard / process_shapefile_upload
  -> selected polygon WKT + layer dictionaries in session state
  -> OSMnx graph_from_polygon
  -> clean_graph -> prepare_graph
  -> selected incident edge (u, v, key)
  -> get_surrounding_turns -> generate_incident_graph -> get_detour
  -> rank candidate tuples -> Accept/Reject
  -> Evaluate All Accepted Routes -> optional get_points_in_buffer
  -> accepted_detours + analysis_complete -> function-based export
```

Initial setup downloads through cached `load_and_prepare_graph_from_polygon`; the sidebar duplicates the download/prepare logic and adds a Unix signal timeout. They are not equivalent platform paths.

## Graph preparation and routing semantics

### Cleaning and weighting

`clean_graph` (`detour_utils.py:295`) copies the graph, normalizes list/boolean attributes and road refs, supplies missing line geometry, estimates a UTM projection for meter lengths, and normalizes/infer speeds. Its CRS assumption is EPSG:4326; its UTM construction and raw-number default speed unit (`mph`) need broader geography/unit tests.

`prepare_graph` (`:506`) calls:

- `compute_traveltime_bearing`: `travel_time` in seconds from length/speed, plus start/end bearings.
- `compute_turntime`: a quadratic angle penalty up to 120 seconds per U-turn angle, averaged across all incoming edges and added to `total_time`.
- `find_turns`: candidate turns where incoming/outgoing ref sets differ and the node has branching connectivity.

The averaged turn penalty is an edge heuristic, not a movement-specific signal-delay or legal-turn model. Missing/zero bearings, missing refs, parallel edges, access restrictions and units require explicit validation.

### Incident and turn discovery

`get_surrounding_turns` (`:606`) traverses the incident road in both directions using common refs and bearing alignment to find candidate entry/exit nodes. The app supplies `n=max(max_alternatives, 10)`. Unreferenced urban roads and complex intersections can therefore behave differently from referenced highways.

`generate_incident_graph` (`:717`) sets `total_time=1e9` on **all edges with exactly matching ref sets**, not just a local incident segment. Empty refs can match many unrelated roads. This is broad mainline discouragement, not a general closure scenario model.

`get_detour` (`:737`) copies the incident graph and attempts edge removal, then calls `nx.single_source_dijkstra(..., weight='total_time')` for each distinct start/end pair. Its `G_input.edges(incident_edge[0], incident_edge[1], keys=True)` call does not express a keyed `(u,v,key)` selection: the second positional argument is passed to the edge-view API, and the resulting removal needs reproduction against the chosen NetworkX version.

The result is a dictionary keyed by `(start, end)`, with tuple values `(valid, total_time, freeflow_time, node_path)`. Invalid entries contain reason strings and `None` paths: Too Short, Too Long, Needs Mainline, or No Route. Broad exception handling also maps unexpected failures to No Route.

Freeflow time is recomputed using the **first parallel edge** for each node pair, which may not be the edge selected by weighted routing. Routes are rejected below 120 seconds, above the user maximum freeflow time, or at the mainline penalty threshold. There is no enforced distance bound.

This is one shortest path per candidate node pair, not K alternative paths per fixed origin/destination, a capacity assignment, or a time-dependent multimodal solver.

### UI ranking and review

The application ranking block (`app_v1_5_6.py:2554`) drops entries without paths, computes efficiency as freeflow/total time, and uses:

```text
score = 0.7 * total_time_seconds
      + 0.2 * number_of_path_nodes
      + 100 * (1 - freeflow_time_seconds / total_time_seconds)
```

Lower is preferred. Although the UI names 70/20/10 weights, the inputs are not normalized to comparable scales; those numbers are not calibrated percentages of route quality. Uploaded assets do not enter this score.

Acceptance/rejection is stored using `route_i` display keys. Evaluation creates `accepted_detours` records containing status, `(start,end)`, tuple data, a convenience `path`, `buffer_points`, and `buffer_miles`, then sets `analysis_complete=True`. These are mutable session dictionaries, not stable plan identifiers or approvals.

## Inputs, spatial analysis, and output contracts

Upload parsing (`process_shapefile_upload`, app `:408`) accepts shapefiles, reprojects known CRS to WGS84, and chooses the first ZIP/shapefile. Jurisdiction uploads require polygons; asset uploads are more general. Historic URL/ArcGIS imports are not connected.

`get_points_in_buffer` (`detour_utils.py:1192`) gathers route geometry and searches point/MultiPoint layers. `buffer_search` (`:1108`) uses degree-to-meter approximation for geographic CRS and a 1% tolerance; a fallback uses a more generous `buffer_miles/50` degree buffer. Neither is a fully projected/geodesic distance contract. A generic intersection helper exists, but the current point-returning workflow does not score school zones or operate assets.

Evaluation filters points with `within(selected_polygon)` and other geometries with `intersects`. This can exclude boundary points and partially intersecting MultiPoints; jurisdiction CRS/geometry must be coherent. Point deduplication uses rounded x/y and ID, not an authoritative cross-source asset identity.

| Export path | Actual contract / limitation |
|---|---|
| `export_to_pdf` (`:441`) | Matplotlib/PdfPages title, maps, route segments and buffer details; not the older ReportLab class path; map failure can fall back to text |
| `export_to_geojson` (`:962`) | Incident/route FeatureCollection, counts/metadata; route geometry lookup may fall back to node coordinates |
| `export_to_kml` (`:1071`) | Styled incident/route lines; KMZ wraps its output in `doc.kml` |
| `export_to_shapefile` (`:1181`) | Route lines, `route_key`, `buffer_pts`, ZIP components; no incident/asset layers |
| `export_to_excel` (`:1311`) | Conditional Incident Edge / Route Segments / Buffer Points sheets |
| `export_to_csv` (`:1495`) | Incident/route-segment rows, no asset-point rows |

Line exporters request unkeyed multigraph edge data and then look for top-level `geometry`. On a MultiDiGraph that result is keyed by edge ID, so full curved route geometry can be lost. Tabular/PDF functions often choose the first parallel edge. Matching route weights, IDs, geometry and exports is baseline work.

Older `PDFReportGenerator`, `GeospatialExporter`, and `TabularExporter` classes consume a separate `export_data` model and are not instantiated by the app. `export_to_geopackage` exists but is not imported or offered by the UI. Helper presence alone is not feature availability.

## State, caching, and persistence

- Streamlit session state stores selections, graph, uploads and results; resource caches store boundary data and setup-prepared graphs.
- `save_session_data` (app `:119`) expects objects with `to_wkt`, but upload dictionaries are `{gdf, timestamp}`. It can write empty dictionaries rather than saved layers.
- `load_session_data` (`:161`) uses a GeoDataFrame WKT reconstruction call and restores plain GeoDataFrames, whereas downstream code expects dictionaries with a `gdf` member. Recovery requires schema/round-trip tests.
- The two JSON filenames under `session_data` are shared paths. A session UUID does not make those files isolated or durable.
- Underscored arguments in jurisdiction cache helpers should be audited: the comments' session/state cache-key claims are not sufficient evidence of isolation.
- Accept/reject, evaluated payloads and flags are not fully cleared on incident/area/parameter changes. Reset does not explicitly clear every analysis flag.
- There is no connected durable network cache, reviewed-plan database, successful-operation feedback store, or reusable validated-plan lifecycle.
- `osm_network_loader` expects `data\osm_networks\states\<state>.pkl.gz`; that directory was absent in the reviewed checkout. Metadata is not proof the networks are available.

## Baseline discrepancies

These are source observations or reproducible-test targets, **not fixes made in this change**. They identify where the development baseline needs evidence before feature expansion.

| ID | Finding and evidence | Development consequence |
|---|---|---|
| B01 | Missing `app.py` targeted by both launch scripts; evaluated union annotation at detour `:219`; unpinned dependency range | Reconcile entry point and establish an actual compatible environment |
| B02 | Virginia-only setup (app `:547`) versus full sidebar state list (`:1009`); duplicate download code and SIGALRM (`:1330`) | Make platform/setup behavior deliberate; reproduce Windows re-preparation |
| B03 | Distance only converted/printed (app `:2448`); buffer slider (`:1741`) never assigns the key read at `:2745`/`:2890` | Define and enforce parameter semantics end to end |
| B04 | Dict uploads versus WKT persistence expectations (app `:119-200`, `:739-789`) | Prove retention/isolation before adding a library |
| B05 | Label-keyed incident options (app `:1661-1700`), broad ref penalties (detour `:717`), edge-removal call (`:744`), first-edge metrics | Preserve exact directed keyed edges; reproduce closure correctness |
| B06 | Failed pairs stored/countable, no-path ranking still calls min/max on empty lists (app `:2598-2610`); exceptions collapse to No Route | Distinguish no feasible routes from execution failures |
| B07 | Route selections keyed by display index; evaluated payload/flags not comprehensively invalidated | Stable analysis/route identity and stale-export prevention |
| B08 | Geographic buffer approximation/fallback (detour `:1108-1373`); unkeyed export geometry lookups | Establish metric accuracy and format fidelity with fixtures |
| B09 | Unused loader; absent expected state graph files; no polygon trimming (loader `:196-240`) | Do not claim offline network caching until integrated and verified |
| B10 | Turn/ref assumptions and edge-averaged penalties; no freight, capacity, live-traffic or transit constraints | Bound suitability and validate each new routing policy explicitly |

## Roadmap gap matrix

All desired outcomes below come from Work Wiki `Topics\ITS\ARPL\Roadmap.md`; current evidence is linked to repository code. The named development packages are proposals in the [development roadmap](ARPL_DEVELOPMENT_ROADMAP.md).

| Theme | Current evidence | Missing outcome | Proposed work |
|---|---|---|---|
| Multiple links / affected areas | [Incident graph and paths](../detour_utils.py#L717-L779), single incident selector; sector helpers are not wired | Explicit scenario closures, direction/area policy, closure-safe paths and exports | C1-C3 |
| Asset retrieval / delivery | [Shapefile processing](../app_v1_5_6.py#L408-L528), [point buffers](../detour_utils.py#L1192-L1373), format-specific outputs | Source adapters, canonical asset schema, reliable distances and operator-ready consistent bundle | A1-A3 |
| Stored response-plan library | [Local save/load](../app_v1_5_6.py#L119-L200), disconnected [loader](../osm_network_loader.py#L196-L240) | Durable network/assets, versioned scenarios, reviewed plans, recall and invalidation | P1-P3 |
| Signal/asset states and scoring | [Current ranking](../app_v1_5_6.py#L2554-L2586), assets only retrieved/displayed | Hard restrictions versus preferences, asset-aware explainable scoring; later advisory signal states | S1-S2 |
| Live travel times / GTFS | [Static weights and shortest paths](../detour_utils.py#L407-L514), no connected feed | Timestamped traffic estimates, schedule/time-dependent transit and bus/mode-specific routing | D1-D3 |
| Granularity / geography | [Ref-based traversal](../detour_utils.py#L549-L616), OSM class filters, US boundary UI | Urban/unreferenced roads, international units/CRS/turn rules, verified vehicle policy | G1-G2 |

## Development history: retain lessons, not unverifiable claims

The timeline describes notebook -> Streamlit -> ArcGIS/export expansion -> performance modes -> Leafmap -> a Kepler/mock experiment -> onboarding/local uploads -> cloud/session work -> export/asset refinements. Its chronology is internally inconsistent (later versions dated before earlier ones), so it should not be used as an authoritative release calendar.

Corroborated current artifacts include notebook-derived graph algorithms, Streamlit UI, Leafmap/Folium mapping, performance filters, local shapefile processing, export functions and JSON save/load attempts. The timeline explicitly says URL downloads were removed; current UI supports that interpretation. Kepler/mock/HTML availability, measured speedups, full export fidelity, corrected isolation, and "all critical bugs fixed" are historical claims, not current verification.

Git commit `545783c` explicitly changed setup selection to Virginia. No inference is made that it intentionally restricted every other app surface.

The Antigravity worklog's ingestion/map reference is a lead for future recovery, not proof of a batch subsystem here. Batch creation of many independent incident plans is also distinct from closing several links in one scenario; the roadmap does not automatically authorize batch processing or the timeline's other V2 ideas.

## Validation boundary

All four Python modules were AST-readable in the documentation review. NetworkX was absent from the available Python interpreter, and no dependencies were installed. Source checks establish wiring and discrepancies, not runtime reliability. Next-stage tests should use synthetic directed multigraphs and known geospatial fixtures before any client pilot or operational use.
