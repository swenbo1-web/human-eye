"""Lightweight verification wrappers. No sys.setprofile; oracle is a later RPC."""
import builtins
from collections import Counter
import json
import os
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent


def install(folder,spec_path,owned=False):
    assert sys.getprofile() is None
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    helper={'__name__':'entry_opt_helpers','__file__':str(HERE/'qa_fixture.py')}
    exec(compile((HERE/'qa_fixture.py').read_bytes(),str(HERE/'qa_fixture.py'),'exec'),helper)
    helper['configure'](spec_path);helper['STATE']['observer_folder']=str(folder)
    destination=folder/'blender_events.jsonl'
    def emit(value):
        with destination.open('a',encoding='utf8') as stream:stream.write(json.dumps(value,ensure_ascii=False)+'\n')
    emit(dict(event='observer_armed',pid=os.getpid(),profile_none=sys.getprofile() is None,
        scope='light wrappers; event/packet writes and direct oracle only in later inspect control'))
    counts=Counter();active=[False];instrumented=set();sequence=[0]
    def counted(owner,name,key):
        original=getattr(owner,name)
        def wrapped(*a,**kw):
            if active[0]:counts[key]+=1
            return original(*a,**kw)
        setattr(owner,name,wrapped)
    def instrument(module):
        if id(module) in instrumented:return
        instrumented.add(id(module))
        counted(module.BoundArmPatch,'capture','capture_entries')
        counted(module.BoundArmPatch,'_read_static','static_read_entries')
        original_copy=module.deepcopy
        def copy(value,*a,**kw):
            if active[0] and type(value) is dict and value.get('schema')=='arm-twist-patch-v1':
                counts['static_patch_copies']+=1
            return original_copy(value,*a,**kw)
        module.deepcopy=copy
        expert=sys.modules[module.__package__+'.arm_twist_expert']
        counted(expert,'prepare_patch','prepare_entries')
        counted(expert.ArmTwistExpert,'predict_prepared','predict_entries')
    def attach(host):
        helper['STATE']['host']=host
        original_module=host._arm_twist_source_module
        def source_module():
            module=original_module();instrument(module);return module
        host._arm_twist_source_module=source_module
        original=host.observe_arm_twist
        def observed(selection):
            assert sys.getprofile() is None
            sequence[0]+=1
            old=getattr(host,'_arm_twist_bound',None)
            work_before=old.work_totals() if old is not None else {}
            prepared_before=id(old.prepared) if old is not None and old.prepared is not None else None
            before=counts.copy();result=None;failure=None
            active[0]=True;started=time.perf_counter_ns()
            try:
                result=original(selection);return result
            except BaseException as exc:failure=repr(exc);raise
            finally:
                product_ms=(time.perf_counter_ns()-started)/1e6;active[0]=False
                bound=getattr(host,'_arm_twist_bound',None)
                after=bound.work_totals() if bound is not None else {}
                helper['STATE']['last_event']=dict(event='expert',index=sequence[0],pid=os.getpid(),
                    selection=selection,result=result,error=failure,product_method_ms=product_ms,
                    profile_none=sys.getprofile() is None,
                    calls={key:counts[key]-before.get(key,0) for key in counts if counts[key]!=before.get(key,0)},
                    work_before=work_before,work_after=after,
                    work_delta={key:after[key]-work_before.get(key,0) for key in after if after[key]!=work_before.get(key,0)} if bound is old else after,
                    bound_same=bound is old,prepared_before=prepared_before,
                    prepared_after=id(bound.prepared) if bound is not None and bound.prepared is not None else None)
        host.observe_arm_twist=observed
        emit(dict(event='observer_attached',pid=os.getpid(),profile_none=sys.getprofile() is None,
            source=sys.modules[type(host).__module__].__file__))
    original_build=builtins.__build_class__
    def build(func,name,*a,**kw):
        cls=original_build(func,name,*a,**kw)
        if name=='BlenderSceneHost' and func.__code__.co_filename.replace('\\','/').endswith('/blender_host.py'):
            builtins.__build_class__=original_build
            original_init=cls.__init__
            def init(self,*args,**kwargs):
                original_init(self,*args,**kwargs);attach(self)
            cls.__init__=init
        return cls
    builtins.__build_class__=build
    if owned:
        original_stdin=sys.stdin
        class Input:
            def __iter__(self):return self
            def __next__(self):
                line=self.readline()
                if not line:raise StopIteration
                return line
            def readline(self,*a):
                line=original_stdin.readline(*a);control=folder/'control.json'
                if line and control.exists():
                    value=json.loads(control.read_text(encoding='utf8'));started=time.perf_counter_ns()
                    result=helper['control'](value['params'])
                    emit(dict(event='control',id=value['id'],params=value['params'],result=result,
                        duration_ms=(time.perf_counter_ns()-started)/1e6,scope='separate control outside measured tool'))
                    control.rename(folder/('control_'+str(value['id'])+'.done.json'))
                return line
            def __getattr__(self,name):return getattr(original_stdin,name)
        sys.stdin=Input()
    return helper['control']


if __name__=='__main__':
    install(os.environ['EXPERT_QA_DIRECTORY'],os.environ['EXPERT_QA_SPEC'],owned=True)
