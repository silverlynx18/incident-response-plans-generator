# ARPL User Guide

This guide follows the current `app_v1_5_6.py` source, whose title is **Traffic Detour Finder V1.6.1**. It is a source-grounded operating guide, not evidence of a successful runtime or an operationally validated response plan. See [deployment notes](../DEPLOYMENT_README.md) before starting.

## Intended use and safety boundary

Use ARPL to explore candidate detours around a selected road incident, review routes, and export supporting analysis. The existing workflow is single-incident and road-based. It does not model live congestion, diversion capacity, freight clearance/compliance, signal timing changes, GTFS connections, or a validated response-plan library.

An **Accept** action is a UI selection for analysis/export, not transport-authority approval. Independently check direction, geometry, access restrictions, vehicle suitability, bridge limits, network coverage, asset accuracy, and traffic-management measures before operational use.

## 1. Configure the analysis

On a new session, the app opens a **single-page setup**, not the six-step wizard described in historical documentation.

Under **Jurisdiction Selection**, the setup **Select State:** list currently contains Virginia only. Choose **Jurisdiction Type:** County, MPO, Urban Area, or Custom, then select the relevant jurisdiction. Standard boundaries use the packaged state/county/MPO/urban-area layers.

For custom boundaries, use **Data Upload**:

1. Upload one jurisdiction dataset using **Upload Jurisdiction Shapefile:**.
2. Select **Process Jurisdiction Files**. Jurisdictions must contain Polygon or MultiPolygon geometries.
3. Enter **Jurisdiction Name:** and select **Save Jurisdiction**.
4. Choose **Custom** under Jurisdiction Type, select the saved layer, and select a polygon if it contains more than one feature.

The states layer is still required even for a custom boundary. The save action makes the layer available in the current session; it is not a reliable promise of retention after restarting.

### Upload requirements

The connected upload UI accepts ZIP or individual `.shp`, `.shx`, `.dbf`, `.prj`, and `.cpg` files. Supply matching filenames and a known CRS; a ZIP containing one complete shapefile is simplest. The parser uses the first ZIP and first shapefile it finds, so process multiple datasets separately. GeoJSON and ArcGIS URL ingestion are not offered by this checkout's upload interface.

CRS conversion to EPSG:4326 is attempted when CRS metadata exists. Missing CRS is not evidence that coordinates are WGS84; repair the dataset in GIS before upload rather than assuming a coordinate system.

### Optional asset layers

Under **Additional Data (Optional)**, use **Upload Additional Shapefiles:**, **Process Data Files**, a **Data Layer Name:**, and **Save Data Layer**. Point/line/polygon data can be loaded and displayed, but the route proximity helper only returns point/MultiPoint assets. A displayed school-zone polygon does not currently influence route scoring.

Signal icons are selected using layer/column-name heuristics, not a validated signal inventory schema. Inspect the loaded attributes and coordinate locations.

## 2. Prepare the network and launch

Select **Performance Mode:** under **Ready to Launch**, then **Launch Application**. This downloads the selected area's OSM driving network, cleans graph attributes, and prepares routing weights.

| Mode | Implemented coverage |
|---|---|
| Fast | Highway filter including motorway, trunk, primary, secondary, and link classes matched by the filter |
| Balanced | Broader filter adding tertiary, residential, unclassified, and associated matched links |
| Complete | OSMnx `network_type="drive"` without the custom highway filter; not every kind of OSM way |

Start with a modest analysis area. Smaller or filtered networks may omit useful alternatives; a route cannot use roads absent from the downloaded graph. No current download-time benchmark has been established.

After launch, the sidebar shows **1. Data Configuration**, **2. Area Selection**, **3. Actions**, **Additional Data Layers**, **4. Analysis**, and **5. Actions**. The main sidebar's state selector uses the full loaded state list, unlike setup's Virginia-only selection.

For a later area/mode change, **Prepare Network** is the intended action, but its Windows timeout implementation is a known source-level blocker. On Windows, do not assume it works because setup succeeded. See [known limitations](ARPL_TECHNICAL_REFERENCE.md#baseline-discrepancies).

**Restart Setup** returns to setup; **Reset Session** clears selections, graph, route results, and in-memory layer dictionaries. Export needed work first. Neither action is a reliable disk-cleanup or isolation mechanism.

## 3. Select an incident

Inspect road popups on **Network Graph View**, then use **Select Incident Edge** in the sidebar. Labels combine OSMID, road name, and highway type. Search for the OSMID/name, inspect the location and direction, and choose the intended link.

**Confirm Incident Link** sets the zoom/highlight feedback; it is not an additional validation or required closure-approval step. **Pick Random Edge** is available for exploration, not a substitute for choosing the actual incident.

Map-click selection is attempted in code but relies on Leafmap callback behavior and inconsistent multigraph lookup. Use the sidebar as the predictable source of selection and verify the highlight. Labels are not guaranteed unique when multiple graph edges share the same OSMID/name/type; exact edge identity is an engineering prerequisite, not solved by this guide.

## 4. Set analysis parameters

| Control | Range; default | Actual source behavior |
|---|---|---|
| Max Detour Distance (km) | 1-50; 10 | Converted to meters but not applied to routing or route filtering. Do not treat it as an enforced limit. |
| Max Detour Time (minutes) | 5-120; 30 | Converted to seconds and applied to estimated freeflow route time, not total penalized time or live travel time. |
| Max Alternatives | 1-20; 5 | Limits the displayed ranked routes unless Show All Routes is enabled; also sets turn-search depth to at least 10. It is not a fixed number of distinct paths for one origin/destination pair. |
| Buffer Distance for Points (miles) | 0.1-2.0; 0.1, step 0.1 | Slider is not assigned to the `buffer_distance_miles` state key used by evaluation/export. Those paths default to 0.1 miles when the key is absent. Verify the reported effective value; changing the slider is not reliable configuration. |

The source also applies a fixed **120-second minimum freeflow time**. There is no current detour-tolerance or separate turn-node control matching the old README.

## 5. Find and review detours

Select **Find Detours**. The code finds entry/exit turn candidates around the incident road, applies incident/mainline restrictions, and computes shortest paths between candidate node pairs.

The success count can include unsuccessful node pairs, so it is not necessarily the count of usable routes. The current all-invalid/no-path display branch needs repair; if an exception or empty result appears, record it rather than assuming analysis succeeded.

Routes with paths are ranked using total estimated time with turn penalties, node count, and the freeflow-to-total-time ratio. These are heuristic scores, not a calibrated congestion or safety assessment. Review each route's map and **Route Details**.

Use **Accept**, **Reject**, and **Hide** to manage displayed routes. **Show All Routes** toggles between the default top-ranked subset and all ranked routes. Acceptance state is indexed by display position; after changes to incident, area, settings, or displayed routes, do not assume earlier selections still refer to the intended analysis.

## 6. Evaluate accepted routes

After accepting at least one route, optionally enable **Enable Buffer Search for Detour Analysis**, then select **Evaluate All Accepted Routes**. This builds the accepted-route payload and enables the export section.

The point search first filters uploaded features to the selected jurisdiction, then checks proximity to routes. Counts distinguish unique points from repeated points across routes. Boundary behavior, approximate geographic distances, MultiPoint handling, and effective buffer settings need verification; these results are indicative proximity, not engineering-grade distance certification.

Accepted routes are visualized on the network map after evaluation. Re-evaluate after changing accept/reject choices. Because old evaluated state is not comprehensively invalidated, restart/reset and repeat a fresh workflow before relying on an export from a changed analysis.

## 7. Export

In **Export Results**, choose **Choose export format:**, select **Export** for that format, then use its **Download** button.

| Format | Connected output |
|---|---|
| PDF Report | Title/route analysis, optional maps, paginated segment information including OSM IDs, and stored buffer-point details |
| GeoJSON | FeatureCollection with incident and accepted route lines; route buffer counts, not a complete asset layer |
| KML | Incident and route lines with styles |
| KMZ | ZIP containing `doc.kml`, generated from the KML function |
| Shapefile | ZIP of accepted route geometries/attributes; the connected function does not include an incident layer |
| Excel | Incident Edge, Route Segments, and Buffer Points sheets when each has data |
| CSV | Combined incident/route-segment table; the connected function does not add buffer-point rows |

GeoPackage exists as a helper but is not in the current export dropdown. Historical HTML/Kepler exports are not current options.

Inspect exports in the target GIS or document viewer. Route-line exporters can fall back to node-to-node coordinates rather than preserve every curved keyed edge; incident attributes and parallel-edge selection can also differ. Downloading a nonempty file alone is not proof of fidelity.

## Troubleshooting

| Symptom | Useful action or boundary |
|---|---|
| `app.py` not found | Run `python -m streamlit run app_v1_5_6.py` from the repository root; unchanged launch scripts use the wrong filename. |
| State shapefile required / layer fails to load | Check data paths, all shapefile components, CRS metadata, and working directory. |
| Only Virginia appears at setup | This is the current setup list, not a data-download failure. Broader setup coverage is proposed work. |
| Network preparation fails on Windows with a signal API error | The sidebar path uses Unix alarm APIs. Record the failure; fixing it is baseline backlog work. |
| No start/end nodes or no usable route | Check network coverage, refs, connectivity, and time bounds. The routing/no-path branches may need repair; do not infer all incidents are reroutable. |
| Slider change appears ineffective | Distance is not enforced and evaluation buffer state is unwired; see the parameter table. |
| No export section | Accept a route and Evaluate All Accepted Routes; ensure an actual evaluated payload exists. |
| Uploaded data disappears after restart | Local save/load code does not match the layer structure. Keep originals and do not rely on retention. |
| Asset count or route geometry looks wrong | Inspect CRS, jurisdiction clipping, actual edge geometry and effective buffer; avoid operational reliance pending fixture/pilot validation. |

For engineering issues and proposed fixes, use the [technical reference](ARPL_TECHNICAL_REFERENCE.md) and [development roadmap](ARPL_DEVELOPMENT_ROADMAP.md). Runtime behavior has not been tested as part of this documentation consolidation.
