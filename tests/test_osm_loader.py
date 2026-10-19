"""
Unit tests for ARPL OSM Network Loader module.
"""

import pytest
from pathlib import Path
from arpl.core.osm_loader import OSMNetworkLoader, STATE_ABBREV, STATE_NAMES

class TestOSMNetworkLoader:
    """Test OSM Network Loader functionality."""

    def test_state_mappings(self):
        """Test state name and abbreviation mappings."""
        assert STATE_ABBREV['VA'] == 'virginia'
        assert STATE_ABBREV['NY'] == 'new_york'
        assert STATE_ABBREV['CA'] == 'california'
        assert STATE_NAMES['virginia'] == 'VA'
        assert STATE_NAMES['california'] == 'CA'

    def test_loader_initialization(self):
        """Test loader instantiation and metadata access."""
        loader = OSMNetworkLoader()
        assert loader is not None
        assert hasattr(loader, 'metadata')
        states = loader.get_available_states()
        assert isinstance(states, list)

    def test_state_availability_check(self):
        """Test checking availability of states."""
        loader = OSMNetworkLoader()
        # Non-existent state should return False
        assert loader.is_state_available("fictional_state_123") is False
