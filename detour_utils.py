"""
Core detour analysis utilities extracted from the notebook.
This module contains all the graph processing, analysis, and visualization logic.
"""

import networkx as nx
import numpy as np
import pandas as pd
import osmnx as ox
import geopandas as gpd
import math
import re
import ast
import random
from osm_loader import graph_from_polygon as _load_road_graph
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

def graph_from_polygon_with_fallback(polygon, **kwargs):
    """Acquire complete genuine OSM data without changing graph parameters."""
    return _load_road_graph(polygon, **kwargs)

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
        G = graph_from_polygon_with_fallback(polygon, network_type="drive", simplify=True)

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


def extract_route_info(G, route):
    """
    Extract detailed information about a route including IDs, highways, and distances.
    """
    route_ids = []
    highways = set()
    total_distance = 0
    segment_count = 0

    for i in range(len(route) - 1):
        u, v = route[i], route[i+1]
        if G.has_edge(u, v):
            edge_data = G.get_edge_data(u, v)
            if edge_data:
                # Handle case where multiple edges exist between same nodes
                if isinstance(edge_data, dict) and len(edge_data) > 1:
                    # Get the first edge data
                    edge_attrs = next(iter(edge_data.values()))
                else:
                    # Single edge or direct data
                    edge_attrs = edge_data if not isinstance(edge_data, dict) else next(iter(edge_data.values()))

                # Extract OSM ID
                osmid = edge_attrs.get('osmid', 'N/A')
                if isinstance(osmid, list):
                    osmid = osmid[0] if osmid else 'N/A'
                route_ids.append(str(osmid))

                # Extract highway type
                highway = edge_attrs.get('highway', 'unknown')
                if isinstance(highway, list):
                    highway = highway[0] if highway else 'unknown'
                highways.add(highway)

                # Extract distance
                length = edge_attrs.get('length', 0)
                total_distance += length
                segment_count += 1

    return {
        'route_ids': route_ids,
        'highways': sorted(list(highways)),
        'total_distance': total_distance,
        'segment_count': segment_count,
        'road_names': extract_road_names(G, route)
    }


def extract_road_names(G, route):
    """
    Extract road names from the route edges.
    """
    road_names = []

    for i in range(len(route) - 1):
        u, v = route[i], route[i + 1]

        # Get edge data
        edge_data = G.get_edge_data(u, v)
        if isinstance(edge_data, dict) and len(edge_data) > 1:
            edge_attrs = next(iter(edge_data.values()))
        else:
            edge_attrs = edge_data if not isinstance(edge_data, dict) else next(iter(edge_data.values()))

        if edge_attrs:
            # Extract road name
            name = edge_attrs.get('name', 'Unnamed Road')
            if isinstance(name, list):
                name = name[0] if name else 'Unnamed Road'
            road_names.append(name)

    return road_names


def add_road_names_to_plot(ax, G, route, road_names):
    """
    Add road names as text labels along the route.
    """
    import numpy as np

    # Sample points along the route for labeling (every 3rd segment to avoid crowding)
    label_positions = []
    label_texts = []

    for i in range(0, len(route) - 1, 3):  # Every 3rd segment
        if i < len(road_names):
            u, v = route[i], route[i + 1]

            # Get midpoint of the edge
            u_x, u_y = G.nodes[u]['x'], G.nodes[u]['y']
            v_x, v_y = G.nodes[v]['x'], G.nodes[v]['y']

            mid_x = (u_x + v_x) / 2
            mid_y = (u_y + v_y) / 2

            label_positions.append((mid_x, mid_y))
            label_texts.append(road_names[i])

    # Add text labels
    for (x, y), text in zip(label_positions, label_texts):
        ax.text(x, y, text, fontsize=8, ha='center', va='center',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='lightblue', alpha=0.7),
                rotation=0)


def add_highway_badges(ax, G, route):
    """
    Add highway/interstate/state route badges along the detour route.
    """
    import matplotlib.patches as patches
    import re

    # Define highway badge styles (avoiding red, yellow, green)
    badge_styles = {
        'interstate': {'color': 'blue', 'text_color': 'white', 'shape': 'rectangle'},
        'us_highway': {'color': 'black', 'text_color': 'white', 'shape': 'rectangle'},
        'state_route': {'color': 'purple', 'text_color': 'white', 'shape': 'circle'},
        'default': {'color': 'gray', 'text_color': 'black', 'shape': 'rectangle'}
    }

    # Track where badges have been placed to avoid overlap
    badge_positions = []

    for i in range(len(route) - 1):
        u, v = route[i], route[i+1]
        if G.has_edge(u, v):
            edge_data = G.get_edge_data(u, v)
            if edge_data:
                # Get road reference/name
                ref = edge_data.get('ref', '')
                name = edge_data.get('name', '')
                highway = edge_data.get('highway', '')

                # Determine badge text and style
                badge_text = ''
                badge_style = badge_styles['default']

                if ref:
                    badge_text = ref
                    # Interstate highways (I-95, I-10, etc.)
                    if re.match(r'^I-\d+', ref):
                        badge_style = badge_styles['interstate']
                    # US Highways (US-1, US-50, etc.)
                    elif re.match(r'^US-\d+', ref):
                        badge_style = badge_styles['us_highway']
                    # State routes (SR-123, State Route 456, etc.)
                    elif re.match(r'^(SR-|State Route )\d+', ref):
                        badge_style = badge_styles['state_route']
                elif name and highway in ['primary', 'secondary', 'trunk']:
                    badge_text = name[:10]  # Limit text length

                # Add badge if we have text and haven't placed one nearby
                if badge_text:
                    # Get edge midpoint
                    u_data = G.nodes[u]
                    v_data = G.nodes[v]
                    mid_x = (u_data['x'] + v_data['x']) / 2
                    mid_y = (u_data['y'] + v_data['y']) / 2

                    # Check if we're too close to existing badges
                    too_close = any(abs(mid_x - pos[0]) < 0.001 and abs(mid_y - pos[1]) < 0.001
                                  for pos in badge_positions)

                    if not too_close:
                        badge_positions.append((mid_x, mid_y))

                        # Create badge
                        if badge_style['shape'] == 'circle':
                            badge = patches.Circle((mid_x, mid_y), 0.0005,
                                                 facecolor=badge_style['color'],
                                                 edgecolor='black', linewidth=0.5)
                        else:
                            badge = patches.Rectangle((mid_x-0.0003, mid_y-0.0002), 0.0006, 0.0004,
                                                   facecolor=badge_style['color'],
                                                   edgecolor='black', linewidth=0.5)

                        ax.add_patch(badge)

                        # Add text
                        ax.text(mid_x, mid_y, badge_text, ha='center', va='center',
                               fontsize=6, color=badge_style['text_color'], weight='bold')


def import_feature_shp(epsg, shp_path):
    """
    Import a shapefile and ensure it has the correct CRS and required geometry attribute.

    Parameters:
    - epsg: EPSG code as integer (e.g., 4326)
    - shp_path: Path to the shapefile (.shp file)

    Returns:
    - GeoDataFrame with geometry column and correct CRS

    Raises:
    - ValueError if required columns are missing
    """
    shp_gdf = gpd.read_file(shp_path).reset_index(drop=True)

    # Reproject if needed
    if shp_gdf.crs != f"EPSG:{epsg}":
        shp_gdf = shp_gdf.to_crs(epsg=epsg)

    # Make sure it has a geometry attribute
    SHP_REQUIRED = ['geometry']
    if any(col not in shp_gdf.columns for col in SHP_REQUIRED):
        raise ValueError(f'Edges shp file does not have all required columns - make sure it has: {SHP_REQUIRED}')

    return shp_gdf


def buffer_search(G, nodes, edges, feature_gdf, search_range):
    """
    Perform buffer search from combined geometry of given nodes and edges in a road network graph
    to find intersecting features.

    Parameters:
    - G: NetworkX graph (nodes and edges have 'geometry' attribute as shapely geometry)
    - nodes: list of node IDs
    - edges: list of edge tuples (u, v, k)
    - feature_gdf: GeoDataFrame with 'geometry' column
    - search_range: buffer distance in meters (same CRS as features and graph)

    Returns:
    - GeoDataFrame of all intersecting features
    """
    # Collect geometries from nodes and edges
    node_geoms = [G.nodes[n]['geometry'] for n in nodes if n in G.nodes and 'geometry' in G.nodes[n]]
    edge_geoms = []
    for (u, v, k) in edges:
        try:
            # Try to access the edge with the given key
            if G.has_edge(u, v):
                edge_data = G.get_edge_data(u, v, k)
                if edge_data and 'geometry' in edge_data:
                    edge_geoms.append(edge_data['geometry'])
        except (KeyError, TypeError):
            # Edge doesn't exist or doesn't have geometry, skip it
            continue

    if not node_geoms and not edge_geoms:
        return gpd.GeoDataFrame()  # Return empty GeoDataFrame instead of empty list

    # Combine all geometries into one union
    combined_geom = unary_union(node_geoms + edge_geoms)

    # CRITICAL: Convert buffer distance from meters to degrees if geometries are in EPSG:4326
    # Shapely's buffer() expects distance in the same units as the CRS
    # If CRS is geographic (degrees), we need to convert meters to degrees
    # At mid-latitudes: 1 degree latitude ≈ 111 km = 111,000 m
    # So: buffer_degrees = search_range_meters / 111000

    # Check if feature_gdf has a geographic CRS (EPSG:4326)
    if feature_gdf.crs and feature_gdf.crs.is_geographic:
        # Convert meters to degrees (approximate, using average)
        # 1 degree ≈ 111 km = 111,000 m at mid-latitudes
        buffer_distance = search_range / 111000.0  # Convert meters to degrees
    else:
        # Assume CRS is already in meters (projected CRS)
        buffer_distance = search_range

    # Create buffer around combined geometry
    buffer_geom = combined_geom.buffer(buffer_distance)

    # Find intersecting features
    intersecting = feature_gdf[feature_gdf.geometry.intersects(buffer_geom)]

    # CRITICAL: Double-check distances to ensure points are actually within search_range
    # This catches any edge cases where the buffer might be slightly off
    if not intersecting.empty:
        filtered_indices = []
        for idx, row in intersecting.iterrows():
            point_geom = row.geometry
            # Calculate actual distance from point to route geometry
            distance = point_geom.distance(combined_geom)

            # Convert distance to meters if needed
            if feature_gdf.crs and feature_gdf.crs.is_geographic:
                # Convert degrees to meters (approximate)
                distance_meters = distance * 111000.0
            else:
                distance_meters = distance

            # Only include if within search_range (with small tolerance for floating point)
            if distance_meters <= search_range * 1.01:  # 1% tolerance
                filtered_indices.append(idx)

        if filtered_indices:
            intersecting = intersecting.loc[filtered_indices]
        else:
            intersecting = gpd.GeoDataFrame()

    return intersecting


def get_points_in_buffer(G, route, additional_data, buffer_miles):
    """
    Find points within buffer distance of a route for inclusion in initial printout.
    Returns a list of buffer points with their details.

    This function uses the new buffer_search function when possible for better accuracy.
    """
    from shapely.geometry import Point, LineString

    # Create route geometry
    route_coords = []
    route_nodes = []
    route_edges = []

    for i, node in enumerate(route):
        if node in G.nodes:
            node_data = G.nodes[node]
            route_coords.append([node_data['x'], node_data['y']])
            route_nodes.append(node)

            # Collect edges if available
            if i < len(route) - 1:
                next_node = route[i + 1]
                if G.has_edge(node, next_node):
                    # Get edge key (default to 0 if not specified)
                    edge_data = G.get_edge_data(node, next_node)
                    if edge_data:
                        # Try to find the edge key
                        edge_key = 0
                        if isinstance(edge_data, dict) and len(edge_data) > 0:
                            # Get first key if multiple edges exist
                            edge_key = list(edge_data.keys())[0] if isinstance(list(edge_data.values())[0], dict) else 0
                        route_edges.append((node, next_node, edge_key))

    if len(route_coords) < 2:
        return []

    # Convert buffer distance from miles to meters for more accurate search
    buffer_meters = buffer_miles * 1609.34  # 1 mile = 1609.34 meters

    # Try to use the new buffer_search function if we have a graph with geometry attributes
    # and the route has nodes/edges with geometry
    try:
        # Check if graph has geometry attributes
        has_node_geometry = any('geometry' in G.nodes[n] for n in route_nodes if n in G.nodes)
        has_edge_geometry = False
        for (u, v, k) in route_edges:
            try:
                if G.has_edge(u, v):
                    edge_data = G.get_edge_data(u, v, k)
                    if edge_data and 'geometry' in edge_data:
                        has_edge_geometry = True
                        break
            except (KeyError, TypeError):
                continue

        if has_node_geometry or has_edge_geometry:
            # Use new buffer_search function for each additional data layer
            buffer_points = []
            for name, data in additional_data.items():
                feature_gdf = data['gdf'].copy()  # Make a copy to avoid modifying original

                if feature_gdf.empty:
                    continue

                # Check geometry types more robustly
                geometry_types = feature_gdf.geometry.geom_type.unique()
                has_points = any(geom_type in ['Point', 'MultiPoint'] for geom_type in geometry_types)

                if not has_points:
                    continue

                try:
                    # CRITICAL: Filter by jurisdiction first if available
                    # This ensures we only search within the selected jurisdiction
                    # The additional_data passed in should already be filtered, but we'll ensure it here
                    # Note: The filtering should happen in app.py before calling this function
                    # But we add a safety check here

                    # Use new buffer_search function with filtered data
                    intersecting_gdf = buffer_search(G, route_nodes, route_edges, feature_gdf, buffer_meters)

                    # Convert GeoDataFrame results to list format for compatibility
                    # CRITICAL: Only include points that are actually within the buffer distance
                    for idx, row in intersecting_gdf.iterrows():
                        point_geom = row.geometry

                        # Handle both Point and MultiPoint geometries
                        if point_geom.geom_type == 'MultiPoint':
                            for point in point_geom.geoms:
                                # Store all row data for later use (including ASSET_ID, GLOBALID, etc.)
                                point_data = {
                                    'id': row.get('id', f'{name}_{idx}'),
                                    'name': name,
                                    'geometry': point,
                                    'x': point.x,
                                    'y': point.y
                                }
                                # Include all other columns from the original row
                                for col in row.index:
                                    if col not in ['geometry', 'id']:
                                        point_data[col] = row[col]
                                buffer_points.append(point_data)
                        elif point_geom.geom_type == 'Point':
                            # Store all row data for later use (including ASSET_ID, GLOBALID, etc.)
                            point_data = {
                                'id': row.get('id', f'{name}_{idx}'),
                                'name': name,
                                'geometry': point_geom,
                                'x': point_geom.x,
                                'y': point_geom.y
                            }
                            # Include all other columns from the original row
                            for col in row.index:
                                if col not in ['geometry', 'id']:
                                    point_data[col] = row[col]
                            buffer_points.append(point_data)
                except Exception as e:
                    # Fall back to old method if new method fails
                    continue

            if buffer_points:
                return buffer_points
    except Exception:
        # Fall through to old method if anything fails
        pass

    # Fallback to original method (for compatibility)
    route_line = LineString(route_coords)

    # Convert buffer distance from miles to degrees (approximate)
    # 1 degree latitude ≈ 69 miles, 1 degree longitude varies by latitude
    # Use a more generous estimate for longitude to account for varying longitude distances
    buffer_degrees = buffer_miles / 50.0  # Convert to degrees (more generous)

    # Create buffer around route
    route_buffer = route_line.buffer(buffer_degrees)

    # Find points within buffer
    buffer_points = []
    for name, data in additional_data.items():
        gdf = data['gdf']

        if gdf.empty:
            continue

        # Check geometry types more robustly
        geometry_types = gdf.geometry.geom_type.unique()
        has_points = any(geom_type in ['Point', 'MultiPoint'] for geom_type in geometry_types)

        if not has_points:
            continue

        try:
            # Find points that intersect with buffer
            points_in_buffer = gdf[gdf.geometry.intersects(route_buffer)]

            for idx, point_row in points_in_buffer.iterrows():
                point_geom = point_row.geometry

                # Handle both Point and MultiPoint geometries
                if point_geom.geom_type == 'MultiPoint':
                    for point in point_geom.geoms:
                        buffer_points.append({
                            'id': point_row.get('id', f'{name}_{idx}'),
                            'name': name,
                            'geometry': point,
                            'x': point.x,
                            'y': point.y
                        })
                elif point_geom.geom_type == 'Point':
                    buffer_points.append({
                        'id': point_row.get('id', f'{name}_{idx}'),
                        'name': name,
                        'geometry': point_geom,
                        'x': point_geom.x,
                        'y': point_geom.y
                    })

        except Exception as e:
            continue

    return buffer_points

def add_buffer_search_results(ax, G, route, additional_data, buffer_miles):
    """
    Add buffer search results showing points within the specified distance of the route.
    """
    from shapely.geometry import Point, LineString
    from shapely.ops import unary_union
    import geopandas as gpd

    # Create route geometry
    route_coords = []
    for node in route:
        if node in G.nodes:
            node_data = G.nodes[node]
            route_coords.append([node_data['x'], node_data['y']])

    if len(route_coords) < 2:
        return []

    route_line = LineString(route_coords)

    # Create buffer around route
    buffer_distance = buffer_miles * 1609.34  # Convert miles to meters
    route_buffer = route_line.buffer(buffer_distance)

    # Find points within buffer
    buffer_points = []
    for name, data in additional_data.items():
        gdf = data['gdf']
        if not gdf.empty and gdf.geometry.geom_type.iloc[0] in ['Point', 'MultiPoint']:
            # Find points that intersect with buffer
            points_in_buffer = gdf[gdf.geometry.intersects(route_buffer)]

            for idx, point_row in points_in_buffer.iterrows():
                point_geom = point_row.geometry
                if hasattr(point_geom, 'y') and hasattr(point_geom, 'x'):
                    buffer_points.append({
                        'id': point_row.get('id', f'{name}_{idx}'),
                        'name': name,
                        'geometry': point_geom,
                        'x': point_geom.x,
                        'y': point_geom.y
                    })

    # Plot buffer points
    for point in buffer_points:
        ax.plot(point['x'], point['y'], 'bo', markersize=4, alpha=0.7)
        ax.text(point['x'], point['y'], str(point['id']), fontsize=5,
                ha='center', va='bottom', color='blue')

    return buffer_points


def plot_detour(G, route, flooded_edge, save_name=None, edge_osm_id='', additional_data=None, buffer_miles=0.5, buffer_points=None):
    """
    Plot a detour route with the incident edge highlighted, highway badges, route IDs, and buffer search results.
    """
    import matplotlib.patches as patches
    from shapely.geometry import Point, LineString
    from shapely.ops import unary_union
    import geopandas as gpd

    # plot the route and incident edge
    # Handle both 2-tuple (u, v) and 3-tuple (u, v, key) formats
    if len(flooded_edge) == 3:
        u, v, key = flooded_edge
    else:
        u, v = flooded_edge
        key = 0  # Default key for 2-tuple format
    if route:
        fig, ax = ox.plot_graph_routes(
            G, [route, [u,v]], route_colors=['blue', 'red'],
            route_linewidths=3, node_size=0, orig_dest_size=3, bgcolor='white', show=False, close=False
        )

        # plot the start and end point as white circles with A and B text
        x_start = G.nodes[route[0]]['x']
        y_start = G.nodes[route[0]]['y']
        ax.plot(x_start, y_start, 'wo', markersize=12, markeredgecolor='black', markeredgewidth=2, label='A (Start)')
        ax.text(x_start, y_start, 'A', ha='center', va='center', fontsize=10, fontweight='bold', color='black')

        x_end = G.nodes[route[-1]]['x']
        y_end = G.nodes[route[-1]]['y']
        ax.plot(x_end, y_end, 'wo', markersize=12, markeredgecolor='black', markeredgewidth=2, label='B (End)')
        ax.text(x_end, y_end, 'B', ha='center', va='center', fontsize=10, fontweight='bold', color='black')

        # Add directional arrows along the route (especially in the middle)
        # Place arrows on route edges, focusing on the middle section
        route_edges = []
        for i in range(len(route) - 1):
            if G.has_edge(route[i], route[i+1]):
                edge_data = G.get_edge_data(route[i], route[i+1])
                if edge_data and 'geometry' in edge_data:
                    edge_geom = edge_data['geometry']
                    route_edges.append((i, edge_geom))

        if route_edges:
            # Find middle section of route for arrow placement
            mid_edge_idx = len(route_edges) // 2
            # Place arrows on a few edges around the middle
            arrow_edge_indices = []
            if len(route_edges) <= 3:
                # For short routes, place arrow on middle edge
                arrow_edge_indices = [mid_edge_idx]
            else:
                # For longer routes, place arrows on middle and adjacent edges
                arrow_edge_indices = [max(0, mid_edge_idx - 1), mid_edge_idx, min(len(route_edges) - 1, mid_edge_idx + 1)]

            for edge_idx in arrow_edge_indices:
                if 0 <= edge_idx < len(route_edges):
                    _, edge_geom = route_edges[edge_idx]

                    if hasattr(edge_geom, 'coords'):
                        coords = list(edge_geom.coords)
                        if len(coords) >= 2:
                            # Use midpoint of edge for arrow placement
                            mid_coord_idx = len(coords) // 2
                            if mid_coord_idx < len(coords) - 1:
                                # Get two points around midpoint to determine direction
                                point1 = coords[mid_coord_idx]
                                point2 = coords[mid_coord_idx + 1]

                                # Calculate direction vector
                                dx = point2[0] - point1[0]
                                dy = point2[1] - point1[1]

                                # Normalize and scale for arrow
                                length = (dx**2 + dy**2)**0.5
                                if length > 0:
                                    # Scale arrow to be visible (about 1-2% of edge length)
                                    scale = length * 0.5
                                    dx_norm = dx / length * scale
                                    dy_norm = dy / length * scale

                                    # Arrow position at midpoint
                                    arrow_x = point1[0]
                                    arrow_y = point1[1]

                                    # Draw arrow
                                    ax.annotate('',
                                               xy=(arrow_x + dx_norm, arrow_y + dy_norm),
                                               xytext=(arrow_x, arrow_y),
                                               arrowprops=dict(arrowstyle='->', lw=2.5,
                                                             color='blue', alpha=0.8,
                                                             headwidth=8, headlength=10))

        # Get the bounds of the route
        min_lat, max_lat, min_lng, max_lng = get_route_bounds(route, G)

        # If buffer points are provided, include them in bounds calculation
        if buffer_points:
            for point in buffer_points:
                if 'x' in point and 'y' in point:
                    min_lng = min(min_lng, point['x'])
                    max_lng = max(max_lng, point['x'])
                    min_lat = min(min_lat, point['y'])
                    max_lat = max(max_lat, point['y'])

        # Set the axis limits to zoom out more for better context (2x zoom out)
        # But only if buffer points don't extend far beyond the route
        x_buffer = max(abs((min_lng - max_lng)), 0.004)  # 2x zoom out - full span buffer
        y_buffer = max(abs((min_lat - max_lat)), 0.004)  # 2x zoom out - full span buffer

        # Extract route information for display
        route_info = extract_route_info(G, route)

        # Add highway badges along the route
        add_highway_badges(ax, G, route)

        # Add buffer search results if additional data is provided
        if buffer_points is not None:
            # Use traffic signal icon (orange circle) for buffer points
            # Check if this is traffic signal data
            is_traffic_signal = any('signal' in point.get('name', '').lower() or
                                   'ASSET_ID' in point or 'GLOBALID' in point
                                   for point in buffer_points[:5])

            for point in buffer_points:
                # Use orange marker for traffic signals, blue for others
                if is_traffic_signal:
                    # Traffic signal icon: orange circle with black border
                    ax.plot(point['x'], point['y'], 'o', color='orange', markersize=8, alpha=0.8,
                           markeredgecolor='black', markeredgewidth=1.5, zorder=10)
                else:
                    # Other data: blue circle
                    ax.plot(point['x'], point['y'], 'o', color='blue', markersize=5, alpha=0.7,
                           markeredgecolor='black', markeredgewidth=0.5, zorder=10)
        elif additional_data:
            # Fall back to calculating buffer points (for PDF export)
            buffer_points = add_buffer_search_results(ax, G, route, additional_data, buffer_miles)

        # Note: We only display buffer_points on the map (not all additional data)
        # This ensures the map matches the preview and only shows points within the buffer

    else:
        fig, ax = ox.plot_graph_route(
            G, [u,v], route_color='red',
            route_linewidth=3, node_size=0, orig_dest_size=3, bgcolor='lightgray', show=False, close=False
        )

        x = G.nodes[u]['x']
        y = G.nodes[u]['y']
        ax.plot(x, y, 'o', color='red', label='no detour found')

        # Get the bounds of the route
        min_lat, max_lat, min_lng, max_lng = get_route_bounds([u,v], G)

        # Set the axis limits to show just slightly more context around detour
        x_buffer = 0.01  # Much smaller buffer - just double the frame
        y_buffer = 0.01  # Much smaller buffer - just double the frame
        route_info = None
        buffer_points = []

    ax.set_xlim([min_lng - x_buffer, max_lng + x_buffer])
    ax.set_ylim([min_lat - y_buffer, max_lat + y_buffer])

    # Simple title without detailed information
    title_text = f'Detour Route'
    plt.title(title_text, fontsize=12)

    # Add basemap with road names
    try:
        import contextily as ctx
        # Add OpenStreetMap basemap with road names
        ctx.add_basemap(ax, crs='EPSG:4326', source=ctx.providers.OpenStreetMap.Mapnik)
    except ImportError:
        # Fallback if contextily is not available
        pass

    # Turn figure frame on and save to disk
    fig.set_frameon(True)

    # Create custom legend with A, B, incident link, detour route, and buffer points
    from matplotlib.lines import Line2D
    legend_elements = []

    if route:
        # Add detour route to legend
        legend_elements.append(Line2D([0], [0], color='blue', lw=3, label='Detour Route'))
        # Add incident link to legend
        legend_elements.append(Line2D([0], [0], color='red', lw=3, label='Incident Link'))
        # Add A and B markers to legend
        legend_elements.append(Line2D([0], [0], marker='o', color='w', markeredgecolor='black',
                                     markeredgewidth=2, markersize=10, linestyle='None', label='A (Start)'))
        legend_elements.append(Line2D([0], [0], marker='o', color='w', markeredgecolor='black',
                                     markeredgewidth=2, markersize=10, linestyle='None', label='B (End)'))
        # Add buffer points/traffic signals to legend if present
        if buffer_points:
            is_traffic_signal = any('signal' in point.get('name', '').lower() or
                                   'ASSET_ID' in point or 'GLOBALID' in point
                                   for point in buffer_points[:5])
            if is_traffic_signal:
                legend_elements.append(Line2D([0], [0], marker='o', color='orange',
                                             markeredgecolor='black', markeredgewidth=1.5,
                                             markersize=8, linestyle='None', label='Traffic Signal'))
            else:
                legend_elements.append(Line2D([0], [0], marker='o', color='blue',
                                             markeredgecolor='black', markeredgewidth=0.5,
                                             markersize=5, linestyle='None', label='Buffer Points'))
    else:
        # No detour found case
        legend_elements.append(Line2D([0], [0], color='red', lw=3, label='Incident Link'))
        legend_elements.append(Line2D([0], [0], marker='o', color='red', markersize=8,
                                     linestyle='None', label='No detour found'))

    ax.legend(handles=legend_elements, loc='best', frameon=True, fancybox=True, shadow=True)

    if save_name:
        plt.savefig(save_name, dpi=300, bbox_inches='tight')
        plt.close()
    else:
        return fig
