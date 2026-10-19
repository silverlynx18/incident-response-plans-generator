"""
User preferences module for ARPL V2.
Manages user settings and default values.
"""

import json
from datetime import datetime
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from database import DatabaseManager, UserPreference

class PreferencesManager:
    """Manages user preferences and settings."""

    def __init__(self, db_manager: DatabaseManager):
        """Initialize preferences manager with database connection."""
        self.db_manager = db_manager
        self._cache = {}  # Simple in-memory cache
        self._cache_dirty = True

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a preference value.

        Args:
            key: Preference key
            default: Default value if not found

        Returns:
            Preference value or default
        """
        # Check cache first
        if not self._cache_dirty and key in self._cache:
            return self._cache[key]

        try:
            with self.db_manager.get_session() as db:
                preference = db.query(UserPreference).filter(UserPreference.key == key).first()

                if preference and preference.value:
                    # Try to deserialize JSON value
                    try:
                        value = json.loads(preference.value)
                    except (json.JSONDecodeError, TypeError):
                        value = preference.value

                    # Update cache
                    self._cache[key] = value
                    return value

                # Store default in cache
                self._cache[key] = default
                return default

        except Exception as e:
            print(f"Error getting preference {key}: {e}")
            return default

    def save(self, key: str, value: Any) -> bool:
        """
        Save a preference value.

        Args:
            key: Preference key
            value: Value to save

        Returns:
            True if successful, False otherwise
        """
        try:
            with self.db_manager.get_session() as db:
                # Serialize value
                if isinstance(value, (dict, list)):
                    serialized_value = json.dumps(value)
                else:
                    serialized_value = str(value)

                # Check if preference exists
                preference = db.query(UserPreference).filter(UserPreference.key == key).first()

                if preference:
                    # Update existing
                    preference.value = serialized_value
                    preference.updated_at = datetime.utcnow()
                else:
                    # Create new
                    preference = UserPreference(
                        key=key,
                        value=serialized_value
                    )
                    db.add(preference)

                db.commit()

                # Update cache
                self._cache[key] = value
                return True

        except Exception as e:
            print(f"Error saving preference {key}: {e}")
            return False

    def save_all(self, preferences: Dict[str, Any]) -> bool:
        """
        Save multiple preferences at once.

        Args:
            preferences: Dictionary of key-value pairs

        Returns:
            True if all successful, False otherwise
        """
        success = True
        for key, value in preferences.items():
            if not self.save(key, value):
                success = False

        return success

    def get_all(self) -> Dict[str, Any]:
        """
        Get all preferences as a dictionary.

        Returns:
            Dictionary of all preferences
        """
        try:
            with self.db_manager.get_session() as db:
                preferences = db.query(UserPreference).all()

                result = {}
                for pref in preferences:
                    try:
                        value = json.loads(pref.value)
                    except (json.JSONDecodeError, TypeError):
                        value = pref.value

                    result[pref.key] = value

                # Update cache
                self._cache.update(result)
                self._cache_dirty = False

                return result

        except Exception as e:
            print(f"Error getting all preferences: {e}")
            return {}

    def delete(self, key: str) -> bool:
        """
        Delete a preference.

        Args:
            key: Preference key to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            with self.db_manager.get_session() as db:
                preference = db.query(UserPreference).filter(UserPreference.key == key).first()

                if preference:
                    db.delete(preference)
                    db.commit()

                    # Remove from cache
                    if key in self._cache:
                        del self._cache[key]

                    return True
                return False

        except Exception as e:
            print(f"Error deleting preference {key}: {e}")
            return False

    def reset_to_defaults(self) -> bool:
        """
        Reset all preferences to default values.

        Returns:
            True if successful, False otherwise
        """
        try:
            defaults = self.get_default_preferences()
            return self.save_all(defaults)
        except Exception as e:
            print(f"Error resetting to defaults: {e}")
            return False

    def get_default_preferences(self) -> Dict[str, Any]:
        """
        Get default preference values.

        Returns:
            Dictionary of default preferences
        """
        return {
            # Analysis defaults
            'default_turn_nodes': 5,
            'default_sector_angle': 180,
            'default_max_detour_length': 2.0,

            # UI defaults
            'default_display_mode': 'selection',
            'show_counties': True,
            'show_mpos': True,
            'show_urban_areas': True,

            # Export defaults
            'default_export_format': 'GeoJSON',
            'include_metadata': True,
            'compress_exports': False,

            # Performance defaults
            'cache_networks': True,
            'cache_duration_days': 30,
            'auto_save_sessions': False,
            'max_edges_display': 50000,

            # Batch processing defaults
            'batch_progress_updates': True,
            'batch_parallel_processing': False,
            'batch_max_concurrent': 1
        }

    def get_analysis_defaults(self) -> Dict[str, Any]:
        """Get analysis-specific default preferences."""
        return {
            'turn_nodes': self.get('default_turn_nodes', 5),
            'sector_angle': self.get('default_sector_angle', 180),
            'max_detour_length': self.get('default_max_detour_length', 2.0)
        }

    def get_ui_defaults(self) -> Dict[str, Any]:
        """Get UI-specific default preferences."""
        return {
            'display_mode': self.get('default_display_mode', 'selection'),
            'show_counties': self.get('show_counties', True),
            'show_mpos': self.get('show_mpos', True),
            'show_urban_areas': self.get('show_urban_areas', True)
        }

    def get_export_defaults(self) -> Dict[str, Any]:
        """Get export-specific default preferences."""
        return {
            'format': self.get('default_export_format', 'GeoJSON'),
            'include_metadata': self.get('include_metadata', True),
            'compress': self.get('compress_exports', False)
        }

    def get_performance_defaults(self) -> Dict[str, Any]:
        """Get performance-specific default preferences."""
        return {
            'cache_networks': self.get('cache_networks', True),
            'cache_duration_days': self.get('cache_duration_days', 30),
            'auto_save_sessions': self.get('auto_save_sessions', False),
            'max_edges_display': self.get('max_edges_display', 50000)
        }

    def export_preferences(self, format: str = 'json') -> str:
        """
        Export preferences to string format.

        Args:
            format: Export format ('json', 'csv')

        Returns:
            Exported preferences as string
        """
        preferences = self.get_all()

        if format.lower() == 'json':
            return json.dumps(preferences, indent=2)

        elif format.lower() == 'csv':
            import csv
            import io

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['Key', 'Value'])

            for key, value in preferences.items():
                writer.writerow([key, str(value)])

            return output.getvalue()

        else:
            raise ValueError(f"Unsupported export format: {format}")

    def import_preferences(self, data: str, format: str = 'json') -> bool:
        """
        Import preferences from string format.

        Args:
            data: Preferences data as string
            format: Import format ('json', 'csv')

        Returns:
            True if successful, False otherwise
        """
        try:
            if format.lower() == 'json':
                preferences = json.loads(data)
                return self.save_all(preferences)

            elif format.lower() == 'csv':
                import csv
                import io

                reader = csv.DictReader(io.StringIO(data))
                preferences = {}

                for row in reader:
                    key = row.get('Key')
                    value = row.get('Value')
                    if key and value:
                        # Try to parse as JSON, fallback to string
                        try:
                            preferences[key] = json.loads(value)
                        except (json.JSONDecodeError, TypeError):
                            preferences[key] = value

                return self.save_all(preferences)

            else:
                raise ValueError(f"Unsupported import format: {format}")

        except Exception as e:
            print(f"Error importing preferences: {e}")
            return False

    def get_preference_history(self, key: str) -> List[Dict[str, Any]]:
        """
        Get history of changes for a specific preference.
        Note: This is a placeholder - would need additional table for history tracking.

        Args:
            key: Preference key

        Returns:
            List of historical values (placeholder implementation)
        """
        # This would require a separate preferences_history table
        # For now, return current value as single history entry
        current_value = self.get(key)
        if current_value is not None:
            return [{
                'value': current_value,
                'updated_at': datetime.utcnow().isoformat(),
                'action': 'current'
            }]
        return []
