"""Isolated Blender integration and downstream VG quality for a frozen BC candidate.

Run Blender --background --factory-startup --disable-autoexec --python this.py
-- --candidate PATH --output-dir NEW_DIR. No timing benefit is inferred here.
"""

import argparse
from dataclasses import asdict, replace
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    args.output_dir.mkdir(parents=True, exist_ok=False)
    candidate = args.candidate.resolve()
    baseline = ROOT / 'verification/baselines/bc_implementation.py'
    # Inject before any fixture/test import: all real RB->BC consumers use R.
    r = load(candidate, 'human_eye_fast.fast_bvh_clearance')
    a = load(baseline, '_native_bc_original_A')
    import bpy
    import gpu
    import numpy as np
    gpu.init()
    from human_eye_fast.raycast_saccade_gpu import VGRenderer
    from verification.vg_fixtures import build_fixture
    from verification.test_raycast_saccade_gpu import SceneOracle, score_observation, decode_png

    paths = [candidate, baseline, Path(__file__),
             ROOT / 'human_eye_fast/raycast_saccade_gpu.py',
             ROOT / 'human_eye_fast/blender_resident_bridge.py',
             ROOT / 'verification/vg_fixtures.py',
             ROOT / 'verification/test_raycast_saccade_gpu.py',
             ROOT / 'verification/test_blender_bc_acceptance.py',
             ROOT / 'verification/test_vg_refinement.py']
    hashes = {str(path): sha256(path.read_bytes()).hexdigest() for path in paths}
    report = {'source_sha256_before': hashes, 'blender': bpy.app.version_string,
              'gpu': {'backend': gpu.platform.backend_type_get(),
                      'renderer': gpu.platform.renderer_get()}, 'cases': [], 'passed': False}
    try:
        suite = unittest.defaultTestLoader.loadTestsFromNames([
            'verification.test_blender_bc_acceptance', 'verification.test_vg_refinement'])
        tests = unittest.TextTestRunner(verbosity=2).run(suite)
        report['native_tests'] = {'count': tests.testsRun, 'passed': tests.wasSuccessful(),
                                  'failures': len(tests.failures), 'errors': len(tests.errors)}
        renderer = VGRenderer()
        try:
            for scene_id in range(24):
                fixture = build_fixture(scene_id)
                try:
                    indices = [a.SurfaceIndex(fixture.meshes[key].world_m,
                                              fixture.meshes[key].triangles)
                               for key in fixture.target_ids]
                    original = replace(fixture, witness=a.surface_distance(*indices))
                    prepared = renderer.prepare(fixture.meshes)
                    entries, pixels = {}, {}
                    for method, current in (('implementation', original), ('candidate', fixture)):
                        observation = renderer.observe(
                            prepared, current.witness, target_ids=current.target_ids,
                            frame_id=current.frame_id, scale_length=current.scale_length,
                            mode=current.mode, audit=True)
                        score = score_observation(current, observation,
                                                  oracle=SceneOracle(current), baseline=False)
                        path = args.output_dir / f'{scene_id:02d}_{method}.png'
                        path.write_bytes(observation.png)
                        entries[method] = {'witness': asdict(current.witness), 'score': score,
                                           'metadata': observation.metadata,
                                           'png_path': str(path), 'png_sha256': sha256(observation.png).hexdigest()}
                        pixels[method] = decode_png(observation.png)
                    report['cases'].append({'scene_id': scene_id, 'family': fixture.family,
                        'mode': fixture.mode, 'methods': entries,
                        'same_decoded_rgba': bool(np.array_equal(*pixels.values()))})
                finally:
                    fixture.close()
        finally:
            renderer.close()
        report['source_sha256_after'] = {str(path): sha256(path.read_bytes()).hexdigest() for path in paths}
        report['passed'] = bool(tests.wasSuccessful() and len(report['cases']) == 24
            and hashes == report['source_sha256_after']
            and all(case['methods'][method]['score']['passed'] for case in report['cases']
                    for method in ('implementation', 'candidate')))
    finally:
        def numeric(value):
            if hasattr(value, 'tolist'):
                return value.tolist()
            raise TypeError(type(value).__name__)
        (args.output_dir / 'report.json').write_text(
            json.dumps(report, indent=2, default=numeric, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'cases': len(report['cases']),
                      'same_rgba': sum(case['same_decoded_rgba'] for case in report['cases'])}))
    if not report['passed']:
        raise RuntimeError('Candidate BC/native/VG regression failed')


if __name__ == '__main__':
    main()
