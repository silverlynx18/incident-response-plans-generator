"""
Playbook Manager for ARPL (Automated Route Planning & Logistics) - Package P2/P3.
Provides high-level lifecycle and repository management for pre-planned detour playbooks
and critical corridor contingency plans.
"""

import uuid
import json
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from sqlalchemy import create_engine, select, update, delete
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from .models import Base, IncidentPlanPlaybook, PlaybookEdgeAssociation

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = "session_data/arpl_playbooks.db"


class PlaybookManager:
    """
    CRUD and governance manager for pre-planned Incident Response Playbooks.
    Supports lifecycle states: DRAFT -> REVIEWED -> APPROVED -> STALE -> RETIRED.
    Enforces link-keyed association so pre-vetted plans can be instantly resurfaced
    whenever a specific road link (u, v) is closed.
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        # Ensure parent directory exists
        import os
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            echo=False,
            poolclass=NullPool
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def create_playbook(
        self,
        title: str,
        jurisdiction: str,
        facility_name: str,
        incident_level: str = "LEVEL_2_INTERMEDIATE",
        corridors: Optional[List[Dict[str, Any]]] = None,
        primary_detour: Optional[Dict[str, Any]] = None,
        truck_detour: Optional[Dict[str, Any]] = None,
        advance_signage: Optional[List[Dict[str, Any]]] = None,
        standards_compliance: Optional[Dict[str, Any]] = None,
        associated_edges: Optional[List[Any]] = None,
        osm_way_ids: Optional[List[str]] = None
    ) -> IncidentPlanPlaybook:
        """Creates and persists a new draft contingency playbook with edge-level indexing."""
        playbook_id = str(uuid.uuid4())
        norm_edges = []
        if associated_edges:
            for e in associated_edges:
                if isinstance(e, (list, tuple)) and len(e) >= 2:
                    norm_edges.append([str(e[0]), str(e[1]), int(e[2]) if len(e) >= 3 else 0])

        playbook = IncidentPlanPlaybook(
            id=playbook_id,
            title=title,
            jurisdiction=jurisdiction,
            facility_name=facility_name,
            incident_level=incident_level,
            status="DRAFT",
            version=1,
            corridors_json=json.dumps(corridors or []),
            primary_detour_json=json.dumps(primary_detour or {}),
            truck_detour_json=json.dumps(truck_detour or {}),
            advance_signage_json=json.dumps(advance_signage or []),
            associated_edges_json=json.dumps(norm_edges)
        )

        with self.SessionLocal() as session:
            session.add(playbook)
            # Create link-level index associations
            for e in norm_edges:
                assoc = PlaybookEdgeAssociation(
                    playbook_id=playbook_id,
                    u=str(e[0]),
                    v=str(e[1]),
                    edge_key=int(e[2]),
                    osm_way_id=None
                )
                session.add(assoc)

            if osm_way_ids:
                for w_id in osm_way_ids:
                    assoc = PlaybookEdgeAssociation(
                        playbook_id=playbook_id,
                        u="OSM",
                        v="WAY",
                        edge_key=0,
                        osm_way_id=str(w_id)
                    )
                    session.add(assoc)

            session.commit()
            session.refresh(playbook)
            logger.info(f"Created Playbook '{title}' (ID: {playbook_id}) with {len(norm_edges)} indexed road edges")
            return playbook

    def get_playbook(self, playbook_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a playbook by UUID."""
        with self.SessionLocal() as session:
            stmt = select(IncidentPlanPlaybook).where(IncidentPlanPlaybook.id == playbook_id)
            playbook = session.scalar(stmt)
            if not playbook:
                return None

            return {
                **playbook.to_dict(),
                "corridors": json.loads(playbook.corridors_json),
                "primary_detour": json.loads(playbook.primary_detour_json),
                "truck_detour": json.loads(playbook.truck_detour_json),
                "advance_signage": json.loads(playbook.advance_signage_json),
                "standards_compliance": json.loads(playbook.standards_compliance_json)
            }

    def list_playbooks(
        self,
        jurisdiction: Optional[str] = None,
        status: Optional[str] = None,
        incident_level: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Lists playbooks with optional filters."""
        with self.SessionLocal() as session:
            stmt = select(IncidentPlanPlaybook).order_by(IncidentPlanPlaybook.updated_at.desc())
            if jurisdiction:
                stmt = stmt.where(IncidentPlanPlaybook.jurisdiction == jurisdiction)
            if status:
                stmt = stmt.where(IncidentPlanPlaybook.status == status)
            if incident_level:
                stmt = stmt.where(IncidentPlanPlaybook.incident_level == incident_level)

            results = session.scalars(stmt).all()
            return [p.to_dict() for p in results]

    def update_playbook_status(
        self,
        playbook_id: str,
        new_status: str,
        approved_by: Optional[str] = None
    ) -> bool:
        """Transitions playbook lifecycle (DRAFT -> REVIEWED -> APPROVED -> STALE -> RETIRED)."""
        valid_statuses = {"DRAFT", "REVIEWED", "APPROVED", "STALE", "RETIRED"}
        if new_status not in valid_statuses:
            raise ValueError(f"Invalid status '{new_status}'. Must be one of {valid_statuses}")

        with self.SessionLocal() as session:
            stmt = select(IncidentPlanPlaybook).where(IncidentPlanPlaybook.id == playbook_id)
            playbook = session.scalar(stmt)
            if not playbook:
                return False

            playbook.status = new_status
            if new_status == "APPROVED":
                playbook.approved_by = approved_by or "Authorized Traffic Management Supervisor"
                playbook.approval_date = datetime.now(timezone.utc)
            elif new_status in ("STALE", "RETIRED"):
                playbook.approved_by = None
                playbook.approval_date = None

            session.commit()
            logger.info(f"Updated Playbook {playbook_id} status to '{new_status}'")
            return True

    def delete_playbook(self, playbook_id: str) -> bool:
        """Deletes a playbook."""
        with self.SessionLocal() as session:
            stmt = delete(IncidentPlanPlaybook).where(IncidentPlanPlaybook.id == playbook_id)
            result = session.execute(stmt)
            session.commit()
            return result.rowcount > 0

    def associate_edges_with_playbook(
        self,
        playbook_id: str,
        edges: List[Any],
        osm_way_ids: Optional[List[str]] = None
    ) -> int:
        """Associates specific road links (u, v) and OSM way IDs with an existing playbook."""
        with self.SessionLocal() as session:
            pb = session.scalar(select(IncidentPlanPlaybook).where(IncidentPlanPlaybook.id == playbook_id))
            if not pb:
                return 0

            existing_edges = json.loads(pb.associated_edges_json) if pb.associated_edges_json else []
            added_count = 0

            for e in edges:
                if isinstance(e, (list, tuple)) and len(e) >= 2:
                    u_str, v_str = str(e[0]), str(e[1])
                    k_val = int(e[2]) if len(e) >= 3 else 0
                    assoc = PlaybookEdgeAssociation(
                        playbook_id=playbook_id,
                        u=u_str,
                        v=v_str,
                        edge_key=k_val,
                        osm_way_id=None
                    )
                    session.add(assoc)
                    existing_edges.append([u_str, v_str, k_val])
                    added_count += 1

            if osm_way_ids:
                for w_id in osm_way_ids:
                    assoc = PlaybookEdgeAssociation(
                        playbook_id=playbook_id,
                        u="OSM",
                        v="WAY",
                        edge_key=0,
                        osm_way_id=str(w_id)
                    )
                    session.add(assoc)
                    added_count += 1

            pb.associated_edges_json = json.dumps(existing_edges)
            session.commit()
            return added_count

    def get_vetted_plans_for_edge(
        self,
        u: Any,
        v: Any,
        osm_way_id: Optional[str] = None,
        only_approved: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Finds vetted pre-approved response plans covering road edge (u, v) or (v, u) or osm_way_id.
        """
        u_str, v_str = str(u) if u is not None else "", str(v) if v is not None else ""
        with self.SessionLocal() as session:
            associations = []
            if u_str and v_str:
                stmt = select(PlaybookEdgeAssociation).where(
                    ((PlaybookEdgeAssociation.u == u_str) & (PlaybookEdgeAssociation.v == v_str)) |
                    ((PlaybookEdgeAssociation.u == v_str) & (PlaybookEdgeAssociation.v == u_str))
                )
                associations.extend(session.scalars(stmt).all())

            if osm_way_id:
                stmt_osm = select(PlaybookEdgeAssociation).where(
                    PlaybookEdgeAssociation.osm_way_id == str(osm_way_id)
                )
                associations.extend(session.scalars(stmt_osm).all())

            if not associations:
                return []

            playbook_ids = list({a.playbook_id for a in associations})
            pb_stmt = select(IncidentPlanPlaybook).where(IncidentPlanPlaybook.id.in_(playbook_ids))
            if only_approved:
                pb_stmt = pb_stmt.where(IncidentPlanPlaybook.status.in_(["APPROVED", "REVIEWED"]))

            playbooks = session.scalars(pb_stmt).all()
            results = []
            for pb in playbooks:
                results.append({
                    **pb.to_dict(),
                    "primary_detour": json.loads(pb.primary_detour_json),
                    "truck_detour": json.loads(pb.truck_detour_json),
                    "matched_link": (u_str, v_str)
                })
            return results

    def resurface_vetted_plans_for_closure(
        self,
        incident_edges: List[Any],
        osm_way_ids: Optional[List[str]] = None,
        only_approved: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Checks all closed incident links against the playbook database and resurfaces all pre-vetted response plans.
        """
        resurfaced = {}
        for e in incident_edges:
            if isinstance(e, (list, tuple)) and len(e) >= 2:
                u, v = e[0], e[1]
                plans = self.get_vetted_plans_for_edge(u, v, only_approved=only_approved)
                for p in plans:
                    p_id = p["id"]
                    if p_id not in resurfaced:
                        resurfaced[p_id] = p
                        resurfaced[p_id]["triggered_by_links"] = [[str(u), str(v)]]
                    else:
                        resurfaced[p_id]["triggered_by_links"].append([str(u), str(v)])

        if osm_way_ids:
            for w_id in osm_way_ids:
                plans = self.get_vetted_plans_for_edge(None, None, osm_way_id=w_id, only_approved=only_approved)
                for p in plans:
                    p_id = p["id"]
                    if p_id not in resurfaced:
                        resurfaced[p_id] = p
                        resurfaced[p_id]["triggered_by_links"] = [f"OSM_WAY:{w_id}"]

        return list(resurfaced.values())

