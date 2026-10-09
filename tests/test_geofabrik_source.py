"""Policy/fault tests only: these do not demonstrate a synthetic road network."""
import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from shapely.geometry import box, mapping

import geofabrik_source as source


class Response:
    def __init__(self, body=b"", headers=None, status=200):
        self.body, self.headers, self.status_code = body, headers or {}, status
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("HTTP error")

    def iter_content(self, chunk_size):
        for offset in range(0, len(self.body), chunk_size):
            yield self.body[offset:offset + chunk_size]

    def close(self):
        self.closed = True


class Session:
    verify = True

    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return next(self.responses)


class TagPolicyTests(unittest.TestCase):
    def test_native_highway_prefilter_never_narrows_other_queries(self):
        self.assertTrue(source._requires_highway(('[' + '"highway"~"motorway|primary"]',)))
        self.assertTrue(source._requires_highway(('[' + '"highway"]["access"!="private"]',)))
        self.assertFalse(source._requires_highway(('[' + '"railway"="rail"]',)))
        self.assertFalse(source._requires_highway(('[' + '"highway"!="footway"]',)))
        self.assertFalse(source._requires_highway(('[' + '"highway"]', '["railway"]')))

    def test_unanchored_and_union(self):
        match = source._compile_filters(('[' + '"highway"~"motorway|primary"]',
                                         '["highway"="residential"]'))
        self.assertTrue(match({"highway": "motorway_link"}))
        self.assertTrue(match({"highway": "residential"}))
        self.assertFalse(match({"highway": "footway"}))

    def test_missing_tags_and_conjunction(self):
        match = source._compile_filters((
            '["highway"]["area"!~"yes"]["access"!="private"]'
            '["motor_vehicle"!~"no"]',))
        self.assertTrue(match({"highway": "primary"}))
        self.assertFalse(match({}))
        self.assertFalse(match({"highway": "primary", "area": "yes"}))
        self.assertFalse(match({"highway": "primary", "access": "private"}))
        self.assertFalse(match({"highway": "primary", "motor_vehicle": "no"}))

    def test_positive_clauses_require_tag(self):
        for clause in ('["highway"="primary"]', '["highway"~"primary"]'):
            self.assertFalse(source._compile_filters((clause,))({}))

    def test_installed_osmnx_complete_drive_filter(self):
        from osmnx._overpass import _get_network_filter
        accepts = source._compile_filters((_get_network_filter("drive"),))
        self.assertTrue(accepts({"highway": "primary"}))
        for tags in ({"highway": "service"}, {"highway": "footway"},
                     {"highway": "primary", "access": "private"},
                     {"highway": "primary", "motorcar": "no"}):
            self.assertFalse(accepts(tags))

    def test_unsupported_or_invalid_filters_fail_closed(self):
        for filters in ((), ('[highway]',), ('["a"~"["]',),
                        ('["a"] garbage',), ('["a"];out;',)):
            with self.subTest(filters=filters), self.assertRaises(ValueError):
                source._compile_filters(filters)


class CoverageTests(unittest.TestCase):
    def feature(self, name, bounds, url=None):
        return {"type": "Feature", "geometry": mapping(box(*bounds)),
                "properties": {"id": name, "urls": {"pbf": url or
                    f"https://download.geofabrik.de/{name}-latest.osm.pbf"}}}

    def test_smallest_single_cover_and_border(self):
        catalogue = {"type": "FeatureCollection", "features": [
            self.feature("small", (0, 0, 1, 1)),
            self.feature("parent", (-1, -1, 3, 3)),
            self.feature("world", (-10, -10, 10, 10))]}
        chosen = source._choose_dataset(catalogue, box(.9, .2, 1.1, .8))
        self.assertEqual(chosen["id"], "parent")

    def test_partial_and_nonpublic_sources_rejected(self):
        for feature in (self.feature("small", (0, 0, 1, 1)),
                        self.feature("private", (-2, -2, 2, 2),
                            "https://osm-internal.download.geofabrik.de/a.osm.pbf")):
            with self.assertRaises(ValueError):
                source._choose_dataset({"type": "FeatureCollection",
                    "features": [feature]}, box(.5, .5, 1.5, 1.5))


class TransferTests(unittest.TestCase):
    def test_official_latest_to_dated_redirect_is_followed(self):
        redirect = Response(headers={"Location": "/north-america/us/virginia-261008.osm.pbf"}, status=307)
        final = Response(b"transfer test, not OSM")
        session = Session([redirect, final])
        response = source._request(session,
            "https://download.geofabrik.de/north-america/us/virginia-latest.osm.pbf",
            time.monotonic() + 10)
        self.assertIs(response, final)
        self.assertTrue(redirect.closed)
        self.assertEqual(session.calls[-1][0],
            "https://download.geofabrik.de/north-america/us/virginia-261008.osm.pbf")

    def test_external_or_insecure_redirect_is_rejected(self):
        for location in ("https://example.com/a.osm.pbf", "http://download.geofabrik.de/a.osm.pbf"):
            redirect = Response(headers={"Location": location}, status=307)
            with self.assertRaises(ValueError):
                source._request(Session([redirect]), "https://download.geofabrik.de/a.osm.pbf",
                    time.monotonic() + 10)
            self.assertTrue(redirect.closed)

    def test_unknown_length_still_bounded(self):
        response = Response(b"abcdef")
        with self.assertRaises(source.ResourceLimitError):
            source._read_small(Session([response]),
                "https://download.geofabrik.de/a", 5, time.monotonic() + 10)
        self.assertTrue(response.closed)

    def test_redirect_and_oversized_pbf_rejected_without_writing(self):
        for response in (Response(status=302),
                         Response(headers={"Content-Length": str(source.MAX_PBF_BYTES + 1)})):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "part"
                with self.assertRaises((ValueError, source.ResourceLimitError)):
                    source._download(Session([response]),
                        "https://download.geofabrik.de/a.osm.pbf", path,
                        "0" * 32, time.monotonic() + 10)
                self.assertFalse(path.exists())
                self.assertTrue(response.closed)

    def test_bounded_response_closes_on_error(self):
        response = Response(b"abcdef", {"Content-Length": "6"})
        session = Session([response])
        with self.assertRaises(source.ResourceLimitError):
            source._read_small(session, "https://download.geofabrik.de/a", 5,
                               time.monotonic() + 10)
        self.assertTrue(response.closed)

    def test_timeout_and_tls_enforced(self):
        session = Session([])
        with self.assertRaises(TimeoutError):
            source._read_small(session, "https://download.geofabrik.de/a", 10,
                               time.monotonic() - 1)
        self.assertEqual(session.calls, [])
        session.verify = False
        with self.assertRaises(ValueError):
            source._read_small(session, "https://download.geofabrik.de/a", 10,
                               time.monotonic() + 10)

    def test_download_checksum_and_actual_size(self):
        body = b"transfer fault fixture, not OSM data"
        checksum = hashlib.md5(body).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "download.part"
            source._download(Session([Response(body)]),
                "https://download.geofabrik.de/a.osm.pbf", path,
                checksum, time.monotonic() + 10)
            self.assertEqual(path.read_bytes(), body)
            with self.assertRaises(ValueError):
                source._download(Session([Response(body)]),
                    "https://download.geofabrik.de/a.osm.pbf", path,
                    "0" * 32, time.monotonic() + 10)

    def test_declared_size_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                source._download(Session([Response(b"short", {"Content-Length": "10"})]),
                    "https://download.geofabrik.de/a.osm.pbf", Path(directory) / "part",
                    hashlib.md5(b"short").hexdigest(), time.monotonic() + 10)


class SnapshotTests(unittest.TestCase):
    def test_selection_expiry_and_lookup_reservation_reclaim_disposable_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            metadata = {"sha256": "a" * 64, "verified_at": time.time() - source.CACHE_TTL - 1,
                        "timestamp": "2026-01-01T00:00:00Z"}
            payload = {"elements": [], "osm3s": {"timestamp_osm_base": metadata["timestamp"]}}
            source._write_selection(cache, "expired", metadata, payload)
            source._cleanup_cache(cache)
            self.assertFalse((cache / "selection-expired.json").exists())
            (cache / "selection-disposable.json").write_bytes(b"x" * 1000)
            with patch.object(source, "MAX_DISK_BYTES", 1200), patch.object(source, "MAX_LOCATION_BYTES", 800):
                source._reserve_lookup_space(cache)
            self.assertFalse((cache / "selection-disposable.json").exists())

    def test_selected_osm_cache_is_snapshot_specific_and_expires(self):
        metadata = {"sha256": "a" * 64, "verified_at": time.time(),
                    "timestamp": "2026-01-01T00:00:00Z"}
        polygon, filters = box(0, 0, 1, 1), ('["highway"]',)
        payload = {"elements": [], "osm3s": {"timestamp_osm_base": metadata["timestamp"]}}
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            key = source._selection_key(polygon, filters, metadata)
            source._write_selection(cache, key, metadata, payload)
            self.assertEqual(source._read_selection(cache, key, metadata), payload)
            different = dict(metadata, sha256="b" * 64)
            self.assertIsNone(source._read_selection(cache, key, different))
            path = cache / f"selection-{key}.json"
            record = json.loads(path.read_text())
            record["valid_until"] = time.time() - 1
            path.write_text(json.dumps(record))
            self.assertIsNone(source._read_selection(cache, key, metadata))

    def test_repeated_refresh_reclaims_expired_snapshots(self):
        dataset = {"id": "region", "url": "https://download.geofabrik.de/region.osm.pbf"}
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)

            def transfer(session, url, path, checksum, deadline, progress):
                body = checksum.encode() * 20  # Transfer fixture, not a network.
                path.write_bytes(body)
                return {"size": len(body), "sha256": hashlib.sha256(body).hexdigest(), "md5": checksum}

            with patch.object(source, "MAX_DISK_BYTES", 1800), \
                    patch.object(source, "_download", side_effect=transfer), \
                    patch.object(source, "_timestamp", return_value="2026-01-01T00:00:00Z"):
                for number in range(5):
                    with patch.object(source, "_checksum", return_value=f"{number:032x}"):
                        with source._cache_lock(cache, time.monotonic() + 10, lambda message: None):
                            source._snapshot(dataset, Session([]), cache,
                                time.monotonic() + 10, lambda message: None)
                    manifest = cache / (hashlib.sha256(dataset["url"].encode()).hexdigest() + ".json")
                    record = json.loads(manifest.read_text())
                    record["verified_at"] = time.time() - source.CACHE_TTL - 1
                    manifest.write_text(json.dumps(record))
                self.assertEqual(len(list(cache.glob("*.osm.pbf"))), 1)

    def test_abandoned_transfer_is_reclaimed(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            abandoned = cache / "tmp-crashed.part"
            abandoned.write_bytes(b"abandoned transfer")
            with source._cache_lock(cache, time.monotonic() + 10, lambda message: None):
                source._cleanup_cache(cache)
            self.assertFalse(abandoned.exists())

    def test_expired_snapshot_is_not_silently_served(self):
        dataset = {"id": "region", "url": "https://download.geofabrik.de/region.osm.pbf"}
        with tempfile.TemporaryDirectory() as directory:
            key = hashlib.sha256(dataset["url"].encode()).hexdigest()
            body = b"cache fault fixture, not OSM data"
            digest = hashlib.sha256(body).hexdigest()
            Path(directory, digest + ".osm.pbf").write_bytes(body)
            Path(directory, key + ".json").write_text(json.dumps({
                "sha256": digest, "size": len(body), "url": dataset["url"],
                "dataset": dataset["id"], "verified_at": time.time() - source.CACHE_TTL - 1}))
            with patch.object(source, "_checksum", side_effect=ConnectionError("offline")):
                with self.assertRaises(ConnectionError):
                    source._snapshot(dataset, Session([]), Path(directory),
                                     time.monotonic() + 10, lambda message: None)

    def test_header_reader_explicit_format_and_closure(self):
        import osmium
        reader = MagicMock()
        reader.header.return_value.get.return_value = "2026-01-01T00:00:00Z"
        with patch.object(osmium.io, "Reader", return_value=reader), \
                patch.object(osmium.io, "File", wraps=osmium.io.File) as file_constructor:
            self.assertEqual(source._timestamp(Path("snapshot.part")), "2026-01-01T00:00:00Z")
            file_constructor.assert_called_once_with("snapshot.part", "pbf")
            reader.close.assert_called_once()

    def test_header_missing_timestamp_fails_and_closes(self):
        import osmium
        reader = MagicMock()
        reader.header.return_value.get.return_value = ""
        with patch.object(osmium.io, "Reader", return_value=reader):
            with self.assertRaises(ValueError):
                source._timestamp(Path("snapshot.part"))
            reader.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
