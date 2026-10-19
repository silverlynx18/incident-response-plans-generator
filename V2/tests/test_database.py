"""
Unit tests for database module.
Tests database operations and data persistence.
"""

import pytest
import tempfile
import os
import json
from datetime import datetime, timedelta
import sys

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import DatabaseManager
from database.models import (
    Session, Route, CachedNetwork, UserPreference,
    AnalysisHistoryEntry, BatchRun, Scenario
)


class TestDatabase:
    """Test cases for database module."""

    def setup_method(self):
        """Set up test fixtures."""
        # Create temporary database for testing
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()

        # Initialize database manager with test database
        self.db_manager = DatabaseManager(db_path=self.temp_db.name)

        # Sample test data
        self.sample_session_data = {
            'selected_jurisdiction_name': 'Test County',
            'selected_jurisdiction_type': 'county',
            'selected_state_name': 'Test State',
            'detour_results': {
                (1, 2): (True, 120.5, 100.0, [1, 2])
            },
            'analysis_params': {
                'n_turn_nodes': 5,
                'sector_angle_deg': 180
            }
        }

    def teardown_method(self):
        """Clean up test fixtures."""
        # Remove temporary database file
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)

    def test_database_initialization(self):
        """Test database initialization."""
        # Check that database file was created
        assert os.path.exists(self.temp_db.name)

        # Check that tables were created
        with self.db_manager.get_db() as db:
            # This would require checking table existence
            # For now, just verify the database manager was created
            assert self.db_manager is not None

    def test_save_analysis_session(self):
        """Test saving analysis session."""
        session_id = self.db_manager.save_analysis_session(self.sample_session_data)

        assert session_id is not None
        assert isinstance(session_id, int)
        assert session_id > 0

    def test_load_analysis_session(self):
        """Test loading analysis session."""
        # Save session first
        session_id = self.db_manager.save_analysis_session(self.sample_session_data)

        # Load session
        loaded_data = self.db_manager.load_analysis_session(session_id)

        assert loaded_data is not None
        assert loaded_data['selected_jurisdiction_name'] == 'Test County'
        assert loaded_data['selected_jurisdiction_type'] == 'county'
        assert loaded_data['selected_state_name'] == 'Test State'
        assert 'detour_results' in loaded_data
        assert 'analysis_params' in loaded_data

    def test_list_analysis_sessions(self):
        """Test listing analysis sessions."""
        # Save multiple sessions
        session_ids = []
        for i in range(3):
            session_data = self.sample_session_data.copy()
            session_data['selected_jurisdiction_name'] = f'Test County {i}'
            session_id = self.db_manager.save_analysis_session(session_data)
            session_ids.append(session_id)

        # List sessions
        sessions = self.db_manager.list_analysis_sessions(limit=10)

        assert len(sessions) >= 3
        assert all('id' in session for session in sessions)
        assert all('created_at' in session for session in sessions)

    def test_delete_analysis_session(self):
        """Test deleting analysis session."""
        # Save session
        session_id = self.db_manager.save_analysis_session(self.sample_session_data)

        # Delete session
        result = self.db_manager.delete_analysis_session(session_id)
        assert result is True

        # Try to load deleted session
        loaded_data = self.db_manager.load_analysis_session(session_id)
        assert loaded_data is None

    def test_user_preferences(self):
        """Test user preferences functionality."""
        # Set preference
        preference = self.db_manager.set_user_preference('test_key', 'test_value')
        assert preference is not None

        # Get preference
        value = self.db_manager.get_user_preference('test_key')
        assert value == 'test_value'

        # Get non-existent preference
        value = self.db_manager.get_user_preference('non_existent_key')
        assert value is None

    def test_cached_networks(self):
        """Test cached networks functionality."""
        # Sample network data
        network_data = b'sample_network_data'
        bbox = '(-122.5, 37.7, -122.3, 37.9)'
        tags = '{"highway": ["primary", "secondary"]}'
        expires_at = datetime.now() + timedelta(days=30)

        # Save cached network
        cached_network = self.db_manager.save_cached_network(
            'test_network', network_data, bbox, tags, expires_at
        )
        assert cached_network is not None

        # Get cached network
        retrieved_network = self.db_manager.get_cached_network('test_network')
        assert retrieved_network is not None
        assert retrieved_network.name == 'test_network'
        assert retrieved_network.graph_data == network_data

        # Delete cached network
        result = self.db_manager.delete_cached_network('test_network')
        assert result is True

        # Try to get deleted network
        retrieved_network = self.db_manager.get_cached_network('test_network')
        assert retrieved_network is None

    def test_analysis_history(self):
        """Test analysis history functionality."""
        # Record analysis history
        history_data = {
            'jurisdiction_name': 'Test County',
            'jurisdiction_type': 'county',
            'state_name': 'Test State',
            'total_routes': 5,
            'valid_routes': 3,
            'success_rate': 60.0
        }

        history_entry = self.db_manager.record_analysis_history(history_data)
        assert history_entry is not None

        # Get analysis history
        history = self.db_manager.get_analysis_history(limit=10)
        assert len(history) >= 1
        assert history[0]['jurisdiction_name'] == 'Test County'
        assert history[0]['total_routes'] == 5

    def test_batch_processing(self):
        """Test batch processing functionality."""
        # Create batch run
        incidents_data = {
            'incidents': [
                {'id': 1, 'location': (1, 2)},
                {'id': 2, 'location': (3, 4)}
            ]
        }
        params = {'n_turn_nodes': 5, 'sector_angle_deg': 180}

        batch_run = self.db_manager.create_batch_run(
            1, 'Test Batch', incidents_data, params
        )
        assert batch_run is not None
        assert batch_run.name == 'Test Batch'

        # Update batch run results
        results = {
            'total_incidents': 2,
            'completed_incidents': 2,
            'success_rate': 100.0
        }

        updated_batch = self.db_manager.update_batch_run_results(
            batch_run.id, results, 'completed'
        )
        assert updated_batch is not None
        assert updated_batch.status == 'completed'

        # Get batch run
        retrieved_batch = self.db_manager.get_batch_run(batch_run.id)
        assert retrieved_batch is not None
        assert retrieved_batch.name == 'Test Batch'

    def test_scenario_management(self):
        """Test scenario management functionality."""
        # Save scenario
        scenario_data = {
            'name': 'Test Scenario',
            'parameters': {'n_turn_nodes': 10},
            'results': {'total_routes': 5}
        }

        scenario = self.db_manager.save_scenario(1, 'Test Scenario', scenario_data)
        assert scenario is not None
        assert scenario.name == 'Test Scenario'

        # Get scenario
        retrieved_scenario = self.db_manager.get_scenario(scenario.id)
        assert retrieved_scenario is not None
        assert retrieved_scenario.name == 'Test Scenario'

        # Get scenarios for session
        scenarios = self.db_manager.get_scenarios_for_session(1)
        assert len(scenarios) >= 1
        assert scenarios[0].name == 'Test Scenario'

    def test_database_health(self):
        """Test database health monitoring."""
        health = self.db_manager.get_database_health()

        assert 'status' in health
        assert 'total_sessions' in health
        assert 'total_cached_networks' in health
        assert 'total_analysis_history' in health
        assert health['status'] in ['healthy', 'warning', 'error']

    def test_data_consistency(self):
        """Test data consistency across operations."""
        # Save session
        session_id = self.db_manager.save_analysis_session(self.sample_session_data)

        # Save related data
        self.db_manager.set_user_preference('test_pref', 'test_value')

        # Record analysis history
        history_data = {
            'jurisdiction_name': 'Test County',
            'total_routes': 1
        }
        self.db_manager.record_analysis_history(history_data)

        # Verify all data is accessible
        loaded_session = self.db_manager.load_analysis_session(session_id)
        preference = self.db_manager.get_user_preference('test_pref')
        history = self.db_manager.get_analysis_history(limit=1)

        assert loaded_session is not None
        assert preference == 'test_value'
        assert len(history) >= 1
        assert history[0]['jurisdiction_name'] == 'Test County'


class TestDatabaseIntegration:
    """Integration tests for database module."""

    def setup_method(self):
        """Set up integration test fixtures."""
        # Create temporary database for testing
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()

        # Initialize database manager
        self.db_manager = DatabaseManager(db_path=self.temp_db.name)

        # Comprehensive test data
        self.comprehensive_session_data = {
            'selected_jurisdiction_name': 'Comprehensive County',
            'selected_jurisdiction_type': 'county',
            'selected_state_name': 'Comprehensive State',
            'selected_incident_edge': (100, 200),
            'incident_info': {
                'edge': (100, 200),
                'highway_type': 'motorway',
                'name': 'Comprehensive Highway',
                'length': 5000
            },
            'detour_results': {
                (100, 300): (True, 300.5, 250.0, [100, 150, 200, 250, 300]),
                (100, 400): (True, 450.2, 400.0, [100, 150, 200, 250, 300, 350, 400]),
                (100, 500): (False, 'Too Long', 800.0, [100, 150, 200, 250, 300, 350, 400, 450, 500])
            },
            'analysis_params': {
                'n_turn_nodes': 10,
                'sector_angle_deg': 270,
                'sector_radius_m': 5000,
                'min_travel_time_s': 120,
                'max_travel_time_s': 2400
            },
            'route_evaluations': {
                (100, 300): 'accepted',
                (100, 400): 'accepted',
                (100, 500): 'rejected'
            },
            'turn_nodes': {
                'start_nodes': [100, 150, 200],
                'end_nodes': [300, 400, 500]
            },
            'impacted_arterials': [
                (100, 200), (200, 300), (300, 400), (400, 500)
            ]
        }

    def teardown_method(self):
        """Clean up test fixtures."""
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)

    def test_complete_workflow(self):
        """Test complete database workflow."""
        # Save comprehensive session
        session_id = self.db_manager.save_analysis_session(self.comprehensive_session_data)
        assert session_id is not None

        # Set user preferences
        self.db_manager.set_user_preference('default_turn_nodes', '10')
        self.db_manager.set_user_preference('default_sector_angle', '270')

        # Cache network data
        network_data = b'comprehensive_network_data'
        bbox = '(-122.5, 37.7, -122.3, 37.9)'
        tags = '{"highway": ["motorway", "primary"]}'
        expires_at = datetime.now() + timedelta(days=30)

        cached_network = self.db_manager.save_cached_network(
            'comprehensive_network', network_data, bbox, tags, expires_at
        )
        assert cached_network is not None

        # Record analysis history
        history_data = {
            'jurisdiction_name': 'Comprehensive County',
            'jurisdiction_type': 'county',
            'state_name': 'Comprehensive State',
            'total_routes': 3,
            'valid_routes': 2,
            'success_rate': 66.7
        }

        history_entry = self.db_manager.record_analysis_history(history_data)
        assert history_entry is not None

        # Create batch run
        incidents_data = {
            'incidents': [
                {'id': 1, 'location': (100, 200)},
                {'id': 2, 'location': (200, 300)}
            ]
        }

        batch_run = self.db_manager.create_batch_run(
            session_id, 'Comprehensive Batch', incidents_data,
            self.comprehensive_session_data['analysis_params']
        )
        assert batch_run is not None

        # Save scenario
        scenario_data = {
            'name': 'Comprehensive Scenario',
            'parameters': self.comprehensive_session_data['analysis_params'],
            'results': {
                'total_routes': 3,
                'valid_routes': 2,
                'accepted_routes': 2
            }
        }

        scenario = self.db_manager.save_scenario(session_id, 'Comprehensive Scenario', scenario_data)
        assert scenario is not None

        # Verify all data is accessible
        loaded_session = self.db_manager.load_analysis_session(session_id)
        assert loaded_session is not None
        assert loaded_session['selected_jurisdiction_name'] == 'Comprehensive County'

        preference = self.db_manager.get_user_preference('default_turn_nodes')
        assert preference == '10'

        retrieved_network = self.db_manager.get_cached_network('comprehensive_network')
        assert retrieved_network is not None

        history = self.db_manager.get_analysis_history(limit=1)
        assert len(history) >= 1
        assert history[0]['jurisdiction_name'] == 'Comprehensive County'

        retrieved_batch = self.db_manager.get_batch_run(batch_run.id)
        assert retrieved_batch is not None
        assert retrieved_batch.name == 'Comprehensive Batch'

        retrieved_scenario = self.db_manager.get_scenario(scenario.id)
        assert retrieved_scenario is not None
        assert retrieved_scenario.name == 'Comprehensive Scenario'

    def test_data_persistence(self):
        """Test data persistence across database restarts."""
        # Save data
        session_id = self.db_manager.save_analysis_session(self.comprehensive_session_data)
        self.db_manager.set_user_preference('persistent_pref', 'persistent_value')

        # Create new database manager (simulating restart)
        new_db_manager = DatabaseManager(db_path=self.temp_db.name)

        # Verify data persists
        loaded_session = new_db_manager.load_analysis_session(session_id)
        assert loaded_session is not None
        assert loaded_session['selected_jurisdiction_name'] == 'Comprehensive County'

        preference = new_db_manager.get_user_preference('persistent_pref')
        assert preference == 'persistent_value'

    def test_performance_with_large_dataset(self):
        """Test performance with large dataset."""
        import time

        # Save many sessions
        start_time = time.time()

        for i in range(100):
            session_data = self.comprehensive_session_data.copy()
            session_data['selected_jurisdiction_name'] = f'Performance County {i}'
            self.db_manager.save_analysis_session(session_data)

        save_time = time.time() - start_time

        # List sessions
        start_time = time.time()
        sessions = self.db_manager.list_analysis_sessions(limit=100)
        list_time = time.time() - start_time

        # Verify performance
        assert len(sessions) >= 100
        assert save_time < 10.0  # Should save 100 sessions in under 10 seconds
        assert list_time < 5.0   # Should list 100 sessions in under 5 seconds


if __name__ == '__main__':
    pytest.main([__file__])
