"""Fixed-source/real-model checks of optional expert preparation.

Uses the accepted native-index RNA doubles and saved 402-point packet. This is
not another Blender/effect trial. The exact accepted source is compiled from
Git; current expert/weights are frozen and unchanged. Only diagnostic analyze
requests invoke the real model, counted separately from geometry captures.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import types
import unittest
from unittest.mock import patch

import numpy as np

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
if 'human_eye_plugin' not in sys.modules:
    package=types.ModuleType('human_eye_plugin');package.__path__=[str(ROOT/'human_eye_plugin')]
    sys.modules['human_eye_plugin']=package

from human_eye_plugin import arm_twist_source as candidate
from human_eye_plugin import arm_twist_expert as expert
from verification.m6_arm_source_001 import test_arm_source as native

BASE_COMMIT='a3a72b929f55c40f195ff5e1a9f64ceb303b6360'
BASE_SOURCE_SHA='5cd8f002b264e0f07753794f360e01766b77470f92ac9b6f7346613160ab2b58'
BASE_RAW=subprocess.check_output(['git','show',BASE_COMMIT+':human_eye_plugin/arm_twist_source.py'],cwd=ROOT)
assert hashlib.sha256(BASE_RAW).hexdigest()==BASE_SOURCE_SHA
baseline=types.ModuleType('human_eye_plugin._accepted_arm_source')
baseline.__package__='human_eye_plugin'
exec(compile(BASE_RAW,'<accepted-a3a72b9-arm-source>','exec'),baseline.__dict__)

EVENTS=[]


class DiagnosticModel:
    def __init__(self):self.calls=0;self.real=expert.get_default_expert()
    def predict_prepared(self,prepared,current,poses):
        self.calls+=1
        return self.real.predict_prepared(prepared,current,poses)


MODEL=DiagnosticModel()


def bind(module,fixture):
    def topology(obj,indices):
        allowed=set(indices)
        return [row[:] for row in fixture.global_triangles if all(i in allowed for i in row)]
    return module.ArmTwistSource(fixture.host,topology_reader=topology).bind(fixture.selection)


class SourcePreparationTests(unittest.TestCase):
    def fixture(self):
        f=native.make_host()
        self.addCleanup(f.host.close_residency)
        return f

    def compare_reports(self,old,new):
        a=old.analyze(model=MODEL);b=new.analyze(model=MODEL)
        self.assertEqual(a,b)
        self.assertFalse(b['execution_authority'])
        return b

    def test_default_capture_and_analyze_keep_exact_accepted_output(self):
        f=self.fixture();old=bind(baseline,f);new=bind(candidate,f)
        self.assertEqual(old.capture(),new.capture())
        prepared=new.prepared
        self.assertIsNotNone(prepared)
        self.assertEqual(new.work_totals()['preparations'],1)
        self.assertEqual(old.capture(),new.capture())
        self.assertIs(new.prepared,prepared)
        self.compare_reports(old,new)
        self.assertEqual(new.work_totals()['preparations'],1)
        EVENTS.append({'case':'default','work':new.work_totals(),'model_calls':2})

    def test_geometry_then_analyze_prepares_once_without_static_change(self):
        f=self.fixture();old=bind(baseline,f);new=bind(candidate,f)
        self.assertEqual(old.capture(),new.capture(_prepare_expert=False))
        self.assertIsNone(new.prepared)
        self.assertEqual(new.work_totals()['preparations'],0)
        second=new.capture(_prepare_expert=False)
        self.assertFalse(second['static_changed']);self.assertIsNone(second['static_patch'])
        self.assertIsNone(new.prepared)
        revision=second['source']['static_revision']
        self.compare_reports(old,new)
        self.assertEqual(new.work_totals()['preparations'],1)
        self.assertEqual(new._static_revision,revision)
        prepared=new.prepared
        third=new.capture()
        self.assertFalse(third['static_changed']);self.assertIs(new.prepared,prepared)
        self.assertEqual(new.work_totals()['preparations'],1)
        EVENTS.append({'case':'deferred','work':new.work_totals(),'model_calls':2})

    def test_unchanged_geometry_retains_valid_prepared_without_rebuilding(self):
        f=self.fixture();old=bind(baseline,f);new=bind(candidate,f)
        self.assertEqual(old.capture(),new.capture())
        prepared=new.prepared
        self.assertEqual(old.capture(),new.capture(_prepare_expert=False))
        self.assertIs(new.prepared,prepared)
        self.compare_reports(old,new)
        self.assertEqual(new.work_totals()['preparations'],1)
        EVENTS.append({'case':'reuse_valid','work':new.work_totals(),'model_calls':2})

    def test_static_change_invalidates_then_uses_current_weights_for_analyze(self):
        f=self.fixture();old=bind(baseline,f);new=bind(candidate,f)
        self.assertEqual(old.capture(),new.capture())
        stale=new.prepared;self.compare_reports(old,new)
        vertex=next(f.mesh.data.vertices.rows[i]
                    for section in f.selection['sections'] for i in section
                    if len(f.mesh.data.vertices.rows[i].groups)==2)
        vertex.groups[0].weight=.7;vertex.groups[1].weight=.3
        native.replay_selected(f);native.notify(f,f.mesh)
        actual=new.capture(_prepare_expert=False)
        self.assertEqual(old.capture(),actual)
        self.assertTrue(actual['static_changed'])
        self.assertIsNone(new.prepared)
        self.assertEqual(new.work_totals()['preparations'],1)
        revision=actual['source']['static_revision']
        self.compare_reports(old,new)
        self.assertEqual(new.work_totals()['preparations'],2)
        self.assertEqual(new._static_revision,revision)
        self.assertIsNot(new.prepared,stale)
        self.assertFalse(np.array_equal(new.prepared._blend,stale._blend))
        EVENTS.append({'case':'changed_weights','work':new.work_totals(),'model_calls':4})

    def test_geometry_preserves_closed_section_validation_and_invalidates_stale(self):
        f=self.fixture();old=bind(baseline,f);new=bind(candidate,f)
        self.assertEqual(old.capture(),new.capture())
        edge=set(f.selection['sections'][0][:2])
        f.global_triangles[:]=[row for row in f.global_triangles if not edge.issubset(row)]
        native.notify(f,f.mesh)
        for bound,kwargs in ((old,{}),(new,{'_prepare_expert':False})):
            with self.subTest(version='old' if bound is old else 'new'):
                with self.assertRaisesRegex(ValueError,'^closed_section_topology$'):
                    bound.capture(**kwargs)
        self.assertIsNone(new.prepared)
        self.assertEqual(new._static_revision,1)
        self.assertEqual(new.work_totals()['preparations'],1)
        with self.assertRaisesRegex(ValueError,'^closed_section_topology$'):
            new.analyze(model=MODEL)
        EVENTS.append({'case':'closed_topology_rejected','work':new.work_totals(),'model_calls':0})

    def test_geometry_preserves_unsupported_modifier_rejection(self):
        f=self.fixture();f.mesh.modifiers[0].use_deform_preserve_volume=True
        old=bind(baseline,f);new=bind(candidate,f)
        for bound,kwargs in ((old,{}),(new,{'_prepare_expert':False})):
            with self.subTest(version='old' if bound is old else 'new'):
                with self.assertRaisesRegex(ValueError,'^unsupported_modifier_use_deform_preserve_volume$'):
                    bound.capture(**kwargs)
        self.assertEqual(new.work_totals()['preparations'],0)
        self.assertIsNone(new.prepared)
        EVENTS.append({'case':'unsupported_modifier','work':new.work_totals(),'model_calls':0})

    def test_geometry_still_checks_actual_same_index_lbs_and_counts_real_prepare(self):
        for prepare in (False,True):
            with self.subTest(prepare=prepare):
                f=self.fixture();old=bind(baseline,f);new=bind(candidate,f)
                f.mesh.evaluated.data.vertices.rows[f.indices[0]].co[0]+=.02
                for bound,kwargs in ((old,{}),(new,{'_prepare_expert':prepare})):
                    with self.assertRaisesRegex(ValueError,'^same_index_lbs_readback_mismatch$'):
                        bound.capture(**kwargs)
                self.assertEqual(new.work_totals()['preparations'],int(prepare))
                self.assertEqual(new.work_totals()['captures'],0)
                self.assertEqual(new._static_revision,0)
                self.assertIsNone(new.prepared)
                EVENTS.append({'case':'lbs_rejected','requested_prepare':prepare,
                               'work':new.work_totals(),'model_calls':0})

    def test_preparation_exception_has_no_constructed_count_or_static_commit(self):
        f=self.fixture();new=bind(candidate,f)
        new.capture(_prepare_expert=False)
        revision=new._static_revision
        with patch.object(expert,'prepare_patch',side_effect=ValueError('injected_prepare_failed')):
            with self.assertRaisesRegex(ValueError,'^injected_prepare_failed$'):
                new.capture()
        self.assertEqual(new.work_totals()['preparations'],0)
        self.assertEqual(new._static_revision,revision)
        self.assertIsNone(new.prepared)
        new.capture()
        self.assertEqual(new.work_totals()['preparations'],1)
        self.assertEqual(new._static_revision,revision)
        EVENTS.append({'case':'prepare_exception','work':new.work_totals(),'model_calls':0})

    def test_default_analyze_model_resolution_retains_frozen_output(self):
        f=self.fixture();old=bind(baseline,f);new=bind(candidate,f)
        new.capture(_prepare_expert=False)
        # Only instrument default model resolution; prediction is still the
        # exact frozen model. Neither call supplies a model argument.
        with patch.object(expert,'get_default_expert',return_value=MODEL):
            a=old.analyze();b=new.analyze()
        self.assertEqual(a,b)
        self.assertEqual(b['model_id'],MODEL.real.model_id)
        self.assertEqual(new.work_totals()['preparations'],1)
        EVENTS.append({'case':'default_model_resolution','work':new.work_totals(),'model_calls':2})

    def test_reference_degeneracy_remains_unknown_after_geometry_capture(self):
        f=self.fixture();old=bind(baseline,f);new=bind(candidate,f)
        # Keep a valid indexed/topological source while making one reference
        # section nonplanar. This was an expert unknown, not a parse rejection.
        index=f.selection['sections'][1][0]
        f.mesh.data.vertices.rows[index].co[1]+=.01
        native.replay_selected(f);native.notify(f,f.mesh)
        self.assertEqual(old.capture(),new.capture(_prepare_expert=False))
        self.assertIsNone(new.prepared)
        report=self.compare_reports(old,new)
        self.assertEqual(report['status'],'unknown')
        self.assertEqual(report['reason'],'section_nonplanar_or_reference_degenerate')
        self.assertEqual(report['regions'],[])
        self.assertEqual(new.work_totals()['preparations'],1)
        EVENTS.append({'case':'nonplanar_reference_unknown','work':new.work_totals(),'model_calls':2})


def hashes():
    members=('human_eye_plugin/arm_twist_source.py','human_eye_plugin/arm_twist_expert.py',
             'human_eye_plugin/arm_twist_weights.py','human_eye_plugin/rig_pose.py',
             'verification/m6_arm_expert_001/run_01/dataset.json.gz',
             'verification/arm_correction_execution_opt_001/test_source.py')
    return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in members}


def main():
    output=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).parent/'source_01'
    output.mkdir(parents=True,exist_ok=False)
    before=hashes();before_calls=MODEL.calls
    with (output/'TESTS.log').open('w',encoding='utf-8',newline='\n') as stream:
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(SourcePreparationTests))
    after=hashes()
    record={'passed':result.wasSuccessful() and before==after,
            'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skips':len(result.skipped),
            'before_sha256':before,'after_sha256':after,'sources_unchanged':before==after,
            'baseline_commit':BASE_COMMIT,'baseline_source_sha256':BASE_SOURCE_SHA,
            'diagnostic_model_calls':MODEL.calls-before_calls,'events':EVENTS,
            'geometry_model_calls':0,'Blender_runs':0,'new_effect_assets':0,
            'scope':'CPU_native_index_RNA_doubles_saved_patch_real_frozen_model_exact_accepted_source_comparison'}
    record['model_count_matches_recorded_events']=record['diagnostic_model_calls']==sum(e['model_calls'] for e in EVENTS)
    record['passed']=record['passed'] and record['model_count_matches_recorded_events']
    (output/'RESULT.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'passed':record['passed'],'tests':record['tests'],
                      'diagnostic_model_calls':record['diagnostic_model_calls']}))
    if not record['passed']:raise SystemExit(1)


if __name__=='__main__':main()
