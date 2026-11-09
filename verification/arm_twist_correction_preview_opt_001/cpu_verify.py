"""CPU regression: ten existing methods, two root cases and one precision guard.

Imports the root test class by AST only. Its old-source assertion and pinned
main are intentionally not executed, and all original evidence remains intact.
"""
from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).parent
REVIEW=Path('D:/hefe/verification/fixes/20261109_architecture_completion/correction_preview_review/behavior')
OLD_COMMIT='612e4fe900f14cb8caa5be4752665436161bd02e'
OLD_SOURCE_SHA256='9146cd465af25024e876de6d8af6447ea5af33302ca374dca16c190b71a38771'


def encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf8')


def sha(raw):return hashlib.sha256(raw).hexdigest()


def save(folder,name,value):
    (folder/name).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')


def configure_imports():
    sys.path.insert(0,str(ROOT))
    package=types.ModuleType('human_eye_plugin');package.__path__=[str(ROOT/'human_eye_plugin')]
    sys.modules['human_eye_plugin']=package


def load_product(name,raw,origin):
    spec=importlib.util.spec_from_file_location(name,origin)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module
    exec(compile(raw,str(origin),'exec'),module.__dict__)
    return module


def root_test_class(preview):
    import numpy as np
    from verification.arm_twist_correction_preview_001 import cases,oracle,test_preview
    raw=(REVIEW/'review.py').read_bytes();tree=ast.parse(raw)
    classes=[node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=='IndependentTests']
    if len(classes)!=1:raise AssertionError('single_root_IndependentTests_required')
    subtree=ast.Module(body=classes,type_ignores=[]);ast.fix_missing_locations(subtree)
    details={}
    namespace={'np':np,'copy':__import__('copy'),'unittest':unittest,'cases':cases,'oracle':oracle,
               'preview_axial_redistribution':preview,'DETAILS':details,'__name__':'root_review_reused'}
    exec(compile(subtree,str(REVIEW/'review.py'),'exec'),namespace)
    cls=namespace['IndependentTests']
    original=cls.test_accepted_weight_slack_cannot_claim_reachable_target_unreachable
    def exact_unsupported_domain(self):
        original(self)
        actual=details['accepted_weight_slack']
        self.assertEqual(actual['status'],'not_applicable',actual)
        self.assertEqual(actual['reason'],'non_adjacent_weights',actual)
        self.assertEqual(actual['target_j'],.25+5.5e-11)
        self.assertEqual(actual['area_tolerance'],1e-12)
        self.assertEqual(actual['epsilon'],5e-11)
    cls.test_accepted_weight_slack_cannot_claim_reachable_target_unreachable=exact_unsupported_domain
    return cls,details,{'review_path':str(REVIEW/'review.py'),'source_sha256':sha(raw),
        'extracted_class_ast_sha256':sha(ast.dump(subtree,include_attributes=False).encode()),
        'old_bind_source_and_main_executed':False,
        'tiny_third_test_extension':'Require exact not_applicable/non_adjacent_weights; original test and witness remain referenced.'}


def feasible_witness():
    """Recompute geometric feasibility with the unchanged original task."""
    import numpy as np
    from verification.arm_twist_correction_preview_001 import cases,oracle
    case=deepcopy(cases.make_cases()[0]);packet,task=case['patch'],case['task']
    for index in packet['sections'][8]:packet['weights'][index]=[.5-5e-11,.5,5e-11]
    packet['current_vertices']=oracle.skin_vertices(packet)
    task['max_section_area_loss']=.25+5.5e-11;task['area_tolerance']=1e-12
    poses=oracle.chain_poses([bone['rest_matrix'] for bone in packet['bone_chain']],59.999999995,120.)
    points=np.asarray(oracle.skin_vertices(packet,poses));before=np.asarray(packet['current_vertices'])
    objective=oracle.section_objective(packet['rest_vertices'],points,packet['sections'])
    rows=[i for i,native in enumerate(packet['vertex_ids']) if native in set(task['protected_vertex_ids'])]
    protected=float(np.linalg.norm(points[rows]-before[rows],axis=1).max())
    centers=max(float(np.linalg.norm(points[s].mean(axis=0)-before[s].mean(axis=0))) for s in packet['sections'])
    ends=max(float(np.max(np.abs(np.asarray(poses[i])-np.asarray(packet['bone_chain'][i]['pose_matrix'])))) for i in (0,2))
    assert objective['max_section_area_loss']<=task['max_section_area_loss']+task['area_tolerance']
    assert protected<=task['position_tolerance_m'] and centers<=task['position_tolerance_m'] and ends<=1e-12
    assert task['u_interval_deg'][0]<=59.999999995<=task['u_interval_deg'][1]
    return {'geometric_feasibility_preserved':True,'u_deg':59.999999995,
        'task_sha256':sha(encoded(task)),'packet_sha256':sha(encoded(packet)),
        'target_max_section_area_loss':task['max_section_area_loss'],'area_tolerance':task['area_tolerance'],
        'measured_max_section_area_loss':objective['max_section_area_loss'],
        'fixed_end_matrix_max_delta':ends,'protected_vertex_max_delta_m':protected,
        'section_center_max_delta_m':centers,'new_product_domain_admission':'not_claimed; tiny third influence is out of the exact analytic domain',
        'original_FEASIBLE_WITNESS_path':str(REVIEW/'FEASIBLE_WITNESS.json')}


def precision_guard_class(preview):
    from verification.arm_twist_correction_preview_001 import cases,oracle
    details={}
    class PrecisionGuard(unittest.TestCase):
        def test_near_exact_area_minimum_cannot_claim_proven_unreachable(self):
            case=deepcopy(cases.make_cases()[0]);packet,task=case['patch'],case['task']
            task['max_section_area_loss']=.25-1e-14;task['area_tolerance']=1e-16
            frozen=encoded([packet,task]);result=preview(packet,task)
            self.assertEqual(encoded([packet,task]),frozen)
            self.assertEqual(result['status'],'not_applicable',result)
            self.assertEqual(result['reason'],'area_target_below_supported_precision')
            self.assertIsNone(result['candidate'])
            poses=oracle.chain_poses([bone['rest_matrix'] for bone in packet['bone_chain']],60.,120.)
            actual=oracle.section_objective(packet['rest_vertices'],oracle.skin_vertices(packet,poses),packet['sections'])
            self.assertGreater(actual['max_section_area_loss'],task['max_section_area_loss']+task['area_tolerance'])
            self.assertGreater(result['objective']['after']['max_section_area_loss'],task['max_section_area_loss']+task['area_tolerance'])
            self.assertAlmostEqual(oracle.known_objective(120.,60.),.25,delta=1e-15)
            floor=result['objective']['minimum_loss_lower_bound']
            self.assertLessEqual(floor,.25)
            self.assertLessEqual(floor,task['max_section_area_loss']+task['area_tolerance'])
            details.update({'status':result['status'],'reason':result['reason'],
                'target_j':task['max_section_area_loss'],'area_tolerance':task['area_tolerance'],
                'analytic_minimum_j':.25,'actual_half_angle_j':actual['max_section_area_loss'],
                'reported_half_angle_j':result['objective']['after']['max_section_area_loss'],
                'minimum_loss_lower_bound':floor,'task_and_packet_unchanged':True,
                'counted_in_eight_effect_cases':False})
    return PrecisionGuard,details


def main():
    if len(sys.argv)!=2:raise ValueError('usage: cpu_verify.py NEW_OUTPUT_DIRECTORY')
    out=Path(sys.argv[1]).resolve()
    if out.exists():raise ValueError('new_output_directory_required')
    out.mkdir(parents=True);configure_imports()
    source=ROOT/'human_eye_plugin/arm_twist_correction.py';raw=source.read_bytes()
    watched=[source,HERE/'cpu_verify.py']
    watched.extend(ROOT/'verification/arm_twist_correction_preview_001'/name for name in ('cases.py','oracle.py','test_preview.py'))
    watched.extend(REVIEW/name for name in ('review.py','RESULT.json','DETAILS.json','FEASIBLE_WITNESS.json','feasible_witness.py'))
    watched.extend(ROOT/'human_eye_plugin'/name for name in ('arm_twist_expert.py','arm_twist_weights.py','rig_pose.py'))
    watched.append(ROOT/'verification/m6_arm_expert_001/run_01/dataset.json.gz')
    hashes=lambda:{str(p):sha(p.read_bytes()) for p in watched}
    before=hashes();assert sha(raw)==before[str(source)]
    old_record=json.loads((REVIEW/'RESULT.json').read_text(encoding='utf8'))
    assert old_record['commit']==OLD_COMMIT and old_record['source_sha256_before_after']==OLD_SOURCE_SHA256
    assert old_record['tests']==12 and old_record['failures']==1 and old_record['passed'] is False
    module=load_product('human_eye_plugin.arm_twist_correction',raw,source)
    from verification.arm_twist_correction_preview_001 import test_preview
    independent,details,binding=root_test_class(module.preview_axial_redistribution)
    precision,precision_details=precision_guard_class(module.preview_axial_redistribution)
    loader=unittest.defaultTestLoader
    suite=unittest.TestSuite([loader.loadTestsFromTestCase(test_preview.CorrectionPreviewTests),
        loader.loadTestsFromTestCase(independent),loader.loadTestsFromTestCase(precision)])
    assert suite.countTestCases()==13
    save(out,'INPUT_FREEZE.json',{'files':before,'executed_product_source_sha256':sha(raw),'root_reuse':binding,
        'tests':13,'fixed_effect_tasks':8,'original_guard_methods':2,'root_counterexample_methods':2,'precision_guard_methods':1,
        'model_Blender_network_training_calls':0})
    def forbidden(*args,**kwargs):raise AssertionError('No network or child process in CPU verification')
    stream=io.StringIO()
    with patch.object(socket,'socket',side_effect=forbidden),patch.object(socket,'create_connection',side_effect=forbidden),patch.object(subprocess,'Popen',side_effect=forbidden):
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
        witness=feasible_witness()
    after=hashes()
    record={'passed':result.wasSuccessful() and before==after,'tests':result.testsRun,'failures':len(result.failures),
        'errors':len(result.errors),'skips':len(result.skipped),'inputs_sources_unchanged':before==after,
        'executed_product_source_sha256':sha(raw),'before_sha256':before,'after_sha256':after,'root_reuse':binding,
        'root_details':details,'precision_guard':precision_details,'feasible_witness':witness,'old_failure_preserved':old_record,
        'thin_crossing_guard':getattr(test_preview.CorrectionPreviewTests,'thin_crossing_guard_evidence',None),
        'scope':'pure_CPU_preview_no_Blender_capture_MLP_training_or_external_API'}
    (out/'TESTS.log').write_text(stream.getvalue(),encoding='utf8',newline='\n')
    save(out,'RESULT.json',record)
    print(json.dumps({'passed':record['passed'],'tests':record['tests'],'failures':record['failures'],'errors':record['errors'],
        'source_sha256':sha(raw),'result':str(out/'RESULT.json')}))
    if not record['passed']:print(stream.getvalue());raise SystemExit(1)


if __name__=='__main__':main()
