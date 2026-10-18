"""
Unit tests for ARPL Federal Standards Compliance & Playbook Architecture.
Tests FHWA TIM incident severity classification, IEEE 1512 message export,
commercial vehicle freight routing, Playbook persistence, and spatial network tiling.
"""

import json
import pytest
import networkx as nx
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from detour_utils import classify_incident_severity, get_detour
from export_ieee1512 import export_to_ieee1512_json, classify_fhwa_tim_level
from database.models import Base, IncidentPlanSession, IncidentPlanPlaybook
from spatial_network_store import SpatialNetworkStore


def test_fhwa_tim_classification():
    """Verify FHWA / USDOT Traffic Incident Management classification rules."""
    # Level 1 Minor: < 30 mins, 1 lane
    assert classify_fhwa_tim_level(duration_minutes=15, lanes_blocked=1, is_full_closure=False) == "LEVEL_1_MINOR"
    assert classify_incident_severity(duration_minutes=20, lanes_blocked=1, is_full_closure=False) == "LEVEL_1_MINOR"

    # Level 2 Intermediate: 30 to 120 mins or multi-lane
    assert classify_fhwa_tim_level(duration_minutes=45, lanes_blocked=1, is_full_closure=False) == "LEVEL_2_INTERMEDIATE"
    assert classify_fhwa_tim_level(duration_minutes=15, lanes_blocked=2, is_full_closure=False) == "LEVEL_2_INTERMEDIATE"
    assert classify_incident_severity(duration_minutes=90, lanes_blocked=2, is_full_closure=False) == "LEVEL_2_INTERMEDIATE"

    # Level 3 Major: > 120 mins or full corridor closure
    assert classify_fhwa_tim_level(duration_minutes=150, lanes_blocked=1, is_full_closure=False) == "LEVEL_3_MAJOR"
    assert classify_fhwa_tim_level(duration_minutes=20, lanes_blocked=1, is_full_closure=True) == "LEVEL_3_MAJOR"
    assert classify_incident_severity(duration_minutes=200, lanes_blocked=4, is_full_closure=True) == "LEVEL_3_MAJOR"


def test_export_to_ieee1512_json():
    """Verify IEEE 1512 JSON schema generation and compliance."""
    session_id = "test-session-uuid-1234"
    plan_name = "I-95 Northbound Incident Bypass"
    closed_edges = [(10, 20, 0), (20, 30, 0)]
    accepted_detours = {
        "1": {
            "path": [10, 101, 102, 30],
            "distance_m": 4500.0,
            "time_s": 240.0,
            "turn_penalty_s": 15.0
        }
    }
    detour_params = {
        "max_time_s": 3600,
        "penalize_unreferenced": True,
        "vehicle_type": "truck"
    }

    raw_json = export_to_ieee1512_json(
        session_id=session_id,
        plan_name=plan_name,
        incident_edges=closed_edges,
        accepted_detours=accepted_detours,
        detour_params=detour_params,
        jurisdiction="Virginia",
        agency_id="VDOT_TMC_RICHMOND",
        duration_minutes=75,
        lanes_blocked=2,
        is_full_closure=False,
        truck_route_id="1"
    )

    data = json.loads(raw_json)

    # Validate top-level schema blocks
    assert "ieee1512MessageHeader" in data
    assert "incidentContext" in data
    assert "alternateRoutePlan" in data
    assert "trafficManagementGuidance" in data

    # Validate header fields
    header = data["ieee1512MessageHeader"]
    assert header["standardVersion"] == "IEEE-1512-2006"
    assert header["originatingAgency"] == "VDOT_TMC_RICHMOND"
    assert header["messageType"] == "INCIDENT_ALTERNATE_ROUTE_BROADCAST"

    # Validate incident classification
    inc_ctx = data["incidentContext"]
    assert inc_ctx["incidentClassification"]["fhwaTimSeverity"] == "LEVEL_2_INTERMEDIATE"
    assert inc_ctx["totalClosedLinks"] == 2
    assert inc_ctx["closedRoadwayLinks"][0]["linkId"] == "10_20_0"

    # Validate alternate route payload
    alt_routes = data["alternateRoutePlan"]["recommendedRoutes"]
    assert len(alt_routes) == 1
    assert alt_routes[0]["routeType"] == "COMMERCIAL_FREIGHT_SUITABLE"
    assert alt_routes[0]["metrics"]["totalDistanceMeters"] == 4500.0

    # Validate MUTCD DMS signs
    dms_messages = data["trafficManagementGuidance"]["mutcdCompliance"]["dmsActionMessages"]
    assert len(dms_messages) == 2
    assert "FOLLOW DETOUR" in dms_messages[0]["phase2"]


def test_truck_freight_routing_suitability():
    """Verify freight suitability routing penalizes residential streets under 23 CFR Part 658."""
    G = nx.MultiDiGraph()
    # Direct closed link: 1 -> 4
    G.add_edge(1, 4, key=0, total_time=10.0, travel_time=10.0, highway="motorway")

    # Detour Alternative A: Short shortcut through residential street (1 -> 2 -> 4)
    # total_time = 12s, but residential
    G.add_edge(1, 2, key=0, total_time=6.0, travel_time=6.0, highway="residential")
    G.add_edge(2, 4, key=0, total_time=6.0, travel_time=6.0, highway="residential")

    # Detour Alternative B: Longer arterial highway bypass (1 -> 3 -> 4)
    # total_time = 20s, but primary arterial
    G.add_edge(1, 3, key=0, total_time=10.0, travel_time=10.0, highway="primary")
    G.add_edge(3, 4, key=0, total_time=10.0, travel_time=10.0, highway="primary")

    incident_edge = (1, 4, 0)
    start_nodes = [1]
    end_nodes = [4]

    # 1. Standard Passenger Vehicle: selects the fastest path (via residential: 1 -> 2 -> 4)
    detours_passenger = get_detour(G, incident_edge, start_nodes, end_nodes, 0, 100, vehicle_type="passenger")
    assert (1, 4) in detours_passenger
    success_pass, _, _, path_pass = detours_passenger[(1, 4)]
    assert success_pass is True
    assert path_pass == [1, 2, 4]

    # 2. Commercial Truck: penalizes residential streets, selects arterial bypass (1 -> 3 -> 4)
    detours_truck = get_detour(G, incident_edge, start_nodes, end_nodes, 0, 100, vehicle_type="truck")
    assert (1, 4) in detours_truck
    success_truck, _, _, path_truck = detours_truck[(1, 4)]
    assert success_truck is True
    assert path_truck == [1, 3, 4]


def test_playbook_database_models():
    """Verify IncidentPlanPlaybook schema and lifecycle states in SQLite."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    playbook = IncidentPlanPlaybook(
        id="playbook-uuid-9999",
        title="I-64 Eastbound Hampton Roads Bridge-Tunnel Contingency",
        jurisdiction="Virginia",
        facility_name="I-64 Eastbound at HRBT",
        incident_level="LEVEL_3_MAJOR",
        status="DRAFT",
        version=1
    )
    session.add(playbook)
    session.commit()

    retrieved = session.query(IncidentPlanPlaybook).filter_by(id="playbook-uuid-9999").first()
    assert retrieved is not None
    assert retrieved.facility_name == "I-64 Eastbound at HRBT"
    assert retrieved.incident_level == "LEVEL_3_MAJOR"
    assert retrieved.status == "DRAFT"

    d = retrieved.to_dict()
    assert d["id"] == "playbook-uuid-9999"
    assert d["title"] == "I-64 Eastbound Hampton Roads Bridge-Tunnel Contingency"
    session.close()


def test_spatial_network_store():
    """Verify spatial bounding box subgraph extraction."""
    store = SpatialNetworkStore(buffer_meters=1000.0)

    G = nx.MultiDiGraph()
    # Inside bounding box around (37.5, -77.4)
    G.add_node(1, x=-77.42, y=37.52)
    G.add_node(2, x=-77.41, y=37.53)
    G.add_edge(1, 2, key=0, highway="primary")

    # Far away (e.g. 50 miles away)
    G.add_node(3, x=-76.20, y=36.80)
    G.add_node(4, x=-76.21, y=36.81)
    G.add_edge(3, 4, key=0, highway="motorway")

    subgraph = store.extract_subgraph_in_bounds(
        base_graph=G,
        minx=-77.45,
        miny=37.50,
        maxx=-77.40,
        maxy=37.55,
        apply_buffer=False
    )

    assert 1 in subgraph.nodes
    assert 2 in subgraph.nodes
    assert 3 not in subgraph.nodes
    assert 4 not in subgraph.nodes
    assert subgraph.number_of_edges() == 1
