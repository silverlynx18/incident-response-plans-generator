"""
IEEE 1512 Standards-Compliant Incident Management Message Exporter for ARPL.
Conforms to the IEEE 1512 family of standards (Standard for Common Incident Management Message Sets)
for real-time message exchange between Traffic Management Centers (TMC), Public Safety,
and Emergency Management dispatch systems.

This module is strictly ADDITIVE and does not modify or overwrite any existing ARPL deliverables
(PDF, Excel, CSV, GeoJSON, KML/KMZ).
"""

import json
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple


def classify_fhwa_tim_level(duration_minutes: int, lanes_blocked: int = 1, is_full_closure: bool = False) -> str:
    """
    Classifies an incident according to FHWA / USDOT Traffic Incident Management (TIM) hierarchy:
    - Level 1 (Minor): < 30 minutes, shoulder or single-lane blockage.
    - Level 2 (Intermediate): 30 minutes to 2 hours, multi-lane highway impact.
    - Level 3 (Major): > 2 hours or full corridor closure (hazardous materials, structural bridge failure).
    """
    if is_full_closure or duration_minutes > 120:
        return "LEVEL_3_MAJOR"
    elif duration_minutes >= 30 or lanes_blocked >= 2:
        return "LEVEL_2_INTERMEDIATE"
    else:
        return "LEVEL_1_MINOR"


def export_to_ieee1512_json(
    session_id: str,
    plan_name: str,
    incident_edges: List[Any],
    accepted_detours: Dict[str, Any],
    detour_params: Dict[str, Any],
    jurisdiction: str = "Virginia",
    agency_id: str = "VDOT_TMC",
    incident_type: str = "ROAD_CLOSURE_HAZARD",
    duration_minutes: int = 60,
    lanes_blocked: int = 2,
    is_full_closure: bool = False,
    truck_route_id: Optional[str] = None
) -> str:
    """
    Generates an IEEE 1512 XML/JSON compatible Incident Management Message payload.

    Args:
        session_id: Deterministic plan UUID
        plan_name: Human-readable plan name
        incident_edges: Normalized closed edges list
        accepted_detours: Accepted detour alternatives and their turn-by-turn metrics
        detour_params: Search parameters (max time, penalties, vehicle class)
        jurisdiction: Operating jurisdiction / state / MPO
        agency_id: Responsible Traffic Management Center identifier
        incident_type: Incident category
        duration_minutes: Estimated incident duration
        lanes_blocked: Number of lanes obstructed
        is_full_closure: True if both carriageways / full roadway blocked
        truck_route_id: ID of the dedicated commercial vehicle / truck route if present

    Returns:
        JSON-serialized IEEE 1512 message payload.
    """
    tim_level = classify_fhwa_tim_level(duration_minutes, lanes_blocked, is_full_closure)
    now_utc = datetime.now(timezone.utc).isoformat()

    # Format closed road links conforming to IEEE 1512 RoadwayLinkSpecification
    closed_link_elements = []
    for edge in incident_edges:
        if isinstance(edge, (list, tuple)):
            u = edge[0]
            v = edge[1]
            key = edge[2] if len(edge) > 2 else 0
            closed_link_elements.append({
                "linkId": f"{u}_{v}_{key}",
                "upstreamNode": str(u),
                "downstreamNode": str(v),
                "edgeKey": int(key),
                "status": "CLOSED_IMPASSABLE",
                "trafficDirection": "ONE_WAY"
            })

    # Format recommended alternate routes conforming to IEEE 1512 AlternateRouteAdvisory
    route_elements = []
    for route_idx, (r_id, r_data) in enumerate(accepted_detours.items(), 1):
        is_truck = (str(r_id) == str(truck_route_id))
        path_nodes = r_data.get("path", [])
        route_elements.append({
            "routeIdentifier": str(r_id),
            "priorityRank": route_idx,
            "routeType": "COMMERCIAL_FREIGHT_SUITABLE" if is_truck else "GENERAL_VEHICLE_ALTERNATE",
            "metrics": {
                "totalDistanceMeters": round(r_data.get("distance_m", 0.0), 1),
                "totalDistanceMiles": round(r_data.get("distance_m", 0.0) / 1609.34, 2),
                "freeFlowTravelTimeSeconds": round(r_data.get("time_s", 0.0), 1),
                "turnDelaySeconds": round(r_data.get("turn_penalty_s", 0.0), 1),
                "totalEstimatedTravelTimeMinutes": round((r_data.get("time_s", 0.0) + r_data.get("turn_penalty_s", 0.0)) / 60.0, 2)
            },
            "nodeSequence": [str(n) for n in path_nodes],
            "nodeCount": len(path_nodes)
        })

    # Format Dynamic Message Signs (DMS) advance warning messages per MUTCD Chapter 6I
    dms_advisories = [
        {
            "dmsIdentifier": f"DMS-{jurisdiction[:2].upper()}-01",
            "phase1": f"INCIDENT ON CORRIDOR",
            "phase2": f"FOLLOW DETOUR ROUTE 1"
        },
        {
            "dmsIdentifier": f"DMS-{jurisdiction[:2].upper()}-02",
            "phase1": f"{tim_level.replace('_', ' ')}",
            "phase2": f"EXPECT DELAYS"
        }
    ]

    ieee1512_payload = {
        "ieee1512MessageHeader": {
            "messageId": f"MSG-IEEE1512-{session_id[:8]}",
            "standardVersion": "IEEE-1512-2006",
            "originatingAgency": agency_id,
            "jurisdiction": jurisdiction,
            "dateTimeStamp": now_utc,
            "messageType": "INCIDENT_ALTERNATE_ROUTE_BROADCAST",
            "operationalStatus": "ACTIVE_ADVISORY"
        },
        "incidentContext": {
            "planId": session_id,
            "planName": plan_name,
            "incidentClassification": {
                "fhwaTimSeverity": tim_level,
                "durationMinutesEstimate": duration_minutes,
                "lanesObstructed": lanes_blocked,
                "isFullCorridorClosure": is_full_closure,
                "incidentType": incident_type
            },
            "closedRoadwayLinks": closed_link_elements,
            "totalClosedLinks": len(closed_link_elements)
        },
        "alternateRoutePlan": {
            "recommendedRoutes": route_elements,
            "totalAlternativeRoutes": len(route_elements),
            "routingParameters": {
                "maxSearchTimeSeconds": detour_params.get("max_time_s", 7200),
                "unreferencedPenaltyApplied": detour_params.get("penalize_unreferenced", True),
                "vehicleClass": detour_params.get("vehicle_type", "passenger")
            }
        },
        "trafficManagementGuidance": {
            "mutcdCompliance": {
                "standard": "MUTCD Chapter 6I - Emergency Traffic Control",
                "dmsActionMessages": dms_advisories
            },
            "interAgencyCoordination": {
                "notifiedEntities": [
                    "State Highway Patrol",
                    "Department of Transportation TMC",
                    "Municipal Emergency Medical Services",
                    "Regional Transit Authority"
                ]
            }
        }
    }

    return json.dumps(ieee1512_payload, indent=2)
