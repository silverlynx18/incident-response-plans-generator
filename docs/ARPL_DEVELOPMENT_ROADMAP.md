# ARPL Next-Stage Development Roadmap

**Status:** proposed development blueprint, based on the 2026-10-08 source assessment and Work Wiki `Topics\ITS\ARPL\Roadmap.md`. No feature, schema, database, dependency, deployment, or external feed selection has been implemented or approved by this document.

**Purpose:** move from an explainable single-incident detour tool toward a reusable, reviewed response-plan library, while retaining the ability to create plans for new situations. The immediate starting point is a reproducible baseline, not a replacement platform.

Use the [technical reference](ARPL_TECHNICAL_REFERENCE.md) for current wiring, source provenance, historical contradictions and B01-B10 findings, and the [user guide](ARPL_USER_GUIDE.md) for the current workflow. Historical agent summaries are supporting context; missing transcripts must not block discovery or become assumed completed work.

## Boundaries and product decisions

The original roadmap identifies open-data limitations and notes that the earlier client network was preselected for freight suitability. Generic OSM coverage does not reproduce that approval. Routes remain advisory until the responsible authority validates them.

This blueprint recommends small increments in the existing Streamlit/Python architecture. Do not introduce a new frontend, microservice system, visualization engine or database merely because it appeared in an earlier experiment. Extraction of a pure analysis function or shared geometry helper is warranted only when it removes duplicated logic or enables reliable tests.

Resolve these consequential choices before the package that depends on them:

| Decision | Recommendation / alternatives | Gate |
| --- | --- | --- |
| First deployment/user | Start with a bounded planner/operator pilot, not a public autonomous routing service; confirm jurisdiction, operator tasks, vehicle class and review owner | Before baseline scope is finalized |
| Platform and dependencies | Validate one supported Python/OS/package combination before changing floors or locking dependencies; local Windows versus hosted deployment has different constraints | B0 |
| Distance semantics | Recommend total detour-route length, not extra distance relative to a baseline; the latter requires a defined unobstructed reference trip | B3 |
| Closure policy | Preserve directed `(u,v,key)` identity; decide explicit expansion to both directions/all parallel carriageways and area-touch rules | C1-C2 |
| Persistence | Evaluate local file/embedded storage for a single deployment versus a server database for concurrent users; select only after tenancy, backup and deployment needs are known | P1 |
| Scoring / operations | Hard legal/safety restrictions are exclusions; school-zone avoidance may be a weighted preference or time-dependent exclusion; signal outputs initially advisory, never device commands | S1-S2 |
| Dynamic feeds | Confirm provider/license/coverage, refresh and stale-data limits, fallback policy, and transit use case before choosing APIs or libraries | D1-D3 |
| Broader coverage | Choose a specific urban and non-US pilot with authority-approved data; do not promise global/freight compliance from generic OSM tags | G1-G2 |

Market size, commercial model, client count and revenue discussed in `ARPL DIF.md` remain unvalidated discovery questions. They do not dictate storage/provider architecture. A library generator, a live response tool, and batch generation of independent scenarios are distinct products/workflows; batch processing is not part of the first increment.

## Dependency-aware stages

Stages are capability gates, not a calendar or staffing estimate.

| Stage | Packages | Exit gate |
| --- | --- | --- |
| 0. Trustworthy baseline | B0-B6 | Fresh single-incident workflow and all connected exports pass reproducible checks; no stale-analysis export or mislabeled constraints |
| 1. Closure scenarios | C1-C3 | Multiple keyed links and an affected area have explicit exclusion policy, stable results and complete scenario exports |
| 2. Asset and library foundation | A1-A3, P1-P3 | Traceable asset ingestion/delivery plus durable, reviewable, versioned plan recall |
| 3. Asset-aware decisions | S1-S2 | Explained exclusions/preferences and reviewed advisory asset actions; no control-system actuation |
| 4. Dynamic and modal evidence | D1-D3 | Freshness-aware traffic estimates, validated static transit data and one bounded transit/bus use case |
| Coverage track | G1-G2 | Urban/non-US/vehicle acceptance fixtures and pilot checks support explicit coverage claims |

Coverage fixtures and data discovery can start during Stage 0; broader routing changes depend on the keyed-edge/constraint baseline. Asset work can begin after Stage 0 without waiting for every closure increment. Durable scenario-plan storage depends on the scenario/result contract, not merely a successful upload-save function.

## Stage 0: concrete first-development backlog

All test paths below are **proposed new tests**, not existing executable commands. Choose the repository-standard runner during B0; no test framework or dependencies were added during this documentation phase. Reproduce each suspected defect before fixing it, then keep its regression test.

| ID | Work / exact touchpoints | Dependencies | Completion evidence |
| --- | --- | --- | --- |
| B0 | Establish approved target environment, data fixture policy and runner; reconcile `run.bat`/`run.sh` with `app_v1_5_6.py`; verify direct imports and geospatial drivers | Product/platform decision | Clean install and launch on the chosen target; record exact interpreter/package versions and a setup smoke path; dependency/config changes reviewed separately |
| B1 | Characterize `clean_graph`, `prepare_graph`, `get_surrounding_turns`, `generate_incident_graph`, `get_detour` in `detour_utils.py` using small directed MultiDiGraphs | B0 | Proposed `tests\test_routing_baseline.py`: known shortest path/cost, disconnected pairs, time boundaries, parallel edges and input graph unchanged |
| B2 | Correct incident identity/removal and preserve selected keyed edges through routing, metrics and geometry; app `get_edge_options`, detour path/removal code, export helpers | B1; closure policy | Two identically labeled edges remain separately selectable; a selected closed key cannot appear in output; unrelated outgoing edges remain; route cost/IDs/geometry use the same keys |
| B3 | Define/enforce distance and time semantics; wire buffer control; unify initial/sidebar network preparation without SIGALRM dependence | B1, B2; distance/platform decisions | Proposed `tests\test_analysis_parameters.py`: total-distance boundary cases, 120-second/current maximum time behavior or explicitly approved replacement, slider value reaches evaluation/export, both entry paths work on Windows if supported |
| B4 | Give analyses/routes stable identity, invalidate evaluated results on incident/network/parameter/layer changes, and separate no-route from errors; app ranking/state/evaluation/export blocks | B2, B3 | Proposed `tests\test_analysis_state.py`: all-invalid results show no-route without empty min/max crash; reorder does not transfer acceptance; changed inputs cannot export old evaluated routes |
| B5 | Repair upload round-trip/isolation; canonical keyed geometry and metric buffer computation; consistent function-based export payloads | B2, B3; tenancy decision | Proposed `tests\test_assets_and_exports.py`: saved layer restores geometry/CRS/attributes/metadata; two sessions remain isolated; curved/parallel edges survive every connected format; conditional sheets/rows have documented contents |
| B6 | Exercise full single-incident workflow on fixture network and approved small pilot; document actual supported environment and remaining issues | B4, B5 | Setup -> selection -> analysis -> acceptance -> evaluation -> seven exports completed; exported data matches approved fixture; source/runtime/client-validation statuses remain distinct |

**Start gate:** accept the bounded pilot, target environment and reproduction scope. **Exit gate:** B0-B6 evidence is recorded, blocking correctness/isolation issues are resolved, and existing single-incident acceptance cases are green. A launch alone does not pass Stage 0.

For fixtures, use directed paths with declared costs and keyed parallel edges, an incident with empty refs, a disconnected destination, a route exactly at a configured time/distance boundary, and curved segment geometries. Create synthetic spatial data in a metric CRS with points at 99, 100 and 101 meters from a route for a 100-meter inclusive buffer. Specify numeric precision before assertions; do not use generous fallbacks that hide wrong units.

Compatibility means retaining the single-incident workflow and independently verified behavior, not preserving defective outputs from the current checkout. Before B2, define fixture expectations from the declared directed keyed graph and policy: the chosen closed key is absent, unrelated outgoing keys remain eligible, feasible alternatives are found, path cost and exported geometry use the same edge keys, and the source graph is unchanged. Characterization tests must identify known defects rather than freeze them as correct snapshots. C1 compares against the corrected, verified B6 baseline.

## Provisional common contracts

These are design proposals, not committed API signatures or migrations. Extend existing payloads conservatively and decide exact types during feature design:

- **AnalysisContext:** analysis ID, jurisdiction/polygon/CRS, network snapshot/version, source timestamps, vehicle/mode, departure time when relevant, explicit parameters and scoring-policy version.
- **Scenario:** scenario ID/version, incident description, explicit set of directed keyed closed edges, optional affected geometry and closure policy, source/validity interval.
- **RouteResult:** stable route ID, node path **and keyed edge sequence**, geometry, distance in meters, freeflow/turn/total time in seconds, validity/rejection reason, score breakdown and contributing assets.
- **AssetLayer:** source and stable IDs, type, geometry/CRS, source-specific attributes, mapped canonical fields, timestamp/version, quality warnings and license.
- **Plan:** scenario/context snapshot, chosen route/action set, supporting export/evidence references, status, review/approval provenance, operational feedback and invalidation reasons.

Prefer one coherent result contract shared by UI and exporters to multiple incompatible dictionary/tuple fallbacks. Stable IDs must not be display positions or unverifiable OSMIDs; graph snapshot + `(u,v,key)` establishes edge identity within that snapshot, not eternal identity across OSM updates.

## C: multiple road links and affected areas

**Outcome:** represent closures caused by multiple incidents, queues, flooding or events; every returned path respects the scenario, not just one visual incident marker.

**Reuse/touchpoints:** app incident selector and map layers, `get_surrounding_turns`, `generate_incident_graph`, `get_detour`, research `create_sector`/`get_impacted_arterials`, and all connected `export_to_*` functions. Sector helpers are leads to assess, not ready-made validated area closures.

| Package | Small increment / follow-on work | Dependencies and acceptance |
| --- | --- | --- |
| C1 | First support an explicit list of keyed closed edges with one chosen upstream/downstream anchor pair; then add alternative entry/exit selection for compound incidents | B6, approved direction/mainline policy. Single-link case retains the workflow and passes corrected B6 route invariants, not defective historical outputs; duplicate/unknown edges are handled explicitly; original graph is unchanged; no returned keyed path uses a closed edge; legitimate unrelated roads are not accidentally blocked |
| C2 | Convert an uploaded/drawn affected polygon into a previewed closure set using actual edge geometry; then support additional valid geometry forms if needed | C1, metric/CRS baseline, approved intersects-versus-contained/touch policy. Crossing, tangent, disjoint, invalid, empty and MultiPolygon fixtures produce the declared exclusion set; reverse directions and partial segments follow explicit policy |
| C3 | Carry scenario ID, closed-edge set/area, anchors and policy through route review and every export; keep the single-incident legacy view available | C1; C2 for area outputs. Every output identifies the full scenario and the same route keys/geometry; zero-route scenario is explicit; changed closures invalidate old results |

**Data/tests:** synthetic graph with known detour alternatives and disconnected cases; a bounded flood/event polygon and approved network for pilot. Validate queue extent from actual input, not a fixed-degree wedge. No flood severity/model or queue forecasting is promised.

**Design choice:** hard removal/exclusion of explicit closed keys versus large-cost discouragement. Recommend hard exclusions for closures, keeping broad mainline discouragement a separate policy. Resolve endpoint/anchor selection when the entire incident corridor is blocked.

## A: asset retrieval, normalization and operator-ready delivery

**Outcome:** load inconsistent authority datasets with visible quality checks and deliver complete, traceable route/asset information.

**Reuse/touchpoints:** `process_shapefile_upload`, `get_best_name_field`, layer dictionaries, `is_traffic_signal_data`, `buffer_search`/`get_points_in_buffer`, export functions. Extract a shared canonical schema/geometry helper only as needed.

| Package | Small increment / follow-on work | Dependencies and acceptance |
| --- | --- | --- |
| A1 | First map one pilot authority's uploaded signal dataset to canonical identity/type/CRS fields while preserving source attributes; then add explicit source adapters (GeoJSON/ArcGIS only if authorized) | B6, source/license approval. Missing CRS/ID, duplicates, empty/mixed geometry and ambiguous mappings produce actionable warnings/errors; no layer is silently misclassified by its name |
| A2 | Apply one metric route/asset intersection engine for points and approved line/polygon associations; allow attribute mapping and preview | A1, keyed route geometry. Known-distance tests include boundary/multipart/high-latitude cases; schools zones are returned as zones, not coerced into points; independent GIS comparison matches declared precision |
| A3 | Define an operator-approved bundle/schema with scenario, keyed routes, asset tables, maps, units, provenance and warnings; implement in the existing export paths | A2, C3 for multi-closure bundles, operator template approval. All seven connected formats round-trip required data or explicitly state format limitations; names/IDs/geometry/units agree; assets are not silently omitted |

**Data/tests:** one authority sample plus synthetic missing/duplicate IDs, mixed geometries and CRS fixtures; source permission, redistribution limits, schema changes and refresh expectations recorded. Data adapters must distinguish network failure from an empty dataset.

**Design choice:** generic field mapping versus bespoke city adapters. Recommend a small mapping contract plus a first concrete adapter, not universal ingestion. Human-confirmed schema mapping is more reliable than broad traffic/signal keyword heuristics.

## P: durable data and a validated response-plan library

**Outcome:** reuse prepared data and reviewed plans without confusing an accepted candidate, an approved plan, and an operationally successful plan.

**Reuse/touchpoints:** app `save_session_data`/`load_session_data`, state initialization/reset, `osm_network_loader` metadata/graph loading, analysis/evaluation payloads, and export provenance.

| Package | Small increment / follow-on work | Dependencies and acceptance |
| --- | --- | --- |
| P1 | Define deployment/tenancy, snapshot identity, persistence/backup policy, and storage choice; first retain network/assets with a proven save/load contract | B5, A1; storage approval. Restart restores geometry, CRS, metadata and versions; two tenants do not see/overwrite each other's data; missing/corrupt/incompatible snapshots fail explicitly; restore from backup is demonstrated |
| P2 | Store scenario + reviewed route/action snapshots; add browse/search/recall and an explicit review status, without automatic operational approval | P1, C3, approved review owner/lifecycle. A draft cannot masquerade as approved; reviewer/time/source captured; recall reconstructs the same scenario, routes and artifacts; changing inputs creates a new version |
| P3 | Add stale/invalidation checks, operational feedback, and controlled reuse of proven plans; later expand retrieval only if operators need it | P2; network/asset/scoring version policy. Changed edge keys, expired data or policy invalidate/flag affected plans before reuse; success/failure/unknown feedback is distinguishable; superseded plans remain auditable |

**Proposed lifecycle:** draft -> reviewed -> approved; retired/superseded/stale are explicit states. Operational success is separate evidence linked to an execution/event, not a consequence of clicking Accept. Decide whether stale approved plans are blocked or viewable with a warning; recommend blocking operational reuse pending review while allowing historical inspection.

**Data/tests:** restart/round-trip fixtures, version migration/corruption tests, concurrent write/isolation tests on the chosen deployment, network-change and lost-edge fixtures. Confirm client retention/privacy/export rights, backups and refresh policy. Do not load untrusted serialized graphs as an ingestion strategy.

**Design choice:** embedded database/file snapshots versus server database; simple filters versus similarity retrieval. Recommend the least complex storage meeting concurrency and audit needs, with explicit keys/filter recall first. No database package or backend architecture is chosen in this phase.

## S: asset states and route scoring

**Outcome:** explain why a route is feasible/preferred and what asset actions a reviewed response plan might require.

**Reuse/touchpoints:** graph weight preparation, `get_detour`, app composite ranking and route-details UI, canonical assets from A, library policies from P, PDF/tabular metadata.

| Package | Small increment / follow-on work | Dependencies and acceptance |
| --- | --- | --- |
| S1 | First support one school-zone avoidance preference with explicit units and score explanation; also model mandatory restrictions separately; then extend reviewed policy types | B6, A2, C1, approved exclusion/preference semantics. Forbidden edges never appear; changing a preference changes a known fixture's ranking predictably; zero weights preserve baseline order; score explains each contribution; time windows use a declared timezone |
| S2 | First attach advisory signal/asset-state requirements and responsible review to a plan; only model timing impact when validated movement/signal data exists | S1, P2, approved client timing/state data. Missing/conflicting/expired plans are marked unknown/unusable; signal impacts are traceable; no field device or controller receives commands |

**Data/tests:** dated school zones, vehicle restrictions, signal identifiers/control plans and approved response measures. Validate nonnegative/consistent routing costs; school preference is not a calibrated congestion model. Route ranking alone cannot correct a shortest-path search that ignored mandatory restrictions.

**Design choice:** score existing candidates versus modify path costs. Recommend exclusions in feasibility/search and transparent preferences in costs/ranking, with candidate coverage tests. Replace the current unnormalized "percentage" interpretation only through a documented calibration decision.

## D: near-real-time traffic and transit

**Outcome:** use timestamped evidence rather than imply that estimated OSM speeds are live; support one precise transit/bus problem before general multimodal routing.

**Reuse/touchpoints:** `compute_traveltime_bearing`, `compute_turntime`, `get_detour`, analysis context/departure-time UI, versioned snapshots/library invalidation and exports. Existing static Dijkstra is not sufficient for schedule-dependent multimodal transfers.

| Package | Small increment / follow-on work | Dependencies and acceptance |
| --- | --- | --- |
| D1 | First apply a fixed-time road travel-time snapshot matched to graph edges; then add an authorized refresh adapter | B6, P1, G1 matching/coverage contract, feed approval. Unmatched links, missing values, stale/future timestamps and outage are visible; effective timestamp/source exported; a known fixture's route changes with its weights; fallback is explicitly selected/labeled |
| D2 | Ingest/validate one static GTFS feed and show routes/stops/schedules for planning before routing with it | A1, P1, transit dataset/license approval. Stop geometry, trip/calendar relationships, timezone, service exceptions and times beyond 24:00 tested; date with no service is explicit; feed version retained |
| D3 | Implement one approved use case: bus road detour preserving required stops **or** driver-to-transit transfer routing; split the other into later work | D1, D2, C1, G2, approved vehicle/transfer/accessibility policy. Correct directed roads, stops, boarding/service availability and arrival sequence on timetable fixtures; no-service/unreachable/late-transfer cases give explicit outcomes; no static fallback presented as live |

**Data/tests:** provider-approved traffic links with timestamp/units/coverage and static GTFS fixtures. Define maximum permitted age and refresh cadence with the provider/client, not invented constants. Real-time GTFS is a separate later adapter requiring disruption/freshness handling.

**Design choice:** road snapshot integration versus time-dependent routing; overlay versus full multimodal solver. Recommend snapshot road weights and static transit validation first. Consider a dedicated time-dependent routing model only after selecting D3's use case; evaluate dependency alternatives before any integration.

## G: granularity, geography and vehicle suitability

**Outcome:** make coverage explicit for urban/unreferenced roads and selected non-US networks, with vehicle suitability enforced where authority data supports it.

**Reuse/touchpoints:** OSM filters and jurisdiction controls in app, `clean_graph`, speed/ref normalization, `find_turns`/`traverse_direction`, metric buffers, keyed route contracts and export CRS.

| Package | Small increment / follow-on work | Dependencies and acceptance |
| --- | --- | --- |
| G1 | First decouple turn/anchor discovery from mandatory shared road refs for one urban fixture; then validate a selected non-US area with correct units/CRS/driving rules | B6, C1 for closure regressions, approved geography. Empty refs, roundabouts, dual carriageways, one-way streets, ramps, crossings and disconnected/partial polygons behave explicitly; meters/speed units and southern-hemisphere projection validated; original highway fixtures stay green |
| G2 | First enforce a client-approved eligible-road network or vehicle restriction dataset for one vehicle class; then expand height/weight/access/turn checks as data permits | G1, A1, client suitability policy; needed before D3 bus/freight claims. Known forbidden links/turns never appear; missing eligibility is unknown, not compliant; feasible/no-feasible cases and exported warnings agree with authority checks |

**Data/tests:** approved urban and non-US graphs, referenced and unreferenced roads, metric/imperial speeds, CRS edge cases, vehicle restrictions, bridge clearances/weights and any authority-approved diversion network. OSM completeness and diversion capacity are independent constraints; absent demand/capacity evidence must remain a limitation.

**Design choice:** topology-based local turn discovery versus continuation heuristics, and hard eligibility whitelist versus attribute constraints. Recommend a validated bounded geometry/topology approach and an authority-approved network for the first vehicle pilot, not unsupported global compliance.

## Dependency register

Package dependencies below complement the Stage 0 table and prevent a feature being planned on top of an absent prerequisite:

```text
B0 -> B1 -> B2 -> B3
B2 + B3 -> B4 + B5 -> B6
B6 -> C1 -> C2; C1 -> C3 (C2 required for area delivery)
B6 -> A1 -> A2 -> A3 (C3 required for multi-closure delivery)
B5 + A1 -> P1; P1 + C3 -> P2 -> P3
B6 + A2 + C1 -> S1; S1 + P2 -> S2
B6 + C1 -> G1; G1 + A1 -> G2
B6 + P1 + G1 -> D1; A1 + P1 -> D2
D1 + D2 + C1 + G2 -> D3
```

Approval/data gates also apply even when the code dependency is satisfied. Parallel work is possible after common contracts are agreed, but each package needs its own review and acceptance evidence.

## Validation and handoff gates

| Level | Required evidence |
| --- | --- |
| Unit / synthetic | Known keyed paths/costs; no closure violations; unchanged input graph; exact time/distance policy boundaries; invalid/empty input and no-path/error distinction |
| Geospatial / formats | Consistent CRS/units; independent metric-distance comparison; curved/parallel-edge geometry round-trips; multipart/boundary cases; identities and provenance agree across formats |
| Integration / lifecycle | UI parameters reach analysis/export; stale results cannot be reused; restart/isolation/version/backup checks; dataset/feed failure visibly distinct from empty data |
| Domain pilot | Authority reviews diversion legality, vehicle suitability, asset accuracy and operator bundle; measured runtime on a defined area/environment; documented limitations and sign-off |
| Operational library | Reviewed plan lifecycle, current evidence, explicit invalidation and feedback; library recall never implies unreviewed operational approval |

Start a later implementation session with **B0-B1**, reproducing the baseline rather than adding a roadmap feature immediately. Agree consequential design choices at their package gates; write executable tests and detailed implementation plans for the selected increment, not speculative code for the entire roadmap.
