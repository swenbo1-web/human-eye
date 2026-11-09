"""Narrow entry-selection and static-export regressions on indexed bpy doubles.

No Blender, socket, training or model API is used. Bridge checks retain the
production codecs and replace only the endpoint, like the accepted entry tests.
"""
from contextlib import ExitStack
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from human_eye_plugin import arm_twist_source as current_source
from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer
from human_eye_plugin.owned_task_mcp import OwnedTaskMCP
from verification.arch_expert_entry_001 import test_entry as entry_fixture
from verification.m6_arm_source_001 import test_arm_source as source_fixture

OLD_COMMIT = 'c5116e30024ed12825aea6119c0f5172e6b9b46d'
OLD_SOURCE_SHA = '653eaaa9ee3292a1a490ba4a01637e495977bd9f668e1c584c9649927cf92715'
OBSERVATIONS = {}


def load_old_source():
    filename = 'human_eye_plugin/arm_twist_source.py'
    raw = subprocess.check_output(['git', 'show', OLD_COMMIT + ':' + filename], cwd=ROOT)
    if hashlib.sha256(raw).hexdigest() != OLD_SOURCE_SHA:
        raise AssertionError('Old source Git bytes differ from accepted source')
    module = ModuleType('human_eye_plugin._entry_opt_old_source')
    module.__package__ = 'human_eye_plugin'
    exec(compile(raw, OLD_COMMIT + ':' + filename, 'exec'), module.__dict__)
    return module


class EntryOptimizationTests(unittest.TestCase):
    def fixture(self, *, module=current_source):
        fixture = source_fixture.make_host()
        self.addCleanup(fixture.host.close_residency)
        def topology(obj, indices):
            allowed = set(indices)
            return [face[:] for face in fixture.global_triangles if all(i in allowed for i in face)]
        adapter = module.ArmTwistSource(fixture.host, topology_reader=topology)
        fixture.host._arm_twist_adapter = adapter
        return fixture, adapter

    def selections(self, fixture):
        explicit = copy.deepcopy(fixture.selection)
        explicit['sections'] = explicit['sections'][:-1]
        implicit = {key: copy.deepcopy(value) for key, value in explicit.items() if key != 'vertex_indices'}
        self.assertEqual(len(explicit['vertex_indices']), 402)
        self.assertEqual(len(set(i for section in implicit['sections'] for i in section)), 384)
        return explicit, implicit

    def assert_repeat(self, fixture, selection, bound, report):
        prepared = bound.prepared
        before = bound.work_totals()
        repeated = fixture.host.observe_arm_twist(copy.deepcopy(selection))
        self.assertIs(fixture.host._arm_twist_bound, bound)
        self.assertIs(bound.prepared, prepared)
        self.assertEqual(repeated, report)
        after = bound.work_totals()
        self.assertEqual(after['captures'], before['captures'] + 1)
        self.assertEqual(after['preparations'], before['preparations'])
        self.assertEqual(after['static_reads'], before['static_reads'])

    def test_explicit_superset_to_default_uses384_and_both_requests_repeat_warm(self):
        fixture, adapter = self.fixture()
        explicit, implicit = self.selections(fixture)
        first = fixture.host.observe_arm_twist(explicit)
        old_bound = fixture.host._arm_twist_bound
        self.assertEqual(first['source']['selected_vertices'], 402)
        self.assert_repeat(fixture, explicit, old_bound, first)
        changed = fixture.host.observe_arm_twist(implicit)
        bound = fixture.host._arm_twist_bound
        expected = adapter.bind(implicit).analyze()
        self.assertIsNot(bound, old_bound)
        self.assertEqual(changed['status'], 'estimated')
        self.assertEqual(changed['source']['selected_vertices'], 384)
        self.assertNotEqual(changed['source']['selection_key'], first['source']['selection_key'])
        self.assertEqual(changed, expected)
        self.assert_repeat(fixture, implicit, bound, changed)

    def test_default_to_explicit_superset_uses402_and_both_requests_repeat_warm(self):
        fixture, adapter = self.fixture()
        explicit, implicit = self.selections(fixture)
        first = fixture.host.observe_arm_twist(implicit)
        old_bound = fixture.host._arm_twist_bound
        self.assertEqual(first['source']['selected_vertices'], 384)
        self.assert_repeat(fixture, implicit, old_bound, first)
        changed = fixture.host.observe_arm_twist(explicit)
        bound = fixture.host._arm_twist_bound
        expected = adapter.bind(explicit).analyze()
        self.assertIsNot(bound, old_bound)
        self.assertEqual(changed['status'], 'estimated')
        self.assertEqual(changed['source']['selected_vertices'], 402)
        self.assertNotEqual(changed['source']['selection_key'], first['source']['selection_key'])
        self.assertEqual(changed, expected)
        self.assert_repeat(fixture, explicit, bound, changed)

    def test_caller_adds_indices_and_mutates_lists_without_rewriting_retained_request(self):
        fixture, _ = self.fixture()
        explicit, implicit = self.selections(fixture)
        fixture.host.observe_arm_twist(implicit)
        default_bound = fixture.host._arm_twist_bound
        retained = copy.deepcopy(default_bound._selection)
        implicit['vertex_indices'] = explicit['vertex_indices'][:]
        self.assertEqual(default_bound._selection, retained)
        report = fixture.host.observe_arm_twist(implicit)
        explicit_bound = fixture.host._arm_twist_bound
        self.assertIsNot(explicit_bound, default_bound)
        self.assertEqual(report['source']['selected_vertices'], 402)
        valid_request = copy.deepcopy(implicit)
        retained = copy.deepcopy(explicit_bound._selection)
        implicit['vertex_indices'].reverse()
        implicit['sections'][0].reverse()
        self.assertEqual(explicit_bound._selection, retained)
        self.assert_repeat(fixture, valid_request, explicit_bound, report)

    def test_public_capture_static_export_is_deeply_isolated_from_cache_and_prepared(self):
        fixture, adapter = self.fixture()
        bound = adapter.bind(fixture.selection)
        with patch.object(current_source, 'deepcopy', wraps=copy.deepcopy) as copies:
            capture = bound.capture()
        exports = [call for call in copies.call_args_list if isinstance(call.args[0], dict)
                   and call.args[0].get('schema') == 'arm-twist-patch-v1']
        self.assertEqual(len(exports), 1)
        original = copy.deepcopy(bound._static)
        prepared = bound.prepared
        expected = prepared.analyze(capture['current_vertices'], capture['pose_matrices'])
        exported = capture['static_patch']
        self.assertIsNot(exported, bound._static)
        exported['rest_vertices'][0][0] += 10.
        exported['weights'][0][0] = 99.
        exported['bone_chain'][0]['rest_matrix'][0][3] += 10.
        exported['triangles'][0][0] = -1
        exported['sections'][0][0] = -1
        exported['vertex_ids'][0] = -1
        self.assertEqual(bound._static, original)
        self.assertIs(bound.prepared, prepared)
        repeated = bound.capture()
        self.assertFalse(repeated['static_changed'])
        self.assertIsNone(repeated['static_patch'])
        self.assertIs(bound.prepared, prepared)
        self.assertEqual(prepared.analyze(repeated['current_vertices'], repeated['pose_matrices']), expected)
        self.assertEqual(bound._static, original)

    def test_old_new_analyze_work_and_reports_match_while_changed_exports_drop3_to0(self):
        def run(module):
            fixture, adapter = self.fixture(module=module)
            bound = adapter.bind(fixture.selection)
            reports = []
            counts = []
            capture_calls = []
            for step in ('first', 'repeat', 'static', 'load'):
                if step == 'static':
                    for native in fixture.selection['sections'][0]:
                        fixture.mesh.data.vertices.rows[native].co[0] += 1e-4
                    source_fixture.replay_selected(fixture)
                    source_fixture.notify(fixture, fixture.mesh.data)
                if step == 'load':
                    for callback in tuple(fixture.bpy.app.handlers.load_post):
                        callback(fixture.host.scene)
                with patch.object(module, 'deepcopy', wraps=copy.deepcopy) as copies:
                    with patch.object(bound, 'capture', wraps=bound.capture) as captures:
                        report = bound.analyze()
                counts.append(sum(isinstance(call.args[0], dict)
                    and call.args[0].get('schema') == 'arm-twist-patch-v1' for call in copies.call_args_list))
                capture_calls.append(captures.call_count)
                reports.append(report)
            return reports, counts, capture_calls, bound.work_totals()
        old = run(load_old_source())
        new = run(current_source)
        self.assertEqual(old[1], [1, 0, 1, 1])
        self.assertEqual(new[1], [0, 0, 0, 0])
        self.assertEqual(old[2], [1, 1, 1, 1])
        self.assertEqual(new[2], old[2])
        self.assertEqual(old[3], new[3])
        self.assertEqual(new[3]['captures'], 4)
        self.assertEqual(new[3]['preparations'], 3)
        for previous, candidate in zip(old[0], new[0]):
            self.assertEqual({k: v for k, v in previous.items() if k != 'source'},
                             {k: v for k, v in candidate.items() if k != 'source'})
            for key in ('epoch', 'static_revision', 'selection_key', 'frame', 'unit', 'coordinate_frame',
                        'selected_vertices', 'selected_bones'):
                self.assertEqual(previous['source'][key], candidate['source'][key])
        OBSERVATIONS['static_exports'] = dict(sequence=['first', 'repeat', 'static', 'load'],
            old=old[1], new=new[1], captures=new[2], old_work=old[3], new_work=new[3])

    def unknown_route(self, route):
        fixture, _ = self.fixture()
        rest0 = np.asarray(fixture.rig.data.bones[0].matrix_local)
        rest1 = np.asarray(fixture.rig.data.bones[1].matrix_local)
        fixture.rig.pose.bones[0].matrix = rest0.tolist()
        fixture.rig.pose.bones[1].matrix = (rest1 @ np.diag([1., -1., -1., 1.])).tolist()
        source_fixture.replay_selected(fixture)
        source_fixture.notify(fixture, fixture.rig)
        host = fixture.host
        if route == 'owned_bridge_mcp':
            host, endpoint, _ = entry_fixture.owned_client()
        elif route == 'shared_bridge_owned_task':
            host = entry_fixture.SharedEndpoint()
            self.addCleanup(host.close)
            endpoint = host.endpoint
        if route != 'direct_service_mcp':
            original = endpoint.dispatch
            def dispatch(request):
                if request['command'] == 'observe_arm_twist':
                    return {'result': fixture.host.observe_arm_twist(request['params']['selection'])}
                return original(request)
            endpoint.dispatch = dispatch
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            config = folder / 'connector.json'
            config.write_text(json.dumps(dict(schema_version='1.0', enabled=True, project_root=str(ROOT),
                state_file='state.json', audit_file='audit.jsonl', quad_size=64)), encoding='utf8')
            service = LiveSpatialService(config, host=host)
            service.state_path.write_bytes(b'opaque entry-opt action ledger')
            mcp = LiveSpatialMCPServer(service, 'entry-opt-unknown')
            entry = mcp
            if route == 'shared_bridge_owned_task':
                entry = object.__new__(OwnedTaskMCP)
                entry.initialized = True
                entry.live = mcp
                entry.episodes = {}
                entry._goal = entry_fixture.forbidden
            def request(request_id):
                message = dict(jsonrpc='2.0', id=request_id, method='tools/call', params=dict(
                    name=entry_fixture.TOOL, arguments={'selection': copy.deepcopy(fixture.selection)}))
                return entry.handle(message) if isinstance(entry, OwnedTaskMCP) else entry.handle_jsonrpc_message(message)
            with ExitStack() as stack:
                for name in ('_locked', '_runtime', '_save'):
                    stack.enter_context(patch.object(service, name, side_effect=entry_fixture.forbidden))
                reply = request(1)
                self.assertIs(reply['result']['isError'], False)
                unknown = json.loads(reply['result']['content'][0]['text'])
                self.assertEqual(unknown['status'], 'unknown')
                self.assertEqual(unknown['reason'], 'bone_twist_branch_unknown')
                self.assertEqual(unknown['regions'], [])
                self.assertNotIn('max_severity', unknown)
                self.assertEqual(unknown['source']['selected_vertices'], 402)
                bound = fixture.host._arm_twist_bound
                prepared = bound.prepared
                self.assertEqual(bound.work_totals()['captures'], 1)
                source_fixture.set_pose(fixture, fixture.packet)
                source_fixture.notify(fixture, fixture.rig)
                reply = request(2)
                self.assertIs(reply['result']['isError'], False)
                recovered = json.loads(reply['result']['content'][0]['text'])
                self.assertEqual(recovered['status'], 'estimated')
                self.assertNotEqual(unknown['source']['revision'], recovered['source']['revision'])
                self.assertIs(fixture.host._arm_twist_bound, bound)
                self.assertIs(bound.prepared, prepared)
                self.assertEqual(bound.work_totals()['captures'], 2)
                self.assertEqual(bound.work_totals()['preparations'], 1)
            self.assertEqual(service.state_path.read_bytes(), b'opaque entry-opt action ledger')
        OBSERVATIONS.setdefault('unknown_routes', []).append(dict(route=route, tool_calls=2,
            unknown_reason=unknown['reason'], unknown_is_error=False, recovered=recovered['status'], captures=2,
            ledger_unchanged=True, actual_blender=False, endpoints='in_process_real_codecs'))

    def test_unknown_direct_service_mcp_is_normal_report_and_recovers(self):
        self.unknown_route('direct_service_mcp')

    def test_unknown_owned_and_shared_codecs_are_normal_reports_and_recover(self):
        for route in ('owned_bridge_mcp', 'shared_bridge_owned_task'):
            with self.subTest(route=route):
                self.unknown_route(route)


if __name__ == '__main__':
    unittest.main(verbosity=2)
