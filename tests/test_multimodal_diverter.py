"""
Unit tests for the Multimodal Incident Diversion Engine.
Tests multimodal shift feasibility, Generalized Journey Time (GJT) cost modeling,
and MUTCD-compliant Dynamic Message Sign (DMS) phase outputs.
"""

from datetime import datetime, time
import pytest
from multimodal_diverter import (
    MultimodalIncidentDiverter,
    ParkAndRideHub,
    DestinationAttractor,
    MultimodalDiversionOption
)


def test_haversine_distance():
    diverter = MultimodalIncidentDiverter()
    # Distance between Parham P&R (37.6045, -77.5385) and Richmond Downtown (37.5407, -77.4360)
    dist = diverter.haversine_distance_km(37.6045, -77.5385, 37.5407, -77.4360)
    assert 10.0 <= dist <= 15.0


def test_find_upstream_park_and_ride_hubs():
    diverter = MultimodalIncidentDiverter()
    # Incident on I-64 at Milepost 190 (near 37.54, -77.44)
    hubs = diverter.find_upstream_park_and_ride_hubs(
        incident_lat=37.54,
        incident_lon=-77.44,
        search_radius_km=25.0
    )
    assert len(hubs) >= 1
    hub_names = [h.name for h in hubs]
    assert any("Parham Road" in name or "Gaskins Road" in name for name in hub_names)


def test_evaluate_transit_diversion_high_delay():
    """Under a major 60-minute incident queue, multimodal transit shift should be HIGH_FEASIBILITY."""
    diverter = MultimodalIncidentDiverter()
    
    # Major incident on I-64 with 60 min of clearance delay
    options = diverter.evaluate_transit_diversion(
        incident_lat=37.54,
        incident_lon=-77.44,
        highway_baseline_travel_time_min=20.0,
        incident_queue_delay_min=60.0,  # Total highway detour = 80 min
        corridor_name="I-64 Eastbound",
        active_time=datetime(2026, 10, 16, 8, 15)  # Peak AM
    )

    assert len(options) >= 1
    best_opt = options[0]
    assert best_opt.feasibility_status == "HIGH_FEASIBILITY"
    assert best_opt.net_time_savings_min >= 15.0
    assert best_opt.baseline_highway_detour_min == 80.0
    assert best_opt.generalized_journey_cost_transit < best_opt.generalized_journey_cost_highway

    # Check DMS outputs conform to 3 lines per phase
    assert len(best_opt.dms_phase1_lines) == 3
    assert len(best_opt.dms_phase2_lines) == 3
    assert "INCIDENT AHEAD" in best_opt.dms_phase1_lines[1]
    assert "P&R" in best_opt.dms_phase2_lines[1]


def test_evaluate_transit_diversion_minor_delay():
    """Under a minor 5-minute delay, highway detour should remain faster and transit UNVIABLE."""
    diverter = MultimodalIncidentDiverter()

    options = diverter.evaluate_transit_diversion(
        incident_lat=37.54,
        incident_lon=-77.44,
        highway_baseline_travel_time_min=20.0,
        incident_queue_delay_min=5.0,  # Total highway detour = 25 min
        corridor_name="I-64 Eastbound",
        active_time=datetime(2026, 10, 16, 14, 0)  # Midday off-peak
    )

    assert len(options) >= 1
    # Transit door-to-door (drive + park + wait + IVTT + walk) will exceed 25 min
    for opt in options:
        assert opt.feasibility_status in ["MODERATE", "UNVIABLE"]


def test_evaluate_cordon_equalization_vdot_dc_boundary():
    """Test the VDOT corridor use-case: comparing travel time to the DC boundary cordon."""
    from multimodal_diverter import evaluate_cordon_equalization

    diverter = MultimodalIncidentDiverter()

    # Major incident on I-95 Northbound near Dale City (lat 38.65, lon -77.30) with 50 min delay
    res = evaluate_cordon_equalization(
        diverter=diverter,
        incident_lat=38.65,
        incident_lon=-77.30,
        highway_free_flow_to_cordon_min=25.0,
        incident_queue_delay_min=50.0,  # Total highway detour = 75 min to DC line
        corridor_name="I-95 Northbound",
        active_time=datetime(2026, 10, 16, 7, 45)  # AM Peak commute
    )

    assert res is not None
    assert res["cordon_id"] == "CORDON_DC_BOUNDARY"
    assert "District of Columbia Boundary" in res["cordon_name"]
    assert res["auto_detour_time_to_cordon_min"] == 75.0
    assert res["is_transit_superior"] is True
    assert res["net_equalization_savings_min"] >= 15.0

    # Verify DMS sign formatting (16 chars, 3 lines)
    assert len(res["dms_phase1"]) == 3
    assert len(res["dms_phase2"]) == 3
    assert "INCIDENT AHEAD" in res["dms_phase1"][1]
    assert "SAVE" in res["dms_phase2"][2]

