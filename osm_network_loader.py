"""
OSM Network Loader Module

Provides fast loading of pre-processed state networks from pickle files.
Integrates with the V1.5.3 app for instant network loading.
"""

import os
import json
import pickle
import gzip
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
from datetime import datetime

import networkx as nx
import geopandas as gpd
from shapely.geometry import Polygon
from shapely.wkt import loads

# Configuration
MODULE_DIR = Path(__file__).parent
# Try multiple possible data locations
POSSIBLE_DATA_DIRS = [
    MODULE_DIR / "data" / "osm_networks",  # When in V1.6.1 directory
    Path.cwd() / "data" / "osm_networks",  # When in portable archive or cloud
    Path.cwd() / "V1.6.1" / "data" / "osm_networks",  # When in project root
    Path.cwd() / "V1.6" / "data" / "osm_networks",  # Fallback to V1.6
    Path.cwd() / "V1.5" / "data" / "osm_networks",  # Fallback to V1.5
]

# Find the first existing data directory
NETWORKS_DIR = None
for data_dir in POSSIBLE_DATA_DIRS:
    if data_dir.exists():
        NETWORKS_DIR = data_dir
        break

if NETWORKS_DIR is None:
    # Fallback to the first option
    NETWORKS_DIR = POSSIBLE_DATA_DIRS[0]

STATES_DIR = NETWORKS_DIR / "states"
METADATA_FILE = NETWORKS_DIR / "metadata.json"

# US States mapping for jurisdiction matching
STATE_ABBREV = {
    'AL': 'alabama', 'AK': 'alaska', 'AZ': 'arizona', 'AR': 'arkansas',
    'CA': 'california', 'CO': 'colorado', 'CT': 'connecticut', 'DE': 'delaware',
    'FL': 'florida', 'GA': 'georgia', 'HI': 'hawaii', 'ID': 'idaho',
    'IL': 'illinois', 'IN': 'indiana', 'IA': 'iowa', 'KS': 'kansas',
    'KY': 'kentucky', 'LA': 'louisiana', 'ME': 'maine', 'MD': 'maryland',
    'MA': 'massachusetts', 'MI': 'michigan', 'MN': 'minnesota', 'MS': 'mississippi',
    'MO': 'missouri', 'MT': 'montana', 'NE': 'nebraska', 'NV': 'nevada',
    'NH': 'new_hampshire', 'NJ': 'new_jersey', 'NM': 'new_mexico', 'NY': 'new_york',
    'NC': 'north_carolina', 'ND': 'north_dakota', 'OH': 'ohio', 'OK': 'oklahoma',
    'OR': 'oregon', 'PA': 'pennsylvania', 'RI': 'rhode_island', 'SC': 'south_carolina',
    'SD': 'south_dakota', 'TN': 'tennessee', 'TX': 'texas', 'UT': 'utah',
    'VT': 'vermont', 'VA': 'virginia', 'WA': 'washington', 'WV': 'west_virginia',
    'WI': 'wisconsin', 'WY': 'wyoming', 'DC': 'district_of_columbia'
}

STATE_NAMES = {v: k for k, v in STATE_ABBREV.items()}

class OSMNetworkLoader:
    """Fast loader for pre-processed OSM networks."""

    def __init__(self):
        self.metadata = self._load_metadata()
        self.logger = logging.getLogger(__name__)
        # Debug: Log the paths being used
        self.logger.info(f"OSMNetworkLoader initialized with NETWORKS_DIR: {NETWORKS_DIR}")
        self.logger.info(f"STATES_DIR: {STATES_DIR}")
        self.logger.info(f"METADATA_FILE: {METADATA_FILE}")
        self.logger.info(f"Available states: {self.get_available_states()}")

    def _load_metadata(self) -> Dict:
        """Load network metadata."""
        if not METADATA_FILE.exists():
            return {"states": {}}

        try:
            with open(METADATA_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.warning(f"Could not load metadata: {e}")
            return {"states": {}}

    def get_available_states(self) -> List[str]:
        """Get list of available state networks."""
        return list(self.metadata.get("states", {}).keys())

    def get_state_info(self, state_key: str) -> Optional[Dict]:
        """Get information about a state network without loading it."""
        return self.metadata.get("states", {}).get(state_key)

    def is_state_available(self, state_key: str) -> bool:
        """Check if a state network is available."""
        return state_key in self.metadata.get("states", {})

    def load_state_network(self, state_key: str) -> Optional[nx.MultiDiGraph]:
        """
        Load a pre-processed state network.

        Args:
            state_key: State identifier (e.g., 'california', 'new_york')

        Returns:
            NetworkX MultiDiGraph or None if not found
        """
        if not self.is_state_available(state_key):
            self.logger.warning(f"State network not available: {state_key}")
            return None

        filename = f"{state_key}.pkl.gz"
        filepath = STATES_DIR / filename

        if not filepath.exists():
            self.logger.error(f"State file not found: {filepath}")
            return None

        try:
            with gzip.open(filepath, 'rb') as f:
                graph = pickle.load(f)

            self.logger.info(f"Loaded {state_key}: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
            return graph

        except Exception as e:
            self.logger.error(f"Error loading {state_key}: {e}")
            return None

    def _normalize_state_name(self, state_name: str) -> str:
        """Normalize state name to state key."""
        # Handle common variations
        state_name = state_name.lower().strip()

        # Handle full state names
        if state_name in STATE_NAMES:
            return state_name

        # Handle abbreviations
        if state_name.upper() in STATE_ABBREV:
            return STATE_ABBREV[state_name.upper()]

        # Handle common variations
        variations = {
            'dc': 'district_of_columbia',
            'washington dc': 'district_of_columbia',
            'd.c.': 'district_of_columbia',
            'new hampshire': 'new_hampshire',
            'new jersey': 'new_jersey',
            'new mexico': 'new_mexico',
            'new york': 'new_york',
            'north carolina': 'north_carolina',
            'north dakota': 'north_dakota',
            'rhode island': 'rhode_island',
            'south carolina': 'south_carolina',
            'south dakota': 'south_dakota',
            'west virginia': 'west_virginia',
            'virginia': 'virginia'  # Ensure Virginia maps correctly
        }

        return variations.get(state_name, state_name.replace(' ', '_'))

    def _get_state_bounds(self, state_key: str) -> Optional[List[float]]:
        """Get bounding box for a state."""
        state_info = self.get_state_info(state_key)
        if state_info:
            return state_info.get("bounds")
        return None

    def _polygon_intersects_state(self, polygon: Polygon, state_key: str) -> bool:
        """Check if a polygon intersects with a state's bounding box."""
        state_bounds = self._get_state_bounds(state_key)
        if not state_bounds:
            return False

        # Create bounding box polygon
        minx, miny, maxx, maxy = state_bounds
        state_bbox = Polygon([(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)])

        return polygon.intersects(state_bbox)

    def _identify_intersecting_states(self, polygon: Polygon) -> List[str]:
        """Identify which states intersect with the given polygon."""
        intersecting_states = []

        for state_key in self.get_available_states():
            if self._polygon_intersects_state(polygon, state_key):
                intersecting_states.append(state_key)

        return intersecting_states

    def load_jurisdiction_network(self, polygon_wkt: str, jurisdiction_name: str = None) -> Optional[nx.MultiDiGraph]:
        """
        Load network for a jurisdiction by identifying intersecting states.

        Args:
            polygon_wkt: WKT representation of jurisdiction polygon
            jurisdiction_name: Name of jurisdiction (for logging)

        Returns:
            NetworkX MultiDiGraph or None if not found
        """
        try:
            polygon = loads(polygon_wkt)
        except Exception as e:
            self.logger.error(f"Invalid polygon WKT: {e}")
            return None

        # Identify intersecting states
        intersecting_states = self._identify_intersecting_states(polygon)

        if not intersecting_states:
            self.logger.warning(f"No intersecting states found for jurisdiction: {jurisdiction_name}")
            return None

        self.logger.info(f"Loading networks for states: {intersecting_states}")

        # Load and merge state networks
        merged_graph = nx.MultiDiGraph()

        for state_key in intersecting_states:
            state_graph = self.load_state_network(state_key)
            if state_graph:
                # Merge graphs
                merged_graph = nx.compose(merged_graph, state_graph)

        if not merged_graph.nodes():
            self.logger.warning("No nodes found in merged graph")
            return None

        # Trim to jurisdiction boundaries if needed
        # For now, we'll return the full merged graph
        # TODO: Add trimming functionality if needed

        self.logger.info(f"Loaded jurisdiction network: {merged_graph.number_of_nodes()} nodes, {merged_graph.number_of_edges()} edges")
        return merged_graph

    def get_network_stats(self) -> Dict:
        """Get overall statistics about available networks."""
        states = self.metadata.get("states", {})

        total_nodes = sum(state.get("nodes", 0) for state in states.values())
        total_edges = sum(state.get("edges", 0) for state in states.values())
        total_size_mb = sum(state.get("file_size_mb", 0) for state in states.values())

        return {
            "available_states": len(states),
            "total_states": 51,
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "total_size_mb": round(total_size_mb, 2),
            "last_updated": self.metadata.get("last_updated"),
            "states": list(states.keys())
        }

# Global instance for easy access
network_loader = OSMNetworkLoader()

def load_jurisdiction_network(polygon_wkt: str, jurisdiction_name: str = None) -> Optional[nx.MultiDiGraph]:
    """Convenience function to load jurisdiction network."""
    return network_loader.load_jurisdiction_network(polygon_wkt, jurisdiction_name)

def get_available_networks() -> List[str]:
    """Convenience function to get available networks."""
    return network_loader.get_available_states()

def get_network_stats() -> Dict:
    """Convenience function to get network statistics."""
    return network_loader.get_network_stats()

def is_network_available() -> bool:
    """Check if any pre-downloaded networks are available."""
    return len(network_loader.get_available_states()) > 0
