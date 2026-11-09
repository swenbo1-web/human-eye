"""One actual owned scheduler/worker run for eight fixed generated fixtures.

Root invokes this after the CPU/source freeze. Startup injects only the QA
initializer before the unmodified verified worker expression. No Blender is
launched merely by importing or syntax-checking this file.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import traceback
import types

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).parent
BLEND=ROOT/'verification/arch_expert_entry_opt_001/actual_run_01/new_owned_setup/fixture.blend'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path)
    parser.add_argument('--blender',type=Path,default=Path('D:/Tools/blender5.2/blender.exe'))
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT))
    package=types.ModuleType('human_eye_plugin');package.__path__=[str(ROOT/'human_eye_plugin')]
    sys.modules['human_eye_plugin']=package
    from human_eye_plugin.runtime_identity import runtime_identity
    from human_eye_plugin.blender_process import BlenderProcessHost
    from human_eye_plugin.goal_scheduler import OwnedGoalScheduler
    from human_eye_plugin.goal_execution import ArmAxialTaskSpec
    from human_eye_plugin.task_authority import TrustedTaskAuthority
    from verification.arm_twist_correction_preview_001.cases import CASE_DEFINITIONS
    from verification.arm_twist_correction_preview_001.oracle import local_basis_matrices

    identity=runtime_identity(mode='live');sources={row['path']:row['sha256'] for row in identity['source_files']}
    for path,expected in sources.items():assert sha(ROOT/path)==expected
    input_path=ROOT/'verification/arm_twist_correction_preview_001/cpu_final/INPUT_PACKETS.json'
    saved={row['case_id']:row for row in json.loads(input_path.read_text(encoding='utf8'))}
    rows=[]
    for index,definition in enumerate(CASE_DEFINITIONS,1):
        case_id=definition[0];old=saved[case_id];packet=old['patch'];native_ids=list(range(len(packet['rest_vertices'])))
        lookup={logical:native for native,logical in enumerate(packet['vertex_ids'])}
        selection={'mesh_name':'ArmExec_'+str(index).zfill(2)+'_Mesh',
            'armature_name':'ArmExec_'+str(index).zfill(2)+'_Rig','bone_names':[b['name'] for b in packet['bone_chain']],
            'vertex_indices':native_ids,'sections':packet['sections']}
        rows.append({'index':index,'case_id':case_id,'event_id':'arm-exec-'+case_id,
            'fixture_packet':packet,'initial_local_basis':local_basis_matrices(packet),
            'selection':selection,'protected_vertex_ids':[lookup[v] for v in old['task']['protected_vertex_ids']],
            'sentinel_name':'ArmExec_Outside','u_interval_deg':old['task']['u_interval_deg'],
            'max_section_area_loss':.4,'angle_tolerance_deg':.001,'position_tolerance_m':5e-6,'area_tolerance':1e-6,
            'expected_entry_status':'satisfied' if definition[5]=='candidate' else definition[5],
            'expected_preview_status':definition[5]})
    assert len(rows)==8
    fixture_input=out/'FIXTURE_INPUTS.json';save(fixture_input,{'schema':'arm-execution-qa-fixture-v1','cases':rows,
        'recipe_reference':str(input_path),'recipe_sha256':sha(input_path),'candidate_calculations':0})
    initializer=HERE/'native_initializer.py';script_hashes={str(p.relative_to(ROOT)):sha(p) for p in
        (initializer,Path(__file__),input_path,ROOT/'verification/arm_twist_correction_preview_001/cases.py',
         ROOT/'verification/arm_twist_correction_preview_001/oracle.py')}
    blend_before=sha(BLEND)
    save(out/'SOURCE_FREEZE.json',{'runtime_identity':identity,'qa_scripts':script_hashes,
        'fixture_input_sha256':sha(fixture_input),'blend_path':str(BLEND),'blend_sha256':blend_before,
        'native_gates':{'angle_deg':.001,'position_m':5e-6,'area_error':2e-5},'new_effect_assets':0})
    config=out/'config.json';save(config,{'schema_version':'1.0','enabled':True,'observe_on_prompt':False,
        'project_root':str(ROOT),'state_file':str(out/'state.json'),'audit_file':str(out/'audit.jsonl'),
        'quad_size':128,'max_sessions':16,'readback_atol_m':1e-6,
        'expected_identity':{'source_sha256':identity['source_sha256'],'build_id':identity['build_id']}})
    costs=[];rpc=[];host=None;failure=None;process=None;report={'schema':'arm-execution-owned-native-v1','passed':False,
        'cases':[],'source_before':identity,'scope':'generated_owned_copy_actual_scheduler_process_worker_host',
        'model_calls':0,'qa_candidate_assignments':0,'startup_profile_scope':'host_constructor_return_only'}
    log_lock=threading.Lock()
    class StreamLog:
        def __init__(self,raw,path):self.raw=raw;self.path=path
        def write(self,value):
            with log_lock:
                with self.path.open('a',encoding='utf8',newline='') as stream:stream.write(value)
            return self.raw.write(value)
        def readline(self,*a,**kw):
            value=self.raw.readline(*a,**kw)
            if value:
                with log_lock:
                    with self.path.open('a',encoding='utf8',newline='') as stream:stream.write(value)
            return value
        def __getattr__(self,name):return getattr(self.raw,name)
    original_popen=subprocess.Popen
    def launch(command,**kwargs):
        nonlocal process
        if process is not None:raise AssertionError('one_owned_Blender_process_only')
        assert '--python-expr' in command and '--python' not in command
        position=command.index('--python-expr');original_expression=command[position+1]
        blob_sha=sha(initializer)
        expression=("from pathlib import Path as _QP;import hashlib as _QH;"
            "_QB=_QP("+repr(str(initializer))+").read_bytes();assert _QH.sha256(_QB).hexdigest()=="+repr(blob_sha)+
            ";exec(compile(_QB,'<arm-exec-qa>','exec'));del _QB")
        actual=command[:position]+['--python-expr',expression]+command[position:]
        env=dict(os.environ,ARM_EXEC_QA_OUTPUT=str(out),ARM_EXEC_QA_INPUTS=str(fixture_input))
        kwargs['env']=env
        save(out/'COMMAND.json',{'original':command,'actual':actual,'verified_expression_unchanged':actual[actual.index(original_expression)]==original_expression,
            'initializer_sha256':blob_sha,'shell':kwargs.get('shell'),'stream_representation':'ProcessHost text API before JSON, not raw kernel pipe bytes'})
        process=original_popen(actual,**kwargs)
        process.stdin=StreamLog(process.stdin,out/'RPC_TX.txt');process.stdout=StreamLog(process.stdout,out/'RPC_RX.txt')
        save(out/'PROCESS.json',{'pid':process.pid,'argv':actual})
        return process
    def measured(name,original):
        def call(*a,**kw):
            mark=time.perf_counter_ns();error=None
            try:return original(*a,**kw)
            except BaseException as exc:error=type(exc).__name__;raise
            finally:costs.append({'phase':name,'elapsed_ns':time.perf_counter_ns()-mark,'error':error})
        return call
    all_started=time.perf_counter_ns()
    try:
        startup=time.perf_counter_ns();subprocess.Popen=launch
        try:host=BlenderProcessHost(args.blender,BLEND,timeout=30.,startup_timeout=60.)
        finally:subprocess.Popen=original_popen
        report['startup_ns']=time.perf_counter_ns()-startup
        ready=json.loads((out/'OBSERVER_READY.json').read_text());assert ready.get('profile_none') and 'error' not in ready
        report['observer_ready']=ready;report['capabilities']=host.capabilities()
        original_request=host._request
        def request(command,params,**kwargs):
            mark=time.perf_counter_ns();result=None;error=None
            try:result=original_request(command,params,**kwargs);return result
            except BaseException as exc:error=repr(exc);raise
            finally:rpc.append({'command':command,'params':copy.deepcopy(params),'elapsed_ns':time.perf_counter_ns()-mark,
                'result':copy.deepcopy(result),'error':error})
        host._request=request
        def no_grant(*a,**kw):raise AssertionError('arm task must not enter clearance approval')
        scheduler=OwnedGoalScheduler(config,host,TrustedTaskAuthority('arm-native-qa',no_grant))
        original_runtime=scheduler.service._runtime
        def runtime():
            mark=time.perf_counter_ns();value=original_runtime()
            costs.append({'phase':'legacy_runtime_construct','elapsed_ns':time.perf_counter_ns()-mark})
            value.import_state=measured('legacy_runtime_import',value.import_state)
            value.export_state=measured('legacy_runtime_export',value.export_state)
            return value
        scheduler.service._runtime=runtime;scheduler.service._save=measured('service_save',scheduler.service._save)
        specs=[]
        for row in rows:
            parameters={k:row[k] for k in ('event_id','selection','u_interval_deg','max_section_area_loss','protected_vertex_ids',
                'sentinel_name','angle_tolerance_deg','position_tolerance_m','area_tolerance')}
            spec=ArmAxialTaskSpec(**parameters);specs.append(spec)
            mark=time.perf_counter_ns();reply=scheduler.run(spec);duration=time.perf_counter_ns()-mark
            record={'case_id':row['case_id'],'event_id':row['event_id'],'entry_ns':duration,'result':reply}
            report['cases'].append(record);save(out/'PARENT_PARTIAL.json',report)
            assert reply['status']==row['expected_entry_status'],record
            expected=2 if reply['status']=='satisfied' else 0
            assert reply['setter_attempts']==reply['setter_returns']==expected,record
            child=json.loads((out/('case_'+str(row['index']).zfill(2)+'.json')).read_text());assert child['passed'],child.get('checks')
        before_rpc=len(rpc);before_cost=len(costs);mark=time.perf_counter_ns();replay=scheduler.run(specs[0])
        report['replay']={'result':replay,'entry_ns':time.perf_counter_ns()-mark,'rpc_delta':len(rpc)-before_rpc,'cost_delta':len(costs)-before_cost}
        assert replay['replayed'] and replay['new_setter_count']==0 and len(rpc)==before_rpc
        cleanup=json.loads((out/'CHILD_CLEANUP.json').read_text());report['child_cleanup']=cleanup
        assert all(cleanup[k] for k in ('profile_none','host_residency_closed','owned_objects_removed','owned_meshes_removed','owned_rigs_removed','file_unsaved','all_handlers_removed'))
        assert cleanup['work']['initial_basis_assignments']==24 and cleanup['work']['product_calls']==8 and cleanup['work']['candidate_assignments']==0
        product_calls=[r for r in rpc if r['command']=='correct_arm_axial'];assert len(product_calls)==8
        report['product_work']={'mutation_rpc':len(product_calls),'setter_attempts':sum(c['result']['setter_attempts'] for c in report['cases']),
            'setter_returns':sum(c['result']['setter_returns'] for c in report['cases']),
            'preview_calls':sum(c['result']['work']['preview_calls'] for c in report['cases']),
            'source_captures':sum(c['result']['work']['source_captures'] for c in report['cases'])}
        assert report['product_work']=={'mutation_rpc':8,'setter_attempts':8,'setter_returns':8,'preview_calls':8,'source_captures':12}
        report['passed']=True
    except BaseException as exc:
        failure=exc;report['failure']={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
    finally:
        subprocess.Popen=original_popen
        if host is not None:
            mark=time.perf_counter_ns();host.close();report['close_ns']=time.perf_counter_ns()-mark
            report['diagnostics']=host.diagnostics
        if process is not None:
            if process.poll() is None:process.terminate();process.wait(timeout=5)
            report['process_exit']={'pid':process.pid,'returncode':process.returncode,'closed':process.poll() is not None}
        report['total_controller_ns']=time.perf_counter_ns()-all_started
        report['costs']=costs;report['rpc']=rpc;report['cost_counts']=dict(Counter(x['phase'] for x in costs))
        report['source_after']=runtime_identity(mode='live');report['source_unchanged']=report['source_after']==identity
        report['blend_sha256_before']=blend_before;report['blend_sha256_after']=sha(BLEND)
        report['passed']=bool(report['passed'] and report['source_unchanged'] and report['blend_sha256_after']==blend_before
            and report.get('process_exit',{}).get('closed') and report['process_exit']['returncode']==0)
        save(out/'RESULT.json',report)
        print(json.dumps({'passed':report['passed'],'cases':len(report['cases']),'result':str(out/'RESULT.json')}))
    if failure is not None:raise failure


if __name__=='__main__':main()
