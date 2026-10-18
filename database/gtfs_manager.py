"""
GTFS Transit Database Manager for ARPL.
Handles persisting, querying, and spatially filtering GTFS transit stops and routes
stored in the local SQLite database.
"""

from typing import List, Dict, Any, Optional
from sqlalchemy import select, and_
from sqlalchemy.orm import Session
from database.models import Base, TransitAgency, TransitRoute, TransitStop, TransitTrip
from database.session_manager import get_engine


def init_gtfs_db():
    """Initializes the database tables for GTFS transit data."""
    engine = get_engine()
    Base.metadata.create_all(engine)


def store_transit_agency(agency_id: str, name: str, url: str = "", timezone: str = "America/New_York"):
    """Stores or updates a transit agency."""
    init_gtfs_db()
    with Session(get_engine()) as session:
        agency = session.get(TransitAgency, agency_id)
        if not agency:
            agency = TransitAgency(id=agency_id, name=name, url=url, timezone=timezone)
            session.add(agency)
        else:
            agency.name = name
            agency.url = url
            agency.timezone = timezone
        session.commit()


def bulk_insert_routes(routes: List[Dict[str, Any]]):
    """Bulk inserts transit routes."""
    init_gtfs_db()
    with Session(get_engine()) as session:
        for r in routes:
            existing = session.get(TransitRoute, r["route_id"])
            if not existing:
                route_obj = TransitRoute(
                    id=r["route_id"],
                    agency_id=r["agency_id"],
                    short_name=r.get("short_name", r["route_id"]),
                    long_name=r.get("long_name", ""),
                    route_type=str(r.get("route_type", "3"))
                )
                session.add(route_obj)
        session.commit()


def bulk_insert_stops(stops: List[Dict[str, Any]]):
    """Bulk inserts transit stops."""
    init_gtfs_db()
    with Session(get_engine()) as session:
        for s in stops:
            existing = session.get(TransitStop, s["stop_id"])
            if not existing:
                stop_obj = TransitStop(
                    id=s["stop_id"],
                    agency_id=s["agency_id"],
                    name=s["name"],
                    lat=float(s["lat"]),
                    lon=float(s["lon"]),
                    wheelchair_boarding=int(s.get("wheelchair_boarding", 1))
                )
                session.add(stop_obj)
        session.commit()


def get_stops_in_bbox(min_lat: float, max_lat: float, min_lon: float, max_lon: float) -> List[Dict[str, Any]]:
    """Retrieves all transit stops within a geographic bounding box."""
    init_gtfs_db()
    with Session(get_engine()) as session:
        stmt = select(TransitStop).where(
            and_(
                TransitStop.lat >= min_lat,
                TransitStop.lat <= max_lat,
                TransitStop.lon >= min_lon,
                TransitStop.lon <= max_lon
            )
        )
        results = session.scalars(stmt).all()
        return [
            {
                "stop_id": s.id,
                "agency_id": s.agency_id,
                "name": s.name,
                "lat": s.lat,
                "lon": s.lon
            }
            for s in results
        ]


def list_agencies() -> List[Dict[str, Any]]:
    """Lists all stored transit agencies."""
    init_gtfs_db()
    with Session(get_engine()) as session:
        stmt = select(TransitAgency)
        results = session.scalars(stmt).all()
        return [{"id": a.id, "name": a.name, "url": a.url} for a in results]
