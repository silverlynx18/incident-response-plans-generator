"""
Network caching module for ARPL V2.
Manages caching of network graphs for improved performance.
"""

import osmnx as ox
import networkx as nx
import tempfile
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session

from database import DatabaseManager, CachedNetwork

class NetworkCache:
    """Manages caching of network graphs for performance optimization."""

    def __init__(self, db_manager: DatabaseManager):
        """Initialize network cache with database connection."""
        self.db_manager = db_manager

    def save_network(
        self,
        cache_key: str,
        graph: nx.Graph,
        jurisdiction: str,
        expiration_days: int = 30
    ) -> bool:
        """
        Save a network graph to cache.

        Args:
            cache_key: Unique cache key
            graph: NetworkX graph to cache
            jurisdiction: Jurisdiction name
            expiration_days: Days until cache expires

        Returns:
            True if successful, False otherwise
        """
        try:
            # Serialize graph to GraphML
            with tempfile.NamedTemporaryFile(mode='w', suffix='.graphml', delete=False) as tmp_file:
                ox.save_graphml(graph, filepath=tmp_file.name)

                # Read the serialized data
                with open(tmp_file.name, 'r') as f:
                    graph_data = f.read()

                # Clean up temp file
                os.unlink(tmp_file.name)

            # Calculate size
            size_bytes = len(graph_data.encode('utf-8'))

            # Calculate expiration
            expires_at = datetime.utcnow() + timedelta(days=expiration_days)

            with self.db_manager.get_session() as db:
                # Check if cache entry already exists
                existing = db.query(CachedNetwork).filter(
                    CachedNetwork.cache_key == cache_key
                ).first()

                if existing:
                    # Update existing entry
                    existing.graph_data = graph_data
                    existing.jurisdiction = jurisdiction
                    existing.expires_at = expires_at
                    existing.size_bytes = size_bytes
                    existing.created_at = datetime.utcnow()
                else:
                    # Create new entry
                    cache_entry = CachedNetwork(
                        cache_key=cache_key,
                        jurisdiction=jurisdiction,
                        graph_data=graph_data,
                        expires_at=expires_at,
                        size_bytes=size_bytes
                    )
                    db.add(cache_entry)

                db.commit()
                return True

        except Exception as e:
            print(f"Error saving network to cache: {e}")
            return False

    def load_network(self, cache_key: str) -> Optional[nx.Graph]:
        """
        Load a network graph from cache.

        Args:
            cache_key: Cache key to load

        Returns:
            NetworkX graph if found and not expired, None otherwise
        """
        try:
            with self.db_manager.get_session() as db:
                cache_entry = db.query(CachedNetwork).filter(
                    CachedNetwork.cache_key == cache_key
                ).first()

                if not cache_entry:
                    return None

                # Check if expired
                if cache_entry.is_expired():
                    # Remove expired entry
                    db.delete(cache_entry)
                    db.commit()
                    return None

                # Deserialize graph from GraphML
                with tempfile.NamedTemporaryFile(mode='w', suffix='.graphml', delete=False) as tmp_file:
                    tmp_file.write(cache_entry.graph_data)
                    tmp_file.flush()

                    # Load graph
                    graph = ox.load_graphml(filepath=tmp_file.name)

                    # Clean up temp file
                    os.unlink(tmp_file.name)

                return graph

        except Exception as e:
            print(f"Error loading network from cache: {e}")
            return None

    def generate_cache_key(
        self,
        jurisdiction: str,
        polygon_wkt: str,
        network_type: str = "drive"
    ) -> str:
        """
        Generate a unique cache key for a network.

        Args:
            jurisdiction: Jurisdiction name
            polygon_wkt: Polygon WKT string
            network_type: OSMnx network type

        Returns:
            Unique cache key
        """
        # Create hash of polygon and parameters
        content = f"{jurisdiction}_{polygon_wkt}_{network_type}"
        hash_obj = hashlib.md5(content.encode('utf-8'))
        return f"{jurisdiction}_{hash_obj.hexdigest()[:12]}"

    def clear_expired(self) -> int:
        """
        Clear expired cache entries.

        Returns:
            Number of entries removed
        """
        try:
            with self.db_manager.get_session() as db:
                expired_entries = db.query(CachedNetwork).filter(
                    CachedNetwork.expires_at < datetime.utcnow()
                ).all()

                count = len(expired_entries)
                for entry in expired_entries:
                    db.delete(entry)

                db.commit()
                return count

        except Exception as e:
            print(f"Error clearing expired cache entries: {e}")
            return 0

    def clear_all(self) -> int:
        """
        Clear all cache entries.

        Returns:
            Number of entries removed
        """
        try:
            with self.db_manager.get_session() as db:
                all_entries = db.query(CachedNetwork).all()
                count = len(all_entries)

                for entry in all_entries:
                    db.delete(entry)

                db.commit()
                return count

        except Exception as e:
            print(f"Error clearing all cache entries: {e}")
            return 0

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        try:
            with self.db_manager.get_session() as db:
                total_entries = db.query(CachedNetwork).count()
                expired_entries = db.query(CachedNetwork).filter(
                    CachedNetwork.expires_at < datetime.utcnow()
                ).count()

                total_size = db.query(db.func.sum(CachedNetwork.size_bytes)).scalar() or 0

                # Get jurisdiction breakdown
                jurisdiction_stats = db.query(
                    CachedNetwork.jurisdiction,
                    db.func.count(CachedNetwork.id).label('count'),
                    db.func.sum(CachedNetwork.size_bytes).label('size')
                ).group_by(CachedNetwork.jurisdiction).all()

                return {
                    'total_entries': total_entries,
                    'expired_entries': expired_entries,
                    'active_entries': total_entries - expired_entries,
                    'total_size_mb': round(total_size / (1024 * 1024), 2),
                    'jurisdictions': [
                        {
                            'name': stat.jurisdiction,
                            'entries': stat.count,
                            'size_mb': round(stat.size / (1024 * 1024), 2) if stat.size else 0
                        }
                        for stat in jurisdiction_stats
                    ]
                }

        except Exception as e:
            print(f"Error getting cache stats: {e}")
            return {}

    def get_cache_info(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a specific cache entry.

        Args:
            cache_key: Cache key to get info for

        Returns:
            Cache entry info or None if not found
        """
        try:
            with self.db_manager.get_session() as db:
                entry = db.query(CachedNetwork).filter(
                    CachedNetwork.cache_key == cache_key
                ).first()

                if entry:
                    return {
                        'cache_key': entry.cache_key,
                        'jurisdiction': entry.jurisdiction,
                        'created_at': entry.created_at.isoformat() if entry.created_at else None,
                        'expires_at': entry.expires_at.isoformat() if entry.expires_at else None,
                        'size_mb': round(entry.size_bytes / (1024 * 1024), 2),
                        'is_expired': entry.is_expired()
                    }
                return None

        except Exception as e:
            print(f"Error getting cache info: {e}")
            return None

    def list_cached_networks(self, jurisdiction: Optional[str] = None) -> list:
        """
        List all cached networks.

        Args:
            jurisdiction: Filter by jurisdiction (optional)

        Returns:
            List of cache entry info
        """
        try:
            with self.db_manager.get_session() as db:
                query = db.query(CachedNetwork)

                if jurisdiction:
                    query = query.filter(CachedNetwork.jurisdiction == jurisdiction)

                entries = query.order_by(CachedNetwork.created_at.desc()).all()

                return [
                    {
                        'cache_key': entry.cache_key,
                        'jurisdiction': entry.jurisdiction,
                        'created_at': entry.created_at.isoformat() if entry.created_at else None,
                        'expires_at': entry.expires_at.isoformat() if entry.expires_at else None,
                        'size_mb': round(entry.size_bytes / (1024 * 1024), 2),
                        'is_expired': entry.is_expired()
                    }
                    for entry in entries
                ]

        except Exception as e:
            print(f"Error listing cached networks: {e}")
            return []

    def delete_cache_entry(self, cache_key: str) -> bool:
        """
        Delete a specific cache entry.

        Args:
            cache_key: Cache key to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            with self.db_manager.get_session() as db:
                entry = db.query(CachedNetwork).filter(
                    CachedNetwork.cache_key == cache_key
                ).first()

                if entry:
                    db.delete(entry)
                    db.commit()
                    return True
                return False

        except Exception as e:
            print(f"Error deleting cache entry: {e}")
            return False

    def cleanup_old_entries(self, days: int = 7) -> int:
        """
        Clean up cache entries older than specified days.

        Args:
            days: Number of days to keep

        Returns:
            Number of entries removed
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            with self.db_manager.get_session() as db:
                old_entries = db.query(CachedNetwork).filter(
                    CachedNetwork.created_at < cutoff_date
                ).all()

                count = len(old_entries)
                for entry in old_entries:
                    db.delete(entry)

                db.commit()
                return count

        except Exception as e:
            print(f"Error cleaning up old cache entries: {e}")
            return 0
