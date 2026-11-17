"""Two historical R0 assertions against the guarded accepted R1 installation."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import time
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
INSTALL = Path('D:/he_m4_cross_scale_001/R1/product').resolve()
BUILD = ROOT / 'verification/m4_cross_scale_discovery_001/build_R1/BUILD_INSTALL.json'
manifest = json.loads(BUILD.read_bytes())['binding']['source_manifest']
loader_path = INSTALL / 'human_eye_plugin/verified_source_loader.py'
loader_blob = loader_path.read_bytes()
loader_pin = next(row['sha256'] for row in manifest if row['path'] == 'human_eye_plugin/verified_source_loader.py')
assert hashlib.sha256(loader_blob).hexdigest() == loader_pin
bootstrap = types.ModuleType('_source_region_legacy_verified_bootstrap')
bootstrap.__file__ = str(loader_path)
sys.modules[bootstrap.__name__] = bootstrap
exec(compile(loader_blob, str(loader_path), 'exec'), bootstrap.__dict__)
guard = bootstrap.install(INSTALL, manifest, bootstrap_module=bootstrap)
sys.path.insert(0, str(INSTALL))

from PIL import Image
import human_eye_plugin.active_observation_images as images
import human_eye_plugin.active_observation_host as host
import human_eye_plugin.active_observation_region_task as core

path = ROOT / 'verification/m4_cross_scale_discovery_001/core_tests/test_region_task_core.py'
spec = importlib.util.spec_from_file_location('_guarded_legacy_core_baseline', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
names = ['test_local_numeric_insufficiency_preserves_six_constructed_global_frames',
         'test_single_geometry_preparation_shared_meshes_and_source_bound_scopes']
suite = unittest.TestSuite(module.RegionTaskCoreTests(name) for name in names)
stream = io.StringIO()
png_cost = {'calls': 0, 'elapsed_ns': 0}
original_save = Image.Image.save


def save(image, fp, *args, **kwargs):
    started = time.perf_counter_ns()
    try:
        return original_save(image, fp, *args, **kwargs)
    finally:
        png_cost['calls'] += 1
        png_cost['elapsed_ns'] += time.perf_counter_ns() - started


with patch.object(Image.Image, 'save', save):
    outcome = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
record = {'tests': outcome.testsRun, 'failures': len(outcome.failures), 'errors': len(outcome.errors),
          'sys_path': sys.path, 'guard_root': str(guard.root), 'guard_verified': guard.verify_loaded(),
          'guard_manifest_source_count': len(manifest), 'loader_sha256': loader_pin,
          'mock_PNG_encoding_and_publication': png_cost,
          'loaded_products': [{'name': item.__name__, 'file': item.__file__,
                               'sha256': hashlib.sha256(Path(item.__file__).read_bytes()).hexdigest()}
                              for item in (images, host, core)],
          'actual_Blender_starts': 0, 'actual_rasters': 0}
destination = Path(__file__).parent / 'runs/BASELINE_LEGACY_GUARDED_01'
destination.mkdir(parents=True, exist_ok=False)
(destination / 'stdout.txt').write_text(stream.getvalue(), encoding='utf8')
(destination / 'CHECKS.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf8')
print(stream.getvalue())
print(json.dumps(record))
