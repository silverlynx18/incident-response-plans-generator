"""
Unit test suite for ARPL Full-Fat Roadmap Features:
- Mandatory 23 CFR Part 658 Heavy Semi-Truck Compliance by Default
- Link-Keyed Vetted Detour Plan Association and Resurfacing
- Traffic Signal Coordination Client Input Placeholder
- Package D3 GTFS Multimodal Routing & Modal Shift
- Nationwide Transit Feed Registry
"""

import os
import pytest
import networkx as nx
from pathlib import Path

from detour_utils import get_detour, generate_signal_timing_advisories
from database.playbook_manager import PlaybookManager
from gtfs_validator import GTFSTransitValidator
from data_collection.collect_gtfs_feeds import FEEDS


def test_default_mandatory_truck_freight_routing():
    """Verify that get_detour() enforces heavy semi-truck compliance by default."""
    G = nx.MultiDiGraph()
    # Incident link
    G.add_edge(1, 4, key=0, total_time=10.0, travel_time=10.0, highway="motorway")

    # Shortcut A: Residential street (fast for cars: 12s, but forbidden for 53-ft trucks)
    G.add_edge(1, 2, key=0, total_time=6.0, travel_time=6.0, highway="residential")
    G.add_edge(2, 4, key=0, total_time=6.0, travel_time=6.0, highway="residential")

    # Bypass B: Primary arterial corridor (20s, designated STAA truck route)
    G.add_edge(1, 3, key=0, total_time=10.0, travel_time=10.0, highway="primary")
    G.add_edge(3, 4, key=0, total_time=10.0, travel_time=10.0, highway="primary")

    incident_edge = (1, 4, 0)
    start_nodes = [1]
    end_nodes = [4]

    # Calling get_detour without vehicle_type must default to truck compliance
    detours_default = get_detour(G, incident_edge, start_nodes, end_nodes, 0, 1000)
    assert (1, 4) in detours_default
    success, _, _, path = detours_default[(1, 4)]
    assert success is True
    # Must choose the arterial bypass [1, 3, 4], NOT residential [1, 2, 4]
    assert path == [1, 3, 4]


def test_link_keyed_playbook_association_and_resurfacing(tmp_path):
    """Verify that playbooks indexed by specific road links are instantly resurfaced on link closure."""
    db_file = tmp_path / "test_playbooks.db"
    pm = PlaybookManager(str(db_file))

    # 1. Create Playbook with linked edges
    pb = pm.create_playbook(
        title="I-95 Southbound Detour Playbook",
        jurisdiction="Virginia",
        facility_name="I-95 Exit 74 Bypass",
        incident_level="LEVEL_3_MAJOR",
        primary_detour={"route_name": "Arterial US-1 Bypass", "travel_time_s": 1200},
        associated_edges=[(101, 102, 0), (102, 103, 0)],
        osm_way_ids=["way_45678"]
    )
    pm.update_playbook_status(pb.id, "APPROVED", approved_by="VDOT Regional Traffic Engineer")

    # 2. Query by specific edge (forward and reverse)
    plans_fwd = pm.get_vetted_plans_for_edge(101, 102)
    assert len(plans_fwd) == 1
    assert plans_fwd[0]["facility_name"] == "I-95 Exit 74 Bypass"

    plans_rev = pm.get_vetted_plans_for_edge(102, 101)
    assert len(plans_rev) == 1

    # 3. Query by OSM way ID
    plans_osm = pm.get_vetted_plans_for_edge(None, None, osm_way_id="way_45678")
    assert len(plans_osm) == 1

    # 4. Resurface vetted plans when incident closes edge (101, 102)
    resurfaced = pm.resurface_vetted_plans_for_closure([(101, 102, 0)])
    assert len(resurfaced) == 1
    assert resurfaced[0]["id"] == pb.id
    assert resurfaced[0]["triggered_by_links"] == [["101", "102"]]


def test_signal_timing_client_input_placeholder():
    """Verify that signal timing advisories function as an awaiting client input placeholder."""
    G = nx.MultiDiGraph()
    G.add_node(10, highway="traffic_signals", x=-77.436, y=37.540)
    G.add_node(11, x=-77.430, y=37.542)
    G.add_node(12, highway="traffic_signals", x=-77.425, y=37.545)
    G.add_edge(10, 11, total_time=5.0)
    G.add_edge(11, 12, total_time=5.0)

    advisories = generate_signal_timing_advisories([10, 11, 12], G)
    assert len(advisories) == 1  # Node 10 is an approach signal
    adv = advisories[0]
    assert adv["status"] == "AWAITING_CLIENT_CONTROLLER_PLAN"
    assert adv["client_input_required"] is True
    assert "NEMA TS2/ATC" in adv["placeholder_note"]


def test_multimodal_gtfs_routing_modal_shift():
    """Verify Package D3 multimodal driver-to-transit diversion routing."""
    import pandas as pd
    validator = GTFSTransitValidator()

    # Provide synthetic transit network with a Park-and-Ride hub
    validator.routes_df = pd.DataFrame([{
        "route_id": "EXP_95",
        "route_short_name": "95X",
        "route_long_name": "I-95 Express Transit Pulse",
        "route_type": "3"
    }])
    validator.stops_df = pd.DataFrame([
        {"stop_id": "STOP_PR1", "stop_name": "Parham Road Park-and-Ride Hub", "stop_lat": 37.600, "stop_lon": -77.500},
        {"stop_id": "STOP_CITY", "stop_name": "Downtown Transit Center", "stop_lat": 37.540, "stop_lon": -77.430}
    ])
    validator._build_spatial_index()

    G = nx.MultiDiGraph()
    G.add_node(1, x=-77.505, y=37.602)
    G.add_node(2, x=-77.435, y=37.542)

    res = validator.find_multimodal_transit_alternative(
        incident_edges=[(1, 2, 0)],
        G=G,
        start_node=1,
        highway_detour_time_minutes=55.0
    )

    assert res["multimodal_available"] is True
    assert res["status"] == "AVAILABLE"
    assert "Park-and-Ride" in res["upstream_hub"]["name"]
    assert res["transit_service"]["route_short_name"] == "95X"
    assert res["trip_itinerary"]["net_time_savings_minutes"] > 0
    assert "DMS" in res["dms_bulletin"] or "PARK-AND-RIDE" in res["dms_bulletin"]


def test_nationwide_gtfs_registry():
    """Verify that nationwide GTFS feed registry covers major US regions."""
    assert "MTA_NY" in FEEDS
    assert "CTA_IL" in FEEDS
    assert "MBTA_MA" in FEEDS
    assert "MARTA_GA" in FEEDS
    assert "METRO_LA" in FEEDS
    assert "BART_SF" in FEEDS
    assert "RTD_CO" in FEEDS
    assert "DART_TX" in FEEDS
    assert "KCM_WA" in FEEDS
    assert len(FEEDS) >= 12
