"""
Export utilities for ARPL V2 (Automated Route Planning & Logistics).
Enhanced with session metadata, batch export, and export history tracking.
"""

import io
import json
import zipfile
import tempfile
import os
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, LineString
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.backends.backend_pdf import PdfPages
import networkx as nx
import folium
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics import renderPDF
import base64

# V2 Imports
from database import DatabaseManager


class ARPLExporter:
    """Main export class for ARPL V2 analysis results with enhanced features."""

    def __init__(self, analysis_data: Dict[str, Any], db_manager: Optional[DatabaseManager] = None):
        """
        Initialize exporter with analysis data and optional database manager.

        Args:
            analysis_data: Dictionary containing all analysis results and metadata
            db_manager: Optional database manager for export history tracking
        """
        self.analysis_data = analysis_data
        self.db_manager = db_manager
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Setup custom paragraph styles for reports."""
        # Title style
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Title'],
            fontSize=24,
            spaceAfter=30,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#E61E28')
        ))

        # Heading styles
        self.styles.add(ParagraphStyle(
            name='CustomHeading1',
            parent=self.styles['Heading1'],
            fontSize=18,
            spaceAfter=12,
            textColor=colors.HexColor('#E61E28')
        ))

        self.styles.add(ParagraphStyle(
            name='CustomHeading2',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceAfter=8,
            textColor=colors.HexColor('#333333')
        ))

        # Body text style
        self.styles.add(ParagraphStyle(
            name='CustomBody',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=6,
            alignment=TA_LEFT
        ))

    def _record_export_history(self, export_format: str, file_size: int = 0):
        """Record export in database history if db_manager is available."""
        if self.db_manager:
            try:
                # This would require an export_history table
                # For now, we'll use the analysis_history table
                from analysis_history import AnalysisHistory
                history = AnalysisHistory(self.db_manager)

                # Record as a special analysis type
                history.record_analysis(
                    jurisdiction=f"Export_{export_format}",
                    total_routes=0,
                    valid_routes=0,
                    parameters={
                        'export_format': export_format,
                        'file_size_bytes': file_size,
                        'session_id': self.analysis_data.get('metadata', {}).get('session_id'),
                        'export_timestamp': datetime.utcnow().isoformat()
                    }
                )
            except Exception as e:
                print(f"Error recording export history: {e}")


class PDFReportGenerator(ARPLExporter):
    """Generate comprehensive PDF reports for detour analysis with V2 enhancements."""

    def generate_report(self, output_path: str = None) -> bytes:
        """
        Generate a comprehensive PDF report with V2 enhancements.

        Args:
            output_path: Optional path to save the PDF file

        Returns:
            PDF content as bytes
        """
        if output_path is None:
            output_path = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False).name

        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=18
        )

        # Build the story (content)
        story = []

        # Title page
        story.extend(self._create_title_page())
        story.append(PageBreak())

        # Executive summary
        story.extend(self._create_executive_summary())
        story.append(PageBreak())

        # Analysis details
        story.extend(self._create_analysis_details())
        story.append(PageBreak())

        # Route analysis
        story.extend(self._create_route_analysis())
        story.append(PageBreak())

        # V2 Enhancement: Session information
        story.extend(self._create_session_info())
        story.append(PageBreak())

        # Visualizations
        story.extend(self._create_visualizations())
        story.append(PageBreak())

        # Recommendations
        story.extend(self._create_recommendations())

        # Build PDF
        doc.build(story)

        # Read and return content
        with open(output_path, 'rb') as f:
            content = f.read()

        # Record export history
        self._record_export_history('PDF', len(content))

        # Clean up temporary file
        if output_path.startswith('/tmp'):
            os.unlink(output_path)

        return content

    def _create_title_page(self) -> List:
        """Create the title page with V2 enhancements."""
        story = []

        # Main title
        story.append(Paragraph("ARPL V2 Traffic Detour Analysis Report", self.styles['CustomTitle']))
        story.append(Spacer(1, 20))

        # Analysis metadata
        metadata = self.analysis_data.get('metadata', {})
        jurisdiction = metadata.get('jurisdiction', 'Unknown')
        incident_edge = metadata.get('incident_edge', 'Unknown')
        analysis_date = metadata.get('analysis_date', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        session_id = metadata.get('session_id', 'N/A')

        # Metadata table
        metadata_data = [
            ['Analysis Date:', analysis_date],
            ['Jurisdiction:', jurisdiction],
            ['Incident Edge:', str(incident_edge)],
            ['Session ID:', str(session_id)],
            ['Generated By:', 'ARPL v2.0']
        ]

        metadata_table = Table(metadata_data, colWidths=[2*inch, 4*inch])
        metadata_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ]))

        story.append(metadata_table)
        story.append(Spacer(1, 30))

        # Summary statistics
        detour_results = self.analysis_data.get('detour_results', {})
        valid_detours = {k: v for k, v in detour_results.items() if v[0]}

        summary_data = [
            ['Total Detours Found:', str(len(detour_results))],
            ['Valid Detours:', str(len(valid_detours))],
            ['Success Rate:', f"{(len(valid_detours)/len(detour_results)*100):.1f}%" if detour_results else "0%"],
            ['Analysis Parameters:', 'See detailed analysis section']
        ]

        summary_table = Table(summary_data, colWidths=[2*inch, 4*inch])
        summary_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ]))

        story.append(summary_table)

        return story

    def _create_session_info(self) -> List:
        """Create session information section (V2 enhancement)."""
        story = []

        story.append(Paragraph("Session Information", self.styles['CustomHeading1']))
        story.append(Spacer(1, 12))

        metadata = self.analysis_data.get('metadata', {})
        session_id = metadata.get('session_id')

        if session_id:
            story.append(Paragraph("This analysis was saved as part of a session for future reference.", self.styles['CustomBody']))
            story.append(Paragraph(f"Session ID: {session_id}", self.styles['CustomBody']))
        else:
            story.append(Paragraph("This analysis was not saved as part of a session.", self.styles['CustomBody']))

        # Data sources information
        story.append(Paragraph("Data Sources", self.styles['CustomHeading2']))
        data_sources = self.analysis_data.get('data_sources', {})

        source_data = [
            ['Jurisdiction Data:', data_sources.get('jurisdiction_data', 'Unknown')],
            ['TIGER Data Year:', data_sources.get('tiger_year', 'Unknown')],
            ['OSM Data Date:', data_sources.get('osm_data_date', 'Unknown')]
        ]

        source_table = Table(source_data, colWidths=[2*inch, 4*inch])
        source_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))

        story.append(source_table)

        return story

    # Keep all other methods from V1.5 (they remain unchanged)
    def _create_executive_summary(self) -> List:
        """Create executive summary section."""
        story = []

        story.append(Paragraph("Executive Summary", self.styles['CustomHeading1']))
        story.append(Spacer(1, 12))

        # Get analysis data
        detour_results = self.analysis_data.get('detour_results', {})
        valid_detours = {k: v for k, v in detour_results.items() if v[0]}
        metadata = self.analysis_data.get('metadata', {})

        # Key findings
        story.append(Paragraph("Key Findings", self.styles['CustomHeading2']))

        findings = [
            f"• Analysis conducted for {metadata.get('jurisdiction', 'selected area')}",
            f"• {len(detour_results)} total detour routes identified",
            f"• {len(valid_detours)} routes meet specified time criteria",
        ]

        if valid_detours:
            # Calculate average metrics
            total_times = [v[1] for v in valid_detours.values() if isinstance(v[1], (int, float))]
            if total_times:
                avg_time = sum(total_times) / len(total_times)
                findings.append(f"• Average detour travel time: {avg_time/60:.1f} minutes")

        for finding in findings:
            story.append(Paragraph(finding, self.styles['CustomBody']))

        story.append(Spacer(1, 12))

        # Recommendations
        story.append(Paragraph("Immediate Recommendations", self.styles['CustomHeading2']))

        recommendations = [
            "• Review all valid detour routes for feasibility and safety",
            "• Consider traffic signal timing adjustments for detour routes",
            "• Coordinate with emergency services for incident response",
            "• Monitor detour route performance during implementation"
        ]

        for rec in recommendations:
            story.append(Paragraph(rec, self.styles['CustomBody']))

        return story

    def _create_analysis_details(self) -> List:
        """Create analysis details section."""
        story = []

        story.append(Paragraph("Analysis Details", self.styles['CustomHeading1']))
        story.append(Spacer(1, 12))

        # Analysis parameters
        story.append(Paragraph("Analysis Parameters", self.styles['CustomHeading2']))

        params = self.analysis_data.get('analysis_params', {})
        param_data = [
            ['Parameter', 'Value'],
            ['Number of Turn Nodes', str(params.get('n_turn_nodes', 'N/A'))],
            ['Sector Angle (degrees)', str(params.get('sector_angle_deg', 'N/A'))],
            ['Sector Radius (miles)', str(params.get('sector_radius_miles', 'N/A'))],
            ['Minimum Travel Time (seconds)', str(params.get('min_travel_time_s', 'N/A'))],
            ['Maximum Travel Time (seconds)', str(params.get('max_travel_time_s', 'N/A'))],
            ['Maximum Detour Routes', str(params.get('max_detour_routes', 'N/A'))]
        ]

        param_table = Table(param_data, colWidths=[3*inch, 2*inch])
        param_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))

        story.append(param_table)
        story.append(Spacer(1, 12))

        # Network information
        story.append(Paragraph("Network Information", self.styles['CustomHeading2']))

        network_info = self.analysis_data.get('network_info', {})
        network_data = [
            ['Network Nodes:', str(network_info.get('nodes', 'N/A'))],
            ['Network Edges:', str(network_info.get('edges', 'N/A'))],
            ['Analysis Generation Time:', f"{self.analysis_data.get('generation_time', 0):.2f} seconds"]
        ]

        for info in network_data:
            story.append(Paragraph(info, self.styles['CustomBody']))

        return story

    def _create_route_analysis(self) -> List:
        """Create route analysis section."""
        story = []

        story.append(Paragraph("Route Analysis", self.styles['CustomHeading1']))
        story.append(Spacer(1, 12))

        detour_results = self.analysis_data.get('detour_results', {})
        valid_detours = {k: v for k, v in detour_results.items() if v[0]}

        if not valid_detours:
            story.append(Paragraph("No valid detour routes found meeting the specified criteria.", self.styles['CustomBody']))
            return story

        # Route summary table
        story.append(Paragraph("Detour Route Summary", self.styles['CustomHeading2']))

        route_data = [['Route ID', 'Start Node', 'End Node', 'Total Time (min)', 'Freeflow Time (min)', 'Status']]

        for i, ((start, end), (valid, total, freeflow, path)) in enumerate(valid_detours.items()):
            route_data.append([
                f"Route {i+1}",
                str(start),
                str(end),
                f"{total/60:.1f}" if isinstance(total, (int, float)) else str(total),
                f"{freeflow/60:.1f}" if isinstance(freeflow, (int, float)) else str(freeflow),
                "Valid" if valid else "Invalid"
            ])

        route_table = Table(route_data, colWidths=[0.8*inch, 1*inch, 1*inch, 1.2*inch, 1.2*inch, 1*inch])
        route_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))

        story.append(route_table)

        return story

    def _create_visualizations(self) -> List:
        """Create visualizations section."""
        story = []

        story.append(Paragraph("Visualizations", self.styles['CustomHeading1']))
        story.append(Spacer(1, 12))

        detour_results = self.analysis_data.get('detour_results', {})
        valid_detours = {k: v for k, v in detour_results.items() if v[0]}

        if valid_detours:
            # Create travel time comparison chart
            story.append(Paragraph("Travel Time Comparison", self.styles['CustomHeading2']))

            # Extract travel times for chart
            travel_times = []
            route_labels = []
            for i, ((start, end), (valid, total, freeflow, path)) in enumerate(valid_detours.items()):
                if isinstance(total, (int, float)):
                    travel_times.append(total / 60)  # Convert to minutes
                    route_labels.append(f"Route {i+1}")

            if travel_times:
                # Create bar chart
                chart = self._create_travel_time_chart(travel_times, route_labels)
                story.append(chart)
                story.append(Spacer(1, 12))

            # Create road type breakdown chart
            story.append(Paragraph("Road Type Distribution", self.styles['CustomHeading2']))
            road_type_chart = self._create_road_type_chart(valid_detours)
            if road_type_chart:
                story.append(road_type_chart)
                story.append(Spacer(1, 12))

            # Add route efficiency metrics
            story.append(Paragraph("Route Efficiency Metrics", self.styles['CustomHeading2']))
            efficiency_table = self._create_efficiency_table(valid_detours)
            story.append(efficiency_table)

        else:
            story.append(Paragraph("No valid detour routes available for visualization.", self.styles['CustomBody']))

        return story

    def _create_travel_time_chart(self, travel_times: List[float], route_labels: List[str]) -> Drawing:
        """Create a bar chart showing travel time comparison."""
        drawing = Drawing(400, 200)

        # Create bar chart
        chart = VerticalBarChart()
        chart.x = 50
        chart.y = 50
        chart.height = 125
        chart.width = 300
        chart.data = [travel_times]
        chart.categoryAxis.categoryNames = route_labels[:10]  # Limit to 10 routes
        chart.valueAxis.valueMin = 0
        chart.valueAxis.valueMax = max(travel_times) * 1.1 if travel_times else 10

        # Style the chart
        chart.bars[0].fillColor = colors.HexColor('#E61E28')
        chart.bars[0].strokeColor = colors.black
        chart.bars[0].strokeWidth = 1

        drawing.add(chart)
        return drawing

    def _create_road_type_chart(self, valid_detours: Dict) -> Optional[Drawing]:
        """Create a pie chart showing road type distribution."""
        # Count road types across all routes
        road_type_counts = {}

        for (start, end), (valid, total, freeflow, path) in valid_detours.items():
            if path and self.analysis_data.get('graph'):
                graph = self.analysis_data['graph']
                for i in range(len(path) - 1):
                    edge = (path[i], path[i+1])
                    if graph.has_edge(*edge):
                        highway_type = graph.edges[edge].get('highway', 'unknown')
                        if isinstance(highway_type, list):
                            highway_type = highway_type[0]
                        road_type_counts[highway_type] = road_type_counts.get(highway_type, 0) + 1

        if not road_type_counts:
            return None

        # Create pie chart
        drawing = Drawing(200, 200)
        pie = Pie()
        pie.x = 25
        pie.y = 25
        pie.width = 150
        pie.height = 150

        # Prepare data
        labels = list(road_type_counts.keys())[:8]  # Limit to 8 types
        data = [road_type_counts[label] for label in labels]

        pie.data = data
        pie.labels = labels
        pie.slices.strokeWidth = 0.5
        pie.slices.strokeColor = colors.white

        # Color the slices
        colors_list = [colors.HexColor('#E61E28'), colors.HexColor('#FF6B6B'),
                      colors.HexColor('#4ECDC4'), colors.HexColor('#45B7D1'),
                      colors.HexColor('#96CEB4'), colors.HexColor('#FFEAA7'),
                      colors.HexColor('#DDA0DD'), colors.HexColor('#98D8C8')]

        for i, color in enumerate(colors_list[:len(pie.slices)]):
            pie.slices[i].fillColor = color

        drawing.add(pie)
        return drawing

    def _create_efficiency_table(self, valid_detours: Dict) -> Table:
        """Create a table showing route efficiency metrics."""
        table_data = [['Route', 'Total Time (min)', 'Freeflow Time (min)', 'Efficiency %', 'Nodes']]

        for i, ((start, end), (valid, total, freeflow, path)) in enumerate(valid_detours.items()):
            if isinstance(total, (int, float)) and isinstance(freeflow, (int, float)) and freeflow > 0:
                efficiency = (freeflow / total) * 100
                node_count = len(path) if path else 0

                table_data.append([
                    f"Route {i+1}",
                    f"{total/60:.1f}",
                    f"{freeflow/60:.1f}",
                    f"{efficiency:.1f}%",
                    str(node_count)
                ])

        table = Table(table_data, colWidths=[1*inch, 1.2*inch, 1.2*inch, 1*inch, 0.8*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))

        return table

    def _create_recommendations(self) -> List:
        """Create recommendations section."""
        story = []

        story.append(Paragraph("Recommendations and Conclusions", self.styles['CustomHeading1']))
        story.append(Spacer(1, 12))

        detour_results = self.analysis_data.get('detour_results', {})
        valid_detours = {k: v for k, v in detour_results.items() if v[0]}

        story.append(Paragraph("Implementation Recommendations", self.styles['CustomHeading2']))

        if valid_detours:
            recommendations = [
                "• Prioritize detour routes with shortest travel times for immediate implementation",
                "• Consider multiple detour options to distribute traffic load",
                "• Implement temporary traffic control measures at key intersections",
                "• Coordinate with local law enforcement for traffic management",
                "• Monitor detour performance and adjust as needed"
            ]
        else:
            recommendations = [
                "• No suitable detour routes found with current parameters",
                "• Consider adjusting analysis parameters (time limits, search radius)",
                "• Evaluate alternative incident response strategies",
                "• Consider partial road closures or lane restrictions instead"
            ]

        for rec in recommendations:
            story.append(Paragraph(rec, self.styles['CustomBody']))

        story.append(Spacer(1, 12))

        story.append(Paragraph("Next Steps", self.styles['CustomHeading2']))

        next_steps = [
            "• Review and validate recommended detour routes",
            "• Coordinate with relevant transportation agencies",
            "• Develop implementation timeline and resource requirements",
            "• Establish monitoring and evaluation procedures",
            "• Prepare public communication materials"
        ]

        for step in next_steps:
            story.append(Paragraph(step, self.styles['CustomBody']))

        return story


class GeospatialExporter(ARPLExporter):
    """Handle geospatial data exports (GeoJSON, KML, Shapefile) with V2 enhancements."""

    def export_geojson(self) -> str:
        """Export detour routes as GeoJSON with V2 enhancements."""
        features = []
        detour_results = self.analysis_data.get('detour_results', {})
        graph = self.analysis_data.get('graph')
        metadata = self.analysis_data.get('metadata', {})

        if not graph:
            return json.dumps({"type": "FeatureCollection", "features": []})

        for (start, end), (valid, total, freeflow, path) in detour_results.items():
            if valid and path:
                # Create LineString from path
                coords = []
                for node in path:
                    if node in graph.nodes:
                        coords.append([graph.nodes[node]['x'], graph.nodes[node]['y']])

                if len(coords) > 1:
                    feature = {
                        "type": "Feature",
                        "properties": {
                            "start_node": start,
                            "end_node": end,
                            "total_time_min": total/60 if isinstance(total, (int, float)) else 0,
                            "freeflow_time_min": freeflow/60 if isinstance(freeflow, (int, float)) else 0,
                            "route_id": f"{start}_{end}",
                            "status": "valid" if valid else "invalid",
                            "session_id": metadata.get('session_id'),
                            "jurisdiction": metadata.get('jurisdiction'),
                            "analysis_date": metadata.get('analysis_date')
                        },
                        "geometry": {
                            "type": "LineString",
                            "coordinates": coords
                        }
                    }
                    features.append(feature)

        # Add incident point
        incident_edge = metadata.get('incident_edge')
        if incident_edge and graph and graph.has_edge(*incident_edge):
            incident_geom = graph.edges[incident_edge].get('geometry')
            if incident_geom:
                center = incident_geom.centroid
                incident_feature = {
                    "type": "Feature",
                    "properties": {
                        "type": "incident",
                        "edge_id": str(incident_edge),
                        "session_id": metadata.get('session_id')
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": [center.x, center.y]
                    }
                }
                features.append(incident_feature)

        geojson_data = {
            "type": "FeatureCollection",
            "features": features,
            "properties": {
                "generated_by": "ARPL v2.0",
                "generation_date": datetime.now().isoformat(),
                "total_features": len(features),
                "session_id": metadata.get('session_id'),
                "jurisdiction": metadata.get('jurisdiction')
            }
        }

        result = json.dumps(geojson_data, indent=2)
        self._record_export_history('GeoJSON', len(result.encode('utf-8')))
        return result

    def export_kml(self) -> str:
        """Export detour routes as KML with V2 enhancements."""
        detour_results = self.analysis_data.get('detour_results', {})
        graph = self.analysis_data.get('graph')
        metadata = self.analysis_data.get('metadata', {})

        # Start KML document
        kml_content = ['<?xml version="1.0" encoding="UTF-8"?>']
        kml_content.append('<kml xmlns="http://www.opengis.net/kml/2.2">')
        kml_content.append('  <Document>')
        kml_content.append('    <name>ARPL V2 Detour Analysis</name>')
        kml_content.append('    <description>Traffic detour routes generated by ARPL v2.0</description>')

        # Add session metadata
        if metadata.get('session_id'):
            kml_content.append(f'    <ExtendedData>')
            kml_content.append(f'      <Data name="session_id">')
            kml_content.append(f'        <value>{metadata.get("session_id")}</value>')
            kml_content.append(f'      </Data>')
            kml_content.append(f'      <Data name="jurisdiction">')
            kml_content.append(f'        <value>{metadata.get("jurisdiction")}</value>')
            kml_content.append(f'      </Data>')
            kml_content.append(f'    </ExtendedData>')

        # Add incident point
        incident_edge = metadata.get('incident_edge')
        if incident_edge and graph and graph.has_edge(*incident_edge):
            incident_geom = graph.edges[incident_edge].get('geometry')
            if incident_geom:
                center = incident_geom.centroid
                kml_content.append('    <Placemark>')
                kml_content.append('      <name>Incident Location</name>')
                kml_content.append('      <description>Road closure incident point</description>')
                kml_content.append('      <styleUrl>#incidentStyle</styleUrl>')
                kml_content.append('      <Point>')
                kml_content.append(f'        <coordinates>{center.x},{center.y},0</coordinates>')
                kml_content.append('      </Point>')
                kml_content.append('    </Placemark>')

        # Add detour routes
        route_count = 0
        for (start, end), (valid, total, freeflow, path) in detour_results.items():
            if valid and path and graph:
                route_count += 1
                coords = []
                for node in path:
                    if node in graph.nodes:
                        coords.append(f"{graph.nodes[node]['x']},{graph.nodes[node]['y']},0")

                if len(coords) > 1:
                    kml_content.append('    <Placemark>')
                    kml_content.append(f'      <name>Detour Route {route_count}</name>')
                    kml_content.append(f'      <description>')
                    kml_content.append(f'        Start: {start}<br/>')
                    kml_content.append(f'        End: {end}<br/>')
                    kml_content.append(f'        Total Time: {total/60:.1f} minutes<br/>')
                    kml_content.append(f'        Freeflow Time: {freeflow/60:.1f} minutes<br/>')
                    kml_content.append(f'        Status: Valid<br/>')
                    if metadata.get('session_id'):
                        kml_content.append(f'        Session ID: {metadata.get("session_id")}<br/>')
                    kml_content.append(f'      </description>')
                    kml_content.append(f'      <styleUrl>#routeStyle{route_count % 5 + 1}</styleUrl>')
                    kml_content.append('      <LineString>')
                    kml_content.append('        <tessellate>1</tessellate>')
                    kml_content.append(f'        <coordinates>{" ".join(coords)}</coordinates>')
                    kml_content.append('      </LineString>')
                    kml_content.append('    </Placemark>')

        # Add styles
        kml_content.append('    <Style id="incidentStyle">')
        kml_content.append('      <IconStyle>')
        kml_content.append('        <color>ff0000ff</color>')
        kml_content.append('        <scale>1.2</scale>')
        kml_content.append('        <Icon>')
        kml_content.append('          <href>http://maps.google.com/mapfiles/kml/shapes/road_shield3.png</href>')
        kml_content.append('        </Icon>')
        kml_content.append('      </IconStyle>')
        kml_content.append('    </Style>')

        # Add route styles with different colors
        route_colors = ['ff0000ff', 'ff00ff00', 'ffff0000', 'ff00ffff', 'ffff00ff']
        for i, color in enumerate(route_colors):
            kml_content.append(f'    <Style id="routeStyle{i+1}">')
            kml_content.append('      <LineStyle>')
            kml_content.append(f'        <color>{color}</color>')
            kml_content.append('        <width>3</width>')
            kml_content.append('      </LineStyle>')
            kml_content.append('    </Style>')

        kml_content.append('  </Document>')
        kml_content.append('</kml>')

        result = '\n'.join(kml_content)
        self._record_export_history('KML', len(result.encode('utf-8')))
        return result

    def export_shapefile(self) -> bytes:
        """Export detour routes as Shapefile (ZIP) with V2 enhancements."""
        # Create temporary directory for shapefile components
        with tempfile.TemporaryDirectory() as temp_dir:
            detour_results = self.analysis_data.get('detour_results', {})
            graph = self.analysis_data.get('graph')
            metadata = self.analysis_data.get('metadata', {})

            if not graph:
                return b''

            # Create GeoDataFrame for detour routes
            routes_data = []
            for (start, end), (valid, total, freeflow, path) in detour_results.items():
                if valid and path:
                    coords = []
                    for node in path:
                        if node in graph.nodes:
                            coords.append([graph.nodes[node]['x'], graph.nodes[node]['y']])

                    if len(coords) > 1:
                        route_data = {
                            'geometry': LineString(coords),
                            'start_node': start,
                            'end_node': end,
                            'total_time': total/60 if isinstance(total, (int, float)) else 0,
                            'freeflow_time': freeflow/60 if isinstance(freeflow, (int, float)) else 0,
                            'route_id': f"{start}_{end}",
                            'status': 'valid',
                            'session_id': metadata.get('session_id', ''),
                            'jurisdiction': metadata.get('jurisdiction', ''),
                            'analysis_date': metadata.get('analysis_date', '')
                        }
                        routes_data.append(route_data)

            if routes_data:
                gdf = gpd.GeoDataFrame(routes_data, crs='EPSG:4326')
                shapefile_path = os.path.join(temp_dir, 'detour_routes.shp')
                gdf.to_file(shapefile_path)

                # Create ZIP file
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    for file in os.listdir(temp_dir):
                        if file.startswith('detour_routes'):
                            zip_file.write(os.path.join(temp_dir, file), file)

                result = zip_buffer.getvalue()
                self._record_export_history('Shapefile', len(result))
                return result

        return b''

    def export_geopackage(self) -> bytes:
        """Export detour routes as GeoPackage with V2 enhancements."""
        detour_results = self.analysis_data.get('detour_results', {})
        graph = self.analysis_data.get('graph')
        metadata = self.analysis_data.get('metadata', {})

        if not graph:
            return b''

        # Create GeoDataFrame for detour routes
        routes_data = []
        for (start, end), (valid, total, freeflow, path) in detour_results.items():
            if valid and path:
                coords = []
                for node in path:
                    if node in graph.nodes:
                        coords.append([graph.nodes[node]['x'], graph.nodes[node]['y']])

                if len(coords) > 1:
                    route_data = {
                        'geometry': LineString(coords),
                        'start_node': start,
                        'end_node': end,
                        'total_time': total/60 if isinstance(total, (int, float)) else 0,
                        'freeflow_time': freeflow/60 if isinstance(freeflow, (int, float)) else 0,
                        'route_id': f"{start}_{end}",
                        'status': 'valid',
                        'node_count': len(path),
                        'session_id': metadata.get('session_id', ''),
                        'jurisdiction': metadata.get('jurisdiction', ''),
                        'analysis_date': metadata.get('analysis_date', '')
                    }
                    routes_data.append(route_data)

        if routes_data:
            gdf = gpd.GeoDataFrame(routes_data, crs='EPSG:4326')

            # Create GeoPackage in memory
            gpkg_buffer = io.BytesIO()
            gdf.to_file(gpkg_buffer, driver='GPKG', layer='detour_routes')
            result = gpkg_buffer.getvalue()
            self._record_export_history('GeoPackage', len(result))
            return result

        return b''


class TabularExporter(ARPLExporter):
    """Handle tabular data exports (CSV, Excel) with V2 enhancements."""

    def export_csv(self) -> str:
        """Export detour analysis as CSV with V2 enhancements."""
        detour_results = self.analysis_data.get('detour_results', {})
        metadata = self.analysis_data.get('metadata', {})

        # Create comprehensive CSV data
        csv_data = []

        # Add metadata
        csv_data.append(['Analysis Metadata', ''])
        csv_data.append(['Jurisdiction', metadata.get('jurisdiction', 'Unknown')])
        csv_data.append(['Analysis Date', metadata.get('analysis_date', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))])
        csv_data.append(['Incident Edge', str(metadata.get('incident_edge', 'Unknown'))])
        csv_data.append(['Session ID', str(metadata.get('session_id', 'N/A'))])
        csv_data.append(['', ''])

        # Add analysis parameters
        csv_data.append(['Analysis Parameters', ''])
        params = self.analysis_data.get('analysis_params', {})
        for param, value in params.items():
            csv_data.append([param.replace('_', ' ').title(), str(value)])
        csv_data.append(['', ''])

        # Add detour results
        csv_data.append(['Detour Route Results', ''])
        csv_data.append(['Route ID', 'Start Node', 'End Node', 'Valid', 'Total Time (min)', 'Freeflow Time (min)', 'Status'])

        for i, ((start, end), (valid, total, freeflow, path)) in enumerate(detour_results.items()):
            status = "Valid" if valid else "Invalid"
            if not valid:
                status = str(total) if isinstance(total, str) else status

            csv_data.append([
                f"Route_{i+1}",
                str(start),
                str(end),
                str(valid),
                f"{total/60:.2f}" if isinstance(total, (int, float)) else str(total),
                f"{freeflow/60:.2f}" if isinstance(freeflow, (int, float)) else str(freeflow),
                status
            ])

        # Convert to CSV string
        csv_string = io.StringIO()
        for row in csv_data:
            csv_string.write(','.join(f'"{str(cell)}"' for cell in row) + '\n')

        result = csv_string.getvalue()
        self._record_export_history('CSV', len(result.encode('utf-8')))
        return result

    def export_excel(self) -> bytes:
        """Export detour analysis as Excel workbook with V2 enhancements."""
        detour_results = self.analysis_data.get('detour_results', {})
        metadata = self.analysis_data.get('metadata', {})
        params = self.analysis_data.get('analysis_params', {})
        graph = self.analysis_data.get('graph')

        # Create Excel file in memory
        excel_buffer = io.BytesIO()

        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            # Summary sheet
            valid_routes = [v for v in detour_results.values() if v[0]]
            summary_data = {
                'Metric': [
                    'Jurisdiction',
                    'Analysis Date',
                    'Incident Edge',
                    'Session ID',
                    'Total Routes Found',
                    'Valid Routes',
                    'Success Rate (%)',
                    'Network Nodes',
                    'Network Edges',
                    'Generation Time (seconds)'
                ],
                'Value': [
                    metadata.get('jurisdiction', 'Unknown'),
                    metadata.get('analysis_date', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                    str(metadata.get('incident_edge', 'Unknown')),
                    str(metadata.get('session_id', 'N/A')),
                    len(detour_results),
                    len(valid_routes),
                    f"{(len(valid_routes)/len(detour_results)*100):.1f}" if detour_results else "0.0",
                    len(graph.nodes()) if graph else 0,
                    len(graph.edges()) if graph else 0,
                    f"{self.analysis_data.get('generation_time', 0):.2f}"
                ]
            }
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='Summary', index=False)

            # Parameters sheet
            params_df = pd.DataFrame(list(params.items()), columns=['Parameter', 'Value'])
            params_df.to_excel(writer, sheet_name='Parameters', index=False)

            # Routes sheet with detailed metrics
            routes_data = []
            for i, ((start, end), (valid, total, freeflow, path)) in enumerate(detour_results.items()):
                efficiency = (freeflow / total * 100) if isinstance(total, (int, float)) and isinstance(freeflow, (int, float)) and total > 0 else 0
                routes_data.append({
                    'Route_ID': f"Route_{i+1}",
                    'Start_Node': start,
                    'End_Node': end,
                    'Valid': valid,
                    'Total_Time_Min': total/60 if isinstance(total, (int, float)) else 0,
                    'Freeflow_Time_Min': freeflow/60 if isinstance(freeflow, (int, float)) else 0,
                    'Efficiency_Percent': efficiency,
                    'Node_Count': len(path) if path else 0,
                    'Status': "Valid" if valid else str(total) if isinstance(total, str) else "Invalid",
                    'Session_ID': metadata.get('session_id', ''),
                    'Jurisdiction': metadata.get('jurisdiction', '')
                })

            routes_df = pd.DataFrame(routes_data)
            routes_df.to_excel(writer, sheet_name='Routes', index=False)

            # Road Types sheet
            if graph and valid_routes:
                road_type_data = self._analyze_road_types(valid_routes, graph)
                if road_type_data:
                    road_types_df = pd.DataFrame(road_type_data)
                    road_types_df.to_excel(writer, sheet_name='Road_Types', index=False)

            # Performance Metrics sheet
            if valid_routes:
                performance_data = self._calculate_performance_metrics(valid_routes)
                performance_df = pd.DataFrame(performance_data)
                performance_df.to_excel(writer, sheet_name='Performance', index=False)

        result = excel_buffer.getvalue()
        self._record_export_history('Excel', len(result))
        return result

    def _analyze_road_types(self, valid_routes: List, graph) -> List[Dict]:
        """Analyze road type usage across all valid routes."""
        road_type_counts = {}
        road_type_lengths = {}

        for (start, end), (valid, total, freeflow, path) in valid_routes:
            if path:
                for i in range(len(path) - 1):
                    edge = (path[i], path[i+1])
                    if graph.has_edge(*edge):
                        highway_type = graph.edges[edge].get('highway', 'unknown')
                        if isinstance(highway_type, list):
                            highway_type = highway_type[0]

                        # Get edge length
                        edge_length = graph.edges[edge].get('length', 0)

                        road_type_counts[highway_type] = road_type_counts.get(highway_type, 0) + 1
                        road_type_lengths[highway_type] = road_type_lengths.get(highway_type, 0) + edge_length

        # Convert to list of dictionaries
        road_type_data = []
        total_count = sum(road_type_counts.values())
        total_length = sum(road_type_lengths.values())

        for road_type, count in road_type_counts.items():
            length = road_type_lengths.get(road_type, 0)
            road_type_data.append({
                'Road_Type': road_type,
                'Usage_Count': count,
                'Usage_Percent': (count / total_count * 100) if total_count > 0 else 0,
                'Total_Length_Meters': length,
                'Length_Percent': (length / total_length * 100) if total_length > 0 else 0,
                'Average_Length_Meters': length / count if count > 0 else 0
            })

        return sorted(road_type_data, key=lambda x: x['Usage_Count'], reverse=True)

    def _calculate_performance_metrics(self, valid_routes: List) -> List[Dict]:
        """Calculate performance metrics for valid routes."""
        metrics = []

        # Extract numeric values
        total_times = [v[1] for v in valid_routes if isinstance(v[1], (int, float))]
        freeflow_times = [v[2] for v in valid_routes if isinstance(v[2], (int, float))]
        node_counts = [len(v[3]) for v in valid_routes if v[3]]

        if total_times:
            metrics.extend([
                {'Metric': 'Average Total Time (minutes)', 'Value': f"{sum(total_times) / len(total_times) / 60:.2f}"},
                {'Metric': 'Minimum Total Time (minutes)', 'Value': f"{min(total_times) / 60:.2f}"},
                {'Metric': 'Maximum Total Time (minutes)', 'Value': f"{max(total_times) / 60:.2f}"},
            ])

        if freeflow_times:
            metrics.extend([
                {'Metric': 'Average Freeflow Time (minutes)', 'Value': f"{sum(freeflow_times) / len(freeflow_times) / 60:.2f}"},
                {'Metric': 'Minimum Freeflow Time (minutes)', 'Value': f"{min(freeflow_times) / 60:.2f}"},
                {'Metric': 'Maximum Freeflow Time (minutes)', 'Value': f"{max(freeflow_times) / 60:.2f}"},
            ])

        if node_counts:
            metrics.extend([
                {'Metric': 'Average Node Count', 'Value': f"{sum(node_counts) / len(node_counts):.1f}"},
                {'Metric': 'Minimum Node Count', 'Value': f"{min(node_counts)}"},
                {'Metric': 'Maximum Node Count', 'Value': f"{max(node_counts)}"},
            ])

        # Calculate efficiency metrics
        if total_times and freeflow_times and len(total_times) == len(freeflow_times):
            efficiencies = [(f/t*100) for t, f in zip(total_times, freeflow_times) if t > 0]
            if efficiencies:
                metrics.extend([
                    {'Metric': 'Average Efficiency (%)', 'Value': f"{sum(efficiencies) / len(efficiencies):.1f}"},
                    {'Metric': 'Minimum Efficiency (%)', 'Value': f"{min(efficiencies):.1f}"},
                    {'Metric': 'Maximum Efficiency (%)', 'Value': f"{max(efficiencies):.1f}"},
                ])

        return metrics


# V2 Enhancement: Batch Export Functionality
class BatchExporter:
    """Handle batch export of multiple analysis results."""

    def __init__(self, db_manager: DatabaseManager):
        """Initialize batch exporter with database connection."""
        self.db_manager = db_manager

    def export_batch_results(
        self,
        batch_results: Dict[str, Any],
        format: str = 'json'
    ) -> str:
        """
        Export batch analysis results.

        Args:
            batch_results: Results from batch analysis
            format: Export format ('json', 'csv')

        Returns:
            Exported data as string
        """
        if format.lower() == 'json':
            import json
            return json.dumps(batch_results, indent=2, default=str)

        elif format.lower() == 'csv':
            import csv
            import io

            output = io.StringIO()
            writer = csv.writer(output)

            # Write batch summary
            writer.writerow(['Batch Analysis Summary'])
            writer.writerow(['Total Incidents', batch_results.get('incident_count', 0)])
            writer.writerow(['Total Processing Time', f"{batch_results.get('total_processing_time', 0):.2f} seconds"])
            writer.writerow(['Timestamp', batch_results.get('timestamp', '')])
            writer.writerow([])

            # Write individual results
            writer.writerow(['Incident Results'])
            writer.writerow(['Incident Edge', 'Status', 'Total Routes', 'Valid Routes', 'Success Rate', 'Processing Time'])

            results = batch_results.get('results', {})
            for incident_edge, result in results.items():
                if 'error' in result:
                    writer.writerow([
                        f"{incident_edge[0]}-{incident_edge[1]}",
                        'Failed',
                        '0',
                        '0',
                        '0.0%',
                        f"{result.get('processing_time', 0):.2f}s"
                    ])
                else:
                    writer.writerow([
                        f"{incident_edge[0]}-{incident_edge[1]}",
                        'Success',
                        result.get('total_routes', 0),
                        result.get('valid_detours', 0),
                        f"{result.get('success_rate', 0):.1f}%",
                        f"{result.get('processing_time', 0):.2f}s"
                    ])

            return output.getvalue()

        else:
            raise ValueError(f"Unsupported export format: {format}")


def create_export_data(app_session_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create comprehensive export data from Streamlit session state with V2 enhancements.

    Args:
        app_session_state: Streamlit session state dictionary

    Returns:
        Dictionary containing all data needed for exports
    """
    # Extract graph for network info
    graph = app_session_state.get('graph')

    # Extract detour results and selections
    detour_results = app_session_state.get('detour_results', {})
    detour_selections = app_session_state.get('detour_selections', {})

    # Get accepted routes
    accepted_routes = []
    rejected_routes = []
    for route_key, selection in detour_selections.items():
        if selection.get('status') == 'accepted':
            accepted_routes.append(route_key)
        elif selection.get('status') == 'rejected':
            rejected_routes.append(route_key)

    # Extract comprehensive metadata with V2 enhancements
    export_data = {
        'metadata': {
            'jurisdiction': app_session_state.get('selected_jurisdiction_name', 'Unknown'),
            'jurisdiction_type': app_session_state.get('selected_jurisdiction_type', 'Unknown'),
            'state': app_session_state.get('selected_state_name', 'Unknown'),
            'incident_edge': app_session_state.get('selected_incident_edge'),
            'incident_edge_key': app_session_state.get('selected_edge_key', 'Unknown'),
            'analysis_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'analysis_timestamp': datetime.now().isoformat(),
            'app_version': 'ARPL v2.0',
            # V2 enhancements
            'session_id': app_session_state.get('session_id'),
            'current_session_name': app_session_state.get('current_session_name'),
            'batch_analysis': app_session_state.get('batch_results') is not None
        },
        'analysis_params': {
            'n_turn_nodes': app_session_state.get('n_turn_nodes', 5),
            'sector_angle_deg': app_session_state.get('sector_angle_deg', 180),
            'sector_radius_m': app_session_state.get('sector_radius_m', 3000),
            'sector_radius_miles': app_session_state.get('sector_radius_m', 3000) / 1609.34,  # Convert to miles
            'min_travel_time_s': app_session_state.get('min_travel_time_s', 90),
            'max_travel_time_s': app_session_state.get('max_travel_time_s', 1800),
            'max_detour_routes': app_session_state.get('max_detour_routes', 10),
            'performance_mode': app_session_state.get('performance_mode', 'Balanced')
        },
        'detour_results': detour_results,
        'detour_selections': detour_selections,
        'accepted_routes': accepted_routes,
        'rejected_routes': rejected_routes,
        'graph': graph,
        'generation_time': app_session_state.get('detour_generation_time', 0),
        'network_info': {
            'nodes': len(graph.nodes()) if graph else 0,
            'edges': len(graph.edges()) if graph else 0,
            'jurisdiction_bounds': app_session_state.get('jurisdiction_bounds'),
            'network_type': 'drive',  # OSMnx network type used
            'crs': 'EPSG:4326'
        },
        'incident_info': {
            'edge_geometry': graph.edges[app_session_state.get('selected_incident_edge')].get('geometry') if graph and app_session_state.get('selected_incident_edge') and graph.has_edge(*app_session_state.get('selected_incident_edge')) else None,
            'edge_highway_type': graph.edges[app_session_state.get('selected_incident_edge')].get('highway') if graph and app_session_state.get('selected_incident_edge') and graph.has_edge(*app_session_state.get('selected_incident_edge')) else None,
            'edge_length': graph.edges[app_session_state.get('selected_incident_edge')].get('length') if graph and app_session_state.get('selected_incident_edge') and graph.has_edge(*app_session_state.get('selected_incident_edge')) else None
        },
        'data_sources': {
            'jurisdiction_data': app_session_state.get('data_download_status', 'Unknown'),
            'tiger_year': '2023',  # Current TIGER data year
            'osm_data_date': datetime.now().strftime('%Y-%m-%d')
        },
        # V2 enhancements
        'batch_results': app_session_state.get('batch_results'),
        'user_preferences': app_session_state.get('user_preferences', {}),
        'cache_info': {
            'network_cached': app_session_state.get('network_cached', False),
            'cache_hit': app_session_state.get('cache_hit', False)
        }
    }

    return export_data
