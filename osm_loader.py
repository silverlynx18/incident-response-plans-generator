"""Complete OSM acquisition with free backups and isolated OSMnx graph building.

Only the child process replaces OSMnx's data-acquisition function. OSMnx still
owns buffering, topology, directed edges, simplification and polygon truncation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import pickle
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit

import requests


DEFAULT_PROVIDERS = (
    "https://overpass-api.de/api",
    "https://overpass.private.coffee/api",
    "https://maps.mail.ru/osm/tools/overpass/api",
)
USER_AGENT = "ARPL (https://github.com/silverlynx18/incident-response-plans-generator)"
CACHE_TTL = 24 * 60 * 60
MAX_RESPONSE_BYTES = 128 * 1024 * 1024
MAX_QUERY_CACHE_BYTES = 256 * 1024 * 1024
QUERY_TIMEOUT = 120
_WORKER_SLOT = threading.BoundedSemaphore(1)


class DownloadError(RuntimeError):
    """Acquisition was incomplete or unavailable; never a partial success."""


def _peak_rss_bytes():
    """Best-effort local worker measurement, not a claimed cloud memory limit."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in (
                    "peak_rss", "rss", "peak_paged", "paged", "peak_nonpaged", "nonpaged", "pagefile", "peak_pagefile")]

        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        api = ctypes.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
        api.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        if api(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return counters.peak_rss
    elif sys.platform.startswith("linux"):
        try:
            for line in Path("/proc/self/status").read_text().splitlines():
                if line.startswith("VmHWM:"):
                    return int(line.split()[1]) * 1024
        except (OSError, ValueError):
            pass
    return None


def _provider_urls(configured=""):
    urls = [u.strip().rstrip("/") for u in configured.split(",") if u.strip()]
    result = []
    for url in urls or DEFAULT_PROVIDERS:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
            raise DownloadError("Overpass sources must be HTTPS base URLs without credentials or query parameters")
        if parsed.hostname == "overpass.kumi.systems":
            url = "https://overpass.private.coffee/api"
        if url not in result:
            result.append(url)
    return result


def _query_with_timeout(query):
    # Operational timeout changes must not change the road filter or boundary.
    return re.sub(r"\[timeout:[^\]]+\]", f"[timeout:{QUERY_TIMEOUT}]", query, count=1)


def _validate_response(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
        raise DownloadError("OSM source did not return an elements list")
    if "remark" in payload:
        raise DownloadError(f"Incomplete Overpass response: {payload['remark']}")
    nodes = set()
    ways = []
    seen = {}
    for element in payload["elements"]:
        if not isinstance(element, dict):
            raise DownloadError("OSM source returned a malformed element")
        kind, identifier = element.get("type"), element.get("id")
        if kind not in {"node", "way"} or type(identifier) is not int or identifier <= 0:
            raise DownloadError("OSM source returned an invalid element type or ID")
        key = (kind, identifier)
        if key in seen and seen[key] != element:
            raise DownloadError("OSM source returned conflicting duplicate elements")
        seen[key] = element
        tags = element.get("tags", {})
        if not isinstance(tags, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in tags.items()):
            raise DownloadError("OSM source returned malformed tags")
        if kind == "node":
            lat, lon = element.get("lat"), element.get("lon")
            if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
                raise DownloadError("OSM node is missing its coordinates")
            if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
                raise DownloadError("OSM node has invalid coordinates")
            nodes.add(identifier)
        else:
            references = element.get("nodes")
            if not isinstance(references, list) or len(references) < 2 or any(type(n) is not int or n <= 0 for n in references):
                raise DownloadError("OSM road has invalid node references")
            ways.append(references)
    if any(not set(references).issubset(nodes) for references in ways):
        raise DownloadError("Incomplete OSM response: road references missing nodes")
    return payload


def _atomic_json(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as output:
            json.dump(record, output, separators=(",", ":"))
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class _QueryCache:
    """Validated whole query responses, independent of mirror identity."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def path(self, query):
        return self.directory / f"{sha256(query.encode()).hexdigest()}.json"

    def read(self, query):
        try:
            path = self.path(query)
            if path.stat().st_size > MAX_RESPONSE_BYTES * 2:
                return None
            record = json.loads(path.read_text(encoding="utf-8"))
            if record["schema"] != 1 or record["query"] != query or time.time() - record["fetched_at"] > CACHE_TTL:
                return None
            payload = _validate_response(record["payload"])
            digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if digest != record["sha256"]:
                return None
            return payload, {"source": record["source"], "timestamp": record.get("timestamp"),
                             "cache_hit": True, "valid_until": record["fetched_at"] + CACHE_TTL}
        except (OSError, ValueError, KeyError, TypeError, DownloadError):
            return None

    def write(self, query, payload, source):
        _validate_response(payload)
        timestamp = payload.get("osm3s", {}).get("timestamp_osm_base")
        fetched_at = time.time()
        _atomic_json(self.path(query), {
            "schema": 1, "query": query, "fetched_at": fetched_at, "source": source,
            "timestamp": timestamp, "payload": payload,
            "sha256": sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        })
        # Completed payloads are returned in memory; evicting old cache files
        # cannot remove a worker's active data. Only our own JSON cache is swept.
        files = []
        for path in self.directory.glob("*.json"):
            try:
                stat = path.stat()
                files.append((stat.st_mtime, stat.st_size, path))
            except OSError:
                continue
        total = sum(size for _, size, _ in files)
        for _, size, path in sorted(files):
            if total <= MAX_QUERY_CACHE_BYTES:
                break
            try:
                path.unlink()
                total -= size
            except OSError:
                pass
        return {"source": source, "timestamp": timestamp, "cache_hit": False, "valid_until": fetched_at + CACHE_TTL}


def _retry_after(value, minimum):
    try:
        seconds = float(value)
    except (ValueError, TypeError):
        try:
            seconds = (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            seconds = minimum
    return max(minimum, seconds) if math.isfinite(seconds) else minimum


class _Transport:
    def __init__(self, directory, deadline, progress):
        self.cache = _QueryCache(directory / "queries")
        self.deadline, self.progress = deadline, progress
        self.urls = _provider_urls(os.environ.get("OVERPASS_URLS", ""))
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"})
        self.cooldowns = {}
        self.provenance = []
        self.fingerprints = {}
        self.preferred = None

    def close(self):
        self.session.close()

    def fetch(self, query, number, total):
        query = _query_with_timeout(query)
        cached = self.cache.read(query)
        if cached:
            self.progress(f"Query {number}/{total}: reusing complete OSM response")
            self._record(*cached)
            return cached[0]
        errors, attempted = [], {url: 0 for url in self.urls}
        while any(count < 2 for count in attempted.values()):
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise DownloadError("Live OSM request budget exhausted; completed pieces remain cached")
            eligible = [url for url in self.urls if attempted[url] < 2 and self.cooldowns.get(url, 0) <= time.monotonic()]
            if not eligible:
                ready = min(self.cooldowns.get(url, 0) for url in self.urls if attempted[url] < 2)
                pause = max(ready - time.monotonic(), 0.1)
                if pause >= remaining:
                    break
                self.progress(f"Query {number}/{total}: waiting {pause:.0f}s for provider cooldown")
                time.sleep(pause)
                continue
            url = self.preferred if self.preferred in eligible else eligible[0]
            attempted[url] += 1
            self.progress(f"Query {number}/{total}: requesting {urlsplit(url).hostname} (attempt {attempted[url]}/2)")
            try:
                with self.session.post(
                    url + "/interpreter", data={"data": query}, stream=True,
                    timeout=(min(6, remaining), min(QUERY_TIMEOUT + 10, remaining)),
                ) as response:
                    if response.status_code in {429, 406, 500, 502, 503, 504}:
                        pause = _retry_after(response.headers.get("Retry-After"), 30)
                        self.cooldowns[url] = time.monotonic() + pause
                        raise DownloadError(f"HTTP {response.status_code}; respecting {pause:.0f}s cooldown")
                    response.raise_for_status()
                    chunks, size = [], 0
                    for chunk in response.iter_content(1024 * 1024):
                        if time.monotonic() > self.deadline:
                            raise DownloadError("Live OSM request budget exhausted")
                        size += len(chunk)
                        if size > MAX_RESPONSE_BYTES:
                            raise DownloadError("OSM query exceeded the response-size safety limit")
                        chunks.append(chunk)
                    payload = _validate_response(json.loads(b"".join(chunks)))
                try:
                    provenance = self.cache.write(query, payload, url)
                except OSError:
                    # Complete source data remains usable if optional cache
                    # publication fails; never turn that into a partial graph.
                    self.progress("Complete OSM response received, but runtime cache could not be written")
                    provenance = {"source": url, "timestamp": payload.get("osm3s", {}).get("timestamp_osm_base"),
                                  "cache_hit": False, "valid_until": time.time() + CACHE_TTL}
                self._record(payload, provenance)
                self.preferred = url
                self.progress(f"Query {number}/{total}: complete ({size / 1_000_000:.1f} MB)")
                return payload
            except (requests.RequestException, DownloadError, ValueError) as error:
                errors.append(f"{urlsplit(url).hostname}: {error}")
                self.progress(f"Query {number}/{total}: {urlsplit(url).hostname} unavailable: {error}")
                self.cooldowns[url] = max(self.cooldowns.get(url, 0), time.monotonic() + 30)
        raise DownloadError("No live OSM source completed this query: " + "; ".join(errors))

    def _record(self, payload, provenance):
        # Fail closed if independently dated pieces disagree on an overlapping
        # object's actual topology/tags, rather than OSMnx silently overwriting.
        for element in payload["elements"]:
            fields = {key: element[key] for key in ("type", "id", "lat", "lon", "nodes", "tags") if key in element}
            digest = sha256(json.dumps(fields, sort_keys=True).encode()).digest()
            key = (element["type"], element["id"])
            previous = self.fingerprints.setdefault(key, digest)
            if previous != digest:
                raise DownloadError("Overlapping OSM query pieces disagree; a coherent source snapshot is required")
        self.provenance.append(provenance)


def _number_setting(name, default):
    try:
        value = float(os.environ.get(name, default))
    except ValueError as error:
        raise DownloadError(f"Invalid {name}") from error
    if not math.isfinite(value) or value < 1 or value > 3600:
        raise DownloadError(f"{name} must be between 1 and 3600 seconds")
    return value


def _lookup_files(directory, job_id):
    return directory.glob(f"tmp-{job_id}-*.locations")


def _worker(request_path, result_path):
    import osmnx as ox
    from osmnx import _overpass
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    from shapely.wkt import loads

    request = json.loads(Path(request_path).read_text(encoding="utf-8"))
    polygon, kwargs = loads(request["polygon"]), request["kwargs"]
    directory = Path(request["cache_dir"])
    deadline = time.monotonic() + request["timeout"]

    def progress(message):
        print("[ARPL_PROGRESS]" + json.dumps(message), flush=True)

    for name in ("_download_overpass_network", "_make_overpass_polygon_coord_strs"):
        if not callable(getattr(_overpass, name, None)):
            raise DownloadError(f"OSMnx {ox.__version__} does not expose the supported acquisition interface ({name})")
    filter_function = getattr(_overpass, "_get_network_filter", None) or getattr(_overpass, "_get_osm_filter", None)
    if not callable(filter_function):
        raise DownloadError(f"Unsupported OSMnx filter interface in version {ox.__version__}")
    transport = _Transport(directory, min(deadline, time.monotonic() + _number_setting("ARPL_OVERPASS_BUDGET_SECONDS", 180)), progress)
    original = _overpass._download_overpass_network
    source_mode = "overpass"
    provenance = []

    def acquire(buffered_polygon, network_type, custom_filter):
        filters = custom_filter if isinstance(custom_filter, list) else [custom_filter or filter_function(network_type)]
        pieces = _overpass._make_overpass_polygon_coord_strs(buffered_polygon)
        if source_mode == "geofabrik":
            from geofabrik_source import load_elements

            # Match OSMnx's effective six-decimal query footprint, not a new
            # clipping policy. Source results still go through graph_from_polygon.
            footprint = unary_union([Polygon([(float(b), float(a)) for a, b in zip(p.split()[::2], p.split()[1::2])]) for p in pieces])
            payload, info = load_elements(
                footprint, tuple(filters), session=transport.session,
                cache_dir=directory / "extracts", deadline=deadline, progress=progress,
            )
            _validate_response(payload)
            provenance.append(info)
            yield payload
            return
        number, total = 0, len(pieces) * len(filters)
        progress(f"Requesting the complete selection in {total} OSM query pieces")
        for piece in pieces:
            for way_filter in filters:
                number += 1
                query = f"[out:json][timeout:{QUERY_TIMEOUT}];(way{way_filter}(poly:{piece!r});>;);out;"
                yield transport.fetch(query, number, total)
        progress("All OSM query pieces are complete; building and simplifying the road graph")

    try:
        # The mutation exists only in this disposable process, never Streamlit.
        _overpass._download_overpass_network = acquire
        progress("Trying free global Overpass services; the road-selection parameters are unchanged")
        try:
            graph = ox.graph_from_polygon(polygon, **kwargs)
            provenance.extend(transport.provenance)
        except DownloadError as live_error:
            progress(f"Live OSM unavailable: {live_error}")
            progress("Trying the independent free Geofabrik raw-data backup (daily OSM snapshot)")
            source_mode = "geofabrik"
            try:
                graph = ox.graph_from_polygon(polygon, **kwargs)
            except Exception as extract_error:
                raise DownloadError(f"All OSM acquisition paths failed. Live queries: {live_error}. Geofabrik: {extract_error}") from extract_error
        if graph.number_of_edges() == 0:
            raise DownloadError("The complete selection contains no usable road network")
        graph.graph["osm_sources"] = provenance
        graph.graph["osm_source"] = ", ".join(dict.fromkeys(str(p.get("source", "unknown")) for p in provenance))
        graph.graph["osm_timestamps"] = sorted({p["timestamp"] for p in provenance if p.get("timestamp")})
        graph.graph["osm_loader_version"] = 1
        graph.graph["osm_cache_valid_until"] = min(p.get("valid_until", time.time()) for p in provenance)
        peak = _peak_rss_bytes()
        graph.graph["osm_worker_peak_rss_mb"] = round(peak / (1024 * 1024), 1) if peak is not None else None
        progress(f"Complete road graph: {graph.number_of_nodes():,} nodes / {graph.number_of_edges():,} edges")
        with open(result_path, "wb") as output:
            pickle.dump(graph, output, protocol=pickle.HIGHEST_PROTOCOL)
    finally:
        _overpass._download_overpass_network = original
        transport.close()


def _run_graph_job(polygon, *, progress, timeout, **kwargs):
    """Return an independent complete graph or raise; never change selection.

    Temporary graph transfer is generated by our own child process, not read
    from remote sources or user uploads. No prebuilt networks are distributed.
    """
    from geofabrik_source import MAX_LOCATION_BYTES, MIN_FREE_BYTES

    cache_dir = Path(os.environ.get("ARPL_CACHE_DIR", ".arpl-cache")).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    report = progress
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="arpl-job-") as temporary:
        request_path, result_path = Path(temporary) / "request.json", Path(temporary) / "graph.pickle"
        request_path.write_text(json.dumps({
            "polygon": polygon.wkt, "kwargs": kwargs, "cache_dir": str(cache_dir), "timeout": timeout,
        }), encoding="utf-8")
        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "utf-8"
        # OSMnx aggregates tags through sets; ARPL's existing preparation takes
        # the first value of some aggregates. A fresh random seed per job would
        # therefore change routing weights for identical source data.
        environment["PYTHONHASHSEED"] = "0"
        job_id = Path(temporary).name
        environment["ARPL_OSM_JOB_ID"] = job_id
        worker = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--worker", str(request_path), str(result_path)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace", env=environment,
        )
        lines, errors = queue.Queue(), []

        def collect():
            for line in worker.stdout:
                lines.put(line.rstrip())
            lines.put(None)

        reader = threading.Thread(target=collect, daemon=True)
        reader.start()
        try:
            while True:
                if time.monotonic() - started > timeout:
                    raise DownloadError(f"OSM loading exceeded the {timeout:.0f}s overall limit; no partial network was accepted")
                extract_dir = cache_dir / "extracts"
                if extract_dir.is_dir():
                    for lookup in _lookup_files(extract_dir, job_id):
                        try:
                            if lookup.stat().st_size > MAX_LOCATION_BYTES or shutil.disk_usage(extract_dir).free < MIN_FREE_BYTES:
                                raise DownloadError("OSM coordinate lookup exhausted its disk safety budget; no partial network was accepted")
                        except FileNotFoundError:
                            pass
                try:
                    line = lines.get(timeout=0.25)
                except queue.Empty:
                    continue
                if line is None:
                    break
                if line.startswith("[ARPL_PROGRESS]"):
                    report(json.loads(line[len("[ARPL_PROGRESS]"):]))
                else:
                    errors.append(line)
                    errors = errors[-30:]
            worker.wait(timeout=5)
            if worker.returncode != 0 or not result_path.is_file():
                raise DownloadError("OSM loader failed: " + "\n".join(errors[-10:]))
            with result_path.open("rb") as result:
                return pickle.load(result)
        finally:
            if worker.poll() is None:
                worker.terminate()
                try:
                    worker.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    worker.kill()
                    worker.wait(timeout=5)
            worker.stdout.close()
            reader.join(timeout=2)


def graph_from_polygon(polygon, *, progress=None, **kwargs):
    """One bounded graph job per app process; each caller receives its own graph."""
    report = progress or (lambda message: print(f"[ARPL] {message}", flush=True))
    timeout = _number_setting("ARPL_LOADER_TIMEOUT_SECONDS", 900)
    started = time.monotonic()
    acquired = _WORKER_SLOT.acquire(blocking=False)
    if not acquired:
        report("Waiting for the current OSM load to finish (cloud memory protection)")
        acquired = _WORKER_SLOT.acquire(timeout=timeout)
    if not acquired:
        raise DownloadError("OSM loader wait budget exhausted")
    try:
        remaining = timeout - (time.monotonic() - started)
        if remaining <= 0:
            raise DownloadError("OSM loader wait budget exhausted")
        return _run_graph_job(polygon, progress=report, timeout=remaining, **kwargs)
    finally:
        _WORKER_SLOT.release()


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--worker":
        _worker(sys.argv[2], sys.argv[3])
    else:
        raise SystemExit("Use graph_from_polygon from the application; --worker is internal")
