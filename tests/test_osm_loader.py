"""Transport fault checks, not substitutes for genuine OSM integration tests."""

import tempfile
import ast
import json
import time
from pathlib import Path
import unittest

import osm_loader as loader


class ResponseValidationTests(unittest.TestCase):
    def test_http_200_runtime_remark_is_not_success(self):
        with self.assertRaisesRegex(loader.DownloadError, "out of memory"):
            loader._validate_response({"elements": [], "remark": "Query run out of memory"})

    def test_missing_way_nodes_is_not_a_complete_response(self):
        with self.assertRaisesRegex(loader.DownloadError, "missing"):
            loader._validate_response({"elements": [{"type": "way", "id": 1, "nodes": [11, 12]}]})

    def test_empty_piece_is_valid_not_an_invented_network(self):
        self.assertEqual(loader._validate_response({"elements": []}), {"elements": []})

    def test_invalid_coordinates_are_rejected(self):
        with self.assertRaises(loader.DownloadError):
            loader._validate_response({"elements": [{"type": "node", "id": 1, "lat": 99, "lon": 1}]})


class QueryAndCacheTests(unittest.TestCase):
    def test_watchdog_only_observes_its_own_job(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("tmp-old.locations", "tmp-other-job-a.locations", "tmp-current-job-a.locations"):
                (root / name).touch()
            self.assertEqual([p.name for p in loader._lookup_files(root, "current-job")],
                             ["tmp-current-job-a.locations"])

    def test_cached_response_keeps_its_original_expiration(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = loader._QueryCache(Path(directory))
            cache.write("query", {"elements": []}, "source")
            path = cache.path("query")
            record = json.loads(path.read_text())
            record["fetched_at"] = time.time() - loader.CACHE_TTL + 10
            path.write_text(json.dumps(record))
            _, provenance = cache.read("query")
            self.assertLess(provenance["valid_until"], time.time() + 15)

    def test_app_retains_the_original_mode_filters_once(self):
        source = Path("app_v1_5_6.py").read_text(encoding="utf-8")
        values = [node.value for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Constant) and isinstance(node.value, str)]
        fast = '["highway"~"motorway|trunk|primary|secondary|trunk_link|primary_link|secondary_link"]'
        balanced = '["highway"~"motorway|trunk|primary|secondary|tertiary|trunk_link|primary_link|secondary_link|tertiary_link|residential|unclassified"]'
        self.assertEqual(values.count(fast), 1)
        self.assertEqual(values.count(balanced), 1)
        self.assertNotIn("signal.alarm", source)

    def test_retry_after_is_never_shortened(self):
        self.assertEqual(loader._retry_after("120", 30), 120)
        self.assertEqual(loader._retry_after("5", 30), 30)

    def test_future_server_cooldown_is_respected(self):
        self.assertGreater(loader._retry_after("Thu, 01 Jan 2099 00:00:00 GMT", 30), 30)

    def test_timeout_normalization_leaves_filter_and_polygon_unchanged(self):
        query = '[out:json][timeout:180];(way["highway"~"motorway|secondary"](poly:\'1 2 3 4 1 2\');>;);out;'
        normalized = loader._query_with_timeout(query)
        self.assertEqual(normalized, query.replace("[timeout:180]", "[timeout:120]"))

    def test_cache_does_not_require_the_same_mirror(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = loader._QueryCache(Path(directory))
            payload = {"elements": [], "osm3s": {"timestamp_osm_base": "2026-10-09T00:00:00Z"}}
            cache.write("query", payload, "https://maps.mail.ru/osm/tools/overpass/api")
            cached = cache.read("query")
            self.assertEqual(cached[0], payload)
            self.assertEqual(cached[1]["source"], "https://maps.mail.ru/osm/tools/overpass/api")

    def test_corrupt_cache_is_a_miss_not_a_success(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = loader._QueryCache(Path(directory))
            cache.path("query").write_text("not JSON", encoding="utf-8")
            self.assertIsNone(cache.read("query"))

    def test_cache_rejects_runtime_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = loader._QueryCache(Path(directory))
            with self.assertRaises(loader.DownloadError):
                cache.write("query", {"elements": [], "remark": "partial result"}, "source")
            self.assertIsNone(cache.read("query"))

    def test_kumi_alias_is_not_an_independent_backup(self):
        urls = loader._provider_urls("https://overpass.private.coffee/api,https://overpass.kumi.systems/api,https://overpass-api.de/api")
        self.assertEqual(urls, ["https://overpass.private.coffee/api", "https://overpass-api.de/api"])

    def test_insecure_override_is_rejected(self):
        with self.assertRaises(loader.DownloadError):
            loader._provider_urls("http://example.com/api")


if __name__ == "__main__":
    unittest.main()
