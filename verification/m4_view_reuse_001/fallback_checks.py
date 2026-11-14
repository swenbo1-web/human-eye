"""Reuse first-run saved bytes to reproduce and close the no-ref fallback gap."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import inspect
import io
import json
from pathlib import Path
import sys
import traceback
import unittest
from unittest.mock import patch


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=('before', 'after'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root))
    prior = Path(__file__).resolve().parent / 'product_checks_01'
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    images_module = importlib.import_module('human_eye_plugin.active_observation_images')
    active_module = importlib.import_module('human_eye_plugin.active_observation')
    raster_module = importlib.import_module('human_eye_plugin.attention_raster')
    raster_signature = inspect.signature(raster_module.rasterize_attention)
    result = {'schema': 'view-reuse-no-ref-fallback-v1', 'phase': args.phase,
              'image_module': images_module.__file__, 'source_sha256': sha(images_module.__file__),
              'prior_result_sha256': sha(prior / 'RESULT.json'), 'passed': False, 'failures': []}
    try:
        source = json.loads((prior / 'cases' / 'subdivided_patch_INPUT.json').read_text(encoding='utf-8'))
        frame = json.loads((prior / 'cases' / 'subdivided_patch_FRAME.json').read_text(encoding='utf-8'))
        frame.pop('image_ref')
        protected_paths = [Path(frame['arrays_path']), Path(frame['image_path']), prior / 'legacy' / 'patch_only.npz']
        protected_before = {str(path): sha(path) for path in protected_paths}
        with patch.object(images_module, 'rasterize_attention', side_effect=AssertionError('unexpected_product_raster')) as product_raster:
            with patch.object(raster_module, 'rasterize_attention', side_effect=AssertionError('unexpected_direct_raster')) as direct_raster:
                direct_raster.__signature__ = raster_signature
                session = active_module.prepare_scene(source['scene'], source['cameras'])
                images = images_module.ActiveObservationImages(session, output / 'unused_frames')
                actual = images.observe_frame(frame)
                old_binding = (images._binding, images._patch_mapping_identity, frame['view_name'], frame['image_sha256'])
                legacy_expected = 'active-image:' + active_module.fingerprint(old_binding)
                dual_expected = 'active-image:' + active_module.fingerprint(old_binding + (
                    images_module.OWNER_SCHEMA, images._patch_mapping['owner_identity'], frame.get('frame_identity')))
                legacy = {key: value for key, value in frame.items() if key not in (
                    'owner_schema', 'owner_mapping_identity', 'triangle_id_scope', 'owner_capabilities', 'frame_identity')}
                legacy.update(arrays_path=str(protected_paths[-1]), arrays_sha256=sha(protected_paths[-1]))
                legacy_actual = images.observe_frame(legacy)
                result.update(actual_dual_ref=actual['receipt']['image_ref'],
                              actual_legacy_ref=legacy_actual['receipt']['image_ref'],
                              expected_legacy_ref=legacy_expected, expected_dual_ref=dual_expected,
                              defect_reproduced=actual['receipt']['image_ref'] == legacy_actual['receipt']['image_ref'],
                              actual_product_raster_calls=product_raster.call_count,
                              actual_direct_raster_calls=direct_raster.call_count)
                assert legacy_actual['receipt']['image_ref'] == legacy_expected, 'legacy_fallback_must_stay_stable'
                if args.phase == 'before':
                    assert result['defect_reproduced'], 'expected_legacy_collision_before_fix'
                else:
                    assert actual['receipt']['image_ref'] == dual_expected, 'dual_schema_bound_fallback_required'
                    assert not result['defect_reproduced'], 'dual_legacy_fallback_collision'
                    unit_names = (
                        'verification.test_active_observation_images',
                        'verification.test_active_observation_patch_images',
                        'verification.test_active_observation_region_anchors',
                        'verification.test_active_observation_host',
                        'verification.test_active_observation_brief',
                    )
                    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in unit_names)
                    log = io.StringIO()
                    units = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
                    (output / 'UNIT_OUTPUT.txt').write_text(log.getvalue(), encoding='utf-8')
                    result['units'] = {'tests_run': units.testsRun, 'passed': units.wasSuccessful(),
                        'failures': [{'test': str(test), 'traceback': detail} for test, detail in units.failures],
                        'errors': [{'test': str(test), 'traceback': detail} for test, detail in units.errors]}
                    assert units.testsRun == 31 and units.wasSuccessful(), 'affected_mock_units'
                assert product_raster.call_count == direct_raster.call_count == 0, 'zero_raster_contract'
        result['protected_saved_bytes'] = protected_before
        assert protected_before == {str(path): sha(path) for path in protected_paths}, 'first_run_saved_bytes_changed'
        result['passed'] = True
    except Exception as error:
        result['failures'].append({'error_type': type(error).__name__, 'error': str(error),
                                   'traceback': traceback.format_exc()})
    write_json(output / 'RESULT.json', result)
    print(json.dumps({'phase': args.phase, 'passed': result['passed'], 'result': str(output / 'RESULT.json'),
                      'failures': [row['error'] for row in result['failures']]}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
