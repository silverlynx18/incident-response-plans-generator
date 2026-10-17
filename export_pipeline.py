"""
ARPL Detour Analysis Export Pipeline
====================================
Multi-format export helper producing GeoJSON, ESRI Shapefile (zipped),
and CSV summaries from detour analysis results.

Guarantees:
- Line geometries are preserved in EPSG:4326 WGS84 without unkeyed collapse.
- Shapefile attribute names conform to the 10-character DBF specification.
- Handles empty or rejected route collections cleanly.
- Produces consistent, cross-verified outputs across formats.
"""

from typing import Any, Dict, List, Optional, Sequence, Union
import json
import os
import shutil
import tempfile
import zipfile
import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString, mapping

from detour_engine import RouteResult, IncidentClosure, normalize_closures


def route_to_feature(route: RouteResult, crs: str = "EPSG:4326") -> Dict[str, Any]:
    """
    Converts a single RouteResult into a GeoJSON Feature dictionary.
    """
    geom_dict = mapping(route.geometry) if route.geometry is not None else None
    
    properties = {
        "route_id": str(route.route_id),
        "origin": str(route.origin),
        "destination": str(route.destination),
        "valid": bool(route.valid),
        "rejection_reason": route.rejection_reason,
        "total_time_s": round(route.total_time_s, 2),
        "freeflow_time_s": round(route.freeflow_time_s, 2),
        "turn_penalty_s": round(route.turn_penalty_s, 2),
        "distance_m": round(route.distance_m, 2),
        "distance_km": round(route.distance_m / 1000.0, 3),
        "distance_mi": round(route.distance_m / 1609.344, 3),
        "num_turns": route.num_turns,
        "num_nodes": len(route.node_path),
        "score": round(route.score, 3) if route.score is not None and route.score != float("inf") else None,
        "edge_keys": [str(e) for e in route.edge_path],
    }

    return {
        "type": "Feature",
        "geometry": geom_dict,
        "properties": properties
    }


def export_to_geojson(
    routes: Sequence[RouteResult],
    output_path: Optional[str] = None,
    incident_closures: Optional[Union[IncidentClosure, Sequence[Union[IncidentClosure, tuple]]]] = None
) -> str:
    """
    Exports route analysis results to a GeoJSON FeatureCollection.
    
    Args:
        routes: Sequence of RouteResult objects.
        output_path: Optional file path to write the GeoJSON.
        incident_closures: Optional closures to include in metadata.
        
    Returns:
        GeoJSON formatted string.
    """
    features = [route_to_feature(r) for r in routes]

    metadata = {
        "generator": "ARPL Detour Engine (Stage 0)",
        "total_routes": len(routes),
        "valid_routes": sum(1 for r in routes if r.valid),
    }

    if incident_closures:
        norm_closures = normalize_closures(incident_closures)
        metadata["incident_closures"] = [
            {"u": str(c.u), "v": str(c.v), "key": str(c.key), "bidirectional": c.bidirectional}
            for c in norm_closures
        ]

    feature_collection = {
        "type": "FeatureCollection",
        "metadata": metadata,
        "features": features
    }

    geojson_str = json.dumps(feature_collection, indent=2)

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(geojson_str)

    return geojson_str


def routes_to_geodataframe(routes: Sequence[RouteResult], crs: str = "EPSG:4326") -> gpd.GeoDataFrame:
    """
    Converts RouteResult collection to a GeoDataFrame with DBF-safe 10-char column names.
    """
    rows = []
    for r in routes:
        geom = r.geometry if r.geometry is not None else LineString()
        score_val = float(r.score) if r.score is not None and r.score != float("inf") else -1.0
        
        row = {
            "route_id": str(r.route_id)[:50],
            "origin": str(r.origin)[:20],
            "dest": str(r.destination)[:20],
            "valid": int(r.valid),
            "rej_reason": str(r.rejection_reason or "")[:100],
            "tot_time_s": float(round(r.total_time_s, 2)),
            "ff_time_s": float(round(r.freeflow_time_s, 2)),
            "turn_pen_s": float(round(r.turn_penalty_s, 2)),
            "dist_m": float(round(r.distance_m, 2)),
            "num_turns": int(r.num_turns),
            "num_nodes": int(len(r.node_path)),
            "score": float(round(score_val, 3)),
            "geometry": geom
        }
        rows.append(row)

    if not rows:
        # Create empty GeoDataFrame with expected columns and schema
        return gpd.GeoDataFrame(
            columns=["route_id", "origin", "dest", "valid", "rej_reason", "tot_time_s",
                     "ff_time_s", "turn_pen_s", "dist_m", "num_turns", "num_nodes", "score", "geometry"],
            geometry="geometry",
            crs=crs
        )

    return gpd.GeoDataFrame(rows, geometry="geometry", crs=crs)


def export_to_shapefile(
    routes: Sequence[RouteResult],
    output_path: str,
    layer_name: str = "detour_routes"
) -> str:
    """
    Exports route analysis results to an ESRI Shapefile, packaged into a .zip file.
    
    Args:
        routes: Sequence of RouteResult objects.
        output_path: Destination path ending with '.zip' (or base filename).
        layer_name: Base name of shapefile layers inside the zip.
        
    Returns:
        Path to the generated zip file.
    """
    if not output_path.endswith(".zip"):
        zip_output_path = f"{output_path}.zip"
    else:
        zip_output_path = output_path

    os.makedirs(os.path.dirname(os.path.abspath(zip_output_path)), exist_ok=True)

    gdf = routes_to_geodataframe(routes)

    with tempfile.TemporaryDirectory() as tmp_dir:
        shp_base = os.path.join(tmp_dir, layer_name)
        shp_file = f"{shp_base}.shp"

        # Write shapefile
        gdf.to_file(shp_file, driver="ESRI Shapefile")

        # Create zip archive of shapefile bundle (.shp, .shx, .dbf, .prj, .cpg)
        archive_name = os.path.join(tmp_dir, "bundle")
        shutil.make_archive(archive_name, "zip", tmp_dir)

        # Move to target location
        shutil.move(f"{archive_name}.zip", zip_output_path)

    return zip_output_path


def export_to_csv(
    routes: Sequence[RouteResult],
    output_path: Optional[str] = None
) -> str:
    """
    Exports route analysis results to a CSV summary table.
    
    Args:
        routes: Sequence of RouteResult objects.
        output_path: Optional file path to write CSV.
        
    Returns:
        CSV string content.
    """
    rows = []
    for r in routes:
        row = {
            "Route ID": r.route_id,
            "Origin": r.origin,
            "Destination": r.destination,
            "Valid": r.valid,
            "Rejection Reason": r.rejection_reason or "",
            "Total Time (s)": round(r.total_time_s, 2),
            "Freeflow Time (s)": round(r.freeflow_time_s, 2),
            "Turn Penalty (s)": round(r.turn_penalty_s, 2),
            "Distance (m)": round(r.distance_m, 2),
            "Distance (km)": round(r.distance_m / 1000.0, 3),
            "Distance (mi)": round(r.distance_m / 1609.344, 3),
            "Number of Turns": r.num_turns,
            "Number of Nodes": len(r.node_path),
            "Score": round(r.score, 3) if r.score is not None and r.score != float("inf") else "",
            "Keyed Edges": "; ".join([f"({u}->{v}, key={k})" for u, v, k in r.edge_path]),
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    csv_str = df.to_csv(index=False)

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(csv_str)

    return csv_str


def export_all_formats(
    routes: Sequence[RouteResult],
    output_dir: str,
    base_name: str = "detour_analysis",
    incident_closures: Optional[Union[IncidentClosure, Sequence[Union[IncidentClosure, tuple]]]] = None
) -> Dict[str, str]:
    """
    Convenience function to export analysis results across GeoJSON, Shapefile (.zip),
    and CSV formats simultaneously.
    
    Returns:
        Dictionary mapping format name to output file path.
    """
    os.makedirs(output_dir, exist_ok=True)

    geojson_path = os.path.join(output_dir, f"{base_name}.geojson")
    shapefile_path = os.path.join(output_dir, f"{base_name}_shapefile.zip")
    csv_path = os.path.join(output_dir, f"{base_name}_summary.csv")

    export_to_geojson(routes, output_path=geojson_path, incident_closures=incident_closures)
    export_to_shapefile(routes, output_path=shapefile_path, layer_name=base_name)
    export_to_csv(routes, output_path=csv_path)

    return {
        "geojson": geojson_path,
        "shapefile": shapefile_path,
        "csv": csv_path,
    }
