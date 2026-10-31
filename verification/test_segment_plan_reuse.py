"""Differential live-service checks for request-local readback-plan reuse.

The immutable baseline is the v21 implementation saved before this change.
Both arms use the real solver and checked single-step service, with independent
temporary state and a mutable in-memory host; no Blender or provider is called.
"""
from __future__ import annotations

from contextlib import ExitStack
import copy
import importlib.util
import itertools
import json
from pathlib import Path
import re
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid

from human_eye_plugin import goal_execution as candidate
from human_eye_plugin.auto_router import _validated_scene
from human_eye_plugin.live_service import LiveSpatialService
from verification.test_clearance_segment_service import SegmentClock, SegmentHost
from verification.test_support_plane_candidate import flat_scene, slope_scene, tilted_scene
from verification.test_support_plane_segment import PlaneSegmentHost, support_request


ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / 'verification/fixes/20261030_v21_deterministic_reuse/before/human_eye_plugin/goal_execution.py'


def load_baseline():
    spec = importlib.util.spec_from_file_location('human_eye_plugin._segment_reuse_baseline', BASELINE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def box_request(**changes):
    value = {'focal_id': 'part', 'reference_id': 'base', 'axis': '+z',
        'target_clearance_m': .001, 'clearance_tolerance_m': 1e-6,
        'max_steps': 8, 'max_step_translation_m': .001,
        'max_total_translation_m': .04, 'max_duration_s': 10.}
    value.update(changes)
    return value


def _disabled_capability(host):
    host.scene['host_execution'] = {'schema_version': '1.0',
        'operation': 'rigid_transform', 'supported': False,
        'scope': 'independent_static_rigid_meshes',
        'reasons': [{'object_id': 'part', 'object_name': 'part', 'reason': 'test_locked'}]}


def run_case(module, *, solver='support_plane', shape='flat', changes=None,
             mutation=None, mode='normal', expire=None, spoof_post_alias=False,
             execute=True, repeat=False, caller_mutation=None):
    """Freeze clocks/IDs; return full receipts, state and all actual host work."""
    clock = SegmentClock()
    if solver == 'box':
        host = SegmentHost()
        request = box_request(**(changes or {}))
    else:
        scene = {'flat': flat_scene, 'tilted': tilted_scene, 'slope': slope_scene}[shape]()
        host = PlaneSegmentHost(scene, normal=(-.5, 0., 1.) if shape == 'slope' else (0., 0., 1.))
        request = support_request(**{'max_step_translation_m': .001, **(changes or {})})
    host.mode = mode
    if mutation:
        host.change_between_steps = mutation
    if caller_mutation:
        host.change_between_steps = lambda _host: request.update(caller_mutation)
    if expire == 'capture':
        host.after_capture = clock.expire
    elif expire == 'commit':
        host.after_mutation = clock.expire
    real_solve = module.solve_segment_candidate
    calls = []
    hash_calls = []
    original_hash = module._fingerprint
    observed_actions = []
    original_apply = host.apply_transform
    def apply(*args, **kwargs):
        observed_actions.append(copy.deepcopy(args[0]))
        return original_apply(*args, **kwargs)
    host.apply_transform = apply
    def solve(scene, req, **kwargs):
        calls.append({'scene': copy.deepcopy(scene), 'request': copy.deepcopy(req),
            'expected_feature_signature': kwargs.get('expected_feature_signature')})
        return real_solve(scene, req, **kwargs)
    def fingerprint(value):
        if isinstance(value, dict) and 'meshes' in value:
            hash_calls.append(copy.deepcopy(value))
        return original_hash(value)
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        config = {'schema_version': '1.0', 'project_root': str(ROOT),
            'state_file': 'state.json', 'audit_file': 'events.jsonl', 'quad_size': 64,
            'max_sessions': 4, 'enabled': True}
        config_path = folder / 'live.json'
        config_path.write_text(json.dumps(config), encoding='utf-8')
        ids = itertools.count(1)
        with ExitStack() as stack:
            stack.enter_context(patch.object(time, 'monotonic', side_effect=clock.monotonic))
            stack.enter_context(patch.object(time, 'monotonic_ns', side_effect=lambda: int(clock.value * 1e9)))
            stack.enter_context(patch.object(time, 'perf_counter', return_value=0.))
            stack.enter_context(patch.object(time, 'perf_counter_ns', return_value=0))
            stack.enter_context(patch.object(time, 'time', return_value=1000.))
            stack.enter_context(patch.object(uuid, 'uuid4', side_effect=lambda: uuid.UUID(int=next(ids))))
            stack.enter_context(patch.object(module, 'solve_segment_candidate', side_effect=solve))
            stack.enter_context(patch.object(module, '_fingerprint', side_effect=fingerprint))
            # Public entry remains decorated by the real service budget and
            # journaling implementation. Select only the old/new segment body.
            stack.enter_context(patch.object(candidate, 'run_clearance_segment', module.run_clearance_segment))
            service = LiveSpatialService(config_path, host=host)
            if spoof_post_alias:
                # Mutate both host and the retained readback only on the next
                # capture, after the prior post-plan fingerprint was frozen.
                def change_alias(target):
                    target.scene['source'] = 'changed_after_post_plan'
                    active_runtime[0]._last_verified_scene['source'] = 'changed_after_post_plan'
                host.change_between_steps = change_alias
                active_runtime = []
                original_transform = service._transform_locked
                def retain_runtime(value, runtime, *args, **kwargs):
                    active_runtime[:] = [runtime]
                    return original_transform(value, runtime, *args, **kwargs)
                service._transform_locked = retain_runtime
            original = copy.deepcopy(request)
            result = service.run_clearance_segment('reuse-test', 'reuse-request', request,
                execute=execute, include_image=False)
            replay = (service.run_clearance_segment('reuse-test', 'reuse-request', request,
                execute=execute, include_image=False) if repeat else None)
        state_path = folder / 'state.json'
        state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else None
    assert request == ({**original, **caller_mutation} if caller_mutation else original)
    return {'result': result, 'replay': replay, 'scene': host.scene, 'actions': observed_actions,
        'state': state, 'solver_calls': calls, 'scene_hash_calls': len(hash_calls),
        'host_calls': host.calls, 'host_captures': host.captures}


def semantic(value):
    """Canonicalize generated IDs while preserving all references and values.

    Mesh constructors also draw from UUID, so fewer solver calls change later
    step IDs even with a deterministic generator. Full 32-hex generated IDs
    receive first-occurrence tokens; 64-hex geometric digests remain exact.
    """
    ids = {}
    def visit(item):
        if isinstance(item, dict):
            return {visit(key): visit(child) for key, child in item.items()
                if key not in {'configuration_fingerprint'}}
        if isinstance(item, list):
            return [visit(child) for child in item]
        if isinstance(item, str) and re.fullmatch('[a-f0-9]{32}', item):
            if item not in ids:
                ids[item] = 'generated-id-' + str(len(ids))
            return ids[item]
        return item
    return visit(value)


class SegmentPlanReuseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = load_baseline()

    def compare(self, **kwargs):
        old, new = run_case(self.baseline, **kwargs), run_case(candidate, **kwargs)
        # Compare complete results and durable state, including all geometric
        # certificates and actual step actions, not merely the final status.
        for key in ('result', 'replay', 'scene', 'actions', 'state', 'host_calls', 'host_captures'):
            self.assertEqual(semantic(old[key]), semantic(new[key]), key)
        self.assertLessEqual(len(new['solver_calls']), len(old['solver_calls']))
        self.assertLessEqual(new['scene_hash_calls'], old['scene_hash_calls'])
        return old, new

    def test_four_step_support_plane_reuses_only_identical_post_plans(self):
        old, new = self.compare()
        self.assertEqual(new['result']['status'], 'satisfied')
        self.assertEqual((old['host_calls'], new['host_calls']), (4, 4))
        self.assertEqual((len(old['solver_calls']), len(new['solver_calls'])), (10, 7))
        self.assertEqual(new['scene_hash_calls'], old['scene_hash_calls'])
        # Changed remaining caps still produce separate bounded candidate solves.
        self.assertGreater(len(new['solver_calls']), new['host_calls'] + 1)

    def test_box_solver_and_tilted_support_keep_complete_receipts(self):
        for settings in ({'solver': 'box'}, {'shape': 'tilted'}, {'shape': 'slope'}):
            with self.subTest(**settings):
                self.compare(**settings)

    def test_single_step_and_preview_have_no_extra_hash_or_solver(self):
        for settings in ({'changes': {'max_step_translation_m': .01}}, {'execute': False}):
            with self.subTest(**settings):
                old, new = self.compare(**settings)
                self.assertEqual(len(new['solver_calls']), len(old['solver_calls']))
                self.assertEqual(new['scene_hash_calls'], 0)

    def test_step_and_actual_total_budget_limits_keep_partial_receipts(self):
        for changes in ({'max_steps': 1}, {'max_total_translation_m': .0015},
                        {'max_steps': 2, 'max_total_translation_m': .002}):
            with self.subTest(changes=changes):
                old, new = self.compare(changes=changes)
                self.assertEqual(new['result']['status'], 'review_required')
                self.assertLessEqual(new['result']['actual_total_translation_m'], changes.get('max_total_translation_m', .04))

    def test_already_satisfied_precedes_insufficient_motion_budget(self):
        for goal in (.001, .004):
            with self.subTest(target=goal):
                old, new = self.compare(changes={'target_clearance_m': goal,
                    'max_step_translation_m': 1e-7, 'max_total_translation_m': 1e-7})
                self.assertEqual(new['host_calls'], 0)
                self.assertEqual(new['result']['status'], 'satisfied' if goal == .004 else 'review_required')

    def test_same_revision_scene_fields_invalidate_plan(self):
        def geometry(host):
            host.scene['meshes'][1]['vertices'][0][0] += 1e-5
        def pivot(host):
            host.scene['meshes'][1]['pivot_world'][0] += 1e-5
        def frame(host):
            host.scene['meshes'][1]['local_axes'] = [[0., 1., 0.], [-1., 0., 0.], [0., 0., 1.]]
        def source(host):
            host.scene['source'] = {'kind': 'new_provenance'}
        def identity(host):
            host.scene['host_identity']['object_instances']['part'] = 'recreated-part'
        def document(host):
            host.scene['host_identity']['document_epoch'] = 'different-document'
        for mutation in (geometry, pivot, frame, source, identity, document, _disabled_capability):
            with self.subTest(mutation=mutation.__name__):
                old, new = self.compare(mutation=mutation)
                self.assertEqual(new['host_calls'], 1)
                self.assertEqual(new['result']['reason_codes'], ['external_scene_change_between_steps'])

    def test_unknown_write_never_reuses_or_retries(self):
        old, new = self.compare(mode='partial_failure', repeat=True)
        self.assertEqual(new['result']['status'], 'execution_uncertain')
        self.assertEqual(new['host_calls'], 1)
        self.assertEqual(len(new['solver_calls']), 1)

    def test_selected_feature_crossing_is_still_refused_without_write(self):
        old, new = self.compare(shape='tilted', changes={
            'direction_world': [1., 0., .05], 'target_clearance_m': .006,
            'max_step_translation_m': .2, 'max_total_translation_m': .2})
        self.assertEqual(new['result']['status'], 'blocked')
        self.assertEqual(new['host_calls'], 0)

    def test_caller_cannot_change_private_target_or_caps_between_steps(self):
        old, new = self.compare(caller_mutation={'target_clearance_m': .003,
            'max_steps': 1, 'max_step_translation_m': .1, 'max_total_translation_m': 1.})
        self.assertEqual(new['result']['status'], 'satisfied')
        self.assertEqual(new['host_calls'], 4)
        self.assertEqual(new['result']['request']['target_clearance_m'], .001)
        self.assertEqual(new['result']['request']['max_step_translation_m'], .001)

    def test_deadline_before_and_after_commit_keep_existing_stop_semantics(self):
        for expire in ('capture', 'commit'):
            with self.subTest(expire=expire):
                old, new = self.compare(expire=expire)
                self.assertEqual(new['result']['status'], 'review_required')
                self.assertEqual(new['host_calls'], int(expire == 'commit'))

    def test_replay_returns_prior_receipt_without_new_capture(self):
        old, new = self.compare(repeat=True)
        self.assertTrue(new['replay']['historical_receipt'])
        self.assertEqual(new['host_calls'], 4)

    def test_aliased_readback_cannot_change_cached_input_after_planning(self):
        old = run_case(self.baseline, spoof_post_alias=True)
        new = run_case(candidate, spoof_post_alias=True)
        # Explicit strengthening: the old comparison hashes the already
        # modified alias; the frozen new binding detects its content changed.
        self.assertEqual(old['result']['status'], 'satisfied')
        self.assertEqual(old['host_calls'], 4)
        self.assertEqual(new['result']['reason_codes'], ['external_scene_change_between_steps'])
        self.assertEqual(new['host_calls'], 1)


if __name__ == '__main__':
    unittest.main()
