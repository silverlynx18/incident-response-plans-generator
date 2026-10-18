"""
Core detour analysis utilities extracted from the notebook.
This module contains all the graph processing, analysis, and visualization logic.
"""

import os
import networkx as nx
import numpy as np
import pandas as pd
import osmnx as ox
import geopandas as gpd
import math
import re
import ast
import random
from typing import (
    Any, Dict, Iterable, List,
    Optional, Set, Tuple, Union, Sequence, Deque
)
from collections import deque
from shapely.geometry import LineString, Point, MultiLineString, Polygon
from shapely.ops import unary_union
from pyproj import CRS, Transformer
import matplotlib.pyplot as plt

# Constants
ESPG = 4326
ROADTYPE_SPEEDS_KPH = {
    "motorway": 100,
    'motorway_link': 95,
    "trunk": 90,
    'trunk_link': 85,
    "primary": 70,
    'primary_link': 65,
    "secondary": 55,
    'secondary_link': 50,
    "tertiary": 50,
    'tertiary_link': 50,
    "residential": 40,
    "service": 30,
    "living_street": 15,
    'crossing': 30,
    'busway': 50,
}
DEFAULT_SPEED_KPH = 50
DEFAULT_SPEED_UNIT = 'mph'

# Graph Import and Cleanup Functions

def load_osm_graph(espg, area_polygon_shp=None, osm_nodes_shp=None, osm_edges_shp=None):
    """
    Constructs graph object of OSM road network and convert it to local coordinate system (espg).
    - If area_polygon_shp is given, it will download all roads within a given polygon
    - If only osm_nodes_shp and osm_edges_shp are given, it will construct a graph from
    - If all three are given, it will download then filter by the list of nodes and edges
        - Any non-null metadata from nodes/edges shp files will be added/overwritten to that of downloaded graph
    """
    # define constants
    NULL_VALUES = [None, 'nan', 'NaN', 'null', 'NULL', 'N/A', 'n/a', np.nan, '', [], '[]']
    EDGES_REQUIRED = ['u', 'v', 'key', 'highway', 'geometry']
    NODES_REQUIRED = ['osmid', 'geometry']

    # input validation
    if (osm_nodes_shp is None) ^ (osm_edges_shp is None):
        raise ValueError(f"Nodes shp file and edges shp file should be either both present or both omitted.")
    if ((area_polygon_shp is None) and (osm_nodes_shp is None)) and (osm_edges_shp is None):
        raise ValueError(f"Either polygon shp file or nodes/edges shp file should be present.")

    # read in edges and nodes (if they exist) and more input validation
    if osm_edges_shp and osm_nodes_shp:

        gdf_edges = gpd.read_file(osm_edges_shp).reset_index(drop=True)
        gdf_nodes = gpd.read_file(osm_nodes_shp).reset_index(drop=True)

        # Reproject if needed
        if gdf_nodes.crs != f"EPSG:{espg}":
            gdf_nodes = gdf_nodes.to_crs(epsg=espg)
        if gdf_edges.crs != f"EPSG:{espg}":
            gdf_edges = gdf_edges.to_crs(epsg=espg)

        if any(col not in gdf_nodes.columns for col in NODES_REQUIRED):
            raise ValueError(f'Nodes shp file does not have all required columns - make sure it has: {NODES_REQUIRED}')
        if any(col not in gdf_edges.columns for col in EDGES_REQUIRED):
            raise ValueError(f'Edges shp file does not have all required columns - make sure it has: {EDGES_REQUIRED}')

    # if area is given, download from area polygon
    if area_polygon_shp is not None:

        gdf_area = gpd.read_file(area_polygon_shp)

        # Reproject if needed
        if gdf_area.crs != f"EPSG:{espg}":
            gdf_area = gdf_area.to_crs(epsg=espg)

        polygon = gdf_area.union_all()

        # Download network from this area
        G = ox.graph_from_polygon(polygon, network_type="drive", simplify=True)

        # Optionally clean up graph using given shp files
        if osm_edges_shp and osm_nodes_shp:

            # filter for nodes and edges
            edges_filter = set((row['u'], row['v'], row['key']) for _, row in gdf_edges.iterrows())
            nodes_filter = set(row['osmid'] for _, row in gdf_nodes.iterrows())

            G_temp = G.copy()
            for u,v,k in G_temp.edges(keys=True):
                if (u,v,k) not in edges_filter:
                    G.remove_edge(u,v,k)
            for node in G_temp.nodes():
                if node not in nodes_filter:
                    G.remove_node(node)

            # update non-null metatada from gdf_nodes into downloaded graph
            node_meta = {row['osmid']: row for _, row in gdf_nodes.iterrows()}
            for node in G.nodes():
                if node in node_meta:
                    geom = node_meta[node]['geometry']
                    enriched_attrs = {
                        col: node_meta[node][col]
                        for col in gdf_nodes.columns
                        if col != 'osmid' and node_meta[node][col] not in NULL_VALUES
                    }
                    enriched_attrs['x'] = float(geom.x)
                    enriched_attrs['y'] = float(geom.y)
                    G.nodes[node].update(enriched_attrs)

            # update non-null metatada from gdf_edges into downloaded graph
            edge_meta = {(row['u'], row['v'], row['key']): row for _, row in gdf_edges.iterrows()}
            for u, v, k in G.edges(keys=True):
                if (u, v, k) in edge_meta:
                    enriched_attrs = {
                        col: edge_meta[(u, v, k)][col]
                        for col in gdf_edges.columns
                        if col not in ['u', 'v', 'key'] and edge_meta[(u, v, k)][col] not in NULL_VALUES
                    }
                    G.edges[u, v, k].update(enriched_attrs)

    # if only nodes and edges are given, construct graph from scratch
    else:
        # Create graph and set CRS
        G = nx.MultiDiGraph()
        G.graph['crs'] = gdf_nodes.crs

        # Add nodes with metadata
        for _, row in gdf_nodes.iterrows():
            node_id = row['osmid']
            geom = row['geometry']

            node_attrs = {col: row[col] for col in gdf_nodes.columns if col != 'osmid' and row[col] not in NULL_VALUES}
            node_attrs['x'] = geom.x
            node_attrs['y'] = geom.y

            G.add_node(node_id, **node_attrs)

        # Add edges with metadata
        for _, row in gdf_edges.iterrows():
            u = row['u']
            v = row['v']
            key = row['key'] if 'key' in row else 0

            # Only add edge if both nodes exist
            if u in G.nodes and v in G.nodes:
                edge_attrs = {col: row[col] for col in gdf_edges.columns if col not in ['u', 'v', 'key'] and row[col] not in NULL_VALUES}
                G.add_edge(u, v, key=key, **edge_attrs)
            else:
                print(f"Skipping edge ({u}, {v}) — missing node(s)")

    return G


def normalize_list_string(value):
    """
    Normalize a string or list-like input into a flat, deduplicated Python list.
    Preserves original values if not list-like.

    Examples:
    - "[1, 2, 3]" → [1, 2, 3]
    - "a;b;c" → ['a', 'b', 'c']
    - ['I 95;US 17', 'US 17'] → ['I 95', 'US 17']
    - "foo" → "foo"
    - ["x", "y"] → ["x", "y"]
    """

    def split_and_strip(item):
        if isinstance(item, str) and ';' in item:
            return [part.strip() for part in item.split(';') if part.strip()]
        return [item]

    if isinstance(value, list):
        flattened = []
        for item in value:
            flattened.extend(split_and_strip(item))
        # Remove duplicates while preserving order
        seen = set()
        deduped = []
        for item in flattened:
            if item not in seen:
                seen.add(item)
                deduped.append(item)
        return deduped

    if isinstance(value, str):
        cleaned = value.strip()
        try:
            parsed = ast.literal_eval(cleaned)
            if isinstance(parsed, list):
                return normalize_list_string(parsed)
        except (ValueError, SyntaxError):
            pass

        if ';' in cleaned:
            return list(dict.fromkeys(part.strip() for part in cleaned.split(';') if part.strip()))

    return value


def calculate_linestring_length(line: LineString, transformer: Transformer | None = None) -> float:
    """
    Calculates the length of a LineString in meters.
    If a transformer is provided, it will be used to project the geometry.
    """
    if transformer:
        projected_coords = [transformer.transform(x, y) for x, y in line.coords]
        projected_line = LineString(projected_coords)
        return projected_line.length
    else:
        return line.length


def normalize_speed_to_kph(speed_str, default_unit='km/h'):
    """
    Normalize a speed string to kilometers per hour (kph).

    Parameters:
    - speed_str (str): Input string like '50', '50 km/h', '100 mph', etc.
    - default_unit (str): Unit to assume if none is found or recognized. Default is 'km/h'.

    Returns:
    - float: Speed in kilometers per hour.
    """
    unit_conversion = {
        'km/h': 1.0,
        'kilometersperhour': 1.0,
        'kilometers/hour': 1.0,
        'kilometers/h': 1.0,
        'kph': 1.0,
        'kmph': 1.0,
        'mph': 1.60934,
        'miph': 1.60934,
        'milesperhour': 1.60934,
        'miles/hour': 1.60934,
        'miles/h': 1.60934,
        'mi/h': 1.60934,
        'm/s': 3.6,
        'meter/sec': 3.6,
        'mps': 3.6,
        'knots': 1.852,
        'kt': 1.852,
    }

    # Remove all spaces from the input string
    cleaned = speed_str.replace(" ", "").lower()

    # Use regex to extract number and unit
    match = re.match(r'^([\d.]+)([a-zA-Z/]+)?$', cleaned)
    if not match:
        raise ValueError(f"Could not parse speed string: '{speed_str}'")

    value = float(match.group(1))
    unit = match.group(2) or default_unit.lower().replace(" ", "")

    # Convert using the unit conversion dictionary
    if unit in unit_conversion:
        return value * unit_conversion[unit]
    else:
        fallback_unit = default_unit.lower().replace(" ", "")
        if fallback_unit not in unit_conversion:
            raise ValueError(f"Unrecognized default unit: '{default_unit}'")
        return value * unit_conversion[fallback_unit]


def normalize_ref(ref):
    """Normalize the 'ref' attribute to a set of strings."""
    if ref is None:
        return set()
    if isinstance(ref, str):
        return set(ref.split(','))
    if isinstance(ref, list):
        return set(ref)
    return set([str(ref)])


def clean_graph(G_input):
    """
    - Perform all normalizations and cleanups to loaded graph
    - Perform all validation
    """
    G = G_input.copy()

    true_values = {'true', 'True', 'TRUE'}
    false_values = {'false', 'False', 'FALSE'}

    # Normalize node attributes
    for node, node_data in G.nodes(data=True):

        # convert string representations into list and boolean
        for key, value in node_data.items():
            normalized_value = normalize_list_string(value)
            node_data[key] = normalized_value

            if isinstance(normalized_value, str):
                if normalized_value in true_values:
                    node_data[key] = True
                elif normalized_value in false_values:
                    node_data[key] = False

    # precompute coordinate transformer
    crs = CRS.from_epsg(ESPG)
    transformer = None

    if crs.is_geographic:
        # Estimate UTM zone from graph centroid
        all_coords = [data.get('geometry').centroid for _, _, _, data in G.edges(keys=True, data=True) if data.get('geometry')]
        if all_coords:
            avg_centroid = unary_union(all_coords).centroid
            utm_zone = int((avg_centroid.x + 180) / 6) + 1
            utm_crs = CRS.from_proj4(f"+proj=utm +zone={utm_zone} +datum=WGS84 +units=m +no_defs")
            transformer = Transformer.from_crs(crs, utm_crs, always_xy=True)

    # Normalize edge attributes
    for u, v, k, edge_data in G.edges(keys=True, data=True):
        # convert string representations into list and boolean
        for key, value in edge_data.items():
            normalized_value = normalize_list_string(value)
            edge_data[key] = normalized_value
            if isinstance(normalized_value, str):
                if normalized_value in true_values:
                    edge_data[key] = True
                elif normalized_value in false_values:
                    edge_data[key] = False

        # normalize ref into set
        edge_data['ref'] = normalize_ref(edge_data.get('ref'))

        # normalize geometry
        if not edge_data.get('geometry'):
            fallback_geom = LineString(
                [(G.nodes[u]["x"], G.nodes[u]["y"]), (G.nodes[v]["x"], G.nodes[v]["y"])]
            )
            edge_data['geometry'] = fallback_geom

        # normalize length
        geom = edge_data.get('geometry')
        meter_length = calculate_linestring_length(geom, transformer)
        edge_data.update({'length': meter_length})

        # normalize maxspeed to kilometers per hour
        # if maxspeed is missing, infer by roadtype or else fall back to DEFAULT_SPEED_KPH
        ms = edge_data.get("maxspeed")
        if not ms:
            hw = edge_data.get("highway")
            if isinstance(hw, (list, tuple)) and hw:
                hw = hw[0]
            ms = ROADTYPE_SPEEDS_KPH.get(hw, DEFAULT_SPEED_KPH)
        else:
            if isinstance(ms, (list, tuple)) and ms:
                ms = ms[0]
            ms = normalize_speed_to_kph(str(ms), DEFAULT_SPEED_UNIT)
        edge_data['maxspeed'] = ms

    return G


# Graph Analysis Preparation Functions

def calculate_bearings(line):
    def bearing(pointA, pointB):
        lat1 = math.radians(pointA[1])
        lat2 = math.radians(pointB[1])
        diffLong = math.radians(pointB[0] - pointA[0])

        x = math.sin(diffLong) * math.cos(lat2)
        y = math.cos(lat1) * math.sin(lat2) - (
            math.sin(lat1) * math.cos(lat2) * math.cos(diffLong)
        )

        initial_bearing = math.atan2(x, y)

        # Convert bearing from radians to degrees
        initial_bearing = math.degrees(initial_bearing)

        # Normalize the bearing to be between 0 and 360 degrees
        compass_bearing = (initial_bearing + 360) % 360

        return compass_bearing

    # Get the start and end bearings
    coords = line.coords
    start_bearing = bearing(coords[0], coords[1])
    end_bearing = bearing(coords[-2], coords[-1])

    return start_bearing, end_bearing


def compute_traveltime_bearing(G_input: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """
    Compute travel time and bearings for all edges in the graph.
    """
    G = G_input.copy()

    # Compute travel_time and bearings
    for u, v, k, data in G.edges(keys=True, data=True):

        # travel_time in seconds
        speed_mps = data.get('maxspeed') * 0.27777778   # from kph to mps
        length_m = data.get("length", 0.0)
        data["travel_time"] = length_m / speed_mps

        geom = data.get("geometry") or LineString(
            [(G.nodes[u]["x"], G.nodes[u]["y"]), (G.nodes[v]["x"], G.nodes[v]["y"])]
        )
        sb, eb = calculate_bearings(geom)
        data["start_bearing"] = sb
        data["end_bearing"] = eb

    return G


def compute_turntime(G_input):
    """
    Add penalty to each edge based on the cumulative time cost to enter the edge, punishing sharp turns and complex intersections
    - cost function is based on difference between incident and exit angles of each inbound edged to a chosen edge
    - function is (120 / 180^2) * (angle_diff^2), mapping to 2 extra minutes for a U-turn
    - this cost function is computed for each inbound edge into the chosen edge, and cumulative results added to travel_time of chosen edge
    """
    G = G_input.copy()

    for u, v, k, departure_data in G.edges(keys=True, data=True):
        departure_angle = departure_data['start_bearing']

        incoming_edges = list(G.in_edges(u, keys=True, data=True))
        turn_time = 0
        for a, b, c, approach_data in incoming_edges:
            approach_angle = approach_data['end_bearing']

            if approach_angle and departure_angle:
                angle_diff = abs(approach_angle - departure_angle)
                angle_diff = min(angle_diff, 360 - angle_diff)
            else:
                angle_diff = 0   # no penalty if value cannot be calculated

            turn_time += (120 / (180**2)) * (angle_diff ** 2)         # maps to 2 extra minutes for 180 degree turns

        if incoming_edges:
            G[u][v][k]['turn_time'] = turn_time / len(incoming_edges)   # normalize to number of incoming edges
        else:
            G[u][v][k]['turn_time'] = 0

        G[u][v][k]['total_time'] = G[u][v][k]['travel_time'] + G[u][v][k]['turn_time']

    return G


def find_turns(G_input, specific_nodes=None):
    """
    For each node, identify valid turns where the incoming and outgoing edges belong to different roads.
    Assumes all edge 'ref' attributes are sets of strings.
    A turn is valid if:
    - the 'ref' sets of the incoming and outgoing edges are not equal.
    - the number of in edges or out edges is above 1.

    each turn is encoded as ({in edge index}, {in edge ref}, {out edge index}, {out edge ref})
    """
    G = G_input.copy()

    if specific_nodes:
        iter_nodes = [(node, G.nodes[node]) for node in specific_nodes]
    else:
        iter_nodes = G.nodes(data=True)

    results = {}

    for node, node_data in iter_nodes:
        turns = []
        in_edges = list(G.in_edges(node, keys=True, data=True))
        out_edges = list(G.out_edges(node, keys=True, data=True))

        for ui, vi, ki, data_in in in_edges:
            ref_in = data_in.get('ref', set())
            for uo, vo, ko, data_out in out_edges:
                ref_out = data_out.get('ref', set())

                if (ref_in != ref_out) and (len(in_edges) > 1 or len(out_edges) > 1):
                    turns.append(((ui, vi, ki), ref_in, (uo, vo, ko), ref_out))

        if specific_nodes:
            results[node] = turns
        else:
            G.nodes[node]['turns'] = turns

    return results if specific_nodes else G


def prepare_graph(G_input):
    """
    Prepare graph for analysis by computing travel times, bearings, turn times, and finding turns.
    """
    G = G_input.copy()

    G = compute_traveltime_bearing(G)
    G = compute_turntime(G)
    G = find_turns(G)

    return G


# Finding on/off ramps given incident

def bearing_diff(b1, b2):
    """Compute circular bearing difference."""
    return min(abs(b1 - b2), 360 - abs(b1 - b2))


def has_common_ref(ref1, ref2):
    """Check if two ref sets have any common elements."""
    # Convert to sets if they're strings or other types
    if not isinstance(ref1, set):
        ref1 = {ref1} if ref1 else set()
    if not isinstance(ref2, set):
        ref2 = {ref2} if ref2 else set()

    return bool(ref1 & ref2)


def is_valid_turn(turns, reference_ref, visited, forward=True):
    """Check if any turn is valid based on ref and visited node constraints."""
    for in_edge, in_ref, out_edge, out_ref in turns:
        if forward:
            if in_ref != reference_ref and not in_edge[0] in visited:
                return True
        else:
            if out_ref != reference_ref and not out_edge[1] in visited:
                return True
    return False


def traverse_direction(G, edge, n, forward=True):
    """Traverse in one direction from the given edge (u, v, k)."""

    visited = set()
    visited_edges = set()
    turns_nodes = []
    avoid_u, avoid_k,_ = edge
    current_edge = edge
    reference_ref = G.edges[current_edge].get('ref', set())

    while len(turns_nodes) < n:
        u, v, k = current_edge
        next_node = v if forward else u

        if next_node in visited:
            break
        visited.add(next_node)
        visited_edges.add(current_edge)
        node_turns = G.nodes[next_node].get('turns', [])
        if node_turns and is_valid_turn(node_turns, reference_ref, visited, forward):
            turns_nodes.append(next_node)

        # Get candidate edges
        if forward:
            candidates = [(next_node, tgt, key, G[next_node][tgt][key])
                          for tgt in G.successors(next_node)
                          for key in G[next_node][tgt]]
        else:
            candidates = [(src, next_node, key, G[src][next_node][key])
                          for src in G.predecessors(next_node)
                          for key in G[src][next_node]]

        if not candidates:
            break

        # Filter out edges with no common ref
        candidates = [e for e in candidates if has_common_ref(e[3].get('ref', set()), reference_ref)]
        if not candidates:
            break

        if len(candidates) == 1:
            current_edge = candidates[0][:3]
            continue

        # Choose edge with closest bearing
        current_bearing = G.edges[current_edge]['end_bearing'] if forward else G.edges[current_edge]['start_bearing']

        def bearing_key(e):
            edge_bearing = e[3]['start_bearing'] if forward else e[3]['end_bearing']
            return bearing_diff(current_bearing, edge_bearing)

        best_edge = min(candidates, key=bearing_key)
        current_edge = best_edge[:3]

    return [node for node in turns_nodes if node not in [avoid_u, avoid_k]], visited_edges


def get_surrounding_turns(G, incident_edge, n, m=None):
    """
    Traverse both directions from a given edge (u, v, k) to find up to n valid 'turns' nodes.
    - this is used for traffic that is on the same road as incident and want to join back the road downstream
    """
    m = n if m is None else m
    forward_nodes, forward_edges = traverse_direction(G, incident_edge, n, forward=True)
    backward_nodes, backward_edges = traverse_direction(G, incident_edge, m, forward=False)
    return backward_nodes, forward_nodes, backward_edges, forward_edges


# Finding Detours

def create_sector(center, bearing_deg, radius_m, angle_deg, num_points=30):
    """
    Create a sector (wedge) polygon centered at `center` (lon, lat),
    oriented in the reverse direction of `bearing_deg`, with given radius and angle.
    All coordinates are in EPSG:4326.
    """
    # Reverse bearing to fan backward
    reverse_bearing = (bearing_deg + 180) % 360
    half_angle = angle_deg / 2

    # Convert meters to degrees (approximate near equator)
    radius_deg = radius_m / 111320

    # Generate points along the arc
    arc_points = []
    for i in range(num_points + 1):
        angle = reverse_bearing - half_angle + i * (angle_deg / num_points)
        angle_rad = math.radians(angle)
        dx = radius_deg * math.sin(angle_rad)
        dy = radius_deg * math.cos(angle_rad)
        arc_points.append((center.x + dx, center.y + dy))

    # Close the sector polygon
    arc_points.insert(0, (center.x, center.y))
    arc_points.append((center.x, center.y))

    return Polygon(arc_points)


def get_impacted_arterials(G, incident_edge, distance=None, angle=None, custom_shape=None):
    """Find edges that intersect an arc sector (or custom geometry) and connect to the incident edge without backtracking."""
    seen_edges = set()
    impacted_edges = set()

    # Get incident edge geometry and bearing
    geom = G.edges[incident_edge].get('geometry')
    bearing = G.edges[incident_edge].get('start_bearing')
    center = Point(geom.coords[0])
    start_node = incident_edge[0]

    # Create arc sector
    if not custom_shape:
        arc = create_sector(center, bearing, distance, angle)
    else:
        if center not in custom_shape:
            raise ValueError('Starting point of incident edge must be included in the custom geometry.')
        arc = Polygon(custom_shape)

    # Find candidate edges intersecting the arc
    candidates = []
    for u, v, k, data in G.edges(keys=True, data=True):
        edge_geom = data.get('geometry')
        if edge_geom and edge_geom.intersects(arc):
            dist = center.distance(edge_geom)
            candidates.append(((u, v, k), dist))

    # Sort candidates from farthest to closest
    candidates.sort(key=lambda x: -x[1])

    for edge, _ in candidates:
        if edge in seen_edges:
            continue

        try:
            # Get shortest path from candidate edge's target node to incident edge's start node
            path_nodes = nx.shortest_path(G, source=edge[1], target=start_node)

            # Convert to edge path
            edge_path = []
            for i in range(len(path_nodes) - 1):
                for k in G[path_nodes[i]][path_nodes[i+1]]:
                    edge_path.append((path_nodes[i], path_nodes[i+1], k))

            # Discard path if it includes the incident edge
            if incident_edge in edge_path:
                continue

            # Filter path to only include contiguous segment within arc and connected to start_node
            arc_subpath = []
            for e in reversed(edge_path):  # reverse to start from start_node
                edge_geom = G.edges[e].get('geometry')
                if edge_geom and edge_geom.intersects(arc):
                    arc_subpath.append(e)
                else:
                    break  # stop at first edge outside arc

            impacted_edges.update(arc_subpath)
            seen_edges.update(arc_subpath)

        except nx.NetworkXNoPath:
            continue

    if incident_edge in impacted_edges:
        impacted_edges.remove(incident_edge)

    return impacted_edges, arc


def generate_incident_graph(G_input, incident_edge, exact_match=True):
    """
    Using output from get_surrounding_turns, set travel time to max for all edges visited during on/off ramp search
    - This is to prevent further pathfinding to include the mainline near the incident
    """
    G = G_input.copy()

    to_match = G.edges[incident_edge].get('ref')
    max_limit = 1e9
    for edge in G_input.edges(keys=True):
        comparison = G.edges[edge].get('ref')
        if exact_match:
            if to_match == comparison:
                G.edges[edge]['total_time'] = max_limit
        else:
            if to_match & comparison:
                G.edges[edge]['total_time'] = max_limit
    return G


def get_detour(G_input, incident_edge, start_nodes, end_nodes, traveltime_min, traveltime_max):
    """
    Find detour routes between start and end nodes, avoiding the incident edge.
    """
    G = G_input.copy()

    # delete incident edge to extra make sure detour is not made through here
    edges_to_remove = G_input.edges(incident_edge[0], incident_edge[1], keys=True)
    G.remove_edges_from(edges_to_remove)

    # get detours
    shortest_paths = {}
    for start in start_nodes:
        for end in end_nodes:
            if start != end:
                try:
                    # get shortest detour given starting and end points, bounding the travel times between 3-30 min
                    total_time, path = nx.single_source_dijkstra(G, source=start, target=end, weight='total_time')

                    # get travel time assuming freeflow state
                    freeflow_time = 0
                    for i in range(len(path) - 1):
                        u, v = path[i], path[i + 1]
                        for k in G[u][v]:
                            edge_data = G[u][v][k]
                            tt = edge_data.get('travel_time', 0)
                            freeflow_time += tt
                            break  # only get first edge

                    route = (True, total_time, freeflow_time, path)
                    if freeflow_time < traveltime_min:
                        route = (False, 'Too Short', 'Too Short', None)
                    elif freeflow_time > traveltime_max:
                        route = (False, 'Too Long', 'Too Long', None)
                    elif total_time >= 1e9:
                        route = (False, 'Needs Mainline', 'Needs Mainline', None)
                except:
                    route = (False, 'No Route', 'No Route', None)
                shortest_paths[(start, end)] = route

    return shortest_paths


# Visualization Functions

def draw_graph_selections(
    G,
    subgraph=None,
    nodes_list_of_list=None,
    highlight_edges=None,
    node_label=True,
    zoom_factor=1,
    custom_geometries=None  # NEW: list of Shapely geometries to plot
):
    """
    Draw graph with various selections highlighted.
    """
    import matplotlib.pyplot as plt
    import osmnx as ox

    color_list = [
        '#1f77b4', '#9467bd', '#8c564b',
        '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'
    ]

    fig, ax = ox.plot_graph(
        G,
        show=False,
        close=False,
        edge_color="gray",
        edge_alpha=0.3,
        node_size=0
    )

    if subgraph:
        ox.plot_graph(
            subgraph,
            ax=ax,
            show=False,
            close=False,
            edge_color="orange",
            edge_alpha=0.3,
            node_size=0
        )

    min_x, min_y = float('inf'), float('inf')
    max_x, max_y = float('-inf'), float('-inf')

    # Plot highlight edges using their geometry
    if highlight_edges:
        for u, v, k in highlight_edges:
            geom = G.edges[u, v, k].get('geometry')
            if geom:
                x, y = geom.xy
                ax.plot(x, y, color="red", linewidth=2)
                min_x = min(min_x, min(x))
                max_x = max(max_x, max(x))
                min_y = min(min_y, min(y))
                max_y = max(max_y, max(y))

            for node in [u, v]:
                x = G.nodes[node]['x']
                y = G.nodes[node]['y']
                ax.plot(x, y, 'go', markersize=2)
                if node_label:
                    ax.annotate(str(node), (x, y), color='white')
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)

    # Plot node selections
    if nodes_list_of_list:
        for ind, highlight_nodes in enumerate(nodes_list_of_list):
            for n in highlight_nodes:
                x = G.nodes[n]['x']
                y = G.nodes[n]['y']
                ax.plot(x, y, 'o', color=color_list[ind % len(color_list)], markersize=4)
                if node_label:
                    ax.annotate(str(n), (x, y), color='white')
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)

    # Plot custom geometries (e.g., arc sector)
    if custom_geometries:
        for geom in custom_geometries:
            if geom.geom_type == 'Polygon':
                x, y = geom.exterior.xy
                ax.plot(x, y, color='blue', linewidth=2, linestyle='--')
                min_x = min(min_x, min(x))
                max_x = max(max_x, max(x))
                min_y = min(min_y, min(y))
                max_y = max(max_y, max(y))
            elif geom.geom_type == 'LineString':
                x, y = geom.xy
                ax.plot(x, y, color='blue', linewidth=2, linestyle='--')
                min_x = min(min_x, min(x))
                max_x = max(max_x, max(x))
                min_y = min(min_y, min(y))
                max_y = max(max_y, max(y))

    # Zoom to selection
    x_buffer = max(abs(max_x - min_x) / 3, 0.02) / zoom_factor
    y_buffer = max(abs(max_y - min_y) / 3, 0.02) / zoom_factor
    ax.set_xlim(min_x - x_buffer, max_x + x_buffer)
    ax.set_ylim(min_y - y_buffer, max_y + y_buffer)

    return fig


def get_route_bounds(route, G):
    """Get bounding box for a route."""
    nodes = [G.nodes[node] for node in route]
    lats = [node['y'] for node in nodes]
    lngs = [node['x'] for node in nodes]
    return min(lats), max(lats), min(lngs), max(lngs)


def plot_detour(G, route, flooded_edge, save_name=None, edge_osm_id=''):
    """
    Plot a detour route with the incident edge highlighted.
    """
    # plot the route and incident edge
    u, v, key = flooded_edge
    if route:
        fig, ax = ox.plot_graph_routes(
            G, [route, [u,v]], route_colors=['red', 'purple'],
            route_linewidths=3, node_size=0, orig_dest_size=3, bgcolor='lightgray', show=False, close=False
        )

        # plot the start and end point
        x = G.nodes[route[0]]['x']
        y = G.nodes[route[0]]['y']
        ax.plot(x, y, 'ro', label='start')

        x = G.nodes[route[-1]]['x']
        y = G.nodes[route[-1]]['y']
        ax.plot(x, y, 'go', label='end')

        # Get the bounds of the route
        min_lat, max_lat, min_lng, max_lng = get_route_bounds(route, G)

        # Set the axis limits to zoom to the route
        x_buffer = abs((min_lng - max_lng)) / 3
        y_buffer = abs((min_lat - max_lat)) / 3
    else:
        fig, ax = ox.plot_graph_route(
            G, [u,v], route_color='purple',
            route_linewidth=3, node_size=0, orig_dest_size=3, bgcolor='lightgray', show=False, close=False
        )

        x = G.nodes[u]['x']
        y = G.nodes[u]['y']
        ax.plot(x, y, 'o', color='purple', label='no detour found')

        # Get the bounds of the route
        min_lat, max_lat, min_lng, max_lng = get_route_bounds([u,v], G)

        # Set the axis limits to show more context for around detour
        x_buffer = 0.05
        y_buffer = 0.05

    ax.set_xlim([min_lng - x_buffer, max_lng + x_buffer])
    ax.set_ylim([min_lat - y_buffer, max_lat + y_buffer])

    if edge_osm_id:
        plt.title(f'Detour for edge OSMID: {edge_osm_id}')
    else:
        plt.title(f'Detour for edge index: {flooded_edge}')

    # Turn figure frame on and save to disk
    fig.set_frameon(True)
    plt.legend(loc='best')
    if save_name:
        plt.savefig(save_name)
        plt.close()
    else:
        return fig
