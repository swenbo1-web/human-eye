"""Instrumented attribution on a fixed installed entry, never a speed benchmark.

The bootstrap and runtime source bytes remain unchanged. A diagnostic wrapper
sets a Python profile callback, then calls the fixed bootstrap's normal main.
It preserves the exact source guards and real native-image requests. Profile
overhead and extra diagnostic imports are disclosed; uninstrumented AB/BA
measurements are a separate experiment.
"""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,os,shutil,subprocess,sys,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
VERSION='9.7.2+20261103.core.facts.r1'
SOURCE='dbeb471f3120bdb133b1ca1669dbbbd525e4679a9ec1949bc67fdba171182c47'
PYTHON=ROOT/'.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe'
RELEASE=ROOT/'.human-eye/releases'/VERSION
SITE=RELEASE/'site-packages'
ENTRY=RELEASE/'admin/target_runtime_entry.py'
BLENDER=Path('D:/Tools/blender5.2/blender.exe')
FLAGS=getattr(subprocess,'CREATE_NO_WINDOW',0)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path):return json.loads(Path(path).read_bytes())
def save(path,value):
    with Path(path).open('x',encoding='utf8') as f:json.dump(value,f,indent=2,allow_nan=False)


def harness():
    path=ROOT/'verification/run_deployment_cost_qualification.py'
    spec=importlib.util.spec_from_file_location('_source_profile_qa_harness',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.ARMS={'baseline':dict(release=VERSION,count=125,sha=SOURCE)}
    return module


class Recorder:
    """Observe events; never alter a guard, loader or identity function."""
    def __init__(self):
        self.active={};self.frames={};self.checks=[];self.guards=[];self.other={}
        self.stack=[];self.max_frames=100_000;self.overflow=False

    def _inventory(self,guard):
        rows=[]
        for name,module in list(sys.modules.items()):
            path=getattr(module,'__file__',None)
            if path is not None or guard._owned_name(name):
                witness=guard._executed.get(id(module))
                rows.append(dict(name=name,file=str(path) if path is not None else None,
                    owned_name=guard._owned_name(name),executed_witness=bool(witness and witness[0] is module),
                    namespace_witness=guard._namespaces.get(id(module)) is module))
        return rows

    def __call__(self,frame,event,arg):
        name=frame.f_code.co_name;filename=frame.f_code.co_filename.replace('\\','/')
        identity=filename.endswith('/human_eye_plugin/runtime_identity.py')
        guardfile=filename.endswith('/human_eye_plugin/verified_source_loader.py')
        ispath=filename.endswith('/pathlib.py')
        key=None
        python_event=event in ('call','return')
        if python_event and identity and name in ('check_source_drift','_capture_source_identity','_source_manifest'):key=name
        elif python_event and guardfile and name=='verify_loaded':key='verify_loaded'
        elif python_event and ispath and name in ('resolve','read_bytes','glob','is_file'):key='Path.'+name
        elif event in ('c_call','c_return','c_exception') and self.stack:
            cname=getattr(arg,'__name__','')
            if cname in ('openssl_sha256','hexdigest','scandir'):key='C.'+cname
        if key is None:return
        now=time.perf_counter_ns();framekey=(id(frame),key)
        if event in ('call','c_call'):
            if len(self.frames)>self.max_frames:self.overflow=True;return
            row=None
            if key=='check_source_drift':
                row=dict(index=len(self.checks),caller=frame.f_back.f_code.co_name,started_ns=now,functions={},path_resolves=[])
                self.checks.append(row);self.stack.append(row)
            elif key=='verify_loaded':
                guard=frame.f_locals['self'];row=dict(index=len(self.guards),started_ns=now,
                    inside_check=self.stack[-1]['index'] if self.stack else None,root=str(guard.root),functions={},path_resolves=[],
                    modules=self._inventory(guard))
                self.guards.append(row)
            data=dict(start=now,check=self.stack[-1] if self.stack else None,guard=row if key=='verify_loaded' else self.active.get('guard'),key=key)
            if key=='verify_loaded':self.active['guard']=row
            if key=='Path.resolve':
                parent=frame.f_back
                data.update(path=str(frame.f_locals.get('self')),caller=parent.f_code.co_name if parent else None,
                    caller_line=parent.f_lineno if parent else None,caller_file=parent.f_code.co_filename if parent else None)
            self.frames[framekey]=data
        elif event in ('return','c_return','c_exception'):
            data=self.frames.pop(framekey,None)
            if data is None:return
            elapsed=now-data['start'];targets=[]
            if data['check'] is not None:targets.append(data['check'])
            if data['guard'] is not None and data['guard'] not in targets:targets.append(data['guard'])
            for row in targets:
                stats=row['functions'].setdefault(key,dict(calls=0,inclusive_ns=0,read_bytes=0))
                stats['calls']+=1;stats['inclusive_ns']+=elapsed
                if key=='Path.read_bytes' and isinstance(arg,bytes):stats['read_bytes']+=len(arg)
                if key=='Path.resolve':
                    row['path_resolves'].append(dict(path=data['path'],result=str(arg),elapsed_ns=elapsed,
                        caller=data['caller'],caller_line=data['caller_line'],caller_file=data['caller_file']))
            if key=='verify_loaded':
                row=data['guard'];row.update(elapsed_ns=elapsed,returned_true=arg is True)
                self.active.pop('guard',None)
            elif key=='check_source_drift':
                row=data['check'];row.update(elapsed_ns=elapsed,status=arg.get('status') if isinstance(arg,dict) else None,
                    compatible=arg.get('compatible') if isinstance(arg,dict) else None)
                assert self.stack[-1] is row;self.stack.pop()


def child(config,output):
    binding=load(ENTRY.with_name('RUNTIME_BINDING.json'));assert binding['identity']['source_sha256']==SOURCE
    raw=ENTRY.read_bytes();assert hashlib.sha256(raw).hexdigest()==binding['launcher_sha256']
    spec=importlib.util.spec_from_file_location('_source_profile_fixed_entry',ENTRY)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module
    exec(compile(raw,str(ENTRY),'exec',dont_inherit=True),module.__dict__)
    recorder=Recorder();started=time.perf_counter_ns();sys.setprofile(recorder)
    try:result=module.main(['serve','--config',str(config)])
    finally:
        sys.setprofile(None)
        save(output/'PROFILE_EVENTS.json',dict(checks=recorder.checks,guards=recorder.guards,
            overflow=recorder.overflow,wrapper_to_exit_ns=time.perf_counter_ns()-started,
            runtime_source_sha256=SOURCE,source_files=125,entry_sha256=sha(ENTRY),profile_wrapper_sha256=sha(__file__),
            instrumented=True,not_performance_measurement=True,
            guarantee='Observed unchanged fixed target.main; no guard/runtime monkeypatch or source edit',
            limits='Python callback inclusive times include profiling overhead; no sum-of-median causal attribution. Diagnostic imports may add modules; full inventory retained. Main thread only.'))
    return result


def run(output):
    h=harness();output.mkdir(parents=True,exist_ok=False)
    original=ROOT/'verification/fixes/20261103_deployment_core_projection/DEPLOYMENT_COST_fixture.blend'
    binding=load(ENTRY.with_name('RUNTIME_BINDING.json'))
    assert binding['identity']['source_sha256']==SOURCE and len(binding['source_files'])==125
    registration=dict(schema='fixed-source-guard-profile-v1',entry=str(ENTRY),entry_sha256=sha(ENTRY),binding_sha256=sha(ENTRY.with_name('RUNTIME_BINDING.json')),
        runtime_source_sha256=SOURCE,source_files=125,python=str(PYTHON),blender=str(BLENDER),blender_sha256=sha(BLENDER),
        fixture_sha256=sha(original),wrapper_sha256=sha(__file__),requests=['cold_native']+['hot_native']*3+['ordinary_gap_text']*3+['status']*3,
        profile='Python sys.setprofile records unchanged fixed target.main serve execution and guard inventory',
        source_mutation=False,GUIMutation=False,not_uninstrumented_performance=True,
        timings='Per drift and guard invocation inclusive times; source-manifest/read/hash/glob/path resolution; profiler overhead uncorrected',
        limitations=['Diagnostic wrapper adds trusted external modules; complete loaded set recorded','No pure provider or model cost','No comparison to old124 as new125 baseline'])
    save(output/'PROFILE_PREREGISTERED.json',registration);(output/'PROFILE_HARNESS.py').write_bytes(Path(__file__).read_bytes())
    fixture=output/'fixture.blend';shutil.copyfile(original,fixture);folder=output/'server';folder.mkdir()
    streams=[(folder/n).open('wb') for n in ('BLENDER_STDOUT.txt','BLENDER_STDERR.txt')]
    server=client=None;calls=[]
    try:
        command=[str(BLENDER),'--factory-startup','--disable-autoexec','--background',str(fixture),'--python',str(Path(__file__).resolve()),'--','qa-server','--output',str(folder)]
        server=subprocess.Popen(command,stdout=streams[0],stderr=streams[1],creationflags=FLAGS)
        until=time.monotonic()+60
        while not(folder/'READY.json').exists():
            if server.poll() is not None or time.monotonic()>until:raise RuntimeError('QA_start_failed')
            time.sleep(.01)
        ready=load(folder/'READY.json');config=output/'config.json'
        save(config,dict(schema_version='1.0',enabled=True,observe_on_prompt=True,project_root=str(SITE),state_file='state.json',audit_file='events.jsonl',
            quad_size=384,max_sessions=16,readback_atol_m=1e-6,blender=dict(host='127.0.0.1',port=ready['port'],timeout_s=10)))
        client=h.JsonProcess([str(PYTHON),'-I','-B',str(Path(__file__).resolve()),'child','--config',str(config),'--output',str(output)],SITE,output)
        response,raw,*_=client.call(dict(jsonrpc='2.0',id=1,method='initialize'));h.validate_identity(response['result']['_meta']['human_eye'],'baseline')
        (output/'INITIALIZE.json').write_bytes(raw)
        for index,kind in enumerate(registration['requests'],2):
            args={} if kind=='status' else dict(session_id='source-profile',task_instruction='Check the gap between BluePart and GreyBase; observe only, do not move.',
                focal_id=h.object_id('BluePart'),reference_id=h.object_id('GreyBase'),include_image=kind in ('cold_native','hot_native'))
            if kind in ('cold_native','hot_native'):args['query']={'native_visual':{'mode':'multiscale','view':'SCENE'}}
            req=dict(jsonrpc='2.0',id=index,method='tools/call',params=dict(name='human_eye_connection_status' if kind=='status' else 'human_eye_scene_observe',arguments=args))
            response,raw,*_=client.call(req);status,_=h.check_tool(response,'baseline',kind);assert status=='passed',(kind,status)
            (output/f'{index}_{kind}.json').write_bytes(raw);calls.append(dict(id=index,kind=kind,status=status))
        client.close();client=None
    finally:
        if client is not None:client.close()
        if server is not None:
            (folder/'STOP').touch()
            try:server.wait(timeout=15)
            except subprocess.TimeoutExpired:server.kill();server.wait(timeout=5)
        for stream in streams:stream.close()
    result=load(output/'PROFILE_EVENTS.json');assert not result['overflow'] and all(r['compatible'] for r in result['checks'])
    proof=load(folder/'SERVER_RESULT.json');assert proof['scene_unchanged'] and proof['display_restored'] and server.returncode==0
    assert sha(fixture)==registration['fixture_sha256']
    save(output/'PROFILE_RESULT.json',dict(all_passed=True,calls=calls,guard_invocations=len(result['guards']),source_checks=len(result['checks']),
        process_reaped=True,scene_unchanged=True,display_restored=True,source_unchanged=True,instrumented_not_speed_benchmark=True))
    print(json.dumps(dict(all_passed=True,source_checks=len(result['checks']),guard_invocations=len(result['guards']))))


def main():
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('run','child','qa-server'));p.add_argument('--output',type=Path,required=True);p.add_argument('--config',type=Path);a=p.parse_args(argv)
    if a.mode=='run':return run(a.output.resolve())
    if a.mode=='child':return child(a.config.resolve(),a.output.resolve())
    return harness().qa_server('baseline',a.output.resolve())


if __name__=='__main__':raise SystemExit(main())
