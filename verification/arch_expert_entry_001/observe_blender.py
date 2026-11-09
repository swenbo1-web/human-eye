"""Verification-only main-thread observer; unchanged worker expression follows."""
from collections import Counter
import json
import os
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
COUNTS=Counter();ACTIVE={};TIMES=Counter();ATTACHED=False
NAMES={'observe_arm_twist','capture','analyze','prepare_patch','get_default_expert','predict_prepared','_report',
    '_read_static','_inspect','_native_topology','capture_task_scene','capture_nearest_candidates','_capture','_resident_capture'}

def difference(after,before):return {key:after[key]-before.get(key,0) for key in after if after[key]!=before.get(key,0)}

def install(folder,spec_path,owned=False):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    namespace={'__name__':'expert_qa_helpers','__file__':str(HERE/'qa_fixture.py')}
    exec(compile((HERE/'qa_fixture.py').read_bytes(),str(HERE/'qa_fixture.py'),'exec'),namespace)
    namespace['configure'](spec_path)
    destination=folder/'blender_events.jsonl'
    def emit(value):
        with destination.open('a',encoding='utf8') as stream:stream.write(json.dumps(value,ensure_ascii=False,allow_nan=False)+'\n')
    emit(dict(event='observer_armed',pid=os.getpid(),loaded=namespace['loaded'](),
        overhead='profiles, local work snapshots, independent direct RNA+same-model oracle and JSON writes; included, unquantified'))
    if owned:
        original=sys.stdin
        class Input:
            def __iter__(self):return self
            def __next__(self):
                line=self.readline()
                if not line:raise StopIteration
                return line
            def readline(self,*args):
                line=original.readline(*args)
                control=folder/'control.json'
                if line and control.exists():
                    value=json.loads(control.read_text(encoding='utf8'));started=time.perf_counter_ns()
                    result=namespace['control'](value['params'])
                    emit(dict(event='control',id=value['id'],params=value['params'],result=result,
                        duration_ms=(time.perf_counter_ns()-started)/1e6,scope='outside measured tool; before existing capabilities request'))
                    control.rename(folder/('control_'+str(value['id'])+'.done.json'))
                return line
            def __getattr__(self,name):return getattr(original,name)
        sys.stdin=Input()
    def profile(frame,event,arg):
        global ATTACHED
        code=frame.f_code;filename=code.co_filename.replace('\\','/')
        if filename.endswith(('/blender_host.py','/arm_twist_source.py','/arm_twist_expert.py')) and code.co_name in NAMES:
            key=filename.rsplit('/',1)[-1]+':'+code.co_qualname
            if event=='call':COUNTS[key]+=1;ACTIVE[id(frame)]=time.perf_counter_ns()
            elif event=='return':
                started=ACTIVE.pop(id(frame),None)
                if started is not None:TIMES[key]+=time.perf_counter_ns()-started
        if ATTACHED or event!='return' or code.co_name!='__init__' or not filename.endswith('/blender_host.py'):return
        host=frame.f_locals.get('self')
        if host is None or type(host).__name__!='BlenderSceneHost':return
        ATTACHED=True
        original=host.observe_arm_twist;sequence=[0]
        def observed(selection):
            sequence[0]+=1;index=sequence[0]
            before=COUNTS.copy();times=TIMES.copy();loaded_before=namespace['loaded']()
            old=getattr(host,'_arm_twist_bound',None);work_before=old.work_totals() if old is not None else {}
            prepared_before=id(old.prepared) if old is not None and old.prepared is not None else None
            started=time.perf_counter_ns();result=None;failure=None
            try:
                result=original(selection)
                return result
            except BaseException as exc:failure=repr(exc);raise
            finally:
                product_ms=(time.perf_counter_ns()-started)/1e6
                bound=getattr(host,'_arm_twist_bound',None)
                work_after=bound.work_totals() if bound is not None else {}
                product_calls=difference(COUNTS,before);product_times=difference(TIMES,times)
                event=dict(event='expert',index=index,pid=os.getpid(),selection=selection,result=result,error=failure,
                    product_method_ms=product_ms,calls=product_calls,inclusive_profile_ms={k:v/1e6 for k,v in product_times.items()},
                    work_before=work_before,work_after=work_after,
                    work_delta=difference(work_after,work_before) if bound is old else work_after,
                    bound_same=bound is old,prepared_before=prepared_before,
                    prepared_after=id(bound.prepared) if bound is not None and bound.prepared is not None else None,
                    loaded_before=loaded_before,loaded_after=namespace['loaded']())
                if result is not None:
                    # This is a separate verification workload, not another
                    # product capture/prepare. Pause only its profiler counters.
                    sys.setprofile(None);oracle_started=time.perf_counter_ns()
                    try:
                        oracle=namespace['direct'](host,selection)
                        oracle_path=folder/('oracle_'+str(index)+'.json')
                        namespace['write'](oracle_path,oracle)
                        event['oracle_file']=str(oracle_path)
                    except BaseException as exc:event['oracle_error']=repr(exc)
                    finally:
                        event['oracle_ms']=(time.perf_counter_ns()-oracle_started)/1e6
                        sys.setprofile(profile)
                emit(event)
        host.observe_arm_twist=observed
        emit(dict(event='observer_attached',pid=os.getpid(),source=sys.modules[type(host).__module__].__file__,loaded=namespace['loaded']()))
    sys.setprofile(profile)

if __name__=='__main__':
    install(os.environ['EXPERT_QA_DIRECTORY'],os.environ['EXPERT_QA_SPEC'],owned=True)
