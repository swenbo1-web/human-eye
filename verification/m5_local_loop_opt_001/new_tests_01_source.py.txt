"""Owned returned-readback behavior; no Blender process or socket is started.

The owned seam delegates real mutable geometry to maintained host doubles.
The delta check uses the actual BlenderSceneHost on fake bpy, actual encoder,
owned client request composition and SceneDeltaDecoder.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
import hashlib
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from human_eye_plugin.auto_router import _validated_scene
from human_eye_plugin.blender_process import BlenderProcessHost
from human_eye_plugin.host_runtime import GuardedHostRuntime
from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.runtime_identity import runtime_identity
from verification import test_host_runtime as runtime_fixture
from verification import test_clearance_segment_service as segment_fixture
from verification import test_blender_process_residency as bridge_fixture
from verification.arch_resident_001 import test_residency_contract as resident_fixture


class OwnedDouble(BlenderProcessHost):
    """No child process: retain the real owned type/private readback boundary."""
    prewrite_refusal_protocol=None

    def __init__(self, backing=None, *, default_worker=True):
        self.backing=backing or runtime_fixture.MutableHost()
        self._default_worker=default_worker
        self.return_result=lambda value:value
        self.last_result=None

    @contextmanager
    def transaction(self):
        with self.backing.transaction():yield

    def capture_scene(self):
        return self.backing.capture_scene()

    def apply_transform(self, action, expected_revision, expected_fingerprint=None, **kwargs):
        value=self.backing.apply_transform(action,expected_revision,expected_fingerprint)
        self.last_result=self.return_result(value)
        return self.last_result


class GenericReturnedScene(runtime_fixture.MutableHost):
    def apply_transform(self,*args,**kwargs):
        value=super().apply_transform(*args,**kwargs)
        # Generic capture is authoritative even if its optional result scene
        # is unusable. Presence of scene is not an owned capability.
        value['scene']={'fabricated_result_scene':True}
        return value


def prepare(runtime):
    return runtime.before_model(session_id='s',task_instruction='Measure part clearance.',
        focal_id='part',reference_id='base',messages=[],format='mcp',include_image=False,
        supports_images=False)


def execute(runtime, *, goal=None):
    return runtime.execute_action(session_id='s',action={'translation':[0.,0.,.1]},goal=goal)


class OwnedReadbackTests(unittest.TestCase):
    def test_default_owned_uses_returned_actual_scene_without_extra_capture(self):
        host=OwnedDouble();runtime=GuardedHostRuntime(host,quad_size=64)
        prepare(runtime)
        self.assertEqual(host.backing.captures,1)
        result=execute(runtime,goal={'target_clearance_m':.2,'clearance_tolerance_m':1e-8})
        self.assertEqual(result['status'],'verified',result)
        self.assertTrue(result['task_succeeded'],result)
        self.assertEqual(host.backing.calls,1)
        self.assertEqual(host.backing.captures,2,'Preparation and fresh prewrite only')
        self.assertEqual(runtime._last_verified_scene['revision'],host.last_result['scene']['revision'])
        self.assertAlmostEqual(runtime._last_actual_translation_m,.1)
        self.assertNotIn('capture_state',host.last_result['scene'])
        self.assertIsNone(runtime._last_verified_observation._capture_state,
            'Returned full readback must not receive an invented resident token')
        wanted=copy.deepcopy(runtime._last_verified_scene)
        host.last_result['scene']['meshes'][1]['vertices'][0][0]=999.
        self.assertEqual(runtime._last_verified_scene,wanted,'Validation detaches the actual readback')

    def test_generic_host_still_captures_and_ignores_optional_returned_scene(self):
        host=GenericReturnedScene();runtime=GuardedHostRuntime(host,quad_size=64)
        prepare(runtime);result=execute(runtime)
        self.assertEqual(result['status'],'verified',result)
        self.assertEqual((host.calls,host.captures),(1,3))
        self.assertEqual(runtime._last_verified_scene['revision'],host.scene['revision'])

    def test_custom_owned_worker_retains_independent_capture(self):
        host=OwnedDouble(default_worker=False)
        host.return_result=lambda value:{**value,'scene':None}
        runtime=GuardedHostRuntime(host,quad_size=64)
        prepare(runtime);result=execute(runtime)
        self.assertEqual(result['status'],'verified',result)
        self.assertEqual((host.backing.calls,host.backing.captures),(1,3))

    def test_missing_or_malformed_default_scene_is_unknown_without_fallback_capture(self):
        def missing(value):
            return {'receipt':{'executed':True,'verified':True}}
        variants=[missing,lambda value:None,lambda value:{**value,'scene':None},
            lambda value:{**value,'scene':[]},lambda value:{**value,'scene':{}},
            lambda value:{**value,'scene':{'revision':'plausible'}}]
        for change in variants:
            with self.subTest(change=variants.index(change)):
                host=OwnedDouble();host.return_result=change
                runtime=GuardedHostRuntime(host,quad_size=64)
                prepare(runtime);result=execute(runtime)
                self.assertEqual(result['status'],'host_readback_uncertain',result)
                self.assertIsNone(result['executed'])
                self.assertTrue(result['host_call_completed'])
                self.assertTrue(runtime.status['quarantined'])
                self.assertEqual((host.backing.calls,host.backing.captures),(1,2))
                self.assertEqual(execute(runtime)['status'],'host_quarantined')
                self.assertEqual(host.backing.calls,1)

    def test_returned_nonfocal_metadata_and_geometry_still_fail_original_checks(self):
        for mode in ('nonfocal_mutation','color_mutation','incorrect','topology_mutation',
                     'collision','same_revision'):
            with self.subTest(mode=mode):
                host=OwnedDouble();runtime=GuardedHostRuntime(host,quad_size=64)
                prepare(runtime);host.backing.mode=mode
                result=execute(runtime)
                self.assertFalse(result['verified'],result)
                self.assertIsNone(result['executed'])
                self.assertTrue(runtime.status['quarantined'])
                self.assertEqual((host.backing.calls,host.backing.captures),(1,2))

    def test_receipt_boolean_cannot_replace_actual_geometry(self):
        host=OwnedDouble();runtime=GuardedHostRuntime(host,quad_size=64)
        prepared=prepare(runtime)
        before=copy.deepcopy(host.backing.scene)
        host.return_result=lambda value:{'scene':copy.deepcopy(before),
            'receipt':{'executed':True,'verified':True,'actual_scene_revision':value['scene']['revision']}}
        result=execute(runtime)
        self.assertFalse(result['verified'],result)
        self.assertIsNone(result['executed'])
        self.assertTrue(runtime.status['quarantined'])
        self.assertEqual(host.backing.calls,1)
        self.assertNotEqual(host.backing.scene['revision'],before['revision'])


class OwnedJournalTests(unittest.TestCase):
    def config(self,folder):
        path=folder/'connector.json'
        path.write_text(json.dumps({'schema_version':'1.0','project_root':str(ROOT),
            'state_file':'state.json','audit_file':'audit.jsonl','quad_size':64}),encoding='utf8')
        return path

    def test_setter_then_lost_or_missing_readback_preserves_journal_and_cannot_resend(self):
        for failure in ('lost_result','missing_scene'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as temporary:
                folder=Path(temporary);host=OwnedDouble(segment_fixture.SegmentHost())
                if failure=='lost_result':host.backing.mode='partial_failure'
                else:host.return_result=lambda value:{'receipt':value['receipt']}
                path=self.config(folder);service=LiveSpatialService(path,host=host)
                action={'focal_id':'part','reference_id':'base','translation':[0.,0.,.002]}
                result=service.transform('s',action)
                self.assertIsNone(result['executed'],result)
                self.assertFalse(result['verified'])
                self.assertEqual(host.backing.calls,1)
                state=json.loads((folder/'state.json').read_text())
                self.assertIsNotNone(state['inflight'])
                other=LiveSpatialService(path,host=host)
                replay=other.transform('s',action)
                self.assertEqual(replay['status'],'host_quarantined',replay)
                self.assertEqual(host.backing.calls,1,'Unknown physical action is never resent')

    def test_next_step_detects_external_change_after_owned_returned_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);backing=segment_fixture.SegmentHost(gap=.024)
            host=OwnedDouble(backing);path=self.config(folder)
            service=LiveSpatialService(path,host=host)
            def edited_after_readback(current):
                # MutableHost already made the detached returned scene. Model
                # an editor changing live state after that exact readback.
                current.scene['revision']+='-external-editor'
                current.scene['meshes'][0]['name']='Changed after actual readback'
            backing.after_mutation=edited_after_readback
            request=segment_fixture.ClearanceSegmentServiceTests.request(
                max_step_translation_m=.001,max_steps=4)
            result=service.run_clearance_segment('s','external-after-readback',request,
                execute=True,include_image=False)
            self.assertEqual(result['status'],'review_required',result)
            self.assertEqual(result['reason_codes'],['external_scene_change_between_steps'])
            self.assertEqual(backing.calls,1)
            self.assertTrue(result['steps'][0]['result']['executed'])
            self.assertGreater(result['steps'][0]['actual_translation_m'],0.)
            captures=backing.captures
            again=LiveSpatialService(path,host=host).run_clearance_segment(
                's','external-after-readback',request,execute=True,include_image=False)
            self.assertTrue(again['historical_receipt'])
            self.assertEqual((backing.calls,backing.captures),(1,captures))


class ReturnedReadbackDeltaTests(unittest.TestCase):
    def test_following_task_and_nearest_delta_catch_up_after_returned_readback(self):
        for first in ('task','nearest'):
            with self.subTest(first=first):
                backend,focal,reference,graph=resident_fixture.make_host()
                self.addCleanup(backend.close_residency)
                host=bridge_fixture.client();host._default_worker=True
                packets=[];commands=[]
                def request(command,params,**kwargs):
                    params=copy.deepcopy(params);commands.append(command)
                    if command=='apply':
                        return backend.apply_transform(**params)
                    known=params.pop('_scene_baseline')
                    if command=='capture':raw=backend.capture_scene()
                    elif command=='capture_task':raw=backend.capture_task_scene(params['selectors'])
                    else:raw=backend.capture_nearest_candidates(**params)
                    packet=backend.capture_delta(raw,known);packets.append(copy.deepcopy(packet))
                    return packet
                host._request=request
                before=host.capture_scene();old_baseline=copy.deepcopy(host._scene_decoder.baseline())
                focal_id=backend.object_id(focal)
                action={'focal_id':focal_id,'translation':[.125,0.,0.]}
                returned=host.apply_transform(action,before['revision'],
                    expected_fingerprint=_validated_scene(before)[2])
                readback=host._readback_after_apply(returned)
                self.assertNotIn('capture_state',readback)
                self.assertEqual(host._scene_decoder.baseline(),old_baseline,
                    'Consuming full owned readback neither forges nor advances delta baseline')
                expected={mesh['object_id']:mesh for mesh in readback['meshes']}
                def task():return host.capture_task_scene([{'name':'Focal'},{'name':'Reference'}])
                def nearest():return host.capture_nearest_candidates(None,
                    time.perf_counter_ns()+5_000_000_000,2_000_000,selector={'name':'Focal'})['capture']
                for consume in ((task,nearest) if first=='task' else (nearest,task)):
                    current=consume()
                    actual={mesh['object_id']:mesh for mesh in current['meshes']}
                    self.assertEqual(actual[focal_id]['vertices'],expected[focal_id]['vertices'])
                    self.assertEqual(actual[focal_id]['pivot_world'],expected[focal_id]['pivot_world'])
                    self.assertNotEqual(current['capture_state']['revision'],before['capture_state']['revision'])
                    self.assertEqual(packets[-1]['resources'],[],
                        'Pose catch-up reuses local resources while mapping the current matrix')
                self.assertEqual(focal.assignments,1)
                self.assertEqual(commands.count('apply'),1)
                self.assertEqual(commands.count('capture'),1,'No hidden full capture after consuming returned scene')


def main():
    # Save executing source and outcome for each attempt; tests never start a
    # child process or socket, even on a failure path.
    OUT.mkdir(exist_ok=True)
    attempt=1
    while (OUT/f'new_tests_{attempt:02d}.json').exists():attempt+=1
    label=f'new_tests_{attempt:02d}'
    (OUT/(label+'_source.py.txt')).write_bytes(Path(__file__).read_bytes())
    identity=runtime_identity()
    (OUT/(label+'_identity.json')).write_text(json.dumps(identity,indent=2)+'\n',encoding='utf8')
    stream=io.StringIO();started=time.perf_counter_ns()
    suite=unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    with (patch.object(subprocess,'Popen',side_effect=AssertionError('Unexpected process')),
          patch.object(socket,'socket',side_effect=AssertionError('Unexpected socket'))):
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    unchanged=all(hashlib.sha256((ROOT/row['path']).read_bytes()).hexdigest()==row['sha256']
        for row in identity['source_files'])
    (OUT/(label+'.log')).write_text(stream.getvalue(),encoding='utf8')
    summary=dict(passed=result.wasSuccessful() and unchanged,tests=result.testsRun,
        failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
        duration_ms=(time.perf_counter_ns()-started)/1e6,source_sha256=identity['source_sha256'],
        source_unchanged=unchanged,failed_methods=[str(t) for t,_ in result.failures+result.errors])
    (OUT/(label+'.json')).write_text(json.dumps(summary,indent=2)+'\n',encoding='utf8')
    print(json.dumps(summary));return 0 if summary['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
