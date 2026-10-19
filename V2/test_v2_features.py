"""
Test suite for ARPL V2 features.
Basic tests for database, session management, and core functionality.
"""

import pytest
import tempfile
import os
from datetime import datetime, timedelta

# Import V2 modules
from database import DatabaseManager
from session_manager import SessionManager
from analysis_history import AnalysisHistory
from user_preferences import PreferencesManager
from network_cache import NetworkCache
from batch_processor import BatchProcessor
from data_manager import DataManager

class TestDatabaseManager:
    """Test database manager functionality."""

    def test_database_creation(self):
        """Test database manager initialization."""
        db = DatabaseManager()
        assert db is not None
        assert db.engine is not None

    def test_health_check(self):
        """Test database health check."""
        db = DatabaseManager()
        health = db.health_check()
        assert health['status'] == 'healthy'
        assert health['connected'] is True
        assert 'tables' in health

    def test_database_stats(self):
        """Test database statistics."""
        db = DatabaseManager()
        stats = db.get_database_stats()
        assert 'sessions' in stats
        assert 'routes' in stats
        assert 'cached_networks' in stats
        assert 'analysis_history' in stats

class TestSessionManager:
    """Test session management functionality."""

    def setup_method(self):
        """Setup test database."""
        self.db = DatabaseManager()
        self.session_manager = SessionManager(self.db)

    def test_session_save_load(self):
        """Test saving and loading sessions."""
        test_state = {
            'test_key': 'test_value',
            'graph': None,  # Non-serializable item
            'analysis_params': {'param1': 'value1'}
        }

        session_id = self.session_manager.save_session('test_session', test_state)
        assert session_id is not None

        loaded_state = self.session_manager.load_session(session_id)
        assert loaded_state is not None
        assert loaded_state['test_key'] == 'test_value'
        assert loaded_state['analysis_params']['param1'] == 'value1'

    def test_session_list(self):
        """Test listing sessions."""
        # Create a test session
        test_state = {'test': 'data'}
        self.session_manager.save_session('list_test', test_state)

        sessions = self.session_manager.list_sessions()
        assert len(sessions) > 0
        assert any(s['name'] == 'list_test' for s in sessions)

    def test_session_delete(self):
        """Test deleting sessions."""
        test_state = {'test': 'data'}
        session_id = self.session_manager.save_session('delete_test', test_state)

        # Verify session exists
        loaded = self.session_manager.load_session(session_id)
        assert loaded is not None

        # Delete session
        success = self.session_manager.delete_session(session_id)
        assert success is True

        # Verify session is deleted
        loaded = self.session_manager.load_session(session_id)
        assert loaded is None

class TestAnalysisHistory:
    """Test analysis history functionality."""

    def setup_method(self):
        """Setup test database."""
        self.db = DatabaseManager()
        self.history = AnalysisHistory(self.db)

    def test_record_analysis(self):
        """Test recording analysis history."""
        record_id = self.history.record_analysis(
            jurisdiction='Test County',
            total_routes=10,
            valid_routes=7,
            parameters={'test_param': 'test_value'},
            processing_time_seconds=5.5
        )
        assert record_id is not None

    def test_get_history(self):
        """Test retrieving analysis history."""
        # Record a test analysis
        self.history.record_analysis('Test County', 10, 7, {})

        history = self.history.get_history(limit=10)
        assert len(history) > 0
        assert history[0]['jurisdiction'] == 'Test County'
        assert history[0]['total_routes'] == 10
        assert history[0]['valid_routes'] == 7

    def test_get_statistics(self):
        """Test getting analysis statistics."""
        # Record some test analyses
        self.history.record_analysis('County A', 10, 8, {})
        self.history.record_analysis('County B', 15, 12, {})

        stats = self.history.get_statistics(days=30)
        assert stats['total_analyses'] >= 2
        assert 'success_rate' in stats
        assert 'jurisdictions' in stats

    def test_export_csv(self):
        """Test CSV export functionality."""
        # Record a test analysis
        self.history.record_analysis('Test County', 10, 7, {})

        csv_content = self.history.export_to_csv()
        assert csv_content is not None
        assert 'Analysis Metadata' in csv_content
        assert 'Test County' in csv_content

class TestPreferencesManager:
    """Test user preferences functionality."""

    def setup_method(self):
        """Setup test database."""
        self.db = DatabaseManager()
        self.prefs = PreferencesManager(self.db)

    def test_save_get_preference(self):
        """Test saving and getting preferences."""
        # Save a preference
        success = self.prefs.save('test_key', 'test_value')
        assert success is True

        # Get the preference
        value = self.prefs.get('test_key')
        assert value == 'test_value'

    def test_get_default(self):
        """Test getting default values."""
        value = self.prefs.get('nonexistent_key', 'default_value')
        assert value == 'default_value'

    def test_save_all(self):
        """Test saving multiple preferences."""
        preferences = {
            'key1': 'value1',
            'key2': 'value2',
            'key3': {'nested': 'object'}
        }

        success = self.prefs.save_all(preferences)
        assert success is True

        # Verify all preferences were saved
        assert self.prefs.get('key1') == 'value1'
        assert self.prefs.get('key2') == 'value2'
        assert self.prefs.get('key3') == {'nested': 'object'}

    def test_get_all(self):
        """Test getting all preferences."""
        # Save some preferences
        self.prefs.save('key1', 'value1')
        self.prefs.save('key2', 'value2')

        all_prefs = self.prefs.get_all()
        assert 'key1' in all_prefs
        assert 'key2' in all_prefs
        assert all_prefs['key1'] == 'value1'
        assert all_prefs['key2'] == 'value2'

    def test_delete_preference(self):
        """Test deleting preferences."""
        # Save a preference
        self.prefs.save('delete_test', 'value')
        assert self.prefs.get('delete_test') == 'value'

        # Delete the preference
        success = self.prefs.delete('delete_test')
        assert success is True

        # Verify it's deleted
        value = self.prefs.get('delete_test')
        assert value is None

class TestNetworkCache:
    """Test network caching functionality."""

    def setup_method(self):
        """Setup test database."""
        self.db = DatabaseManager()
        self.cache = NetworkCache(self.db)

    def test_cache_key_generation(self):
        """Test cache key generation."""
        key = self.cache.generate_cache_key(
            'Test County',
            'POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))',
            'drive'
        )
        assert key is not None
        assert 'Test County' in key
        assert len(key) > 10  # Should include hash

    def test_cache_stats(self):
        """Test cache statistics."""
        stats = self.cache.get_cache_stats()
        assert 'total_entries' in stats
        assert 'active_entries' in stats
        assert 'expired_entries' in stats
        assert 'total_size_mb' in stats

    def test_clear_expired(self):
        """Test clearing expired cache entries."""
        # This test might not have expired entries, but should not fail
        cleared = self.cache.clear_expired()
        assert isinstance(cleared, int)
        assert cleared >= 0

class TestDataManager:
    """Test data manager functionality."""

    def setup_method(self):
        """Setup test data manager."""
        self.data_manager = DataManager()

    def test_data_manager_creation(self):
        """Test data manager initialization."""
        assert self.data_manager is not None
        assert hasattr(self.data_manager, 'tiger_config')
        assert hasattr(self.data_manager, 'local_paths')

    def test_get_data_statistics(self):
        """Test getting data statistics."""
        stats = self.data_manager.get_data_statistics()
        assert 'local_data' in stats
        assert 'available_datasets' in stats
        assert 'supported_years' in stats

    def test_validate_data_quality(self):
        """Test data quality validation."""
        # Test with None
        result = self.data_manager.validate_data_quality(None)
        assert result['status'] == 'invalid'

        # Test with empty GeoDataFrame
        import geopandas as gpd
        empty_gdf = gpd.GeoDataFrame()
        result = self.data_manager.validate_data_quality(empty_gdf)
        assert result['status'] == 'invalid'

class TestBatchProcessor:
    """Test batch processing functionality."""

    def setup_method(self):
        """Setup test database."""
        self.db = DatabaseManager()
        self.batch_processor = BatchProcessor(self.db)

    def test_batch_processor_creation(self):
        """Test batch processor initialization."""
        assert self.batch_processor is not None
        assert self.batch_processor.db_manager is not None
        assert self.batch_processor.history is not None

    def test_validate_incident_edges(self):
        """Test incident edge validation."""
        # Create a simple test graph
        import networkx as nx
        graph = nx.Graph()
        graph.add_edge(1, 2)
        graph.add_edge(2, 3)

        incident_edges = [(1, 2), (2, 3), (3, 4)]  # Last one is invalid

        result = self.batch_processor.validate_incident_edges(graph, incident_edges)
        assert len(result['valid']) == 2
        assert len(result['invalid']) == 1
        assert (3, 4) in result['invalid']

    def test_calculate_batch_stats(self):
        """Test batch statistics calculation."""
        # Mock batch results
        results = {
            (1, 2): {
                'total_routes': 10,
                'valid_detours': 7,
                'processing_time': 2.5
            },
            (2, 3): {
                'total_routes': 8,
                'valid_detours': 6,
                'processing_time': 1.8
            }
        }

        stats = self.batch_processor._calculate_batch_stats(results)
        assert stats['total_routes'] == 18
        assert stats['valid_routes'] == 13
        assert stats['successful_analyses'] == 2
        assert stats['failed_analyses'] == 0

def run_all_tests():
    """Run all tests and return results."""
    test_classes = [
        TestDatabaseManager,
        TestSessionManager,
        TestAnalysisHistory,
        TestPreferencesManager,
        TestNetworkCache,
        TestDataManager,
        TestBatchProcessor
    ]

    results = {
        'passed': 0,
        'failed': 0,
        'errors': []
    }

    for test_class in test_classes:
        test_instance = test_class()

        # Get all test methods
        test_methods = [method for method in dir(test_instance) if method.startswith('test_')]

        for test_method in test_methods:
            try:
                # Setup if method exists
                if hasattr(test_instance, 'setup_method'):
                    test_instance.setup_method()

                # Run test
                getattr(test_instance, test_method)()
                results['passed'] += 1
                print(f"✅ {test_class.__name__}.{test_method}")

            except Exception as e:
                results['failed'] += 1
                error_msg = f"❌ {test_class.__name__}.{test_method}: {str(e)}"
                results['errors'].append(error_msg)
                print(error_msg)

    return results

if __name__ == "__main__":
    print("Running ARPL V2 Test Suite...")
    print("=" * 50)

    results = run_all_tests()

    print("=" * 50)
    print(f"Tests passed: {results['passed']}")
    print(f"Tests failed: {results['failed']}")

    if results['errors']:
        print("\nErrors:")
        for error in results['errors']:
            print(f"  {error}")

    print("\nTest suite completed!")
