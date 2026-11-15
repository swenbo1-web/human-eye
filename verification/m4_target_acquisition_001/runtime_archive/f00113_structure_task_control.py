"""Explicit local lifecycle; selectors in MCP never invoke these mutations."""
from __future__ import annotations
import argparse,hashlib,json,sys,time
from contextlib import contextmanager
from pathlib import Path
from .agent_hooks import _atomic_write,_state_lock,_path,_read_object
from .structure_task import (TaskStore,require,hex_id,encoded,digest,_config,_registration_value)

SCHEMA='structure-task-control-v1'
MAX_REGISTRATIONS=16


class Control:
    def __init__(self,config_path):
        self.config_path=Path(config_path).resolve();legacy,self.fingerprint=_config(self.config_path)
        config=_read_object(self.config_path)
        self.path=_path(self.config_path.parent,config.get('structure_task_control_file'),'structure_task_control_file')
        self.directory=self.path.with_name(self.path.name+'.tasks')
        protected=[self.config_path,legacy]+[_path(self.config_path.parent,config.get(k),k) for k in ('state_file','audit_file')]
        protected += [p.with_name(p.name+'.lock') for p in protected[1:]]
        require(self.path not in protected and self.path.with_name(self.path.name+'.lock') not in protected
            and all(p!=self.directory and self.directory not in p.parents for p in protected),'control_path_collision')

    def store(self,ref):
        require(hex_id(ref),'invalid_task_ref')
        return TaskStore(self.config_path,self.fingerprint,ledger_path=self.directory/(ref+'.json'))

    def read(self,*,create=False):
        if not self.path.exists():
            require(create,'control_registration_required')
            return dict(schema=SCHEMA,config_fingerprint=self.fingerprint,active=None,registrations={})
        with self.path.open('rb') as stream:raw=stream.read(16385)
        require(len(raw)<=16384,'control_byte_budget')
        def unique(pairs):
            value={}
            for k,v in pairs:require(k not in value,'control_duplicate_key');value[k]=v
            return value
        value=json.loads(raw,object_pairs_hook=unique)
        require(type(value) is dict and set(value)=={'schema','config_fingerprint','active','registrations'}
            and value['schema']==SCHEMA and value['config_fingerprint']==self.fingerprint,'control_binding')
        rows=value['registrations']
        require(type(rows) is dict and len(rows)<=MAX_REGISTRATIONS,'control_count')
        refs=[]
        for key,row in rows.items():
            require(type(key) is str and len(key)==64 and all(c in '0123456789abcdef' for c in key)
                and type(row) is dict and set(row)=={'task_ref','parameters_sha256','phase'}
                and hex_id(row['task_ref']) and row['phase'] in ('pending','active','closed')
                and type(row['parameters_sha256']) is str and len(row['parameters_sha256'])==64
                and all(c in '0123456789abcdef' for c in row['parameters_sha256']),'control_record')
            refs.append(row['task_ref'])
        require(len(set(refs))==len(refs),'control_duplicate_generation')
        active=[r['task_ref'] for r in rows.values() if r['phase']=='active']
        require(active==([] if value['active'] is None else [value['active']]),'control_active')
        require(sum(r['phase']=='pending' for r in rows.values())<=1,'control_pending')
        return value

    def write(self,value):
        require(len(encoded(value))<=16384,'control_byte_budget')
        _atomic_write(self.path,value,_buffered=True)

    def summary(self,row):
        result=dict(task_ref=row['task_ref'],phase=row['phase'],execution_authority=False,
            registration_capacity=MAX_REGISTRATIONS,delivery='local_handoff_not_current_scene_evidence')
        if row['phase']=='pending':return result
        store=self.store(row['task_ref'])
        with _state_lock(store.path):state=store._read()
        require(state['task_id']==row['task_ref'],'control_ledger_generation')
        result.update(object_id=state['object_id'],task_budget=store.summary(state),stopped=state['stopped'],
            outcome_unconfirmed=state['inflight'] is not None,service_claimed=state['owner'] is not None,
            expired=not (state['created_ns']<=time.perf_counter_ns()<state['deadline_ns']
                and state['created_wall_ns']<=time.time_ns()<state['deadline_wall_ns']),
            query=dict(mode='mesh_structure',operation='diagnose',request_id='diagnose1',task_ref=row['task_ref']),
            include_image=False)
        return result


def begin(config_path,registration_id,object_id,*,categories=None,limits=None):
    require(type(registration_id) is str and 1<=len(registration_id)<=128
        and all(c.isascii() and (c.isalnum() or c in '_.:-') for c in registration_id),'registration_id')
    control=Control(config_path)
    # Validate and freeze inputs before reserving a registration.
    state=_registration_value(control.fingerprint,object_id,categories=categories,limits=limits)
    parameters=digest(dict(object_id=object_id,categories=state['categories'],limits=state['limits']))
    key=hashlib.sha256(registration_id.encode('ascii')).hexdigest()
    with _state_lock(control.path):
        value=control.read(create=True);old=value['registrations'].get(key)
        if old is not None:
            require(old['parameters_sha256']==parameters,'registration_id_conflict')
            return control.summary(old)
        require(value['active'] is None,'active_task_requires_close')
        require(not any(r['phase']=='pending' for r in value['registrations'].values()),'registration_pending_operator_review')
        require(len(value['registrations'])<MAX_REGISTRATIONS,'registration_capacity_exhausted')
        row=dict(task_ref=state['task_id'],parameters_sha256=parameters,phase='pending')
        value['registrations'][key]=row;control.write(value)
        store=control.store(row['task_ref'])
        with _state_lock(store.path):
            require(not store.path.exists(),'generation_already_exists');store._write(state)
        row['phase']='active';value['active']=row['task_ref'];control.write(value)
        return control.summary(row)


def status(config_path,task_ref=None):
    control=Control(config_path)
    with _state_lock(control.path):
        value=control.read();ref=value['active'] if task_ref is None else task_ref
        row=next((r for r in value['registrations'].values() if r['task_ref']==ref),None)
        if row is None:
            require(task_ref is None,'unknown_task_ref')
            return dict(phase='idle',registrations_used=len(value['registrations']),registration_capacity=MAX_REGISTRATIONS,
                pending=any(r['phase']=='pending' for r in value['registrations'].values()),execution_authority=False)
        return control.summary(row)


def close(config_path,task_ref):
    require(hex_id(task_ref),'invalid_task_ref');control=Control(config_path)
    with _state_lock(control.path):
        value=control.read();row=next((r for r in value['registrations'].values() if r['task_ref']==task_ref),None)
        require(row is not None,'unknown_task_ref')
        if row['phase']=='closed':return control.summary(row)
        require(row['phase']=='active' and value['active']==task_ref,'pending_registration_operator_review')
        store=control.store(task_ref)
        with _state_lock(store.path):
            state=store._read();require(state['task_id']==task_ref,'control_ledger_generation')
            state['stopped']=True;store._write(state)
        row['phase']='closed';value['active']=None;control.write(value)
        return control.summary(row)


@contextmanager
def consumption(service,normalized,timeout_s):
    """Control lock fences replacement until the observation has committed."""
    controlled=bool(service.config.get('structure_task_control_file'))
    if controlled:
        control=Control(service.config_path)
        require(control.fingerprint==service.config_fingerprint,'loaded_config_changed')
        ref=normalized.get('task_ref');require(hex_id(ref),'task_ref_required')
        with _state_lock(control.path,timeout_s=timeout_s):
            state=control.read();require(state['active']==ref,'task_ref_not_active')
            store=getattr(service,'_structure_task_store',None)
            if store is None or store.path!=(control.directory/(ref+'.json')).resolve():
                store=control.store(ref);service._structure_task_store=store
            yield store
    else:
        store=getattr(service,'_structure_task_store',None)
        if store is None:
            store=TaskStore(service.config_path,service.config_fingerprint);service._structure_task_store=store
        yield store


def main(argv=None):
    parser=argparse.ArgumentParser(description='Trusted local single-object read-task lifecycle')
    parser.add_argument('--config',required=True)
    commands=parser.add_subparsers(dest='command',required=True)
    start=commands.add_parser('begin');start.add_argument('--registration-id',required=True);start.add_argument('--object-id',required=True)
    show=commands.add_parser('status');show.add_argument('--task-ref')
    stop=commands.add_parser('close');stop.add_argument('--task-ref',required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=='begin':value=begin(args.config,args.registration_id,args.object_id)
        elif args.command=='status':value=status(args.config,args.task_ref)
        else:value=close(args.config,args.task_ref)
        print(json.dumps(value,ensure_ascii=True,allow_nan=False));return 0
    except Exception as exc:
        print(json.dumps(dict(status='refused',reason=str(exc)[:500],execution_authority=False)),file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
