"""
Unit tests for ARPL Export Pipeline
===================================
Tests covering:
- GeoJSON export format, geometry retention, and properties
- ESRI Shapefile export with DBF 10-character field truncation and .zip creation
- CSV summary table export with metric calculations
- Multi-format batch export helper (export_all_formats)
- Empty / rejected routes resilience without crashes
"""

import unittest
import json
import os
import sys
import tempfile
import zipfile

# Ensure parent directory is in sys.path
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import geopandas as gpd
from shapely.geometry import LineString

from detour_engine import RouteResult, IncidentClosure
from export_pipeline import (
    export_to_geojson,
    export_to_shapefile,
    export_to_csv,
    export_all_formats,
    routes_to_geodataframe
)


class TestExportPipeline(unittest.TestCase):

    def setUp(self):
        self.geom1 = LineString([(-77.0365, 38.8977), (-77.0315, 38.8978), (-77.0265, 38.8977)])
        self.geom2 = LineString([(-77.0365, 38.8977), (-77.0315, 38.8965), (-77.0265, 38.8977)])

        self.route_accepted = RouteResult(
            route_id="route_primary",
            origin="N0",
            destination="N3",
            node_path=["N0", "N1", "N3"],
            edge_path=[("N0", "N1", 0), ("N1", "N3", 0)],
            geometry=self.geom1,
            distance_m=3000.0,
            freeflow_time_s=150.0,
            turn_penalty_s=0.0,
            total_time_s=150.0,
            num_turns=0,
            score=105.6,
            valid=True,
            rejection_reason=None
        )

        self.route_rejected = RouteResult(
            route_id="route_secondary",
            origin="N0",
            destination="N1",
            node_path=["N0", "N1"],
            edge_path=[("N0", "N1", 1)],
            geometry=self.geom2,
            distance_m=1200.0,
            freeflow_time_s=90.0,
            turn_penalty_s=0.0,
            total_time_s=90.0,
            num_turns=0,
            score=63.4,
            valid=False,
            rejection_reason="Too Short: travel time below minimum threshold (120s)."
        )

        self.routes = [self.route_accepted, self.route_rejected]
        self.closure = IncidentClosure(u="N0", v="N1", key=0, description="Test incident")

    def test_geojson_export(self):
        """Verifies GeoJSON export schema, features, properties, and metadata."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = os.path.join(tmp_dir, "test.geojson")
            geojson_str = export_to_geojson(self.routes, output_path=out_file, incident_closures=[self.closure])

            self.assertTrue(os.path.exists(out_file))
            data = json.loads(geojson_str)

            self.assertEqual(data["type"], "FeatureCollection")
            self.assertEqual(data["metadata"]["total_routes"], 2)
            self.assertEqual(data["metadata"]["valid_routes"], 1)
            self.assertEqual(len(data["features"]), 2)

            # Check feature properties
            feat0 = data["features"][0]
            self.assertEqual(feat0["properties"]["route_id"], "route_primary")
            self.assertEqual(feat0["properties"]["valid"], True)
            self.assertEqual(feat0["properties"]["distance_m"], 3000.0)
            self.assertEqual(feat0["geometry"]["type"], "LineString")

            feat1 = data["features"][1]
            self.assertEqual(feat1["properties"]["valid"], False)
            self.assertIn("Too Short", feat1["properties"]["rejection_reason"])

    def test_shapefile_export(self):
        """Verifies ESRI Shapefile export zipped archive and 10-char DBF columns."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_zip = os.path.join(tmp_dir, "test_shp.zip")
            res_zip = export_to_shapefile(self.routes, output_path=out_zip, layer_name="detour_routes")

            self.assertTrue(os.path.exists(res_zip))
            self.assertTrue(zipfile.is_zipfile(res_zip))

            # Inspect zip contents
            with zipfile.ZipFile(res_zip, "r") as z:
                names = z.namelist()
                has_shp = any(n.endswith(".shp") for n in names)
                has_shx = any(n.endswith(".shx") for n in names)
                has_dbf = any(n.endswith(".dbf") for n in names)
                has_prj = any(n.endswith(".prj") for n in names)
                self.assertTrue(has_shp, "Missing .shp in bundle")
                self.assertTrue(has_shx, "Missing .shx in bundle")
                self.assertTrue(has_dbf, "Missing .dbf in bundle")
                self.assertTrue(has_prj, "Missing .prj in bundle")

            # Read back using GeoPandas
            gdf = gpd.read_file(f"zip://{res_zip}")
            self.assertEqual(len(gdf), 2)
            # Verify truncated field names
            self.assertIn("tot_time_s", gdf.columns)
            self.assertIn("ff_time_s", gdf.columns)
            self.assertIn("dist_m", gdf.columns)
            self.assertIn("rej_reason", gdf.columns)

    def test_csv_export(self):
        """Verifies tabular CSV summary export."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_csv = os.path.join(tmp_dir, "test.csv")
            csv_str = export_to_csv(self.routes, output_path=out_csv)

            self.assertTrue(os.path.exists(out_csv))
            self.assertIn("Route ID,Origin,Destination", csv_str)
            self.assertIn("route_primary", csv_str)
            self.assertIn("route_secondary", csv_str)
            self.assertIn("Too Short", csv_str)

    def test_export_all_formats(self):
        """Verifies export_all_formats generates all three artifacts in one directory."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = export_all_formats(self.routes, output_dir=tmp_dir, base_name="pilot_run")

            self.assertTrue(os.path.exists(paths["geojson"]))
            self.assertTrue(os.path.exists(paths["shapefile"]))
            self.assertTrue(os.path.exists(paths["csv"]))

    def test_empty_route_export(self):
        """Verifies exporting an empty route list does not crash and produces valid outputs."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            empty_geojson = os.path.join(tmp_dir, "empty.geojson")
            export_to_geojson([], output_path=empty_geojson)
            self.assertTrue(os.path.exists(empty_geojson))

            empty_csv = os.path.join(tmp_dir, "empty.csv")
            export_to_csv([], output_path=empty_csv)
            self.assertTrue(os.path.exists(empty_csv))

            empty_shp = os.path.join(tmp_dir, "empty.zip")
            export_to_shapefile([], output_path=empty_shp)
            self.assertTrue(os.path.exists(empty_shp))


if __name__ == "__main__":
    unittest.main()
