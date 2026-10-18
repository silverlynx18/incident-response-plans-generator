"""
Unit tests for Package D1 & D2: GTFS Transit Validation & Impact Assessment.
"""

import io
import zipfile
import json
import pytest
import pandas as pd
from shapely.geometry import Point, LineString, Polygon
from gtfs_validator import GTFSTransitValidator


@pytest.fixture
def sample_gtfs_dfs():
    # Routes
    routes_data = {
        "route_id": ["R10", "R20", "R30"],
        "route_short_name": ["10", "20", "30"],
        "route_long_name": ["Downtown Express", "Crosstown Local", "Suburban Feeder"],
        "route_type": ["3", "3", "3"]
    }
    routes_df = pd.DataFrame(routes_data)

    # Stops: Downtown Richmond coordinates approx (lat 37.54, lon -77.44)
    stops_data = {
        "stop_id": ["S1", "S2", "S3", "S4", "S5"],
        "stop_name": ["Main & 1st", "Main & 5th", "Main & 9th", "Broad & 5th", "Broad & 12th"],
        "stop_lat": [37.540, 37.542, 37.545, 37.550, 37.552],
        "stop_lon": [-77.450, -77.445, -77.440, -77.445, -77.435]
    }
    stops_df = pd.DataFrame(stops_data)

    # Trips
    trips_data = {
        "trip_id": ["T10_1", "T10_2", "T20_1", "T30_1"],
        "route_id": ["R10", "R10", "R20", "R30"],
        "service_id": ["WEEKDAY", "WEEKDAY", "WEEKDAY", "WEEKDAY"]
    }
    trips_df = pd.DataFrame(trips_data)

    # Stop Times
    stop_times_data = {
        "trip_id": ["T10_1", "T10_1", "T10_1", "T20_1", "T20_1", "T30_1"],
        "stop_id": ["S1", "S2", "S3", "S2", "S4", "S5"],
        "stop_sequence": [1, 2, 3, 1, 2, 1],
        "arrival_time": ["08:00:00", "08:10:00", "08:20:00", "08:05:00", "08:15:00", "08:30:00"],
        "departure_time": ["08:00:30", "08:10:30", "08:20:30", "08:05:30", "08:15:30", "08:30:30"]
    }
    stop_times_df = pd.DataFrame(stop_times_data)

    return {
        "routes": routes_df,
        "stops": stops_df,
        "trips": trips_df,
        "stop_times": stop_times_df
    }


def test_gtfs_validator_load_from_dict(sample_gtfs_dfs):
    validator = GTFSTransitValidator(sample_gtfs_dfs)
    assert validator.stops_gdf is not None
    assert len(validator.stops_gdf) == 5
    assert len(validator.routes_df) == 3


def test_gtfs_validator_load_from_zip(sample_gtfs_dfs):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, df in sample_gtfs_dfs.items():
            csv_bytes = df.to_csv(index=False).encode("utf-8")
            z.writestr(f"{name}.txt", csv_bytes)

    buf.seek(0)
    validator = GTFSTransitValidator(buf.getvalue())
    assert validator.stops_gdf is not None
    assert len(validator.stops_gdf) == 5
    assert len(validator.routes_df) == 3


def test_evaluate_transit_impact_incident_line(sample_gtfs_dfs):
    validator = GTFSTransitValidator(sample_gtfs_dfs)

    # Incident edge along Main Street passing through stop S2 (lat 37.542, lon -77.445)
    incident_line = LineString([(-77.446, 37.542), (-77.444, 37.542)])

    impact = validator.evaluate_transit_impact(
        incident_geometry=incident_line,
        incident_duration_minutes=45,
        buffer_meters=150.0
    )

    assert impact["status"] == "ANALYZED"
    assert impact["affected_stops_count"] >= 1
    # Stop S2 is at (-77.445, 37.542), right on the line
    closed_stop_ids = [s["stop_id"] for s in impact["closed_stops"]]
    assert "S2" in closed_stop_ids

    # Stop S2 is served by R10 and R20
    affected_routes = [r["route_id"] for r in impact["routes"]]
    assert "R10" in affected_routes
    assert "R20" in affected_routes
    assert "R30" not in affected_routes

    # Check GTFS-RT alerts
    alerts = impact["service_alerts"]
    assert len(alerts) == 2
    assert alerts[0]["alert"]["cause"] == "ACCIDENT"
    assert alerts[0]["alert"]["effect"] == "DETOUR"

    # Check rider bulletin text
    bulletin = validator.generate_rider_bulletin_text(impact)
    assert "TRANSIT RIDER SERVICE ADVISORY" in bulletin
    assert "Route 10" in bulletin
    assert "Main & 5th" in bulletin


def test_evaluate_transit_impact_polygon_closure(sample_gtfs_dfs):
    validator = GTFSTransitValidator(sample_gtfs_dfs)

    # Polygon enclosing S2 (Main & 5th) and S4 (Broad & 5th)
    closure_poly = Polygon([
        (-77.448, 37.541),
        (-77.442, 37.541),
        (-77.442, 37.551),
        (-77.448, 37.551),
        (-77.448, 37.541)
    ])

    impact = validator.evaluate_transit_impact(
        incident_geometry=closure_poly,
        incident_duration_minutes=90
    )

    assert impact["status"] == "ANALYZED"
    closed_stop_ids = [s["stop_id"] for s in impact["closed_stops"]]
    assert "S2" in closed_stop_ids
    assert "S4" in closed_stop_ids
    assert "S5" not in closed_stop_ids


def test_gtfs_validator_auto_discovery():
    # When initialized with None, should discover feeds in data/gtfs/
    validator = GTFSTransitValidator()
    if validator.stops_gdf is not None:
        assert len(validator.stops_gdf) > 0
        assert len(validator.routes_df) > 0


def test_gtfs_database_manager():
    from database.gtfs_manager import (
        init_gtfs_db,
        store_transit_agency,
        bulk_insert_routes,
        bulk_insert_stops,
        get_stops_in_bbox,
        list_agencies
    )
    init_gtfs_db()
    store_transit_agency("TEST_AGENCY", "Test Transit Authority", "https://test.transit.gov")
    
    agencies = list_agencies()
    assert any(a["id"] == "TEST_AGENCY" for a in agencies)

    bulk_insert_routes([{
        "route_id": "TEST_R1",
        "agency_id": "TEST_AGENCY",
        "short_name": "T1",
        "long_name": "Test Route 1",
        "route_type": "3"
    }])

    bulk_insert_stops([{
        "stop_id": "TEST_S1",
        "agency_id": "TEST_AGENCY",
        "name": "Test Central Station",
        "lat": 37.540,
        "lon": -77.440,
        "wheelchair_boarding": 1
    }])

    # Query bounding box
    bbox_stops = get_stops_in_bbox(37.50, 37.60, -77.50, -77.40)
    assert any(s["stop_id"] == "TEST_S1" for s in bbox_stops)

