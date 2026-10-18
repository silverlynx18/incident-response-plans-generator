"""
Unit tests for ARPL Exporters with Compound & Multi-Link Closures (Package C1).
Verifies export_to_geojson, export_to_kml, export_to_kmz, export_to_excel, export_to_csv, and export_to_pdf.
"""

import pytest
import networkx as nx
from shapely.geometry import LineString
import json
import zipfile
import io

import detour_utils as du
import export_utils_v1_5_6 as eu


@pytest.fixture
def sample_network():
    """Synthetic network with 2 mainline edges and an arterial bypass."""
    G = nx.MultiDiGraph()
    G.graph['crs'] = 'EPSG:4326'

    coords = {
        0: (-77.0, 38.0),
        1: (-77.0, 38.1),
        2: (-77.0, 38.2),
        3: (-77.0, 38.3),
        10: (-76.9, 38.0),
        20: (-76.9, 38.3)
    }

    for n, (x, y) in coords.items():
        G.add_node(n, x=x, y=y, turns=[])

    # Mainline edges (closed corridor: (0, 1) and (1, 2))
    for u, v in [(0, 1), (1, 2), (2, 3)]:
        geom = LineString([coords[u], coords[v]])
        G.add_edge(u, v, key=0, ref="I-95", highway="motorway",
                   travel_time=60.0, total_time=60.0, length=1000.0,
                   geometry=geom, start_bearing=0.0, end_bearing=0.0)

    # Bypass edges
    G.add_edge(0, 10, key=0, ref=None, highway="primary", travel_time=120.0, total_time=120.0, length=1500.0,
               geometry=LineString([coords[0], coords[10]]), start_bearing=90.0, end_bearing=90.0)
    G.add_edge(10, 20, key=0, ref=None, highway="primary", travel_time=120.0, total_time=120.0, length=1500.0,
               geometry=LineString([coords[10], coords[20]]), start_bearing=0.0, end_bearing=0.0)
    G.add_edge(20, 3, key=0, ref=None, highway="primary", travel_time=120.0, total_time=120.0, length=1500.0,
               geometry=LineString([coords[20], coords[3]]), start_bearing=270.0, end_bearing=270.0)

    return G


@pytest.fixture
def sample_accepted_detours(sample_network):
    """Accepted detours dictionary formatted as expected by export utilities."""
    return {
        (0, 3): {
            'route_key': (0, 3),
            'path': [0, 10, 20, 3],
            'total_time_minutes': 6.0,
            'freeflow_time_minutes': 6.0,
            'data': (True, 360.0, 360.0, [0, 10, 20, 3]),
            'buffer_points': [{'name': 'Signal 1', 'x': -76.9, 'y': 38.1}],
            'details': {
                'total_distance': 4500.0,
                'segment_count': 3,
                'turn_count': 2,
                'road_names': ['Primary Arterial']
            }
        }
    }


def test_export_to_geojson_compound_closure(sample_network, sample_accepted_detours):
    """Verifies GeoJSON export handles multi-link incident closures."""
    compound_closure = [(0, 1, 0), (1, 2, 0)]
    geojson_out = eu.export_to_geojson(
        sample_network,
        sample_accepted_detours,
        compound_closure,
        additional_data={},
        buffer_miles=0.5
    )

    assert isinstance(geojson_out, str)
    assert len(geojson_out) > 0

    parsed = json.loads(geojson_out)
    assert parsed['type'] == 'FeatureCollection'
    
    # Check that incident features exist and are labeled
    incident_features = [f for f in parsed['features'] if f['properties'].get('type') == 'incident_edge']
    assert len(incident_features) == 2


def test_export_to_kml_and_kmz_compound_closure(sample_network, sample_accepted_detours):
    """Verifies KML and KMZ export handles multi-link incident closures."""
    compound_closure = [(0, 1, 0), (1, 2, 0)]
    
    # Test KML (returns str)
    kml_out = eu.export_to_kml(
        sample_network,
        sample_accepted_detours,
        compound_closure,
        additional_data={},
        buffer_miles=0.5
    )
    assert isinstance(kml_out, str)
    assert '<kml' in kml_out
    assert 'Incident Closure #1' in kml_out
    assert 'Incident Closure #2' in kml_out

    # Test KMZ (returns bytes)
    kmz_bytes = eu.export_to_kmz(
        sample_network,
        sample_accepted_detours,
        compound_closure,
        additional_data={},
        buffer_miles=0.5
    )
    assert isinstance(kmz_bytes, bytes)
    with zipfile.ZipFile(io.BytesIO(kmz_bytes)) as zf:
        assert 'doc.kml' in zf.namelist()


def test_export_to_excel_and_csv_compound_closure(sample_network, sample_accepted_detours):
    """Verifies Excel and CSV exports handle multi-link incident closures."""
    compound_closure = [(0, 1, 0), (1, 2, 0)]

    # Test CSV (returns str)
    csv_out = eu.export_to_csv(
        sample_network,
        sample_accepted_detours,
        compound_closure,
        additional_data={},
        buffer_miles=0.5
    )
    assert isinstance(csv_out, str)
    assert 'Closed Segment 1' in csv_out or 'Incident Edge' in csv_out

    # Test Excel (returns bytes)
    excel_bytes = eu.export_to_excel(
        sample_network,
        sample_accepted_detours,
        compound_closure,
        additional_data={},
        buffer_miles=0.5
    )
    assert isinstance(excel_bytes, bytes)
    assert len(excel_bytes) > 0


def test_export_to_pdf_compound_closure(sample_network, sample_accepted_detours):
    """Verifies PDF report handles multi-link incident closures."""
    compound_closure = [(0, 1, 0), (1, 2, 0)]
    pdf_bytes = eu.export_to_pdf(
        sample_network,
        sample_accepted_detours,
        compound_closure,
        additional_data={},
        buffer_miles=0.5,
        include_maps=False
    )
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b'%PDF')

