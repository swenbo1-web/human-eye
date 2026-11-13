"""Bind the unchanged FIX1 coordinator to the narrow interface-fix transport."""

import importlib.util
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


transport = load('_interface_fix_transport', HERE / 'consumer_transport.py')
legacy = load('_interface_fix_coordinator', ROOT / 'verification/m4_surface_scan_continuity_001_fix1/consumer/episode.py')
legacy.transport = transport
run_episode = legacy.run_episode
