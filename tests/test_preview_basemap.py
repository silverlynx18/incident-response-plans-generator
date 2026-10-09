"""Tile failure regression checks; no generated/fake road-network demo."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import requests
import contextily as ctx
import detour_utils as du


class PreviewBasemapTests(unittest.TestCase):
    def test_request_identifies_arpl_and_uses_persistent_cache(self):
        fig, ax = plt.subplots()
        try:
            with tempfile.TemporaryDirectory() as directory, \
                    patch.dict("os.environ", {"ARPL_CACHE_DIR": directory}), \
                    patch.object(ctx, "set_cache_dir") as cache, \
                    patch.object(ctx, "add_basemap") as add:
                du._add_preview_basemap(ax)
                cache.assert_called_once_with(str(Path(directory) / "tiles"))
                self.assertIn("ARPL", add.call_args.kwargs["headers"]["User-Agent"])
                self.assertEqual(add.call_args.kwargs["source"], ctx.providers.OpenStreetMap.Mapnik)
        finally:
            plt.close(fig)

    def test_tile_403_preserves_the_existing_route_drawing(self):
        fig, ax = plt.subplots()
        route_line, = ax.plot([1, 2], [3, 4], color="blue")
        try:
            with tempfile.TemporaryDirectory() as directory, \
                    patch.dict("os.environ", {"ARPL_CACHE_DIR": directory}), \
                    patch.object(ctx, "set_cache_dir"), \
                    patch.object(ctx, "add_basemap", side_effect=requests.HTTPError("403 Access blocked")):
                du._add_preview_basemap(ax)
            self.assertIn(route_line, ax.lines)
            self.assertTrue(any("Basemap unavailable" in text.get_text() for text in ax.texts))
            self.assertTrue(any("OpenStreetMap contributors" in text.get_text() for text in ax.texts))
        finally:
            plt.close(fig)


if __name__ == "__main__":
    unittest.main()
