"""
Export utilities for ARPL V1.5.6 with enhanced PDF reports.
Includes detailed route information, turn-by-turn directions, and nearby points analysis.
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


class PDFReportGenerator:
    """Enhanced PDF report generator with detailed route information and nearby points."""

    def __init__(self, export_data):
        """
        Initialize PDF report generator.

        Args:
            export_data: Dictionary containing routes, nearby_points, incident_info, etc.
        """
        self.data = export_data
        self.styles = getSampleStyleSheet()

        # Custom styles
        self.title_style = ParagraphStyle(
            'CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#E61E28'),
            spaceAfter=30
        )

        self.heading_style = ParagraphStyle(
            'CustomHeading',
            parent=self.styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#E61E28'),
            spaceAfter=12
        )

        self.subheading_style = ParagraphStyle(
            'CustomSubHeading',
            parent=self.styles['Heading3'],
            fontSize=14,
            textColor=colors.HexColor('#333333'),
            spaceAfter=8
        )

    def export_pdf(self):
        """Generate comprehensive PDF report with detailed route information."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.75*inch, bottomMargin=0.75*inch)
        story = []

        # Title Page
        story.append(Paragraph("Traffic Detour Analysis Report", self.title_style))
        story.append(Spacer(1, 0.2*inch))

        # Executive Summary
        story.append(Paragraph("Executive Summary", self.heading_style))
        story.append(Spacer(1, 0.1*inch))

        summary_data = [
            ['Incident Location:', self.data.get('incident_info', {}).get('name', 'N/A')],
            ['Number of Routes:', str(self.data.get('summary_statistics', {}).get('total_routes', 0))],
            ['Analysis Date:', self.data.get('timestamp', 'N/A')],
            ['Buffer Distance:', f"{self.data.get('summary_statistics', {}).get('buffer_distance_miles', 0.5)} miles"]
        ]

        summary_table = Table(summary_data, colWidths=[2*inch, 4*inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F0F0F0')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('PADDING', (0, 0), (-1, -1), 8)
        ]))
        story.append(summary_table)
        story.append(PageBreak())

        # Detailed Route Information
        for route in self.data.get('routes', []):
            story.append(Paragraph(f"Route {route['route_key']}", self.heading_style))
            story.append(Spacer(1, 0.1*inch))

            # Route Statistics
            stats_data = [
                ['Total Distance:', f"{route['details']['total_distance']/1000:.2f} km"],
                ['Total Time:', f"{route['total_time_minutes']:.1f} minutes"],
                ['Freeflow Time:', f"{route['freeflow_time_minutes']:.1f} minutes"],
                ['Number of Segments:', str(route['details']['segment_count'])],
                ['Number of Turns:', str(route['details']['turn_count'])],
                ['Roads Used:', ', '.join(route['details']['road_names'][:5])]
            ]

            stats_table = Table(stats_data, colWidths=[2*inch, 4*inch])
            stats_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F0F0F0')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('PADDING', (0, 0), (-1, -1), 6)
            ]))
            story.append(stats_table)
            story.append(Spacer(1, 0.2*inch))

            # Turn-by-Turn Directions
            story.append(Paragraph("Turn-by-Turn Directions:", self.subheading_style))
            story.append(Spacer(1, 0.1*inch))

            # Segment details table
            segment_data = [['Step', 'Road Name', 'Highway Type', 'Distance (m)', 'Time (min)']]
            for i, segment in enumerate(route['details']['segments'][:20]):  # Limit to 20 segments
                segment_data.append([
                    str(i+1),
                    str(segment['name'])[:30],
                    str(segment['highway']),
                    f"{segment['length']:.0f}",
                    f"{segment['travel_time']/60:.1f}"
                ])

            segment_table = Table(segment_data, colWidths=[0.5*inch, 2.5*inch, 1*inch, 1*inch, 1*inch])
            segment_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E61E28')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F9F9')])
            ]))
            story.append(segment_table)
            story.append(Spacer(1, 0.2*inch))

            # Nearby Points of Interest
            nearby_points = self.data.get('nearby_points', {}).get(route['route_key'], [])
            if nearby_points:
                story.append(Paragraph("Nearby Points of Interest:", self.subheading_style))
                story.append(Spacer(1, 0.1*inch))

                for layer_info in nearby_points:
                    layer_name = layer_info['layer']
                    points = layer_info['points']

                    story.append(Paragraph(f"From {layer_name}:", self.styles['Heading4']))

                    # Points table
                    point_columns = ['Name', 'Distance (mi)']
                    # Add any additional attributes from the point data
                    if not points.empty:
                        point_data = [point_columns]
                        for idx, row in points.head(10).iterrows():  # Limit to 10 points
                            # Get name field (try common field names)
                            name = row.get('name', row.get('NAME', row.get('Name', 'N/A')))
                            point_data.append([
                                str(name)[:40],
                                f"{row['distance_miles']:.2f}"
                            ])

                        point_table = Table(point_data, colWidths=[4*inch, 1.5*inch])
                        point_table.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4A90E2')),
                            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F9F9')])
                        ]))
                        story.append(point_table)
                        story.append(Spacer(1, 0.1*inch))

            story.append(PageBreak())

        # Build PDF
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()


class GeospatialExporter:
    """Export detour routes to various geospatial formats."""

    def __init__(self, export_data):
        """Initialize geospatial exporter."""
        self.data = export_data

    def export_geojson(self):
        """Export routes as GeoJSON."""
        features = []

        for route in self.data.get('routes', []):
            if route.get('geometry'):
                feature = {
                    "type": "Feature",
                    "properties": {
                        "route_key": route['route_key'],
                        "total_time_minutes": route['total_time_minutes'],
                        "freeflow_time_minutes": route['freeflow_time_minutes'],
                        "segment_count": route['details']['segment_count'],
                        "turn_count": route['details']['turn_count'],
                        "road_names": ', '.join(route['details']['road_names'])
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[coord[0], coord[1]] for coord in route['geometry'].coords]
                    }
                }
                features.append(feature)

        geojson = {
            "type": "FeatureCollection",
            "features": features,
            "properties": {
                "incident_info": self.data.get('incident_info', {}),
                "timestamp": self.data.get('timestamp', ''),
                "buffer_distance_miles": self.data.get('summary_statistics', {}).get('buffer_distance_miles', 0.5)
            }
        }

        return json.dumps(geojson, indent=2)

    def export_kml(self):
        """Export routes as KML."""
        kml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
<name>Detour Routes</name>
<description>Traffic detour analysis results</description>
'''

        for route in self.data.get('routes', []):
            if route.get('geometry'):
                kml_content += f'''
<Placemark>
<name>Route {route['route_key']}</name>
<description>
Total Time: {route['total_time_minutes']:.1f} minutes
Freeflow Time: {route['freeflow_time_minutes']:.1f} minutes
Segments: {route['details']['segment_count']}
Turns: {route['details']['turn_count']}
Roads: {', '.join(route['details']['road_names'][:3])}
</description>
<LineString>
<coordinates>
'''
                for coord in route['geometry'].coords:
                    kml_content += f"{coord[0]},{coord[1]},0 "

                kml_content += '''
</coordinates>
</LineString>
</Placemark>
'''

        kml_content += '''
</Document>
</kml>
'''
        return kml_content

    def export_shapefile(self):
        """Export routes as Shapefile (ZIP)."""
        # Create temporary directory for shapefile components
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create GeoDataFrame
            features = []
            for route in self.data.get('routes', []):
                if route.get('geometry'):
                    features.append({
                        'geometry': route['geometry'],
                        'route_key': route['route_key'],
                        'total_time': route['total_time_minutes'],
                        'freeflow_time': route['freeflow_time_minutes'],
                        'segments': route['details']['segment_count'],
                        'turns': route['details']['turn_count'],
                        'roads': ', '.join(route['details']['road_names'][:5])
                    })

            if features:
                gdf = gpd.GeoDataFrame(features)
                gdf.crs = "EPSG:4326"

                # Save as shapefile
                shapefile_path = os.path.join(temp_dir, "detour_routes.shp")
                gdf.to_file(shapefile_path)

                # Create ZIP file
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    for file in os.listdir(temp_dir):
                        zip_file.write(os.path.join(temp_dir, file), file)

                zip_buffer.seek(0)
                return zip_buffer.getvalue()

        return b""

    def export_geopackage(self):
        """Export routes as GeoPackage."""
        features = []
        for route in self.data.get('routes', []):
            if route.get('geometry'):
                features.append({
                    'geometry': route['geometry'],
                    'route_key': route['route_key'],
                    'total_time': route['total_time_minutes'],
                    'freeflow_time': route['freeflow_time_minutes'],
                    'segments': route['details']['segment_count'],
                    'turns': route['details']['turn_count'],
                    'roads': ', '.join(route['details']['road_names'][:5])
                })

        if features:
            gdf = gpd.GeoDataFrame(features)
            gdf.crs = "EPSG:4326"

            # Save to buffer
            buffer = io.BytesIO()
            gdf.to_file(buffer, driver='GPKG')
            buffer.seek(0)
            return buffer.getvalue()

        return b""


class TabularExporter:
    """Export analysis results to tabular formats."""

    def __init__(self, export_data):
        """Initialize tabular exporter."""
        self.data = export_data

    def export_excel(self):
        """Export routes as Excel workbook."""
        buffer = io.BytesIO()

        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            # Routes summary
            routes_data = []
            for route in self.data.get('routes', []):
                routes_data.append({
                    'Route Key': route['route_key'],
                    'Total Time (min)': route['total_time_minutes'],
                    'Freeflow Time (min)': route['freeflow_time_minutes'],
                    'Segments': route['details']['segment_count'],
                    'Turns': route['details']['turn_count'],
                    'Total Distance (km)': route['details']['total_distance']/1000,
                    'Roads Used': ', '.join(route['details']['road_names'])
                })

            if routes_data:
                routes_df = pd.DataFrame(routes_data)
                routes_df.to_excel(writer, sheet_name='Route Summary', index=False)

            # Detailed segments
            segments_data = []
            for route in self.data.get('routes', []):
                for i, segment in enumerate(route['details']['segments']):
                    segments_data.append({
                        'Route Key': route['route_key'],
                        'Segment': i + 1,
                        'From Node': segment['from_node'],
                        'To Node': segment['to_node'],
                        'OSMID': segment['osmid'],
                        'Road Name': segment['name'],
                        'Highway Type': segment['highway'],
                        'Length (m)': segment['length'],
                        'Travel Time (s)': segment['travel_time'],
                        'Max Speed': segment['maxspeed'],
                        'Ref': segment['ref']
                    })

            if segments_data:
                segments_df = pd.DataFrame(segments_data)
                segments_df.to_excel(writer, sheet_name='Route Segments', index=False)

            # Nearby points
            points_data = []
            for route_key, nearby_points in self.data.get('nearby_points', {}).items():
                for layer_info in nearby_points:
                    layer_name = layer_info['layer']
                    points = layer_info['points']
                    for idx, row in points.iterrows():
                        points_data.append({
                            'Route Key': route_key,
                            'Layer': layer_name,
                            'Name': row.get('name', row.get('NAME', row.get('Name', 'N/A'))),
                            'Distance (miles)': row['distance_miles']
                        })

            if points_data:
                points_df = pd.DataFrame(points_data)
                points_df.to_excel(writer, sheet_name='Nearby Points', index=False)

        buffer.seek(0)
        return buffer.getvalue()

    def export_csv(self):
        """Export routes as CSV."""
        routes_data = []
        for route in self.data.get('routes', []):
            routes_data.append({
                'Route Key': route['route_key'],
                'Total Time (min)': route['total_time_minutes'],
                'Freeflow Time (min)': route['freeflow_time_minutes'],
                'Segments': route['details']['segment_count'],
                'Turns': route['details']['turn_count'],
                'Total Distance (km)': route['details']['total_distance']/1000,
                'Roads Used': ', '.join(route['details']['road_names'])
            })

        if routes_data:
            df = pd.DataFrame(routes_data)
            return df.to_csv(index=False)

        return ""


def export_to_pdf(graph, accepted_detours, incident_edge, additional_data, buffer_miles, include_maps=True):
    """
    Export detour analysis results to PDF format with map visualizations.

    Args:
        graph: NetworkX graph object
        accepted_detours: Dictionary of accepted detour routes
        incident_edge: Incident edge information
        additional_data: Additional data layers
        buffer_miles: Buffer distance in miles
        include_maps: Whether to include map visualizations

    Returns:
        PDF data as bytes
    """
    from io import BytesIO
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    from matplotlib.backends.backend_pdf import PdfPages
    import networkx as nx
    import detour_utils as du

    # Create PDF in memory
    buffer = BytesIO()

    with PdfPages(buffer) as pdf:
        # Title page
        fig, ax = plt.subplots(figsize=(8.5, 11))
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')

        # Title
        ax.text(0.5, 0.9, 'Detour Analysis Report',
                fontsize=24, fontweight='bold', ha='center', va='center')

        # Subtitle
        ax.text(0.5, 0.8, f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
                fontsize=12, ha='center', va='center')

        # Incident information
        if incident_edge:
            ax.text(0.5, 0.7, f'Incident Edge: {incident_edge}',
                    fontsize=14, ha='center', va='center')

        # Summary
        ax.text(0.5, 0.6, f'Total Routes Analyzed: {len(accepted_detours)}',
                fontsize=12, ha='center', va='center')

        ax.text(0.5, 0.5, f'Buffer Distance: {buffer_miles} miles',
                fontsize=12, ha='center', va='center')

        pdf.savefig(fig, bbox_inches='tight')
        plt.close(fig)

        # Route analysis pages
        for route_key, route_data in accepted_detours.items():
            path = route_data.get('path', [])
            buffer_points = route_data.get('buffer_points', [])

            if include_maps and path:
                # Create map visualization using plot_detour
                try:
                    # Generate the detour map
                    map_fig = du.plot_detour(
                        graph,
                        path,
                        incident_edge,
                        additional_data=additional_data,
                        buffer_miles=buffer_miles,
                        buffer_points=buffer_points
                    )

                    # Save the map to PDF
                    pdf.savefig(map_fig, bbox_inches='tight', dpi=300)
                    plt.close(map_fig)

                except Exception as e:
                    # Fallback to text-only if map generation fails
                    print(f"Map generation failed for route {route_key}: {e}")
                    include_maps = False

            # Text analysis page (always included)
            fig, ax = plt.subplots(figsize=(8.5, 11))
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.axis('off')

            # Route title
            ax.text(0.5, 0.95, f'Route Analysis: {route_key}',
                    fontsize=16, fontweight='bold', ha='center', va='center')

            # Route details
            y_pos = 0.85
            path = route_data.get('path', [])

            # Basic route information
            details = [
                f'Route Length: {len(path)} nodes',
                f'Total Distance: {calculate_route_distance(graph, path):.2f} km',
                f'Buffer Points Found: {len(route_data.get("buffer_points", []))}',
                f'Buffer Distance: {route_data.get("buffer_miles", buffer_miles)} miles'
            ]

            for detail in details:
                ax.text(0.1, y_pos, detail, fontsize=12, ha='left', va='center')
                y_pos -= 0.05

            # Route segments analysis - paginate if needed to show ALL segments
            if path and len(path) > 1:
                # Calculate segments per page
                segments_per_page = 25  # Approximate segments that fit on a page
                total_segments = len(path) - 1
                total_pages = (total_segments + segments_per_page - 1) // segments_per_page

                # Create pages for route segments
                for seg_page_num in range(total_pages):
                    start_seg_idx = seg_page_num * segments_per_page
                    end_seg_idx = min(start_seg_idx + segments_per_page, total_segments)

                    # Create a new page for route segments if this is not the first page
                    if seg_page_num > 0:
                        fig_seg, ax_seg = plt.subplots(figsize=(8.5, 11))
                        ax_seg.set_xlim(0, 1)
                        ax_seg.set_ylim(0, 1)
                        ax_seg.axis('off')

                        # Route title
                        ax_seg.text(0.5, 0.95, f'Route Analysis: {route_key}',
                                fontsize=16, fontweight='bold', ha='center', va='center')

                        # Route segments title
                        seg_title = 'Route Segments:'
                        if total_pages > 1:
                            seg_title += f' (Page {seg_page_num + 1} of {total_pages})'
                        ax_seg.text(0.1, 0.88, seg_title,
                                fontsize=14, fontweight='bold', ha='left', va='center')
                        y_pos_seg = 0.82
                    else:
                        # Use existing page for first segment page
                        ax_seg = ax
                        ax_seg.text(0.1, y_pos - 0.05, 'Route Segments:',
                                fontsize=14, fontweight='bold', ha='left', va='center')
                        y_pos_seg = y_pos - 0.1

                    # Analyze segments for this page
                    for i in range(start_seg_idx, end_seg_idx):
                        u, v = path[i], path[i + 1]
                        if graph.has_edge(u, v):
                            edge_data = graph.get_edge_data(u, v)
                            if edge_data:
                                # Get edge attributes
                                edge_attrs = next(iter(edge_data.values())) if isinstance(edge_data, dict) else edge_data

                                # Extract road information
                                road_name = edge_attrs.get('name', 'Unnamed Road')
                                if isinstance(road_name, list):
                                    road_name = road_name[0] if road_name else 'Unnamed Road'

                                highway_type = edge_attrs.get('highway', 'unknown')
                                if isinstance(highway_type, list):
                                    highway_type = highway_type[0] if highway_type else 'unknown'

                                ref = edge_attrs.get('ref', '')
                                if isinstance(ref, list):
                                    ref = ref[0] if ref else ''

                                # Extract OSM ID
                                osmid = edge_attrs.get('osmid', 'N/A')
                                if isinstance(osmid, list):
                                    osmid = osmid[0] if osmid else 'N/A'
                                # Format OSM ID for display
                                if osmid != 'N/A':
                                    osmid_str = str(osmid)
                                else:
                                    osmid_str = 'N/A'

                                # Calculate segment distance
                                u_data = graph.nodes[u]
                                v_data = graph.nodes[v]
                                segment_distance = calculate_distance(
                                    u_data['y'], u_data['x'], v_data['y'], v_data['x']
                                )

                                segment_text = f'Segment {i+1}: {road_name} ({highway_type})'
                                if ref:
                                    segment_text += f' - Ref: {ref}'
                                segment_text += f' - OSM ID: {osmid_str}'
                                segment_text += f' - {segment_distance:.3f} km'

                                ax_seg.text(0.15, y_pos_seg, segment_text, fontsize=10, ha='left', va='center')
                                y_pos_seg -= 0.03

                                # Safety check
                                if y_pos_seg < 0.1:
                                    break

                    # Add summary for segment pages
                    if seg_page_num > 0:
                        summary_text = f'Showing segments {start_seg_idx + 1}-{end_seg_idx} of {total_segments} total segments'
                        ax_seg.text(0.1, 0.05, summary_text,
                                fontsize=10, ha='left', va='center', style='italic')
                        pdf.savefig(fig_seg, bbox_inches='tight')
                        plt.close(fig_seg)
                    else:
                        # Update y_pos for first page to continue with buffer points
                        y_pos = y_pos_seg

            # Buffer points table - will be on separate pages if needed
            buffer_points = route_data.get('buffer_points', [])
            if buffer_points:
                # Determine if this is traffic signal data
                is_traffic_signal = any('signal' in point.get('name', '').lower() or
                                       'ASSET_ID' in point or 'GLOBALID' in point
                                       for point in buffer_points[:5])

                # Calculate how many rows fit per page
                rows_per_page = 20  # Approximate rows that fit on a page
                total_pages = (len(buffer_points) + rows_per_page - 1) // rows_per_page

                # Create table pages for buffer search results
                for page_num in range(total_pages):
                    start_idx = page_num * rows_per_page
                    end_idx = min(start_idx + rows_per_page, len(buffer_points))
                    page_points = buffer_points[start_idx:end_idx]

                    # Create a new page for buffer search results table
                    fig_table, ax_table = plt.subplots(figsize=(8.5, 11))
                    ax_table.set_xlim(0, 1)
                    ax_table.set_ylim(0, 1)
                    ax_table.axis('off')

                    # Route title
                    ax_table.text(0.5, 0.95, f'Route Analysis: {route_key}',
                            fontsize=16, fontweight='bold', ha='center', va='center')

                    # Buffer Search Results title
                    title_text = 'Buffer Search Results:'
                    if total_pages > 1:
                        title_text += f' (Page {page_num + 1} of {total_pages})'
                    ax_table.text(0.1, 0.88, title_text,
                            fontsize=14, fontweight='bold', ha='left', va='center')

                    y_pos = 0.82

                    # Create table header
                    if is_traffic_signal:
                        # Traffic signal table format
                        header_y = y_pos
                        ax_table.text(0.05, header_y, 'Asset ID', fontsize=9, fontweight='bold', ha='left', va='center')
                        ax_table.text(0.25, header_y, 'Major Road', fontsize=9, fontweight='bold', ha='left', va='center')
                        ax_table.text(0.55, header_y, 'Minor Road', fontsize=9, fontweight='bold', ha='left', va='center')
                        ax_table.text(0.75, header_y, 'Coordinates', fontsize=9, fontweight='bold', ha='left', va='center')
                        y_pos -= 0.04

                        # Draw header line
                        ax_table.plot([0.05, 0.95], [header_y - 0.02, header_y - 0.02], 'k-', linewidth=0.5)
                        y_pos -= 0.02

                        # Show buffer points in table format
                        for point in page_points:
                            if y_pos < 0.1:  # Safety check
                                break

                            # Extract Asset ID
                            asset_id = point.get('ASSET_ID') or point.get('GLOBALID') or point.get('id', 'N/A')
                            if isinstance(asset_id, (int, float)):
                                asset_id = str(int(asset_id))
                            else:
                                asset_id = str(asset_id) if asset_id else 'N/A'

                            # Find major and minor roads
                            # First, try to read from point data (traffic signal datasets often include these)
                            # Use dynamic detection similar to traffic signal detection
                            major_road = None
                            minor_road = None

                            # Get all available field names from the point data
                            available_fields = list(point.keys())

                            # Dynamically find major road field by checking column names
                            # Look for fields containing "major" (case-insensitive)
                            for field in available_fields:
                                field_lower = str(field).lower()
                                if 'major' in field_lower and field not in ['geometry', 'id', 'name', 'x', 'y']:
                                    value = point.get(field)
                                    if value and str(value).strip() and str(value).lower() not in ['none', 'null', '']:
                                        major_road = value
                                        break

                            # Dynamically find minor road field by checking column names
                            # Look for fields containing "minor" (case-insensitive)
                            for field in available_fields:
                                field_lower = str(field).lower()
                                if 'minor' in field_lower and field not in ['geometry', 'id', 'name', 'x', 'y']:
                                    value = point.get(field)
                                    if value and str(value).strip() and str(value).lower() not in ['none', 'null', '']:
                                        minor_road = value
                                        break

                            # If not found in point data, calculate from graph
                            if not major_road or not minor_road:
                                try:
                                    calc_major, calc_minor = find_nearest_roads(graph, point['y'], point['x'])
                                    # Use calculated values only if point data didn't have them
                                    if not major_road:
                                        major_road = calc_major
                                    if not minor_road:
                                        minor_road = calc_minor
                                except:
                                    if not major_road:
                                        major_road = "Not Found"
                                    if not minor_road:
                                        minor_road = "Not Found"

                            # Convert to string and clean up
                            major_road = str(major_road).strip() if major_road else "Not Found"
                            minor_road = str(minor_road).strip() if minor_road else "Not Found"

                            # Truncate long names
                            major_road = major_road[:20] if len(major_road) > 20 else major_road
                            minor_road = minor_road[:20] if len(minor_road) > 20 else minor_road

                            # Table row
                            ax_table.text(0.05, y_pos, asset_id[:15], fontsize=8, ha='left', va='center')
                            ax_table.text(0.25, y_pos, major_road, fontsize=8, ha='left', va='center')
                            ax_table.text(0.55, y_pos, minor_road, fontsize=8, ha='left', va='center')
                            ax_table.text(0.75, y_pos, f'({point["x"]:.6f}, {point["y"]:.6f})', fontsize=8, ha='left', va='center')
                            y_pos -= 0.035
                    else:
                        # Generic table format
                        header_y = y_pos
                        ax_table.text(0.05, header_y, 'Data Type', fontsize=9, fontweight='bold', ha='left', va='center')
                        ax_table.text(0.35, header_y, 'ID', fontsize=9, fontweight='bold', ha='left', va='center')
                        ax_table.text(0.55, header_y, 'Coordinates', fontsize=9, fontweight='bold', ha='left', va='center')
                        y_pos -= 0.04

                        # Draw header line
                        ax_table.plot([0.05, 0.95], [header_y - 0.02, header_y - 0.02], 'k-', linewidth=0.5)
                        y_pos -= 0.02

                        # Show buffer points in table format
                        for point in page_points:
                            if y_pos < 0.1:  # Safety check
                                break

                            point_id = point.get('id', 'N/A')
                            if isinstance(point_id, (int, float)):
                                point_id = str(int(point_id))
                            else:
                                point_id = str(point_id) if point_id else 'N/A'

                            # Table row
                            ax_table.text(0.05, y_pos, point.get('name', 'Unknown')[:25], fontsize=8, ha='left', va='center')
                            ax_table.text(0.35, y_pos, point_id[:20], fontsize=8, ha='left', va='center')
                            ax_table.text(0.55, y_pos, f'({point["x"]:.6f}, {point["y"]:.6f})', fontsize=8, ha='left', va='center')
                            y_pos -= 0.035

                    # Add summary at bottom
                    summary_text = f'Showing {start_idx + 1}-{end_idx} of {len(buffer_points)} total points found within buffer'
                    ax_table.text(0.1, 0.05, summary_text,
                            fontsize=10, ha='left', va='center', style='italic')

                    pdf.savefig(fig_table, bbox_inches='tight')
                    plt.close(fig_table)
            else:
                ax.text(0.1, y_pos - 0.05, 'No buffer search conducted or no points found',
                        fontsize=12, ha='left', va='center', style='italic')

            pdf.savefig(fig, bbox_inches='tight')
            plt.close(fig)

        # Summary page with overview map (if maps are enabled and we have routes)
        if include_maps and accepted_detours:
            try:
                # Create overview map showing all routes
                fig, ax = plt.subplots(figsize=(8.5, 11))
                ax.set_xlim(0, 1)
                ax.set_ylim(0, 1)
                ax.axis('off')

                # Title
                ax.text(0.5, 0.95, 'Detour Routes Overview',
                        fontsize=18, fontweight='bold', ha='center', va='center')

                # Summary statistics
                total_routes = len(accepted_detours)
                total_distance = sum(calculate_route_distance(graph, route_data.get('path', []))
                                   for route_data in accepted_detours.values())
                total_buffer_points = sum(len(route_data.get('buffer_points', []))
                                        for route_data in accepted_detours.values())

                summary_text = f"""
Summary Statistics:
• Total Routes: {total_routes}
• Total Distance: {total_distance:.2f} km
• Total Buffer Points Found: {total_buffer_points}
• Buffer Distance: {buffer_miles} miles
• Incident Edge: {incident_edge}
                """

                ax.text(0.1, 0.8, summary_text, fontsize=12, ha='left', va='top',
                        bbox=dict(boxstyle='round,pad=0.5', facecolor='lightgray', alpha=0.8))

                # Route list
                ax.text(0.1, 0.6, 'Route Details:', fontsize=14, fontweight='bold', ha='left', va='center')
                y_pos = 0.55

                for i, (route_key, route_data) in enumerate(accepted_detours.items()):
                    path = route_data.get('path', [])
                    distance = calculate_route_distance(graph, path)
                    buffer_points_count = len(route_data.get('buffer_points', []))

                    route_text = f"{i+1}. {route_key}: {len(path)} nodes, {distance:.2f} km, {buffer_points_count} buffer points"
                    ax.text(0.15, y_pos, route_text, fontsize=10, ha='left', va='center')
                    y_pos -= 0.04

                pdf.savefig(fig, bbox_inches='tight')
                plt.close(fig)

            except Exception as e:
                print(f"Overview page generation failed: {e}")

    buffer.seek(0)
    return buffer.getvalue()


def calculate_route_distance(graph, path):
    """Calculate total distance of a route path."""
    total_distance = 0
    for i in range(len(path) - 1):
        u, v = path[i], path[i + 1]
        if graph.has_node(u) and graph.has_node(v):
            u_data = graph.nodes[u]
            v_data = graph.nodes[v]
            total_distance += calculate_distance(u_data['y'], u_data['x'], v_data['y'], v_data['x'])
    return total_distance


def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in kilometers."""
    from math import radians, cos, sin, asin, sqrt

    # Haversine formula
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    r = 6371  # Radius of earth in kilometers
    return c * r


def find_nearest_roads(graph, point_lat, point_lon, max_distance_m=50):
    """
    Find the nearest roads to a point.
    Returns a tuple of (major_road, minor_road) names.
    Major road is the highest priority road, minor road is a different road (not the same as major).
    """
    from shapely.geometry import Point
    from math import radians, cos, sin, asin, sqrt

    point = Point(point_lon, point_lat)  # Note: Shapely uses (x, y) = (lon, lat)
    nearest_edges = []

    # Find nearest edges within max_distance
    for u, v, k, data in graph.edges(keys=True, data=True):
        edge_geom = data.get('geometry')
        if edge_geom:
            # Calculate distance from point to edge
            dist = point.distance(edge_geom) * 111  # Convert degrees to km (approximate)
            if dist * 1000 <= max_distance_m:  # Convert to meters
                # Get road name
                road_name = data.get('name', 'Unnamed Road')
                if isinstance(road_name, list):
                    road_name = road_name[0] if road_name else 'Unnamed Road'

                # Get highway type for prioritization
                highway_type = data.get('highway', 'unknown')
                if isinstance(highway_type, list):
                    highway_type = highway_type[0] if highway_type else 'unknown'

                # Prioritize major roads
                priority = 0
                if highway_type in ['motorway', 'trunk', 'primary']:
                    priority = 3
                elif highway_type in ['secondary', 'tertiary']:
                    priority = 2
                else:
                    priority = 1

                nearest_edges.append((dist, priority, road_name, highway_type))

    if not nearest_edges:
        return ("Not Found", "Not Found")

    # Sort by priority first (highest priority first), then by distance
    nearest_edges.sort(key=lambda x: (-x[1], x[0]))

    # Get major road (highest priority, closest)
    major_road = nearest_edges[0][2]

    # Find minor road - must be a different road name
    minor_road = "Not Found"
    for dist, priority, road_name, highway_type in nearest_edges[1:]:
        # Skip if it's the same road name as major road
        if road_name != major_road and road_name != 'Unnamed Road':
            minor_road = road_name
            break

    # If we didn't find a different road, try to find one with different highway type
    if minor_road == "Not Found":
        major_highway_type = nearest_edges[0][3]
        for dist, priority, road_name, highway_type in nearest_edges[1:]:
            if highway_type != major_highway_type and road_name != 'Unnamed Road':
                minor_road = road_name
                break

    return (major_road, minor_road)


def export_to_geojson(graph, accepted_detours, incident_edge, additional_data, buffer_miles):
    """Export detour analysis results to GeoJSON format."""
    import json
    from shapely.geometry import Point, LineString

    features = []

    # Add incident edge with actual geometry
    if incident_edge:
        # Handle both 2-tuple and 3-tuple formats
        if len(incident_edge) == 3:
            u, v, k = incident_edge
        else:
            u, v = incident_edge
            k = 0

        if graph.has_edge(u, v):
            edge_data = graph.get_edge_data(u, v, k)
            if edge_data and 'geometry' in edge_data:
                edge_geom = edge_data['geometry']
                # Convert geometry to coordinates
                if hasattr(edge_geom, 'coords'):
                    coords = [[coord[0], coord[1]] for coord in edge_geom.coords]
                    if len(coords) > 1:
                        features.append({
                            "type": "Feature",
                            "properties": {
                                "type": "incident_edge",
                                "description": str(incident_edge),
                                "u": u,
                                "v": v
                            },
                            "geometry": {
                                "type": "LineString",
                                "coordinates": coords
                            }
                        })
            else:
                # Fallback: use node coordinates
                if u in graph.nodes and v in graph.nodes:
                    u_coords = [graph.nodes[u]['x'], graph.nodes[u]['y']]
                    v_coords = [graph.nodes[v]['x'], graph.nodes[v]['y']]
                    features.append({
                        "type": "Feature",
                        "properties": {
                            "type": "incident_edge",
                            "description": str(incident_edge)
                        },
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [u_coords, v_coords]
                        }
                    })

    # Add routes
    for route_key, route_data in accepted_detours.items():
        # Try multiple ways to get the path
        path = None
        if 'data' in route_data and len(route_data['data']) >= 4:
            _, _, _, path = route_data['data']
        elif 'path' in route_data:
            path = route_data['path']

        if path and len(path) > 1:
            # Create route line using edge geometries for accuracy
            route_coords = []
            for i in range(len(path) - 1):
                if graph.has_edge(path[i], path[i+1]):
                    edge_data = graph.get_edge_data(path[i], path[i+1])
                    if edge_data and 'geometry' in edge_data:
                        edge_geom = edge_data['geometry']
                        if hasattr(edge_geom, 'coords'):
                            # Add coordinates from edge geometry
                            for coord in edge_geom.coords:
                                route_coords.append([coord[0], coord[1]])
                    else:
                        # Fallback: use node coordinates
                        if path[i] in graph.nodes:
                            node_data = graph.nodes[path[i]]
                            route_coords.append([node_data['x'], node_data['y']])

            # Add last node if not already included
            if path[-1] in graph.nodes and (not route_coords or route_coords[-1] != [graph.nodes[path[-1]]['x'], graph.nodes[path[-1]]['y']]):
                node_data = graph.nodes[path[-1]]
                route_coords.append([node_data['x'], node_data['y']])

            if len(route_coords) > 1:
                features.append({
                    "type": "Feature",
                    "properties": {
                        "type": "route",
                        "route_key": str(route_key),
                        "buffer_points": len(route_data.get('buffer_points', [])),
                        "buffer_miles": route_data.get('buffer_miles', buffer_miles)
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": route_coords
                    }
                })

    geojson = {
        "type": "FeatureCollection",
        "features": features
    }

    return json.dumps(geojson, indent=2)


def export_to_kml(graph, accepted_detours, incident_edge, additional_data, buffer_miles):
    """Export detour analysis results to KML format."""
    kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
<name>Detour Analysis</name>
<description>Detour routes and incident edge</description>
"""

    # Add incident edge
    if incident_edge:
        # Handle both 2-tuple and 3-tuple formats
        if len(incident_edge) == 3:
            u, v, k = incident_edge
        else:
            u, v = incident_edge
            k = 0

        incident_coords = []
        if graph.has_edge(u, v):
            edge_data = graph.get_edge_data(u, v, k)
            if edge_data and 'geometry' in edge_data:
                edge_geom = edge_data['geometry']
                if hasattr(edge_geom, 'coords'):
                    for coord in edge_geom.coords:
                        incident_coords.append(f"{coord[0]},{coord[1]},0")
            else:
                # Fallback: use node coordinates
                if u in graph.nodes and v in graph.nodes:
                    incident_coords.append(f"{graph.nodes[u]['x']},{graph.nodes[u]['y']},0")
                    incident_coords.append(f"{graph.nodes[v]['x']},{graph.nodes[v]['y']},0")

        if incident_coords:
            kml_content += f"""
<Placemark>
<name>Incident Edge</name>
<description>Blocked/incident road segment</description>
<styleUrl>#incidentStyle</styleUrl>
<LineString>
<coordinates>{' '.join(incident_coords)}</coordinates>
</LineString>
</Placemark>
"""

    # Add routes
    for route_key, route_data in accepted_detours.items():
        # Try multiple ways to get the path
        path = None
        if 'data' in route_data and len(route_data['data']) >= 4:
            _, _, _, path = route_data['data']
        elif 'path' in route_data:
            path = route_data['path']

        if path and len(path) > 1:
            route_coords = []
            # Use edge geometries for accuracy
            for i in range(len(path) - 1):
                if graph.has_edge(path[i], path[i+1]):
                    edge_data = graph.get_edge_data(path[i], path[i+1])
                    if edge_data and 'geometry' in edge_data:
                        edge_geom = edge_data['geometry']
                        if hasattr(edge_geom, 'coords'):
                            for coord in edge_geom.coords:
                                route_coords.append(f"{coord[0]},{coord[1]},0")
                    else:
                        # Fallback: use node coordinates
                        if path[i] in graph.nodes:
                            node_data = graph.nodes[path[i]]
                            route_coords.append(f"{node_data['x']},{node_data['y']},0")

            # Add last node if not already included
            if path[-1] in graph.nodes:
                node_data = graph.nodes[path[-1]]
                last_coord = f"{node_data['x']},{node_data['y']},0"
                if not route_coords or route_coords[-1] != last_coord:
                    route_coords.append(last_coord)

            if len(route_coords) > 1:
                kml_content += f"""
<Placemark>
<name>Route {route_key}</name>
<description>Detour route with {len(route_data.get('buffer_points', []))} buffer points</description>
<styleUrl>#routeStyle</styleUrl>
<LineString>
<coordinates>{' '.join(route_coords)}</coordinates>
</LineString>
</Placemark>
"""

    # Add styles
    kml_content += """
<Style id="incidentStyle">
<LineStyle>
<color>ff0000ff</color>
<width>4</width>
</LineStyle>
</Style>
<Style id="routeStyle">
<LineStyle>
<color>ffff0000</color>
<width>3</width>
</LineStyle>
</Style>
</Document>
</kml>
"""

    return kml_content


def export_to_shapefile(graph, accepted_detours, incident_edge, additional_data, buffer_miles):
    """Export detour analysis results to Shapefile format."""
    import geopandas as gpd
    from shapely.geometry import LineString
    import zipfile
    import tempfile
    from pathlib import Path
    from io import BytesIO

    features = []

    # Add routes
    for route_key, route_data in accepted_detours.items():
        # Try multiple ways to get the path
        path = None
        if 'data' in route_data and len(route_data['data']) >= 4:
            _, _, _, path = route_data['data']
        elif 'path' in route_data:
            path = route_data['path']

        if path and len(path) > 1:
            route_coords = []
            # Use edge geometries for accuracy
            for i in range(len(path) - 1):
                if graph.has_edge(path[i], path[i+1]):
                    edge_data = graph.get_edge_data(path[i], path[i+1])
                    if edge_data and 'geometry' in edge_data:
                        edge_geom = edge_data['geometry']
                        if hasattr(edge_geom, 'coords'):
                            for coord in edge_geom.coords:
                                route_coords.append([coord[0], coord[1]])
                    else:
                        # Fallback: use node coordinates
                        if path[i] in graph.nodes:
                            node_data = graph.nodes[path[i]]
                            route_coords.append([node_data['x'], node_data['y']])

            # Add last node
            if path[-1] in graph.nodes:
                node_data = graph.nodes[path[-1]]
                last_coord = [node_data['x'], node_data['y']]
                if not route_coords or route_coords[-1] != last_coord:
                    route_coords.append(last_coord)

            if len(route_coords) > 1:
                line = LineString(route_coords)
                features.append({
                    'geometry': line,
                    'route_key': str(route_key),
                    'buffer_pts': len(route_data.get('buffer_points', []))
                })

    if features:
        gdf = gpd.GeoDataFrame(features, crs='EPSG:4326')
        # Create ZIP file with shapefile components
        zip_buffer = BytesIO()
        with tempfile.TemporaryDirectory() as temp_dir:
            shp_path = Path(temp_dir) / "detour_routes.shp"
            gdf.to_file(shp_path)
            # Read all shapefile components and add to ZIP
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for ext in ['.shp', '.shx', '.dbf', '.prj']:
                    file_path = shp_path.with_suffix(ext)
                    if file_path.exists():
                        zip_file.write(file_path, file_path.name)
        zip_buffer.seek(0)
        return zip_buffer.getvalue()
    else:
        return b''


def export_to_geopackage(graph, accepted_detours, incident_edge, additional_data, buffer_miles):
    """Export detour analysis results to GeoPackage format."""
    import geopandas as gpd
    from shapely.geometry import LineString
    from io import BytesIO

    features = []

    # Add routes
    for route_key, route_data in accepted_detours.items():
        # Try multiple ways to get the path
        path = None
        if 'data' in route_data and len(route_data['data']) >= 4:
            _, _, _, path = route_data['data']
        elif 'path' in route_data:
            path = route_data['path']

        if path and len(path) > 1:
            route_coords = []
            # Use edge geometries for accuracy
            for i in range(len(path) - 1):
                if graph.has_edge(path[i], path[i+1]):
                    edge_data = graph.get_edge_data(path[i], path[i+1])
                    if edge_data and 'geometry' in edge_data:
                        edge_geom = edge_data['geometry']
                        if hasattr(edge_geom, 'coords'):
                            for coord in edge_geom.coords:
                                route_coords.append([coord[0], coord[1]])
                    else:
                        # Fallback: use node coordinates
                        if path[i] in graph.nodes:
                            node_data = graph.nodes[path[i]]
                            route_coords.append([node_data['x'], node_data['y']])

            # Add last node
            if path[-1] in graph.nodes:
                node_data = graph.nodes[path[-1]]
                last_coord = [node_data['x'], node_data['y']]
                if not route_coords or route_coords[-1] != last_coord:
                    route_coords.append(last_coord)

            if len(route_coords) > 1:
                line = LineString(route_coords)
                features.append({
                    'geometry': line,
                    'route_key': str(route_key),
                    'buffer_pts': len(route_data.get('buffer_points', []))
                })

    if features:
        gdf = gpd.GeoDataFrame(features, crs='EPSG:4326')
        buffer = BytesIO()
        gdf.to_file(buffer, driver='GPKG')
        buffer.seek(0)
        return buffer.getvalue()
    else:
        return b''


def export_to_excel(graph, accepted_detours, incident_edge, additional_data, buffer_miles):
    """Export detour analysis results to Excel format with all incident and route link information."""
    import pandas as pd

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        # Incident Edge Information
        incident_data = []
        if incident_edge:
            if len(incident_edge) == 3:
                u, v, key = incident_edge
            else:
                u, v = incident_edge
                key = 0

            if graph.has_edge(u, v):
                edge_data = graph.get_edge_data(u, v, key) if key > 0 else graph.get_edge_data(u, v)
                if edge_data:
                    # Handle edge data structure
                    if isinstance(edge_data, dict):
                        if len(edge_data) > 0:
                            first_key = next(iter(edge_data.keys()))
                            if isinstance(first_key, int):
                                edge_attrs = edge_data[first_key]
                            elif 'osmid' in edge_data or 'geometry' in edge_data:
                                edge_attrs = edge_data
                            else:
                                edge_attrs = next(iter(edge_data.values()))
                        else:
                            edge_attrs = edge_data
                    else:
                        edge_attrs = edge_data

                    # Extract all edge information
                    osmid = edge_attrs.get('osmid', 'N/A')
                    if isinstance(osmid, list):
                        osmid = osmid[0] if osmid else 'N/A'

                    road_name = edge_attrs.get('name', 'Unnamed Road')
                    if isinstance(road_name, list):
                        road_name = road_name[0] if road_name else 'Unnamed Road'

                    highway_type = edge_attrs.get('highway', 'unknown')
                    if isinstance(highway_type, list):
                        highway_type = highway_type[0] if highway_type else 'unknown'

                    ref = edge_attrs.get('ref', '')
                    if isinstance(ref, list):
                        ref = ref[0] if ref else ''

                    length = edge_attrs.get('length', 0)
                    maxspeed = edge_attrs.get('maxspeed', 'N/A')
                    if isinstance(maxspeed, list):
                        maxspeed = maxspeed[0] if maxspeed else 'N/A'

                    # Get node coordinates
                    u_node = graph.nodes[u]
                    v_node = graph.nodes[v]
                    u_x = u_node.get('x', 0)
                    u_y = u_node.get('y', 0)
                    v_x = v_node.get('x', 0)
                    v_y = v_node.get('y', 0)

                    incident_data.append({
                        'Type': 'Incident Edge',
                        'OSM ID': str(osmid),
                        'From Node': u,
                        'To Node': v,
                        'From X': u_x,
                        'From Y': u_y,
                        'To X': v_x,
                        'To Y': v_y,
                        'Road Name': road_name,
                        'Highway Type': highway_type,
                        'Ref': ref,
                        'Length (m)': length,
                        'Max Speed': str(maxspeed)
                    })

        if incident_data:
            pd.DataFrame(incident_data).to_excel(writer, sheet_name='Incident Edge', index=False)

        # Route Segments Information
        route_segments_data = []
        for route_key, route_data in accepted_detours.items():
            path = None
            if 'data' in route_data and len(route_data['data']) >= 4:
                _, _, _, path = route_data['data']
            elif 'path' in route_data:
                path = route_data['path']

            if path and len(path) > 1:
                for i in range(len(path) - 1):
                    u, v = path[i], path[i+1]
                    if graph.has_edge(u, v):
                        edge_data = graph.get_edge_data(u, v)
                        if edge_data:
                            # Handle edge data structure
                            if isinstance(edge_data, dict):
                                if len(edge_data) > 0:
                                    first_key = next(iter(edge_data.keys()))
                                    if isinstance(first_key, int):
                                        edge_attrs = edge_data[first_key]
                                    elif 'osmid' in edge_data or 'geometry' in edge_data:
                                        edge_attrs = edge_data
                                    else:
                                        edge_attrs = next(iter(edge_data.values()))
                                else:
                                    edge_attrs = edge_data
                            else:
                                edge_attrs = edge_data

                            # Extract all edge information
                            osmid = edge_attrs.get('osmid', 'N/A')
                            if isinstance(osmid, list):
                                osmid = osmid[0] if osmid else 'N/A'

                            road_name = edge_attrs.get('name', 'Unnamed Road')
                            if isinstance(road_name, list):
                                road_name = road_name[0] if road_name else 'Unnamed Road'

                            highway_type = edge_attrs.get('highway', 'unknown')
                            if isinstance(highway_type, list):
                                highway_type = highway_type[0] if highway_type else 'unknown'

                            ref = edge_attrs.get('ref', '')
                            if isinstance(ref, list):
                                ref = ref[0] if ref else ''

                            length = edge_attrs.get('length', 0)
                            travel_time = edge_attrs.get('travel_time', 0)
                            maxspeed = edge_attrs.get('maxspeed', 'N/A')
                            if isinstance(maxspeed, list):
                                maxspeed = maxspeed[0] if maxspeed else 'N/A'

                            # Get node coordinates
                            u_node = graph.nodes[u]
                            v_node = graph.nodes[v]
                            u_x = u_node.get('x', 0)
                            u_y = u_node.get('y', 0)
                            v_x = v_node.get('x', 0)
                            v_y = v_node.get('y', 0)

                            route_segments_data.append({
                                'Route Key': str(route_key),
                                'Segment': i + 1,
                                'Type': 'Detour Route',
                                'OSM ID': str(osmid),
                                'From Node': u,
                                'To Node': v,
                                'From X': u_x,
                                'From Y': u_y,
                                'To X': v_x,
                                'To Y': v_y,
                                'Road Name': road_name,
                                'Highway Type': highway_type,
                                'Ref': ref,
                                'Length (m)': length,
                                'Travel Time (s)': travel_time,
                                'Max Speed': str(maxspeed)
                            })

        if route_segments_data:
            pd.DataFrame(route_segments_data).to_excel(writer, sheet_name='Route Segments', index=False)

        # Buffer Points
        buffer_data = []
        for route_key, route_data in accepted_detours.items():
            buffer_points = route_data.get('buffer_points', [])
            for point in buffer_points:
                buffer_data.append({
                    'Route Key': route_key,
                    'Point Name': point.get('name', 'N/A'),
                    'X': point.get('x', 0),
                    'Y': point.get('y', 0)
                })

        if buffer_data:
            pd.DataFrame(buffer_data).to_excel(writer, sheet_name='Buffer Points', index=False)

    buffer.seek(0)
    return buffer.getvalue()


def export_to_csv(graph, accepted_detours, incident_edge, additional_data, buffer_miles):
    """Export detour analysis results to CSV format with all incident and route link information."""
    import pandas as pd

    all_data = []

    # Add incident edge information
    if incident_edge:
        if len(incident_edge) == 3:
            u, v, key = incident_edge
        else:
            u, v = incident_edge
            key = 0

        if graph.has_edge(u, v):
            edge_data = graph.get_edge_data(u, v, key) if key > 0 else graph.get_edge_data(u, v)
            if edge_data:
                # Handle edge data structure
                if isinstance(edge_data, dict):
                    if len(edge_data) > 0:
                        first_key = next(iter(edge_data.keys()))
                        if isinstance(first_key, int):
                            edge_attrs = edge_data[first_key]
                        elif 'osmid' in edge_data or 'geometry' in edge_data:
                            edge_attrs = edge_data
                        else:
                            edge_attrs = next(iter(edge_data.values()))
                    else:
                        edge_attrs = edge_data
                else:
                    edge_attrs = edge_data

                # Extract all edge information
                osmid = edge_attrs.get('osmid', 'N/A')
                if isinstance(osmid, list):
                    osmid = osmid[0] if osmid else 'N/A'

                road_name = edge_attrs.get('name', 'Unnamed Road')
                if isinstance(road_name, list):
                    road_name = road_name[0] if road_name else 'Unnamed Road'

                highway_type = edge_attrs.get('highway', 'unknown')
                if isinstance(highway_type, list):
                    highway_type = highway_type[0] if highway_type else 'unknown'

                ref = edge_attrs.get('ref', '')
                if isinstance(ref, list):
                    ref = ref[0] if ref else ''

                length = edge_attrs.get('length', 0)
                maxspeed = edge_attrs.get('maxspeed', 'N/A')
                if isinstance(maxspeed, list):
                    maxspeed = maxspeed[0] if maxspeed else 'N/A'

                # Get node coordinates
                u_node = graph.nodes[u]
                v_node = graph.nodes[v]
                u_x = u_node.get('x', 0)
                u_y = u_node.get('y', 0)
                v_x = v_node.get('x', 0)
                v_y = v_node.get('y', 0)

                all_data.append({
                    'Route Key': 'Incident',
                    'Segment': 1,
                    'Type': 'Incident Edge',
                    'OSM ID': str(osmid),
                    'From Node': u,
                    'To Node': v,
                    'From X': u_x,
                    'From Y': u_y,
                    'To X': v_x,
                    'To Y': v_y,
                    'Road Name': road_name,
                    'Highway Type': highway_type,
                    'Ref': ref,
                    'Length (m)': length,
                    'Travel Time (s)': edge_attrs.get('travel_time', 0),
                    'Max Speed': str(maxspeed)
                })

    # Add route segments information
    for route_key, route_data in accepted_detours.items():
        path = None
        if 'data' in route_data and len(route_data['data']) >= 4:
            _, _, _, path = route_data['data']
        elif 'path' in route_data:
            path = route_data['path']

        if path and len(path) > 1:
            for i in range(len(path) - 1):
                u, v = path[i], path[i+1]
                if graph.has_edge(u, v):
                    edge_data = graph.get_edge_data(u, v)
                    if edge_data:
                        # Handle edge data structure
                        if isinstance(edge_data, dict):
                            if len(edge_data) > 0:
                                first_key = next(iter(edge_data.keys()))
                                if isinstance(first_key, int):
                                    edge_attrs = edge_data[first_key]
                                elif 'osmid' in edge_data or 'geometry' in edge_data:
                                    edge_attrs = edge_data
                                else:
                                    edge_attrs = next(iter(edge_data.values()))
                            else:
                                edge_attrs = edge_data
                        else:
                            edge_attrs = edge_data

                        # Extract all edge information
                        osmid = edge_attrs.get('osmid', 'N/A')
                        if isinstance(osmid, list):
                            osmid = osmid[0] if osmid else 'N/A'

                        road_name = edge_attrs.get('name', 'Unnamed Road')
                        if isinstance(road_name, list):
                            road_name = road_name[0] if road_name else 'Unnamed Road'

                        highway_type = edge_attrs.get('highway', 'unknown')
                        if isinstance(highway_type, list):
                            highway_type = highway_type[0] if highway_type else 'unknown'

                        ref = edge_attrs.get('ref', '')
                        if isinstance(ref, list):
                            ref = ref[0] if ref else ''

                        length = edge_attrs.get('length', 0)
                        travel_time = edge_attrs.get('travel_time', 0)
                        maxspeed = edge_attrs.get('maxspeed', 'N/A')
                        if isinstance(maxspeed, list):
                            maxspeed = maxspeed[0] if maxspeed else 'N/A'

                        # Get node coordinates
                        u_node = graph.nodes[u]
                        v_node = graph.nodes[v]
                        u_x = u_node.get('x', 0)
                        u_y = u_node.get('y', 0)
                        v_x = v_node.get('x', 0)
                        v_y = v_node.get('y', 0)

                        all_data.append({
                            'Route Key': str(route_key),
                            'Segment': i + 1,
                            'Type': 'Detour Route',
                            'OSM ID': str(osmid),
                            'From Node': u,
                            'To Node': v,
                            'From X': u_x,
                            'From Y': u_y,
                            'To X': v_x,
                            'To Y': v_y,
                            'Road Name': road_name,
                            'Highway Type': highway_type,
                            'Ref': ref,
                            'Length (m)': length,
                            'Travel Time (s)': travel_time,
                            'Max Speed': str(maxspeed)
                        })

    if all_data:
        df = pd.DataFrame(all_data)
        return df.to_csv(index=False)
    else:
        return ""
