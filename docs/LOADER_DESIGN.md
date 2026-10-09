# Reliable OSM loading: implementation contract

## Existing requirements and scope

Reference notes: the existing Work Wiki's `Topics/ITS/ARPL` folder. These local notes are the requirements reference, not public repository links.

- Original `Roadmap.md`: retain the existing single-incident workflow; open OSM data is not a freight-suitability or diversion-capacity approval. Multiple closures, asset-aware scoring, durable reviewed-plan recall, feeds and broader routing behavior remain separate future work.
- `ARPL Technical Reference.md`, Architecture/connected data flow: boundary shapefile/custom polygon -> OSM graph -> `clean_graph` -> `prepare_graph` -> existing incident/detour/review/export pipeline. This repair changes acquisition, not the subsequent pipeline.
- `ARPL User Guide.md`, section 2: Fast/Balanced use the current matched highway filters; Complete uses the OSMnx drive preset, not all OSM ways. Both initial launch and later Prepare Network must use those same meanings.
- `ARPL Development Roadmap.md`, B0/B3 and technical findings B02/B09: establish a reproducible runtime and unify initial/sidebar loading without SIGALRM. This is only the loading portion of that baseline work; it does not claim B0-B6 or the full B3 package is complete.
- `ARPL Development Roadmap.md`, P1-P3: runtime download caches are **not** a durable response-plan library or an approved persistence design. No database, stored-plan lifecycle or backup architecture is introduced.

The original roadmap and user's current repair constraints take precedence over implementation proposals. Osmium was separately approved for genuine raw-data ingestion; City2Graph is explicitly deferred until the existing app works. No parameter values, classification rules, scoring, exports, incident selection or visualization engine are redesigned.

## Problem and usage

Boundary shapefiles and the app's existing parameters remain unchanged. Setup, sidebar Prepare Network and utility callers all use the same loader:

```python
graph = du.graph_from_polygon_with_fallback(polygon, progress=show_progress,
    network_type="drive", custom_filter=existing_filter, simplify=True,
    retain_all=False)
prepared = du.prepare_graph(du.clean_graph(graph))
```

The UI's prepared-graph cache returns independent deserialized graphs, not shared mutable resources. Complete mode retains OSMnx's drive preset; Fast/Balanced retain the exact existing unanchored regular expressions.

## Shape

- `osm_loader.py`: one public graph-loading operation; supervises a disposable worker, progress, deadline, validated cross-mirror query cache and bounded free Overpass failover. The worker replaces only OSMnx's acquisition seam, leaving buffering, graph creation, directionality, simplification, component selection and street counts to the existing installed OSMnx implementation.
- `geofabrik_source.py`: one raw-data backup operation. Selects complete coverage from the single public Geofabrik catalogue; streams and verifies the raw PBF to runtime cache; reads it with approved `osmium==4.3.1`; retains entire matching ways and every referenced node. Returns genuine OSM elements and provenance to the same OSMnx graph pipeline. No bundles, synthetic graphs or per-state provider integrations.
- Existing `detour_utils.py`: graph cleanup and routing weights stay unchanged; former downloader delegates to the single new loading boundary.

Private backup signature:

```python
load_elements(polygon, filters, *, session, cache_dir, deadline, progress)
# -> (validated OSM payload, source/snapshot provenance)
```

The backup receives the effective OSMnx query footprint, including its existing buffer and polygon-coordinate rounding. It does not simplify or build separate tile graphs.

## Synthesis decision

Compared two independent architecture candidates: isolated query-first acquisition using OSMnx's own graph operation, and catalogue-selected extract-first acquisition with two-pass PBF processing. Choose query-first: genuine Overpass successes can be much quicker than a 408 MB cold state download. Adopt the independent Geofabrik backup and complete-reference extraction from the extract-first candidate. Reject duplicating OSMnx graph finishing, global patches in the Streamlit process, and mutable cached graphs shared across sessions.

## Tradeoffs and boundaries

- Accept worker startup/serialization overhead for enforceable cancellation and isolation of the private OSMnx hook.
- Fix worker `PYTHONHASHSEED=0` for reproducible native tag aggregation. Existing ARPL cleanup sometimes chooses the first aggregate value, so process-random set order would otherwise change weights between identical loads. No speed formula or road-classification rule is changed; native-parity verification uses the same seed.
- Accept one checked private acquisition seam instead of reimplementing graph semantics. Unsupported OSMnx internals must fail clearly.
- Retain complete successful query pieces across mirror failures; fail closed on response remarks, missing references and conflicting overlap data.
- A raw-extract fallback uses one daily snapshot for the whole graph, never silently mixes partial live data with a nightly extract.
- Free endpoints have no promised SLA. Respect cooldowns/Retry-After; do not race or hammer mirrors.
- Geofabrik snapshots update daily. Display actual provenance/timestamps; caches are bounded, runtime-only and ignored by Git.
- Download size, disk and retained-element limits may make the extract backup unavailable for very large/cross-border areas. Report that limitation rather than omitting roads or changing mode.
- City2Graph is a future integration, not part of this repair. The user explicitly wants the existing app restored first.

## Verification

Fault tests can simulate HTTP errors; successful graph/loader demonstrations must use genuine OSM. Compare keyed edges, topology and relevant attributes against unchanged OSMnx on the same actual elements. Exercise both UI loading paths. Separate cold/warm and local/cloud measurements; do not label a local success as verified cloud behavior.
