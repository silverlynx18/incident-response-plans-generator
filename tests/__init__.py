"""ARPL Unit & Baseline Regression Test Suite."""
import sys
import types

try:
    import contextily  # noqa: F401
except ImportError:
    ctx_mod = types.ModuleType("contextily")
    ctx_mod.set_cache_dir = lambda *a, **kw: None
    ctx_mod.add_basemap = lambda *a, **kw: None
    ctx_mod.providers = types.SimpleNamespace(
        OpenStreetMap=types.SimpleNamespace(Mapnik="OpenStreetMap.Mapnik")
    )
    sys.modules["contextily"] = ctx_mod

try:
    import osmium  # noqa: F401
except ImportError:
    osmium_mod = types.ModuleType("osmium")
    io_mod = types.ModuleType("osmium.io")
    io_mod.File = lambda path, fmt=None: (path, fmt)
    io_mod.Reader = lambda *a, **kw: None
    osmium_mod.io = io_mod
    sys.modules["osmium"] = osmium_mod
    sys.modules["osmium.io"] = io_mod
