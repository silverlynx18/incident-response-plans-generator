"""
Session Manager for ARPL (Package P1/P2).
Provides high-level APIs for persisting, querying, updating, and exporting incident plan sessions.
"""

import os
import uuid
import json
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import create_engine, select, desc
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool

from database.models import Base, IncidentPlanSession, SessionAuditEntry

DEFAULT_DB_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "arpl_sessions.db")


def get_engine(db_path: Optional[str] = None):
    """Creates a SQLite SQLAlchemy engine, ensuring parent directory exists."""
    target_path = db_path or DEFAULT_DB_FILE
    target_dir = os.path.dirname(target_path)
    if target_dir and not os.path.exists(target_dir):
        os.makedirs(target_dir, exist_ok=True)
    return create_engine(f"sqlite:///{target_path}", echo=False, poolclass=NullPool)


def init_db(db_path: Optional[str] = None):
    """Initializes the database schema if not present."""
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
    return engine


def get_db_session(db_path: Optional[str] = None) -> Session:
    """Returns a new database session."""
    engine = init_db(db_path)
    SessionMaker = sessionmaker(bind=engine)
    return SessionMaker()


def save_session(
    name: str,
    description: Optional[str] = None,
    network_source: str = "OSM",
    closure_mode: str = "single",
    closed_edges: Optional[List[Any]] = None,
    detour_params: Optional[Dict[str, Any]] = None,
    accepted_detours: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    db_path: Optional[str] = None
) -> IncidentPlanSession:
    """
    Saves or updates an incident plan session.
    If session_id is None, creates a new session.
    """
    with get_db_session(db_path) as db:
        if session_id:
            plan = db.get(IncidentPlanSession, session_id)
            if not plan:
                raise ValueError(f"Session with ID '{session_id}' not found.")
            action = "UPDATED"
        else:
            session_id = str(uuid.uuid4())
            plan = IncidentPlanSession(id=session_id)
            db.add(plan)
            action = "CREATED"

        plan.name = name
        plan.description = description
        plan.network_source = network_source
        plan.closure_mode = closure_mode
        plan.set_closed_edges(closed_edges or [])
        plan.set_detour_params(detour_params or {})
        plan.set_accepted_detours(accepted_detours or {})
        plan.updated_at = datetime.now()

        # Audit entry
        audit = SessionAuditEntry(
            session_id=session_id,
            action=action,
            timestamp=datetime.now()
        )
        audit.set_details({
            "name": name,
            "closed_edges_count": len(closed_edges or []),
            "accepted_routes_count": len(accepted_detours or [])
        })
        db.add(audit)

        db.commit()
        db.refresh(plan)
        return plan


def get_session(session_id: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Loads a session by ID and returns its dictionary representation."""
    with get_db_session(db_path) as db:
        plan = db.get(IncidentPlanSession, session_id)
        if not plan:
            return None
        return plan.to_dict()


def list_sessions(limit: int = 50, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lists existing sessions ordered by most recently updated."""
    with get_db_session(db_path) as db:
        stmt = select(IncidentPlanSession).order_by(desc(IncidentPlanSession.updated_at)).limit(limit)
        results = db.scalars(stmt).all()
        return [p.to_dict() for p in results]


def delete_session(session_id: str, db_path: Optional[str] = None) -> bool:
    """Deletes a session and its associated audit logs."""
    with get_db_session(db_path) as db:
        plan = db.get(IncidentPlanSession, session_id)
        if not plan:
            return False
        db.delete(plan)
        db.commit()
        return True


def export_session_json(session_id: str, db_path: Optional[str] = None) -> str:
    """Exports a session to a formatted JSON string."""
    session_dict = get_session(session_id, db_path)
    if not session_dict:
        raise ValueError(f"Session {session_id} not found.")
    return json.dumps(session_dict, indent=2)


def import_session_json(json_str: str, override_name: Optional[str] = None, db_path: Optional[str] = None) -> Dict[str, Any]:
    """Imports a session from JSON, assigning a new UUID and saving it."""
    data = json.loads(json_str)
    name = override_name or f"{data.get('name', 'Imported Session')} (Imported)"
    saved = save_session(
        name=name,
        description=data.get('description'),
        network_source=data.get('network_source', 'OSM'),
        closure_mode=data.get('closure_mode', 'single'),
        closed_edges=data.get('closed_edges', []),
        detour_params=data.get('detour_params', {}),
        accepted_detours=data.get('accepted_detours', {}),
        db_path=db_path
    )
    return saved.to_dict()
