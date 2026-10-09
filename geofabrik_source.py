"""Bounded, verified public Geofabrik backup; returns raw OSM, never a graph."""
import hashlib
import gc
import json
import os
import re
import shutil
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from shapely.geometry import Point, shape
from shapely.prepared import prep

CATALOGUE_URL = "https://download.geofabrik.de/index-v1.json"
MAX_CATALOGUE_BYTES = 32 * 1024 * 1024
MAX_PBF_BYTES = 768 * 1024 * 1024
MAX_DISK_BYTES = 1536 * 1024 * 1024
MIN_FREE_BYTES = 200 * 1024 * 1024
# Sparse native storage reserves capacity in chunks, plus a small file header.
# Keep the complete Virginia lookup within the existing 1.5 GiB disk budget.
MAX_LOCATION_BYTES = 1025 * 1024 * 1024
MAX_REQUIRED_NODES = 500_000
MAX_WAYS = 250_000
MAX_REFERENCES = 2_000_000
CACHE_TTL = 24 * 60 * 60
MAX_SELECTION_BYTES = 128 * 1024 * 1024
_CLAUSE = re.compile(r'\["((?:\\.|[^"\\])+)"\s*(?:(=|!=|~|!~)\s*"((?:\\.|[^"\\])*)")?\]')


class ResourceLimitError(RuntimeError):
    """The complete extract cannot be acquired within configured resources."""


def _check(deadline):
    if time.monotonic() >= deadline:
        raise TimeoutError("Geofabrik backup deadline exceeded")


def _public_url(url):
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.hostname != "download.geofabrik.de"
            or parts.username or parts.password or parts.port not in (None, 443)
            or parts.query or parts.fragment):
        raise ValueError("Not a public Geofabrik HTTPS URL")
    return url


def _request(session, url, deadline):
    if getattr(session, "verify", True) is False:
        raise ValueError("TLS verification must remain enabled")
    for attempt in range(4):
        _check(deadline)
        _public_url(url)
        response = session.get(url, stream=True, verify=True, allow_redirects=False,
                               headers={"Accept-Encoding": "identity"},
                               timeout=min(30, max(.01, deadline - time.monotonic())))
        try:
            response.raise_for_status()
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")
                if not location or attempt == 3:
                    raise ValueError("Invalid or excessive Geofabrik redirects")
                url = _public_url(urljoin(url, location))
                response.close()
                continue
            if not 200 <= response.status_code < 300:
                raise ValueError("Geofabrik returned an invalid response")
            return response
        except BaseException:
            response.close()
            raise
    raise ValueError("Excessive Geofabrik redirects")


def _length(response, limit):
    value = response.headers.get("Content-Length")
    length = int(value) if value is not None else None
    if length is not None and (length < 0 or length > limit):
        raise ResourceLimitError("Geofabrik response exceeds byte budget")
    return length


def _read_small(session, url, limit, deadline):
    response = _request(session, url, deadline)
    try:
        expected = _length(response, limit)
        body = bytearray()
        for chunk in response.iter_content(chunk_size=64 * 1024):
            _check(deadline)
            if len(body) + len(chunk) > limit:
                raise ResourceLimitError("Geofabrik response exceeds byte budget")
            body.extend(chunk)
        if expected is not None and len(body) != expected:
            raise ValueError("Truncated Geofabrik response")
        _check(deadline)
        return bytes(body)
    finally:
        response.close()


def _compile_filters(filters):
    """Compile the supported exact QL clauses; filters are a union of conjunctions."""
    if not filters:
        raise ValueError("At least one OSMnx way filter is required")
    alternatives = []
    for expression in filters:
        clauses, position = [], 0
        for match in _CLAUSE.finditer(expression):
            if expression[position:match.start()].strip():
                raise ValueError("Unsupported Overpass filter clause")
            key, operator, value = match.groups()
            unescape = lambda text: text.replace('\\"', '"').replace('\\\\', '\\')
            key = unescape(key)
            value = unescape(value) if value is not None else None
            try:
                regex = re.compile(value) if operator in ("~", "!~") else None
            except re.error as exc:
                raise ValueError("Invalid Overpass filter regex") from exc
            clauses.append((key, operator, value, regex))
            position = match.end()
        if not clauses or expression[position:].strip():
            raise ValueError("Unsupported Overpass filter clause")
        alternatives.append(clauses)

    def accepts(tags):
        for clauses in alternatives:
            accepted = True
            for key, operator, value, regex in clauses:
                actual = tags.get(key)
                if operator is None:
                    result = actual is not None
                elif operator == "=":
                    result = actual is not None and actual == value
                elif operator == "!=":
                    result = actual != value
                elif operator == "~":
                    result = actual is not None and regex.search(actual) is not None
                else:
                    result = actual is None or regex.search(actual) is None
                if not result:
                    accepted = False
                    break
            if accepted:
                return True
        return False
    return accepts


def _requires_highway(filters):
    # A compiled key prefilter is safe only when every union alternative has a
    # positive highway clause. It must not narrow arbitrary utility callers.
    return all(any(match.group(1) == "highway" and match.group(2) in (None, "=", "~")
                   for match in _CLAUSE.finditer(expression)) for expression in filters)


def _choose_dataset(catalogue, polygon):
    if catalogue.get("type") != "FeatureCollection":
        raise ValueError("Invalid Geofabrik catalogue")
    candidates = []
    for feature in catalogue.get("features", []):
        properties = feature.get("properties", {})
        url = properties.get("urls", {}).get("pbf")
        if not url:
            continue
        try:
            _public_url(url)
            coverage = shape(feature["geometry"])
        except (ValueError, TypeError, KeyError):
            continue
        if (coverage.geom_type in ("Polygon", "MultiPolygon")
                and coverage.is_valid and coverage.covers(polygon)
                and url.endswith(".osm.pbf")):
            candidates.append((coverage.area, properties["id"], url))
    if not candidates:
        raise ValueError("No single public Geofabrik dataset covers the entire query footprint")
    _, identifier, url = min(candidates)
    return {"id": identifier, "url": url}


def _checksum(session, url, deadline):
    body = _read_small(session, url + ".md5", 4096, deadline).decode("ascii")
    match = re.fullmatch(r"\s*([0-9a-fA-F]{32})(?:\s+[^\r\n]+)?\s*", body)
    if not match:
        raise ValueError("Invalid publisher MD5")
    return match[1].lower()


def _disk_usage(cache_dir):
    return sum(path.stat().st_size for path in cache_dir.rglob("*") if path.is_file())


@contextmanager
def _cache_lock(cache_dir, deadline, progress):
    """Protect snapshot publication, readers and bounded cleanup across workers."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    with (cache_dir / ".cache.lock").open("a+b") as lock:
        if lock.seek(0, os.SEEK_END) == 0:
            lock.write(b"0")
            lock.flush()
        notified = False
        while True:
            _check(deadline)
            try:
                lock.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if not notified:
                    progress("Waiting for the active Geofabrik cache reader/download")
                    notified = True
                time.sleep(min(.1, max(.01, deadline - time.monotonic())))
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _cleanup_cache(cache_dir):
    """Under the cache lease, reclaim only our expired/unreferenced artifacts."""
    retained = set()
    for manifest in cache_dir.glob("*.json"):
        if not re.fullmatch(r"[0-9a-f]{64}\.json", manifest.name):
            continue
        try:
            metadata = json.loads(manifest.read_text(encoding="utf-8"))
            digest = metadata["sha256"]
            if (re.fullmatch(r"[0-9a-f]{64}", digest)
                    and 0 <= time.time() - metadata["verified_at"] < CACHE_TTL):
                retained.add(digest + ".osm.pbf")
        except (OSError, ValueError, KeyError, TypeError):
            continue
    for path in cache_dir.glob("*.osm.pbf"):
        if re.fullmatch(r"[0-9a-f]{64}\.osm\.pbf", path.name) and path.name not in retained:
            path.unlink(missing_ok=True)
    # All production transfers and readers hold the same lease. A .part left
    # here therefore belongs to a terminated job, never an active download.
    for pattern in ("tmp*.part", "tmp*.part.json", "tmp*.locations"):
        for path in cache_dir.glob(pattern):
            try:
                path.unlink(missing_ok=True)
            except PermissionError:
                # Windows/native-library proxies or antivirus can briefly pin
                # completed scratch files. They still count toward the budget;
                # worker exit releases them for the next leased cleanup.
                pass
    for path in cache_dir.glob("selection-*.json"):
        try:
            if time.time() - path.stat().st_mtime >= CACHE_TTL:
                path.unlink(missing_ok=True)
        except FileNotFoundError:
            pass


def _selection_key(polygon, filters, metadata):
    identity = {"version": 1, "polygon": polygon.wkb_hex,
                "filters": filters, "snapshot": metadata["sha256"]}
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def _read_selection(cache_dir, key, metadata):
    path = cache_dir / f"selection-{key}.json"
    try:
        if path.stat().st_size > MAX_SELECTION_BYTES:
            return None
        record = json.loads(path.read_text(encoding="utf-8"))
        payload = record["payload"]
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if (record["key"] != key or record["snapshot"] != metadata["sha256"]
                or record["sha256"] != digest
                or time.time() >= record["valid_until"]
                or payload.get("osm3s", {}).get("timestamp_osm_base") != metadata["timestamp"]):
            return None
        return payload
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def _write_selection(cache_dir, key, metadata, payload):
    record = {"key": key, "snapshot": metadata["sha256"], "payload": payload,
              "valid_until": metadata["verified_at"] + CACHE_TTL,
              "sha256": hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}
    encoded = json.dumps(record, separators=(",", ":")).encode()
    if (len(encoded) > MAX_SELECTION_BYTES
            or _disk_usage(cache_dir) + len(encoded) > MAX_DISK_BYTES
            or shutil.disk_usage(cache_dir).free < len(encoded) + MIN_FREE_BYTES):
        return
    fd, temporary = tempfile.mkstemp(suffix=".part", dir=cache_dir)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(encoded)
        target = cache_dir / f"selection-{key}.json"
        os.replace(temporary, target)
        # Cleanup age follows acquisition expiry, not the later cache-write
        # time. Preparing/caching a selection must not restart its clock.
        os.utime(target, (metadata["verified_at"], metadata["verified_at"]))
    finally:
        Path(temporary).unlink(missing_ok=True)


def _reserve_lookup_space(cache_dir):
    for path in sorted(cache_dir.glob("selection-*.json"), key=lambda p: p.stat().st_mtime):
        if (_disk_usage(cache_dir) + MAX_LOCATION_BYTES <= MAX_DISK_BYTES
                and shutil.disk_usage(cache_dir).free >= MAX_LOCATION_BYTES + MIN_FREE_BYTES):
            break
        path.unlink(missing_ok=True)
    if (shutil.disk_usage(cache_dir).free < MAX_LOCATION_BYTES + MIN_FREE_BYTES
            or _disk_usage(cache_dir) + MAX_LOCATION_BYTES > MAX_DISK_BYTES):
        raise ResourceLimitError("Insufficient disk budget for bounded OSM location lookup")


def _download(session, url, path, checksum, deadline, progress=None):
    response = _request(session, url, deadline)
    try:
        expected = _length(response, MAX_PBF_BYTES)
        reserve = expected if expected is not None else MAX_PBF_BYTES
        if (_disk_usage(path.parent) + reserve > MAX_DISK_BYTES
                or shutil.disk_usage(path.parent).free < reserve + MIN_FREE_BYTES):
            raise ResourceLimitError("Insufficient disk budget for the complete PBF")
        md5, sha256, size = hashlib.md5(), hashlib.sha256(), 0
        reported_at = time.monotonic()
        with path.open("wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                _check(deadline)
                size += len(chunk)
                if size > MAX_PBF_BYTES or size > reserve:
                    raise ResourceLimitError("PBF exceeds reserved download budget")
                if shutil.disk_usage(path.parent).free < len(chunk) + MIN_FREE_BYTES:
                    raise ResourceLimitError("PBF download exhausted free disk reserve")
                if _disk_usage(path.parent) + len(chunk) > MAX_DISK_BYTES:
                    raise ResourceLimitError("Geofabrik cache disk budget exceeded")
                output.write(chunk)
                md5.update(chunk)
                sha256.update(chunk)
                if progress and time.monotonic() - reported_at >= 5:
                    suffix = f" / {expected / 1_000_000:.0f} MB" if expected is not None else ""
                    progress(f"Geofabrik download: {size / 1_000_000:.0f} MB{suffix}")
                    reported_at = time.monotonic()
            output.flush()
            os.fsync(output.fileno())
        if (not size or (expected is not None and size != expected)
                or md5.hexdigest() != checksum):
            raise ValueError("PBF length or publisher checksum mismatch")
        return {"size": size, "sha256": sha256.hexdigest(), "md5": checksum}
    finally:
        response.close()


def _timestamp(path):
    import osmium
    # The verified download still has a .part suffix: never infer its format.
    reader = osmium.io.Reader(osmium.io.File(str(path), "pbf"))
    try:
        timestamp = reader.header().get("osmosis_replication_timestamp")
    finally:
        reader.close()
    if not timestamp:
        raise ValueError("PBF header has no replication timestamp")
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed > datetime.now(timezone.utc):
        raise ValueError("Invalid PBF replication timestamp")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _snapshot(dataset, session, cache_dir, deadline, progress):
    cache_dir.mkdir(parents=True, exist_ok=True)
    _cleanup_cache(cache_dir)
    if _disk_usage(cache_dir) > MAX_DISK_BYTES:
        raise ResourceLimitError("Geofabrik cache disk budget exceeded")
    key = hashlib.sha256(dataset["url"].encode()).hexdigest()
    manifest = cache_dir / (key + ".json")
    # A manifest is a commit marker. A crash between the two renames is harmless.
    if manifest.exists():
        try:
            metadata = json.loads(manifest.read_text(encoding="utf-8"))
            if (not re.fullmatch(r"[0-9a-f]{64}", metadata["sha256"])
                    or metadata["url"] != dataset["url"]
                    or metadata["dataset"] != dataset["id"]):
                raise ValueError("Invalid Geofabrik cache manifest")
            path = cache_dir / (metadata["sha256"] + ".osm.pbf")
            age = time.time() - metadata["verified_at"]
            if (0 <= age < CACHE_TTL
                    and 0 < path.stat().st_size == metadata["size"] <= MAX_PBF_BYTES):
                digest = hashlib.sha256()
                with path.open("rb") as cached:
                    while chunk := cached.read(1024 * 1024):
                        _check(deadline)
                        digest.update(chunk)
                if digest.hexdigest() == metadata["sha256"]:
                    metadata["timestamp"] = _timestamp(path)
                    _check(deadline)
                    progress("Using verified Geofabrik snapshot")
                    return path, metadata
        except TimeoutError:
            raise
        except (KeyError, ValueError, OSError, TypeError):
            pass
    progress("Downloading and verifying complete Geofabrik extract")
    checksum = _checksum(session, dataset["url"], deadline)
    fd, temporary = tempfile.mkstemp(suffix=".part", dir=cache_dir)
    os.close(fd)
    part = Path(temporary)
    sidecar = Path(temporary + ".json")
    try:
        metadata = _download(session, dataset["url"], part, checksum, deadline, progress)
        if _checksum(session, dataset["url"], deadline) != checksum:
            raise ValueError("Geofabrik snapshot changed during download; retry later")
        metadata.update(timestamp=_timestamp(part), verified_at=time.time(),
                        dataset=dataset["id"], url=dataset["url"])
        _check(deadline)
        path = cache_dir / (metadata["sha256"] + ".osm.pbf")
        sidecar.write_text(json.dumps(metadata), encoding="utf-8")
        os.replace(part, path)
        os.replace(sidecar, manifest)
        return path, metadata
    finally:
        part.unlink(missing_ok=True)
        sidecar.unlink(missing_ok=True)


def _extract(path, polygon, accepts, deadline, progress, requires_highway=False):
    import osmium
    required, ways, nodes = set(), {}, {}
    footprint = prep(polygon)
    minx, miny, maxx, maxy = polygon.bounds
    _reserve_lookup_space(path.parent)
    job_id = os.environ.get("ARPL_OSM_JOB_ID", str(os.getpid()))
    handle, location_name = tempfile.mkstemp(prefix=f"tmp-{job_id}-", suffix=".locations", dir=path.parent)
    os.close(handle)
    location_path = Path(location_name)
    processor = iterator = None
    references = 0
    try:
        # C++ handles the millions of irrelevant nodes; Python sees candidate
        # ways only. Sparse disk storage scales with actual node count, not the
        # largest OSM ID (dense-file storage could create enormous sparse files).
        progress("Indexing OSM coordinates and selecting complete road ways")
        processor = osmium.FileProcessor(str(path), osmium.osm.NODE | osmium.osm.WAY)
        processor.with_locations(f"sparse_file_array,{location_path}")
        processor.with_filter(osmium.filter.EntityFilter(osmium.osm.WAY))
        if requires_highway:
            processor.with_filter(osmium.filter.KeyFilter("highway"))
        iterator = iter(processor)
        for way in iterator:
            _check(deadline)
            if location_path.stat().st_size > MAX_LOCATION_BYTES:
                raise ResourceLimitError("OSM location lookup exceeds disk safety limit")
            tags = dict(way.tags)
            if not accepts(tags):
                continue
            selected = False
            for ref in way.nodes:
                if not ref.location.valid():
                    raise ValueError("Incomplete PBF or unsupported node ordering: missing way coordinates")
                x, y = ref.location.lon, ref.location.lat
                if minx <= x <= maxx and miny <= y <= maxy and footprint.covers(Point(x, y)):
                    selected = True
                    break
            if not selected:
                continue
            refs = [ref.ref for ref in way.nodes]
            element = {"type": "way", "id": way.id, "nodes": refs, "tags": tags}
            if way.id in ways:
                if ways[way.id] != element:
                    raise ValueError("Conflicting duplicate OSM way")
                continue
            references += len(refs)
            required.update(refs)
            if (len(ways) >= MAX_WAYS or len(required) > MAX_REQUIRED_NODES
                    or references > MAX_REFERENCES):
                raise ResourceLimitError("Retained OSM elements exceed memory budget")
            ways[way.id] = element
        # Retrieve only required coordinates from the sparse disk map before
        # releasing it. Do not use Pyosmium's dense ID filters: their allocated
        # bit ranges can be large even for a small geographically selected set.
        for identifier in sorted(required):
            _check(deadline)
            location = processor.node_location_storage.get(identifier)
            if not location.valid():
                raise ValueError("Incomplete PBF: missing required OSM node coordinates")
            nodes[identifier] = {"type": "node", "id": identifier, "lon": location.lon,
                                 "lat": location.lat, "tags": {}}
    finally:
        if iterator is not None:
            iterator.close()
        iterator = processor = None
        # A transient Pyosmium way/location proxy can keep the mmap pinned on
        # Windows until this frame returns. Worker exit releases it; the next
        # leased cache cleanup reclaims the file. This is not a data failure.
        try:
            location_path.unlink(missing_ok=True)
        except PermissionError:
            pass
    if not ways:
        raise ValueError("Geofabrik snapshot contains no matching road ways")
    progress("Preserving original tags on selected OSM nodes")
    processor = osmium.FileProcessor(str(path), osmium.osm.NODE)
    # Untagged nodes are already complete. Native filtering skips the millions
    # of irrelevant untagged objects without a Python callback or dense ID set.
    processor.with_filter(osmium.filter.EmptyTagFilter())
    iterator = iter(processor)
    try:
        for node in iterator:
            _check(deadline)
            if node.id not in required:
                continue
            element = {"type": "node", "id": node.id, "lon": node.location.lon,
                       "lat": node.location.lat, "tags": dict(node.tags)}
            previous = nodes[node.id]
            if (previous["lat"] != element["lat"] or previous["lon"] != element["lon"]
                    or previous["tags"] and previous["tags"] != element["tags"]):
                raise ValueError("Conflicting duplicate OSM node")
            nodes[node.id] = element
    finally:
        iterator.close()
    _check(deadline)
    if required.difference(nodes):
        raise ValueError("Incomplete Geofabrik extract: missing referenced OSM nodes")
    return list(nodes.values()) + list(ways.values())


def load_elements(polygon, filters, *, session, cache_dir, deadline, progress):
    """Return one complete genuine snapshot for the effective OSMnx footprint.

    No partial source mixing, graph construction, buffering, or stale-cache use.
    Caller supervises cancellation and supplies a TLS-verifying requests session.
    """
    _check(deadline)
    if polygon.geom_type not in ("Polygon", "MultiPolygon") or not polygon.is_valid or polygon.is_empty:
        raise ValueError("Expected a valid nonempty EPSG:4326 query polygon")
    accepts = _compile_filters(filters)
    import osmium  # Approved optional decoder; fail before downloading if absent.
    progress("Finding a public Geofabrik extract covering the complete query footprint")
    catalogue = json.loads(_read_small(session, CATALOGUE_URL, MAX_CATALOGUE_BYTES, deadline))
    dataset = _choose_dataset(catalogue, polygon)
    progress(f"Geofabrik dataset: {dataset['id']} (full footprint coverage)")
    with _cache_lock(Path(cache_dir), deadline, progress):
        path, metadata = _snapshot(dataset, session, Path(cache_dir), deadline, progress)
        key = _selection_key(polygon, filters, metadata)
        payload = _read_selection(Path(cache_dir), key, metadata)
        if payload is None:
            elements = _extract(path, polygon, accepts, deadline, progress, _requires_highway(filters))
            payload = {"elements": elements, "osm3s": {"timestamp_osm_base": metadata["timestamp"]}}
            gc.collect()
            _cleanup_cache(Path(cache_dir))
            try:
                _write_selection(Path(cache_dir), key, metadata, payload)
            except OSError:
                progress("Complete OSM data acquired; optional selection cache could not be written")
        else:
            progress("Using complete cached OSM selection; no regional scan is needed")
    provenance = {"source": "geofabrik", "timestamp": metadata["timestamp"],
                  "dataset": dataset["id"], "url": dataset["url"],
                  "sha256": metadata["sha256"], "valid_until": metadata["verified_at"] + CACHE_TTL}
    return payload, provenance
