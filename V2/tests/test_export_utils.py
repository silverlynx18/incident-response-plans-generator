"""
Unit tests for export_utils.py module.
Tests export functionality and data processing.
"""

import pytest
import json
import tempfile
import os
from datetime import datetime
import sys

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from export_utils import (
    create_export_data, PDFReportGenerator,
    GeospatialExporter, TabularExporter
)


class TestExportUtils:
    """Test cases for export_utils module."""

    def setup_method(self):
        """Set up test fixtures."""
        # Create sample session state data
        self.sample_session_state = {
            'selected_jurisdiction_name': 'Test County',
            'selected_jurisdiction_type': 'county',
            'selected_state_name': 'Test State',
            'selected_incident_edge': (1, 2),
            'incident_info': {
                'edge': (1, 2),
                'highway_type': 'primary',
                'name': 'Test Highway',
                'length': 1000
            },
            'detour_results': {
                (1, 3): (True, 120.5, 100.0, [1, 2, 3]),
                (1, 4): (True, 150.2, 120.0, [1, 2, 4]),
                (1, 5): (False, 'Too Short', 50.0, [1, 5])
            },
            'analysis_params': {
                'n_turn_nodes': 5,
                'sector_angle_deg': 180,
                'sector_radius_m': 3000,
                'min_travel_time_s': 90,
                'max_travel_time_s': 1800
            },
            'route_evaluations': {
                (1, 3): 'accepted',
                (1, 4): 'pending',
                (1, 5): 'rejected'
            },
            'turn_nodes': {
                'start_nodes': [1, 2],
                'end_nodes': [3, 4, 5]
            },
            'impacted_arterials': [(1, 2), (2, 3), (3, 4)]
        }

    def test_create_export_data(self):
        """Test create_export_data function."""
        export_data = create_export_data(self.sample_session_state)

        # Check required fields
        assert 'jurisdiction_name' in export_data
        assert 'jurisdiction_type' in export_data
        assert 'state_name' in export_data
        assert 'incident_info' in export_data
        assert 'detour_results' in export_data
        assert 'analysis_params' in export_data
        assert 'route_evaluations' in export_data

        # Check data integrity
        assert export_data['jurisdiction_name'] == 'Test County'
        assert export_data['jurisdiction_type'] == 'county'
        assert export_data['state_name'] == 'Test State'
        assert export_data['incident_info']['edge'] == (1, 2)
        assert len(export_data['detour_results']) == 3
        assert len(export_data['route_evaluations']) == 3

    def test_create_export_data_missing_fields(self):
        """Test create_export_data with missing fields."""
        incomplete_state = {
            'selected_jurisdiction_name': 'Test County'
            # Missing other required fields
        }

        export_data = create_export_data(incomplete_state)

        # Should handle missing fields gracefully
        assert 'jurisdiction_name' in export_data
        assert export_data['jurisdiction_name'] == 'Test County'
        assert export_data.get('jurisdiction_type') is None

    def test_pdf_report_generator_init(self):
        """Test PDFReportGenerator initialization."""
        export_data = create_export_data(self.sample_session_state)
        generator = PDFReportGenerator(export_data)

        assert generator.export_data == export_data
        assert generator.jurisdiction_name == 'Test County'
        assert generator.incident_info['edge'] == (1, 2)

    def test_pdf_report_generator_generate_report(self):
        """Test PDF report generation."""
        export_data = create_export_data(self.sample_session_state)
        generator = PDFReportGenerator(export_data)

        # Generate report
        pdf_data = generator.generate_report()

        # Check that PDF data is generated
        assert pdf_data is not None
        assert isinstance(pdf_data, bytes)
        assert len(pdf_data) > 0

        # Check PDF header
        assert pdf_data.startswith(b'%PDF')

    def test_geospatial_exporter_init(self):
        """Test GeospatialExporter initialization."""
        export_data = create_export_data(self.sample_session_state)
        exporter = GeospatialExporter(export_data)

        assert exporter.export_data == export_data
        assert exporter.jurisdiction_name == 'Test County'

    def test_geospatial_exporter_export_geojson(self):
        """Test GeoJSON export."""
        export_data = create_export_data(self.sample_session_state)
        exporter = GeospatialExporter(export_data)

        # Export GeoJSON
        geojson_data = exporter.export_geojson()

        # Check that GeoJSON data is generated
        assert geojson_data is not None
        assert isinstance(geojson_data, bytes)

        # Parse and validate GeoJSON
        geojson_dict = json.loads(geojson_data.decode('utf-8'))
        assert 'type' in geojson_dict
        assert geojson_dict['type'] == 'FeatureCollection'
        assert 'features' in geojson_dict

    def test_geospatial_exporter_export_kml(self):
        """Test KML export."""
        export_data = create_export_data(self.sample_session_state)
        exporter = GeospatialExporter(export_data)

        # Export KML
        kml_data = exporter.export_kml()

        # Check that KML data is generated
        assert kml_data is not None
        assert isinstance(kml_data, bytes)

        # Check KML structure
        kml_str = kml_data.decode('utf-8')
        assert '<?xml' in kml_str
        assert '<kml' in kml_str
        assert '</kml>' in kml_str

    def test_geospatial_exporter_export_shapefile(self):
        """Test Shapefile export."""
        export_data = create_export_data(self.sample_session_state)
        exporter = GeospatialExporter(export_data)

        # Export Shapefile
        shapefile_data = exporter.export_shapefile()

        # Check that Shapefile data is generated
        assert shapefile_data is not None
        assert isinstance(shapefile_data, bytes)

        # Check that it's a ZIP file
        assert shapefile_data.startswith(b'PK')  # ZIP file signature

    def test_geospatial_exporter_export_geopackage(self):
        """Test GeoPackage export."""
        export_data = create_export_data(self.sample_session_state)
        exporter = GeospatialExporter(export_data)

        # Export GeoPackage
        gpkg_data = exporter.export_geopackage()

        # Check that GeoPackage data is generated
        assert gpkg_data is not None
        assert isinstance(gpkg_data, bytes)
        assert len(gpkg_data) > 0

    def test_tabular_exporter_init(self):
        """Test TabularExporter initialization."""
        export_data = create_export_data(self.sample_session_state)
        exporter = TabularExporter(export_data)

        assert exporter.export_data == export_data
        assert exporter.jurisdiction_name == 'Test County'

    def test_tabular_exporter_export_csv(self):
        """Test CSV export."""
        export_data = create_export_data(self.sample_session_state)
        exporter = TabularExporter(export_data)

        # Export CSV
        csv_data = exporter.export_csv()

        # Check that CSV data is generated
        assert csv_data is not None
        assert isinstance(csv_data, bytes)

        # Check CSV structure
        csv_str = csv_data.decode('utf-8')
        assert ',' in csv_str  # Should contain commas
        assert 'Route' in csv_str  # Should contain route data

    def test_tabular_exporter_export_excel(self):
        """Test Excel export."""
        export_data = create_export_data(self.sample_session_state)
        exporter = TabularExporter(export_data)

        # Export Excel
        excel_data = exporter.export_excel()

        # Check that Excel data is generated
        assert excel_data is not None
        assert isinstance(excel_data, bytes)
        assert len(excel_data) > 0

        # Check Excel file signature
        assert excel_data.startswith(b'PK')  # Excel files are ZIP archives

    def test_export_with_no_detour_results(self):
        """Test export with no detour results."""
        empty_state = {
            'selected_jurisdiction_name': 'Test County',
            'selected_jurisdiction_type': 'county',
            'selected_state_name': 'Test State',
            'detour_results': {},
            'route_evaluations': {}
        }

        export_data = create_export_data(empty_state)

        # Test PDF export
        generator = PDFReportGenerator(export_data)
        pdf_data = generator.generate_report()
        assert pdf_data is not None

        # Test GeoJSON export
        exporter = GeospatialExporter(export_data)
        geojson_data = exporter.export_geojson()
        assert geojson_data is not None

        # Test CSV export
        tabular_exporter = TabularExporter(export_data)
        csv_data = tabular_exporter.export_csv()
        assert csv_data is not None

    def test_export_with_invalid_data(self):
        """Test export with invalid data."""
        invalid_state = {
            'selected_jurisdiction_name': None,
            'detour_results': 'invalid_data',
            'analysis_params': None
        }

        export_data = create_export_data(invalid_state)

        # Should handle invalid data gracefully
        assert export_data is not None
        assert export_data.get('jurisdiction_name') is None

        # Test that exports still work
        generator = PDFReportGenerator(export_data)
        pdf_data = generator.generate_report()
        assert pdf_data is not None


class TestExportUtilsIntegration:
    """Integration tests for export_utils module."""

    def setup_method(self):
        """Set up integration test fixtures."""
        # Create comprehensive test data
        self.comprehensive_state = {
            'selected_jurisdiction_name': 'Comprehensive County',
            'selected_jurisdiction_type': 'county',
            'selected_state_name': 'Comprehensive State',
            'selected_incident_edge': (100, 200),
            'incident_info': {
                'edge': (100, 200),
                'highway_type': 'motorway',
                'name': 'Comprehensive Highway',
                'ref': 'I-95',
                'length': 5000,
                'maxspeed': '65 mph'
            },
            'detour_results': {
                (100, 300): (True, 300.5, 250.0, [100, 150, 200, 250, 300]),
                (100, 400): (True, 450.2, 400.0, [100, 150, 200, 250, 300, 350, 400]),
                (100, 500): (True, 600.8, 550.0, [100, 150, 200, 250, 300, 350, 400, 450, 500]),
                (100, 600): (False, 'Too Long', 800.0, [100, 150, 200, 250, 300, 350, 400, 450, 500, 550, 600]),
                (100, 700): (False, 'No Route', 0.0, [])
            },
            'analysis_params': {
                'n_turn_nodes': 10,
                'sector_angle_deg': 270,
                'sector_radius_m': 5000,
                'min_travel_time_s': 120,
                'max_travel_time_s': 2400,
                'max_detour_routes': 20,
                'performance_mode': 'Complete'
            },
            'route_evaluations': {
                (100, 300): 'accepted',
                (100, 400): 'accepted',
                (100, 500): 'pending',
                (100, 600): 'rejected',
                (100, 700): 'rejected'
            },
            'turn_nodes': {
                'start_nodes': [100, 150, 200],
                'end_nodes': [300, 400, 500, 600, 700]
            },
            'impacted_arterials': [
                (100, 200), (200, 300), (300, 400),
                (400, 500), (500, 600), (600, 700)
            ],
            'analysis_timestamp': datetime.now().isoformat()
        }

    def test_comprehensive_export_workflow(self):
        """Test complete export workflow with all formats."""
        export_data = create_export_data(self.comprehensive_state)

        # Test all export formats
        formats_to_test = [
            ('PDF', PDFReportGenerator),
            ('GeoJSON', GeospatialExporter),
            ('KML', GeospatialExporter),
            ('Shapefile', GeospatialExporter),
            ('GeoPackage', GeospatialExporter),
            ('CSV', TabularExporter),
            ('Excel', TabularExporter)
        ]

        for format_name, exporter_class in formats_to_test:
            exporter = exporter_class(export_data)

            if format_name == 'PDF':
                result = exporter.generate_report()
            elif format_name == 'GeoJSON':
                result = exporter.export_geojson()
            elif format_name == 'KML':
                result = exporter.export_kml()
            elif format_name == 'Shapefile':
                result = exporter.export_shapefile()
            elif format_name == 'GeoPackage':
                result = exporter.export_geopackage()
            elif format_name == 'CSV':
                result = exporter.export_csv()
            elif format_name == 'Excel':
                result = exporter.export_excel()

            # Verify export was successful
            assert result is not None, f"{format_name} export failed"
            assert isinstance(result, bytes), f"{format_name} export should return bytes"
            assert len(result) > 0, f"{format_name} export should not be empty"

    def test_export_data_consistency(self):
        """Test that export data is consistent across formats."""
        export_data = create_export_data(self.comprehensive_state)

        # Test that key data is preserved
        assert export_data['jurisdiction_name'] == 'Comprehensive County'
        assert export_data['incident_info']['edge'] == (100, 200)
        assert len(export_data['detour_results']) == 5
        assert len(export_data['route_evaluations']) == 5

        # Test that accepted routes are correctly identified
        accepted_routes = [
            route for route, status in export_data['route_evaluations'].items()
            if status == 'accepted'
        ]
        assert len(accepted_routes) == 2
        assert (100, 300) in accepted_routes
        assert (100, 400) in accepted_routes

    def test_export_performance(self):
        """Test export performance with large datasets."""
        # Create large dataset
        large_state = self.comprehensive_state.copy()
        large_detour_results = {}

        # Add 100 detour routes
        for i in range(100):
            route_key = (100, 300 + i)
            large_detour_results[route_key] = (
                True, 300.0 + i, 250.0 + i,
                list(range(100, 300 + i, 10))
            )

        large_state['detour_results'] = large_detour_results
        export_data = create_export_data(large_state)

        # Test performance
        import time

        # Test PDF export performance
        start_time = time.time()
        generator = PDFReportGenerator(export_data)
        pdf_data = generator.generate_report()
        pdf_time = time.time() - start_time

        assert pdf_data is not None
        assert pdf_time < 10.0  # Should complete in under 10 seconds

        # Test CSV export performance
        start_time = time.time()
        exporter = TabularExporter(export_data)
        csv_data = exporter.export_csv()
        csv_time = time.time() - start_time

        assert csv_data is not None
        assert csv_time < 5.0  # Should complete in under 5 seconds


if __name__ == '__main__':
    pytest.main([__file__])
