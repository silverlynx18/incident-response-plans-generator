"""
Database models for ARPL (Automated Route Planning & Logistics) - Package P1/P2.
Defines persistent schema for Incident Response Plan sessions, routes, closures, and audit logs.
"""

from datetime import datetime
import json
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Text, DateTime, Integer, ForeignKey, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class IncidentPlanSession(Base):
    """
    Stores a complete ARPL incident response plan session.
    Enables saving, naming, reloading, and sharing incident scenarios.
    """
    __tablename__ = "incident_plan_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    network_source: Mapped[str] = mapped_column(String(100), default="OSM")
    closure_mode: Mapped[str] = mapped_column(String(50), default="single")
    incident_level: Mapped[str] = mapped_column(String(50), default="LEVEL_2_INTERMEDIATE")  # FHWA TIM Level 1/2/3
    
    # Serialized JSON blobs
    closed_edges_json: Mapped[str] = mapped_column(Text, default="[]")
    detour_params_json: Mapped[str] = mapped_column(Text, default="{}")
    accepted_detours_json: Mapped[str] = mapped_column(Text, default="{}")
    additional_data_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    standards_compliance_json: Mapped[str] = mapped_column(Text, default="{}")

    # Relationship to audit entries
    audit_entries: Mapped[List["SessionAuditEntry"]] = relationship(
        "SessionAuditEntry", back_populates="session", cascade="all, delete-orphan", order_by="SessionAuditEntry.timestamp"
    )

    def get_closed_edges(self) -> List[Any]:
        try:
            raw = json.loads(self.closed_edges_json)
            return [tuple(e) if isinstance(e, list) else e for e in raw]
        except Exception:
            return []

    def set_closed_edges(self, edges: List[Any]):
        self.closed_edges_json = json.dumps(edges)

    def get_detour_params(self) -> Dict[str, Any]:
        try:
            return json.loads(self.detour_params_json)
        except Exception:
            return {}

    def set_detour_params(self, params: Dict[str, Any]):
        self.detour_params_json = json.dumps(params)

    def get_accepted_detours(self) -> Dict[str, Any]:
        try:
            return json.loads(self.accepted_detours_json)
        except Exception:
            return {}

    def set_accepted_detours(self, detours: Dict[str, Any]):
        # Convert non-string keys if needed
        clean_detours = {}
        for k, v in detours.items():
            str_key = str(k)
            # Ensure path and metrics are JSON serializable
            clean_detours[str_key] = v
        self.accepted_detours_json = json.dumps(clean_detours)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "network_source": self.network_source,
            "closure_mode": self.closure_mode,
            "incident_level": self.incident_level,
            "closed_edges": self.get_closed_edges(),
            "detour_params": self.get_detour_params(),
            "accepted_detours": self.get_accepted_detours(),
            "total_accepted_routes": len(self.get_accepted_detours())
        }


class SessionAuditEntry(Base):
    """
    Audit log trail for changes, calculations, and exports performed on a session.
    """
    __tablename__ = "session_audit_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("incident_plan_sessions.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    details_json: Mapped[str] = mapped_column(Text, default="{}")

    session: Mapped["IncidentPlanSession"] = relationship("IncidentPlanSession", back_populates="audit_entries")

    def get_details(self) -> Dict[str, Any]:
        try:
            return json.loads(self.details_json)
        except Exception:
            return {}

    def set_details(self, details: Dict[str, Any]):
        self.details_json = json.dumps(details)


class IncidentPlanPlaybook(Base):
    """
    Durable Playbook Repository (Roadmap P1-P3).
    Stores pre-planned contingency playbooks for critical corridors and intermodal facilities,
    governed by lifecycle states (DRAFT, REVIEWED, APPROVED, STALE, RETIRED).
    """
    __tablename__ = "incident_plan_playbooks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    jurisdiction: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    facility_name: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g., "I-95 Northbound at Exit 74"
    incident_level: Mapped[str] = mapped_column(String(50), default="LEVEL_2_INTERMEDIATE")  # FHWA TIM Level
    status: Mapped[str] = mapped_column(String(50), default="DRAFT", index=True)  # DRAFT, REVIEWED, APPROVED, STALE, RETIRED
    
    version: Mapped[int] = mapped_column(Integer, default=1)
    approved_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    approval_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    corridors_json: Mapped[str] = mapped_column(Text, default="[]")
    primary_detour_json: Mapped[str] = mapped_column(Text, default="{}")
    truck_detour_json: Mapped[str] = mapped_column(Text, default="{}")
    advance_signage_json: Mapped[str] = mapped_column(Text, default="[]")  # MUTCD DMS messages
    associated_edges_json: Mapped[str] = mapped_column(Text, default="[]")  # List of [u, v, key] or OSM IDs

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "jurisdiction": self.jurisdiction,
            "facility_name": self.facility_name,
            "incident_level": self.incident_level,
            "status": self.status,
            "version": self.version,
            "approved_by": self.approved_by,
            "approval_date": self.approval_date.isoformat() if self.approval_date else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "associated_edges": json.loads(self.associated_edges_json) if self.associated_edges_json else []
        }


class PlaybookEdgeAssociation(Base):
    """
    Indexes pre-vetted response plans directly to road links (u, v) and OSM way IDs (Roadmap P2).
    Enables immediate resurfacing of vetted detour playbooks when any road link is closed.
    """
    __tablename__ = "playbook_edge_associations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    playbook_id: Mapped[str] = mapped_column(String(36), ForeignKey("incident_plan_playbooks.id", ondelete="CASCADE"), index=True)
    u: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    v: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    edge_key: Mapped[int] = mapped_column(Integer, default=0)
    osm_way_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "playbook_id": self.playbook_id,
            "u": self.u,
            "v": self.v,
            "edge_key": self.edge_key,
            "osm_way_id": self.osm_way_id
        }



class TransitAgency(Base):
    """Stores transit agency metadata for GTFS feeds."""
    __tablename__ = "transit_agencies"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), default="America/New_York")


class TransitRoute(Base):
    """Stores GTFS transit route alignments and service types."""
    __tablename__ = "transit_routes"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    agency_id: Mapped[str] = mapped_column(String(50), ForeignKey("transit_agencies.id", ondelete="CASCADE"), index=True)
    short_name: Mapped[str] = mapped_column(String(50), index=True)
    long_name: Mapped[str] = mapped_column(String(255))
    route_type: Mapped[str] = mapped_column(String(10), default="3")  # 3 = Bus, 1 = Subway/Metro, 2 = Rail


class TransitStop(Base):
    """Stores GTFS bus stops and rail stations with spatial coordinates."""
    __tablename__ = "transit_stops"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    agency_id: Mapped[str] = mapped_column(String(50), ForeignKey("transit_agencies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    lat: Mapped[float] = mapped_column(nullable=False, index=True)
    lon: Mapped[float] = mapped_column(nullable=False, index=True)
    wheelchair_boarding: Mapped[int] = mapped_column(Integer, default=1)


class TransitTrip(Base):
    """Stores scheduled transit trips and headways."""
    __tablename__ = "transit_trips"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    route_id: Mapped[str] = mapped_column(String(100), ForeignKey("transit_routes.id", ondelete="CASCADE"), index=True)
    service_id: Mapped[str] = mapped_column(String(50), index=True)
    headsign: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

