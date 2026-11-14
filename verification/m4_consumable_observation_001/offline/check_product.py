"""Zero-raster projection/state checks over saved source-bound receipts."""
import argparse
from collections import Counter
from contextlib import ExitStack
import copy
from dataclasses import replace
from fractions import Fraction
import hashlib
import importlib
import json
from pathlib import Path
import sys
import traceback
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = Path('D:/he_explicit_001/formal/P1/o/product_call_01/SERVICE_RESULT.json')
INDEX = Path('D:/he_anchor_001/run/acceptance_01/server/INDEX_01.json')
TRUTH = ROOT/'verification/m4_region_localization_consumption_001/admin/TRUTH.json'
INPUTS = {}
CHECKS = []


def read(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    INPUTS[str(path)] = hashlib.sha256(data).hexdigest()
    return json.loads(data)


def check(name, value):
    CHECKS.append({'name': name, 'passed': bool(value)})
    if not value:
        raise AssertionError(name)


def install_guards(core, host, rendering, raster, images, calls):
    stack = ExitStack()
    def forbidden(name):
        def reject(*args, **kwargs):
            calls.append(name)
            raise AssertionError('forbidden_new_geometry_or_raster:'+name)
        return reject
    for name in ('geometry', 'partition_regions', 'build_index_from_parsed', 'prepare_scene', 'prepare_scene_from_parsed'):
        stack.enter_context(patch.object(core, name, side_effect=forbidden('core.'+name)))
    for module, names in ((host, ('observe_capture', 'prepare_scene_from_parsed', 'freeze_cameras')),
                          (raster, ('rasterize_attention',)), (rendering, ('rasterize_attention',)),
                          (images, ('rasterize_attention',))):
        for name in names:
            stack.enter_context(patch.object(module, name, side_effect=forbidden(module.__name__+'.'+name)))
    return stack


def saved_session(core, original, metadata):
    regions = tuple(core.Region(row['roi_id'], row['object_index'], row['object_name'],
        tuple(row['triangle_indices']), tuple(tuple(Fraction(value) for value in point) for point in row['vertices']),
        tuple(Fraction(value) for value in row['normal'])) for row in metadata['regions'])
    index = core.CoverageIndex(metadata['scene_identity'], metadata['candidate_identity'], regions,
        tuple(metadata['view_order']), metadata['view_masks'], metadata['classifications'],
        patch_scope=tuple(metadata['patch_scope']))
    check('saved_source_identity', index.scene_identity == original['facts']['scene_identity']
          and index.candidate_identity == original['facts']['candidate_identity'])
    state = core.CoverageState(index)
    state.bind_patch_mapping(original['frames'][0]['patch_mapping_identity'])
    for observation in original['facts']['observations']:
        receipt = dict(observation, scene_identity=index.scene_identity, candidate_identity=index.candidate_identity,
            actual_image_delivered=True, pixel_evidence_scope='actual_common_depth_owner',
            patch_mapping_identity=state.patch_mapping_identity)
        state.observe(receipt)
    return core.ActiveObservationSession((), (), metadata['cameras'], index, state)


def full_value(session, original):
    with patch.object(session.state, 'summary', wraps=session.state.summary) as query:
        facts = session.short_facts()
        check('one_coverage_query_per_short_facts', query.call_count == 1)
    for region in facts['regions']:
        host = original['binding']['objects'][region['object_index']]
        region.update(host_id=host['host_id'], instance_id=host['instance_id'])
    for observation in facts['observations']:
        for row in observation['pixel_rows']:
            host = original['binding']['objects'][row['object_index']]
            row.update(host_id=host['host_id'], object_name=host['object_name'])
    facts['scope'] = copy.deepcopy(original['facts']['scope'])
    facts['location_conventions'] = copy.deepcopy(original['facts']['location_conventions'])
    result = copy.deepcopy(original)
    result['facts'] = facts
    return result


def rows(table):
    return [dict(zip(table['columns'], row)) for row in table['rows']]


def saved_checks(core, mcp, original, metadata, truth):
    session = saved_session(core, original, metadata)
    expected = {row['roi_alias']: row for row in truth['targets']}
    check('all_saved_masks_match_independent_geometry', all(
        bool(session.index.view_masks[view] & (1 << index)) == expected[region.roi_id]['by_view'][view]['geometry_complete']
        for index, region in enumerate(session.regions) for view in session.index.view_order))
    value = full_value(session, original)
    new_result = mcp._tool_result(value, is_error=False)
    brief = json.loads(new_result['content'][0]['text'])
    check('public_schema_v4', brief['schema'] == 'active-observation-brief-v4')
    counts = brief['inspection']['counts']
    check('actual_saved_counts', counts == dict(supported=138, covered=115, unobserved=23,
        pending_geometric_candidate=0, no_geometric_complete_candidate=23, pixel_insufficient=0,
        covered_without_witness=0))
    check('actual_saved_finite_pool_stop', brief['inspection']['state'] == 'finite_pool_exhausted'
          and brief['inspection']['stop_reason'] == 'no_unobserved_geometric_candidates')
    regions, pixels, frames = rows(brief['regions']), rows(brief['pixels']), rows(brief['images'])
    witness_checks = 0
    for index, region in enumerate(regions):
        witness = region['complete_witness_pixel_index']
        if region['status'] != 'covered':
            check('unobserved_has_no_complete_witness_'+str(index), witness is None)
            continue
        pixel = pixels[witness]
        view = frames[pixel['image_index']]['view_name']
        check('complete_witness_'+str(index), pixel['region_index'] == index and pixel['readable']
              and expected[region['roi_id']]['by_view'][view]['geometry_complete']
              and pixel['visible_surface_pixels'] >= 16 and pixel['contrasting_boundary_pixels'] >= 4)
        witness_checks += 1
    check('115_current_complete_witnesses', witness_checks == 115)
    check('unobserved_reason_partition', Counter(row['unobserved_reason'] for row in regions if row['status'] == 'unknown')
          == {'no_front_facing_candidate': 22, 'positive_area_occlusion_all_front_views': 1})
    check('compact_reason_groups', len(brief['unobserved_view_groups']['rows']) == 2)
    missed = next(row for row in regions if row['center_world_m'] == [0.3515625, 0, 0]
                  and row['front_direction_world'] == [0, 0, 1])
    witness = pixels[missed['complete_witness_pixel_index']]
    check('previously_missed_face_BACK_witness', frames[witness['image_index']]['view_name'] == 'BACK'
          and witness['visible_surface_pixels'] == 468 and witness['contrasting_boundary_pixels'] == 84)
    click = next(pixel for pixel in pixels if frames[pixel['image_index']]['view_name'] == 'SCENE'
                 and pixel['visible_pixel_anchor'] == [109, 247])
    check('click_world_location', regions[click['region_index']]['center_world_m'] == [0.15625, -0.15625, 0.11865234375])
    origin_index = next(i for i, row in enumerate(regions) if row['center_world_m'] == [0, 0, 0]
                        and row['front_direction_world'] == [0, 0, 1])
    scene = next(pixel for pixel in pixels if pixel['region_index'] == origin_index
                 and frames[pixel['image_index']]['view_name'] == 'SCENE')
    origin_witness = pixels[regions[origin_index]['complete_witness_pixel_index']]
    witness_view = frames[origin_witness['image_index']]['view_name']
    check('origin_occluded_SCENE_and_other_complete_witness', scene['front_facing'] and scene['visible_surface_pixels'] == 0
          and witness_view != 'SCENE' and expected[regions[origin_index]['roi_id']]['by_view'][witness_view]['geometry_complete']
          and origin_witness['visible_pixel_anchor'] is not None)
    bottom = next(row for row in regions if row['center_world_m'] == [0.15625, -0.15625, 0.11572265625]
                  and row['front_direction_world'] == [0, 0, -1])
    check('bottom_finite_pool_unknown', bottom['status'] == 'unknown' and bottom['unobserved_reason'] == 'no_front_facing_candidate')
    unsupported = brief['scope']['patch_support']['unsupported_components']['rows']
    check('unsupported_triangle_48_retained', unsupported[0][-1] == [[48, 48]])
    old_result = mcp._tool_result(original, is_error=False)
    old_brief = json.loads(old_result['content'][0]['text'])
    stripped = copy.deepcopy(brief)
    stripped['schema'] = old_brief['schema']
    stripped.pop('inspection'); stripped.pop('unobserved_view_groups')
    stripped['regions']['columns'] = stripped['regions']['columns'][:-3]
    stripped['regions']['rows'] = [row[:-3] for row in stripped['regions']['rows']]
    check('historical_v3_fields_preserved_exactly', stripped == old_brief)
    check('native_png_content_unchanged', new_result['content'][1:] == old_result['content'][1:])
    full = mcp._tool_result(value, is_error=False, response_detail='full')
    check('full_debug_preserves_complete_facts', json.loads(full['content'][0]['text'])['facts'] == value['facts'])
    check('full_debug_same_native_images', full['content'][1:] == new_result['content'][1:])
    for name, mutate in (
            ('count_conflict', lambda v: v['facts']['inspection']['counts'].update(covered=114)),
            ('wrong_witness', lambda v: v['facts']['region_evidence'][7]['complete_witness'].update(pixel_row_index=0)),
            ('false_pool_stop', lambda v: v['facts']['region_evidence'][0]['view_reasons'].update(unobserved_geometric_candidate=['SCENE']))):
        changed = copy.deepcopy(value)
        mutate(changed)
        check(name+'_retains_full_fallback', mcp.project_active_observation_brief(changed) is None)
    return dict(current_complete_witnesses=witness_checks, current_region_count=len(regions),
        origin_complete_witness_view=witness_view, origin_complete_witness_pixel=origin_witness['visible_pixel_anchor'],
        old_v3_JSON_bytes=len(old_result['content'][0]['text'].encode('utf8')),
        new_v4_JSON_bytes=len(new_result['content'][0]['text'].encode('utf8')),
        public_JSON_byte_delta=len(new_result['content'][0]['text'].encode('utf8'))-len(old_result['content'][0]['text'].encode('utf8')),
        standalone_projection_CPU='unmeasured; existing scope_and_facts and whole MCP delivery clocks retain their scope')


def boundary_checks(core, original):
    region = core.Region('fixture', 0, 'Fixture', (0, 1),
        tuple(tuple(Fraction(x) for x in p) for p in ((0,0,0),(1,0,0),(1,1,0),(0,1,0))), (0,0,1))
    def session(masks, statuses):
        index = core.CoverageIndex('scene', 'camera', (region,), tuple(masks), masks,
            {name: {'fixture': {'status': status, 'complete': bool(masks[name])}} for name, status in statuses.items()})
        return core.ActiveObservationSession((), (), {}, index, core.CoverageState(index))
    def receipt(value, readable, surface=30, boundary=8):
        frame = original['frames'][0]
        row = dict(roi_id='fixture', object_index=0, view='SCENE', front_facing=True,
            visible_surface_pixels=surface, contrasting_boundary_pixels=boundary, readable=readable,
            minimum_surface_pixels=16, minimum_boundary_pixels=4, minimum_rgb_boundary_contrast=24)
        return dict(scene_identity=value.scene_identity, candidate_identity=value.candidate_identity,
            view_name='SCENE', image_path=frame['image_path'], image_sha256=frame['image_sha256'], image_ref=frame['image_ref'],
            actual_image_delivered=True, pixel_evidence_scope='actual_common_depth_owner',
            readable_roi_ids=['fixture'] if readable else [], pixel_rows=[row])
    partial = session({'SCENE':0, 'BACK':1}, {'SCENE':'positive_area_occlusion', 'BACK':'complete'})
    partial.observe(receipt(partial, True))
    facts = partial.short_facts()
    check('readable_does_not_establish_complete', facts['inspection']['counts']['covered'] == 0
          and facts['region_evidence'][0]['complete_witness'] is None)
    check('unobserved_candidate_not_pool_exhausted', facts['inspection']['state'] == 'observation_required'
          and facts['region_evidence'][0]['view_reasons']['unobserved_geometric_candidate'] == ['BACK'])
    predicted = session({'SCENE':1}, {'SCENE':'complete'})
    facts = predicted.short_facts()
    check('prediction_only_no_evidence', facts['inspection']['state'] == 'prediction_only'
          and facts['inspection']['counts']['covered'] == 0 and not facts['observations'])
    low = session({'SCENE':1}, {'SCENE':'complete'})
    low.observe(receipt(low, False, 10, 3))
    facts = low.short_facts()
    check('actual_pixels_insufficient', facts['inspection']['counts']['pixel_insufficient'] == 1
          and facts['region_evidence'][0]['unobserved_reason'] == 'pixel_evidence_insufficient')
    for field in ('scene_identity', 'candidate_identity'):
        current = session({'SCENE':1}, {'SCENE':'complete'})
        current.observe(receipt(current, True))
        index = replace(current.index, **{field: 'changed'})
        current.state.rebind(index); current.index = index
        facts = current.short_facts()
        check(field+'_invalidates_receipts', facts['inspection']['counts']['covered'] == 0 and not facts['observations'])
    current = session({'SCENE':1}, {'SCENE':'complete'})
    current.state.bind_patch_mapping('patch-a')
    bound = dict(receipt(current, True), patch_mapping_identity='patch-a')
    current.observe(bound)
    current.state.bind_patch_mapping('patch-b')
    check('patch_mapping_rebind_invalidates', current.short_facts()['inspection']['counts']['covered'] == 0)
    try:
        current.observe(bound)
    except ValueError:
        rejected = True
    else:
        rejected = False
    check('old_patch_receipt_rejected', rejected)
    current.state.invalidate_patch_mapping()
    check('patch_mapping_explicit_invalidate', current.short_facts()['inspection']['counts']['covered'] == 0)


def legacy_tests():
    selected = {
        'verification.test_active_observation_brief': ('ActiveObservationBriefTests', None),
        'verification.test_active_observation_patch_delivery': ('ActiveObservationPatchDeliveryTests', 'test_normal_host_entry_text_request_keeps_patch_scope_without_images'),
        'verification.test_active_observation_region_delivery': ('ActiveObservationRegionDeliveryTests', 'test_host_copies_world_clock_and_declares_one_shared_coordinate_contract'),
    }
    suite = unittest.TestSuite()
    for name, (class_name, excluded) in selected.items():
        case = getattr(importlib.import_module(name), class_name)
        for method in unittest.defaultTestLoader.getTestCaseNames(case):
            if method != excluded:
                suite.addTest(case(method))
    world = importlib.import_module('verification.test_active_observation_region_world')
    case = world.ActiveObservationRegionWorldTests
    for method in ('test_non_axis_aligned_rectangle_matches_direct_source_corners',
                   'test_simple_numbers_and_fraction_strings_preserve_exact_values',
                   'test_huge_and_underflowing_rationals_are_lossless'):
        suite.addTest(case(method))
    result = unittest.TestResult()
    suite.run(result)
    return dict(run=result.testsRun, failures=[dict(test=str(test), traceback=text) for test,text in result.failures],
                errors=[dict(test=str(test), traceback=text) for test,text in result.errors],
                passed=result.wasSuccessful())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--product-root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.product_root.resolve()))
    sys.path.append(str(ROOT))
    result = dict(schema='consumable-observation-zero-raster-offline-v1', product_root=str(args.product_root.resolve()),
                  passed=False, new_rasters=0, new_model_calls=0, actual_observe_capture_calls=0)
    forbidden_calls = []
    try:
        import human_eye_plugin.active_observation as core
        import human_eye_plugin.active_observation_host as host
        import human_eye_plugin.active_observation_images as images
        import human_eye_plugin.attention_raster as raster
        import human_eye_plugin.attention_rendering as rendering
        import human_eye_plugin.live_spatial_mcp as mcp
        import numpy as np
        import PIL
        result['runtime'] = dict(python=str(Path(sys.executable).resolve()),
            python_sha256=hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
            numpy=dict(path=np.__file__, version=np.__version__, sha256=hashlib.sha256(Path(np.__file__).read_bytes()).hexdigest()),
            pillow=dict(path=PIL.__file__, version=PIL.__version__, sha256=hashlib.sha256(Path(PIL.__file__).read_bytes()).hexdigest()))
        modules = (core, mcp)
        result['product_modules'] = [dict(path=str(Path(module.__file__).resolve()),
            sha256=hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()) for module in modules]
        check('actual_product_import_root', all(Path(module.__file__).resolve().is_relative_to(args.product_root.resolve()) for module in modules))
        original, metadata, truth = read(SOURCE), read(INDEX), read(TRUTH)
        with install_guards(core, host, rendering, raster, images, forbidden_calls):
            result['saved_result'] = saved_checks(core, mcp, original, metadata, truth)
            boundary_checks(core, original)
            result['legacy_zero_raster_tests'] = legacy_tests()
            check('legacy_zero_raster_subset', result['legacy_zero_raster_tests']['passed'])
        check('no_forbidden_geometry_or_raster_called', not forbidden_calls)
        result['passed'] = True
    except Exception as error:
        result['error'] = dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc())
    result.update(checks=CHECKS, forbidden_calls=forbidden_calls, inputs_sha256=INPUTS,
        unrun='Geometry/index construction, actual observe_capture/service generation, Blender, raster and renderer-dependent tests. No standalone projection timing benchmark.')
    with args.output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')
    print(json.dumps(dict(passed=result['passed'], checks=len(CHECKS), error=result.get('error'),
                         new_rasters=0, actual_observe_capture_calls=0), ensure_ascii=False))
    raise SystemExit(0 if result['passed'] else 1)


if __name__ == '__main__':
    main()
