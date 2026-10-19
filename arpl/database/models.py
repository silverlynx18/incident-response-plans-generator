"""
Database models for ARPL V2.
Defines SQLAlchemy models for sessions, routes, cached networks, user preferences, and analysis history.
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, Float, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .schema import Base

class Session(Base):
    """Stores saved analysis sessions."""
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    state_data = Column(JSON)  # Serialized session state

    # Relationships
    routes = relationship("Route", back_populates="session", cascade="all, delete-orphan")

class Route(Base):
    """Stores individual route analysis results."""
    __tablename__ = "routes"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    route_key = Column(String(255), nullable=False, index=True)
    is_valid = Column(Boolean, default=False)
    travel_time = Column(Float)
    path = Column(JSON)  # Route path data
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    session = relationship("Session", back_populates="routes")

class CachedNetwork(Base):
    """Stores cached network graphs for performance."""
    __tablename__ = "cached_networks"

    id = Column(Integer, primary_key=True, index=True)
    jurisdiction = Column(String(255), nullable=False, index=True)
    cache_key = Column(String(255), nullable=False, unique=True, index=True)
    graph_data = Column(Text)  # Serialized graph data (GraphML)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    size_bytes = Column(Integer, default=0)

    def is_expired(self):
        """Check if cache entry is expired."""
        from datetime import datetime
        return datetime.utcnow() > self.expires_at

class UserPreference(Base):
    """Stores user preferences and settings."""
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(255), nullable=False, unique=True, index=True)
    value = Column(Text)  # JSON serialized value
    pref_type = Column(String(50), default='string')  # Type of preference
    description = Column(Text)  # Description of preference
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class AnalysisHistory(Base):
    """Tracks analysis history and statistics."""
    __tablename__ = "analysis_history"

    id = Column(Integer, primary_key=True, index=True)
    jurisdiction = Column(String(255), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    total_routes = Column(Integer, default=0)
    valid_routes = Column(Integer, default=0)
    success_rate = Column(Float, default=0.0)
    parameters = Column(JSON)  # Analysis parameters used
    processing_time_seconds = Column(Float, default=0.0)

    @property
    def success_rate_percent(self):
        """Calculate success rate as percentage."""
        if self.total_routes == 0:
            return 0.0
        return (self.valid_routes / self.total_routes) * 100
