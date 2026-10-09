# ARPL Incident Response Plans Generator

ARPL is a Streamlit application for exploring road-incident detours. It downloads an OpenStreetMap driving network for a selected jurisdiction, routes around a closed road segment, ranks candidate detours, and exports reviewed routes.

## Run locally

Use Python 3.10 or newer from this repository's root:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app_v1_5_6.py
```

On Windows, use `.venv\Scripts\python.exe` in place of `.venv/bin/python`.

## Streamlit Community Cloud

Deploy this repository with entry point `app_v1_5_6.py`. Network preparation requires outbound HTTPS access to the free Overpass sources and `download.geofabrik.de`. Large jurisdictions may exceed free-tier memory, download or runtime limits; test with a small area first.

## OSM loading and backups

The boundary-shapefile workflow and Fast/Balanced/Complete road selection are unchanged. Setup and **Prepare Network** use the same graph loader and cache:

1. Reuse complete, validated query responses from the runtime cache when available.
2. Request missing pieces sequentially from independent free global Overpass services, with bounded retries and provider cooldowns. Completed pieces survive a later request failure.
3. If live queries cannot complete, use a covering raw Geofabrik PBF extract, verified against the publisher's checksum. The approved `osmium` package selects genuine ways/nodes for the same selection and mode; OSMnx still builds and trims the graph.

An HTTP 200 containing an Overpass runtime-error remark is rejected. Missing node references, conflicting source data and incomplete extract coverage are errors, not usable partial networks. The app shows source and OSM data timestamps; **Geofabrik is a daily snapshot**, not live traffic data.

Network work runs in a cancellable child process, with one job at a time per app process to limit memory pressure. No separate hosted service, database, bundled road graph or paid data provider is required. Runtime files under `.arpl-cache` are excluded from Git and are not durable storage on Community Cloud.

Infrastructure settings can be supplied as environment variables (not changes to analysis parameters):

| Variable | Default | Purpose |
| --- | --- | --- |
| `OVERPASS_URLS` | Main Overpass, Private.coffee, VK Maps | Comma-separated HTTPS base URLs; Kumi is deduplicated as a Private.coffee alias |
| `ARPL_OVERPASS_BUDGET_SECONDS` | `180` | Maximum live-query stage before the independent extract backup |
| `ARPL_LOADER_TIMEOUT_SECONDS` | `900` | Overall loading/queue/graph-build limit |
| `ARPL_CACHE_DIR` | `.arpl-cache` | Runtime-only query/extract cache directory |

Prepared graphs and successful query responses expire after 24 hours. A Geofabrik file is at most 768 MiB; extracts must fit a 1.5 GiB cache budget with 200 MiB free disk reserved. Oversized parent extracts and retained-object limits fail explicitly; they never narrow the selected area or switch performance mode. Cold raw-file downloads can be substantial, especially for large or cross-border selections.

Run transport checks with `python -m unittest discover -s tests -v`. `scripts/verify_osm_loader.py` makes a genuine small-area download and compares topology, attributes and prepared weights with unchanged OSMnx using the same source data; it is not a synthetic success demonstration. Local verification does not establish Community Cloud support or operational route approval. See [loader scope and roadmap references](docs/LOADER_DESIGN.md).

Workers use `PYTHONHASHSEED=0` to keep OSMnx's aggregate tag ordering reproducible. Set the same environment variable before running the native-parity script; use `--richmond-mpo` to exercise the actual larger pilot area. This keeps the existing weight formulas unchanged while avoiding per-job random ordering.

## Limitations

Routes are planning aids, not authority-approved traffic-management plans. ARPL has no live traffic, transit, freight-compliance, or capacity model. Saved session files are local and are not suitable for durable multi-user storage.

## Included data

Boundary datasets are 2018 U.S. Census Bureau cartographic boundary files and Bureau of Transportation Statistics Metropolitan Planning Organization boundaries. Their source metadata is included beside each dataset. Census cartographic boundaries are generalized and should not be used for precise legal or area relationships.
