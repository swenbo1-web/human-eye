"""Execute Git-pinned product/test bytes; preserve all offline outcomes."""
import ast
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
BASE='3b0f67abd6ed5bdab023b2b243e395aa1e8ff109'
HOST='human_eye_plugin/blender_host.py'


def git_blob(ref,path):return subprocess.check_output(['git','show',ref+':'+path],cwd=ROOT)
def digest(blob):return hashlib.sha256(blob).hexdigest()
def save(name,value):(OUT/name).write_bytes((json.dumps(value,indent=2)+'\n').encode())


def execute_module(name,ref,path):
    blob=git_blob(ref,path)
    module=types.ModuleType(name);module.__file__=str(ROOT/path);module.__package__=name.rpartition('.')[0]
    sys.modules[name]=module
    filename='git:'+ref+':'+path
    exec(compile(blob,filename,'exec',dont_inherit=True),module.__dict__)
    return module,dict(module=name,commit=ref,path=path,bytes=len(blob),sha256=digest(blob),
                       execution='exec(compile(exact_git_blob,dont_inherit=True))',code_filename=filename)


def suite_run(names,name):
    stream=io.StringIO();suite=unittest.TestSuite()
    for target in names:
        loaded=sys.modules.get(target)
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(loaded) if loaded is not None
                       else unittest.defaultTestLoader.loadTestsFromName(target))
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (OUT/(name+'.txt')).write_bytes(stream.getvalue().encode())
    return dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
                skipped=len(result.skipped),successful=result.wasSuccessful())


def main():
    ref=sys.argv[1];verification_ref=sys.argv[2] if len(sys.argv)>2 else ref
    assert len(ref)==len(verification_ref)==40
    assert git_blob(ref,HOST)==(ROOT/HOST).read_bytes()
    assert git_blob(verification_ref,'verification/bound_first_face_fix_001/run_fixed.py')==Path(__file__).read_bytes()
    old,old_record=execute_module('_first_face_prior',BASE,HOST)
    candidate,candidate_record=execute_module('_first_face_candidate',ref,HOST)
    candidate._FIRST_FACE_FIXED_GIT=True
    candidate._READONLY_LOADED_HOST_SHA256=candidate_record['sha256']
    sys.path.insert(0,str(ROOT))
    import verification.test_blender_host_contracts as fixtures
    fixtures._module=candidate
    fixtures.BlenderSceneHost=candidate.BlenderSceneHost
    fixtures.BlenderHostError=candidate.BlenderHostError
    sys.modules['human_eye_plugin.blender_host']=candidate
    import verification.test_m4_capture_001 as m4
    assert m4.m is candidate and fixtures.host_fixture()[0].__class__ is candidate.BlenderSceneHost
    _,directed_record=execute_module('verification.bound_source_fix_001.test_source_validation',verification_ref,
                                     'verification/bound_source_fix_001/test_source_validation.py')
    _,first_record=execute_module('verification.bound_first_face_fix_001.test_first_face',verification_ref,
                                  'verification/bound_first_face_fix_001/test_first_face.py')
    assert candidate._acquisition_witness.__code__.co_filename==candidate_record['code_filename']
    assert candidate.BlenderSceneHost.capture_nearest_candidates.__code__.co_filename==candidate_record['code_filename']
    identity=dict(candidate_commit=ref,verification_commit=verification_ref,baseline_commit=BASE,executed=[old_record,candidate_record,directed_record,first_record],
                  target_witness_and_capture_class_bound_to_fixed_git=True,
                  fixture_class_is_fixed_git_candidate=True,blender_sessions=0,real_RPC=0,performance_samples=0)
    save('EXECUTION_IDENTITY.json',identity)
    first=suite_run(['verification.bound_first_face_fix_001.test_first_face'],'FIRST_FACE_TESTS')
    previous=suite_run(['verification.bound_source_fix_001.test_source_validation'],'PRIOR_DIRECTED_TESTS')
    # Legacy mocks predate the RNA layout. Synchronize only our auto-created
    # fields with their existing polygon.vertices view, in this legacy group.
    original=m4.TriangleObject.__init__
    def adapt(data):
        offset=0
        for face in data.polygons:
            indices=tuple(face.vertices)
            if not hasattr(face,'loop_start') and not hasattr(face,'loop_total'):
                face.loop_start=offset;face.loop_total=len(indices);face._first_face_auto_layout=True
            elif getattr(face,'_first_face_auto_layout',False):
                face.loop_start=offset;face.loop_total=len(indices)
            for corner,index in enumerate(indices):
                slot=offset+corner
                if slot>=len(data.loops):continue
                loop=data.loops[slot]
                if loop is None:
                    data.loops[slot]=types.SimpleNamespace(vertex_index=index,_first_face_auto_index=True)
                elif getattr(loop,'_first_face_auto_index',False):loop.vertex_index=index
            offset+=len(indices)
        return data
    def initialize(obj,*args,**kwargs):original(obj,*args,**kwargs);adapt(obj.data)
    witness=candidate._acquisition_witness
    validator=candidate._acquisition_validate_triangles
    def witness_adapter(data,*args):return witness(adapt(data),*args)
    def validator_adapter(data,**kwargs):return validator(adapt(data),**kwargs)
    if '--focused-retry' in sys.argv:
        initial_results=json.loads((OUT/'RESULTS_INITIAL.json').read_bytes())
        initial_identity=json.loads((OUT/'EXECUTION_IDENTITY_INITIAL.json').read_bytes())
        assert initial_identity['candidate_commit']==ref
        assert initial_results['legacy_RNA_adapted']['successful']
        legacy=initial_results['legacy_RNA_adapted']
    else:
        with patch.object(m4.TriangleObject,'__init__',initialize), \
                patch.object(candidate,'_acquisition_witness',side_effect=witness_adapter), \
                patch.object(candidate,'_acquisition_validate_triangles',side_effect=validator_adapter):
            legacy=suite_run(['verification.test_m4_capture_001','verification.m4_capture_opt_001.test_nine_pairs'],'LEGACY_RNA_ADAPTED')
    assert candidate._acquisition_witness is witness and candidate._acquisition_validate_triangles is validator
    assert candidate._acquisition_witness.__code__.co_filename==candidate_record['code_filename']
    summary=dict(first_face=first,prior_directed=previous,legacy_RNA_adapted=legacy,
                 adapter_used_only_in_legacy_group=True,original_history_unchanged=True,
                 target_execution_identity='EXECUTION_IDENTITY.json',legacy_pass_preserved_without_rerun='--focused-retry' in sys.argv,
                 blender_sessions=0,real_RPC=0)
    save('RESULTS.json',summary);print(json.dumps(summary,indent=2))
    if not all(row['successful'] for row in (first,previous,legacy)):raise SystemExit(1)


if __name__=='__main__':main()
