"""
Database manager for ARPL V2.
Provides high-level database operations and health checks.
"""

from sqlalchemy.orm import Session
from sqlalchemy import text, func
from datetime import datetime, timedelta
import json
from typing import Dict, List, Optional, Any

from .schema import SessionLocal, create_tables, engine
from .models import Session as SessionModel, Route, CachedNetwork, UserPreference, AnalysisHistory

class DatabaseManager:
    """High-level database operations manager."""

    def __init__(self):
        """Initialize database manager and create tables if needed."""
        self.engine = engine
        create_tables()

    def get_session(self) -> Session:
        """Get a database session."""
        return SessionLocal()

    def health_check(self) -> Dict[str, Any]:
        """Check database health and return status."""
        try:
            with self.get_session() as db:
                # Test basic connectivity
                result = db.execute(text("SELECT 1")).fetchone()

                # Get table counts
                session_count = db.query(SessionModel).count()
                route_count = db.query(Route).count()
                cache_count = db.query(CachedNetwork).count()
                preference_count = db.query(UserPreference).count()
                history_count = db.query(AnalysisHistory).count()

                return {
                    "status": "healthy",
                    "connected": True,
                    "tables": {
                        "sessions": session_count,
                        "routes": route_count,
                        "cached_networks": cache_count,
                        "user_preferences": preference_count,
                        "analysis_history": history_count
                    },
                    "timestamp": datetime.utcnow().isoformat()
                }
        except Exception as e:
            return {
                "status": "unhealthy",
                "connected": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }

    def cleanup_expired_caches(self) -> int:
        """Remove expired cache entries and return count of removed items."""
        with self.get_session() as db:
            expired_caches = db.query(CachedNetwork).filter(
                CachedNetwork.expires_at < datetime.utcnow()
            ).all()

            count = len(expired_caches)
            for cache in expired_caches:
                db.delete(cache)

            db.commit()
            return count

    def get_database_stats(self) -> Dict[str, Any]:
        """Get comprehensive database statistics."""
        with self.get_session() as db:
            stats = {
                "sessions": {
                    "total": db.query(SessionModel).count(),
                    "recent": db.query(SessionModel).filter(
                        SessionModel.created_at >= datetime.utcnow() - timedelta(days=7)
                    ).count()
                },
                "routes": {
                    "total": db.query(Route).count(),
                    "valid": db.query(Route).filter(Route.is_valid == True).count(),
                    "invalid": db.query(Route).filter(Route.is_valid == False).count()
                },
                "cached_networks": {
                    "total": db.query(CachedNetwork).count(),
                    "expired": db.query(CachedNetwork).filter(
                        CachedNetwork.expires_at < datetime.utcnow()
                    ).count(),
                    "total_size_mb": db.query(func.sum(CachedNetwork.size_bytes)).scalar() or 0
                },
                "analysis_history": {
                    "total": db.query(AnalysisHistory).count(),
                    "avg_success_rate": db.query(func.avg(AnalysisHistory.success_rate)).scalar() or 0
                }
            }

            # Convert bytes to MB
            if stats["cached_networks"]["total_size_mb"]:
                stats["cached_networks"]["total_size_mb"] = round(
                    stats["cached_networks"]["total_size_mb"] / (1024 * 1024), 2
                )

            return stats

    def backup_database(self, backup_path: str) -> bool:
        """Create a backup of the database."""
        try:
            import shutil
            import os

            # Get the database file path
            db_path = self.engine.url.database

            if os.path.exists(db_path):
                shutil.copy2(db_path, backup_path)
                return True
            return False
        except Exception as e:
            print(f"Backup failed: {e}")
            return False

    def restore_database(self, backup_path: str) -> bool:
        """Restore database from backup."""
        try:
            import shutil
            import os

            # Get the database file path
            db_path = self.engine.url.database

            if os.path.exists(backup_path):
                shutil.copy2(backup_path, db_path)
                return True
            return False
        except Exception as e:
            print(f"Restore failed: {e}")
            return False

    # User Preferences Methods
    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get user preference value."""
        with self.get_session() as db:
            preference = db.query(UserPreference).filter(UserPreference.key == key).first()
            if preference:
                # Convert value based on type
                if preference.pref_type == 'boolean':
                    return preference.value.lower() == 'true'
                elif preference.pref_type == 'integer':
                    return int(preference.value)
                elif preference.pref_type == 'float':
                    return float(preference.value)
                elif preference.pref_type == 'json':
                    return json.loads(preference.value)
                else:
                    return preference.value
            return default

    def set_preference(self, key: str, value: Any, pref_type: str = None, description: str = None) -> bool:
        """Set user preference value."""
        try:
            with self.get_session() as db:
                # Auto-detect type if not provided
                if pref_type is None:
                    if isinstance(value, bool):
                        pref_type = 'boolean'
                    elif isinstance(value, int):
                        pref_type = 'integer'
                    elif isinstance(value, float):
                        pref_type = 'float'
                    elif isinstance(value, (dict, list)):
                        pref_type = 'json'
                    else:
                        pref_type = 'string'

                # Convert value to string for storage
                if pref_type == 'json':
                    value_str = json.dumps(value)
                else:
                    value_str = str(value)

                # Check if preference exists
                existing = db.query(UserPreference).filter(UserPreference.key == key).first()

                if existing:
                    # Update existing
                    existing.value = value_str
                    existing.pref_type = pref_type
                    existing.description = description or existing.description
                    existing.updated_at = datetime.utcnow()
                else:
                    # Create new
                    new_pref = UserPreference(
                        key=key,
                        value=value_str,
                        pref_type=pref_type,
                        description=description or '',
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    db.add(new_pref)

                db.commit()
                return True
        except Exception as e:
            print(f"Failed to set preference {key}: {e}")
            return False

    def delete_preference(self, key: str) -> bool:
        """Delete user preference."""
        try:
            with self.get_session() as db:
                preference = db.query(UserPreference).filter(UserPreference.key == key).first()
                if preference:
                    db.delete(preference)
                    db.commit()
                    return True
                return False
        except Exception as e:
            print(f"Failed to delete preference {key}: {e}")
            return False

    def get_all_preferences(self) -> Dict[str, Any]:
        """Get all user preferences."""
        preferences = {}
        with self.get_session() as db:
            prefs = db.query(UserPreference).all()
            for pref in prefs:
                preferences[pref.key] = self.get_preference(pref.key)
        return preferences
