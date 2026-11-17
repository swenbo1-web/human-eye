"""Record synthetic image publications while running the bounded R1 tests once."""

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[2]), 'D:/he_anchor_001/venv/Lib/site-packages']
import numpy as np
from PIL import Image
from human_eye_plugin import attention_raster


def main():
    path = HERE / 'test_region_task_bounds.py'
    specification = importlib.util.spec_from_file_location('_cross_scale_bound_tests', path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
    counts = dict(synthetic_image_save_calls=0, synthetic_NPZ_save_calls=0, real_raster_calls=0)
    original_save, original_npz = Image.Image.save, np.savez_compressed
    def image_save(image, *args, **kwargs):
        counts['synthetic_image_save_calls'] += 1
        return original_save(image, *args, **kwargs)
    def npz_save(*args, **kwargs):
        counts['synthetic_NPZ_save_calls'] += 1
        return original_npz(*args, **kwargs)
    def denied(*args, **kwargs):
        counts['real_raster_calls'] += 1
        raise AssertionError('Real raster is outside pure R1 test scope')
    stream = io.StringIO()
    with patch.object(Image.Image, 'save', image_save), patch.object(np, 'savez_compressed', npz_save), \
            patch.object(attention_raster, 'rasterize_attention', denied):
        outcome = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    result = dict(passed=outcome.wasSuccessful(), tests=outcome.testsRun,
        failures=len(outcome.failures), errors=len(outcome.errors), counts=counts,
        live_Blender=0, live_qualification_rasters=0, model_consumers=0,
        source_pins=[dict(path=str(source), sha256=hashlib.sha256(source.read_bytes()).hexdigest()) for source in
                     (path, HERE / 'run_bound_checks.py', HERE.parents[2] / 'human_eye_plugin/active_observation_region_task.py')])
    (HERE / 'R1_CHECKS.stdout.txt').write_text(stream.getvalue(), encoding='utf8')
    (HERE / 'R1_CHECKS.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf8')
    print(json.dumps(result))
    if not outcome.wasSuccessful():
        raise SystemExit(1)


if __name__ == '__main__':
    main()
