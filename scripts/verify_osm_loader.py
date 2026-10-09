"""Compare new loading with unchanged OSMnx using the same genuine OSM data.

Run from the repo root. This makes a real small-area download; it never supplies
synthetic roads. Query payloads remain in the ignored runtime cache, not Git.
"""

from copy import deepcopy
import argparse
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import networkx as nx
import osmnx as ox
from osmnx import _overpass
from shapely.geometry import box
from shapely.geometry import Polygon
from shapely.ops import unary_union
import requests

import detour_utils as du
import osm_loader


FAST = '["highway"~"motorway|trunk|primary|secondary|trunk_link|primary_link|secondary_link"]'


def equivalent_attributes(left, right):
    # OSMnx simplifies some tags through sets; list order varies with Python's
    # process hash seed. Compare the same values/multiplicities, not that order.
    # Geometry and scalar routing costs must still be exactly equal.
    if set(left) != set(right):
        return False
    return all(sorted(map(repr, left[key])) == sorted(map(repr, right[key]))
               if isinstance(left[key], list) and isinstance(right[key], list)
               else left[key] == right[key] for key in left)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--richmond-mpo", action="store_true", help="Test the actual larger area from the cloud log")
    args = parser.parse_args()
    polygon = box(-77.446, 37.535, -77.439, 37.540)
    if args.richmond_mpo:
        import geopandas as gpd
        mpos = gpd.read_file(next(Path("data/BTS_MPO").glob("*.shp"))).to_crs(4326)
        polygon = mpos.loc[mpos["MPO_NAME"] == "Richmond Area MPO", "geometry"].iloc[0]
    kwargs = dict(network_type="drive", custom_filter=FAST, simplify=True, retain_all=False)
    start = time.monotonic()
    graph = osm_loader.graph_from_polygon(polygon, **kwargs)
    cold = time.monotonic() - start
    start = time.monotonic()
    warm = osm_loader.graph_from_polygon(polygon, **kwargs)
    cached_seconds = time.monotonic() - start

    # Replay only actual successful network responses from the preceding load.
    cache_dir = Path(os.environ.get("ARPL_CACHE_DIR", ".arpl-cache"))
    cache = osm_loader._QueryCache(cache_dir / "queries")
    original = _overpass._download_overpass_network

    def acquired_responses(buffered_polygon, network_type, custom_filter):
        pieces = _overpass._make_overpass_polygon_coord_strs(buffered_polygon)
        if graph.graph["osm_source"] == "geofabrik":
            from geofabrik_source import load_elements
            footprint = unary_union([Polygon([(float(b), float(a)) for a, b in zip(p.split()[::2], p.split()[1::2])]) for p in pieces])
            with requests.Session() as session:
                session.headers["User-Agent"] = osm_loader.USER_AGENT
                payload, provenance = load_elements(
                    footprint, (custom_filter,), session=session,
                    cache_dir=cache_dir / "extracts", deadline=time.monotonic() + 600,
                    progress=print,
                )
            assert provenance["timestamp"] in graph.graph["osm_timestamps"]
            yield payload
            return
        for piece in pieces:
            query = f"[out:json][timeout:120];(way{custom_filter}(poly:{piece!r});>;);out;"
            cached = cache.read(query)
            if cached is None:
                raise RuntimeError("No genuine response available for native graph parity check")
            yield deepcopy(cached[0])

    try:
        _overpass._download_overpass_network = acquired_responses
        baseline = ox.graph_from_polygon(polygon, **kwargs)
    finally:
        _overpass._download_overpass_network = original

    assert set(graph.nodes) == set(baseline.nodes) == set(warm.nodes)
    assert set(graph.edges(keys=True)) == set(baseline.edges(keys=True)) == set(warm.edges(keys=True))
    assert dict(graph.nodes(data=True)) == dict(baseline.nodes(data=True))
    differences = []
    for u, v, k, data in graph.edges(keys=True, data=True):
        reference = baseline.edges[u, v, k]
        if not equivalent_attributes(data, reference):
            for key in set(data) | set(reference):
                if data.get(key) != reference.get(key):
                    differences.append((u, v, k, key, repr(data.get(key)), repr(reference.get(key))))
    if differences:
        print("Native attribute differences:", json.dumps(differences[:10], indent=2))
        raise AssertionError("Native graph edge attributes differ")
    prepared = du.prepare_graph(du.clean_graph(graph))
    prepared_baseline = du.prepare_graph(du.clean_graph(baseline))
    weight_differences = []
    for u, v, k, data in prepared.edges(keys=True, data=True):
        reference = prepared_baseline.edges[u, v, k]
        if not equivalent_attributes(data, reference):
            weight_differences.append((u, v, k, {key: (data.get(key), reference.get(key))
                for key in ("maxspeed", "length", "travel_time", "turn_time", "total_time")
                if data.get(key) != reference.get(key)}))
    if weight_differences:
        print("Prepared weight differences:", json.dumps(weight_differences[:5], indent=2))
        raise AssertionError("Prepared routing weights differ")
    # Exercise real routing over the genuine graph, not just graph counts.
    route = None
    for node in prepared.nodes:
        descendants = nx.descendants(prepared, node)
        if descendants:
            route = nx.shortest_path(prepared, node, next(iter(descendants)), weight="total_time")
            break
    assert route is not None and len(route) > 1
    original_source = warm.graph["osm_sources"][0]["source"]
    graph.graph["osm_sources"][0]["source"] = "mutation-isolation check"
    assert warm.graph["osm_sources"][0]["source"] == original_source
    print(json.dumps({
        "nodes": len(graph), "directed_edges": graph.number_of_edges(),
        "first_load_seconds": round(cold, 2), "cached_load_seconds": round(cached_seconds, 2),
        "source": graph.graph["osm_source"], "timestamps": graph.graph["osm_timestamps"],
        "native_node_edge_attribute_parity": True,
        "comparison_note": "OSMnx unordered aggregate tag lists compared as multisets; geometry and scalar weights exact",
        "prepared_weight_parity": True, "real_route_nodes": len(route),
        "returned_graph_mutation_isolation": True,
        "worker_peak_rss_mb": graph.graph.get("osm_worker_peak_rss_mb"),
        "area": "Richmond Area MPO" if args.richmond_mpo else "small Richmond-city sample",
        "limitation": "local verification, not cloud verification",
    }, indent=2))


if __name__ == "__main__":
    main()
