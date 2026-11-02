"""Explicit operator launch for one owned rigid clearance task.

This authority is deliberately distinct from vertex-reference restoration. It
reuses the existing rigid entry, scheduler and connector journal. Local profile
JSON is input, never approval: only a trusted, explicitly authorized launcher
may create this live object. Receipts never reconstruct execution capability.
"""
import argparse,copy,hashlib,json,os,threading,time,uuid
from pathlib import Path
from .surface_owned import decode,pinned_file
from .task_authority import TrustedTaskAuthority,TaskApproval,ClearanceTaskSpec,_json,_digest
from .task_entry import TrustedTaskEntry
from .owned_task_mcp import proposal
from .goal_supervision import owned_host_counter,validate_owned_motion_report
from .goal_continuation import inspect_current_clearance
from .runtime_identity import runtime_identity,check_source_drift


def require(value,reason):
    if not value:raise ValueError('owned_clearance_operator_'+reason)


class OperatorClearanceTask:
    def __init__(self,profile_path,task_root,*,clock=time.perf_counter):
        self.clock=clock;self.received=clock();self.root=Path(task_root);self.profile_path=Path(profile_path)
        require(self.profile_path.is_absolute() and self.profile_path.resolve()==self.profile_path,'profile_path')
        with self.profile_path.open('rb') as f:self.profile_bytes=f.read(65537)
        require(len(self.profile_bytes)<=65536,'profile_budget');self.profile=decode(self.profile_bytes)
        require(type(self.profile) is dict and set(self.profile)=={'schema','blender_executable','blender_sha256',
            'scene_file','scene_sha256','connector_config','connector_config_sha256','runtime_source_sha256','task'}
            and self.profile['schema']=='owned-clearance-operator-profile-v1','profile_fields_or_wrong_domain')
        self.spec=proposal(self.profile['task']);self.deadline=self.received+self.spec.limits.max_duration_s
        require(self.root.is_absolute() and self.root.resolve()==self.root,'task_root')
        self.root.mkdir(exist_ok=False);self.task_id=uuid.uuid4().hex;self.event_id='operator-clearance:'+self.task_id
        self._gate=threading.Lock();self.used=False;self.approval_used=False;self.bound=None;self.entry=None
        self.started_execution=False;self.closed=False;self._check()
        pinned_file(self.profile['blender_executable'],self.profile['blender_sha256'],128*1024*1024)
        self._publish('INTAKE.json',dict(schema='owned-clearance-operator-task-v1',task_id=self.task_id,
            domain='rigid_clearance',profile=self.profile,profile_sha256=hashlib.sha256(self.profile_bytes).hexdigest(),
            original_received=self.received,original_deadline=self.deadline,
            authorization_origin='explicit_operator_launch_not_MCP_form',human_form_verified=False,
            restart_can_dispatch=False,execution_authority=False))

    def _publish(self,name,value):
        blob=_json(value)
        with (self.root/name).open('xb') as f:f.write(blob);f.flush();os.fsync(f.fileno())

    def _check(self):
        require(not self.closed and self.clock()<self.deadline,'closed_or_original_window_expired')
        with self.profile_path.open('rb') as f:blob=f.read(65537)
        require(blob==self.profile_bytes,'profile_changed')
        pinned_file(self.profile['connector_config'],self.profile['connector_config_sha256'],65536)
        pinned_file(self.profile['scene_file'],self.profile['scene_sha256'],64*1024*1024)
        require(check_source_drift()['compatible'] and runtime_identity()['source_sha256']==self.profile['runtime_source_sha256'],
            'runtime_changed_or_unpinned')

    def _bind_source(self,spec,scope,packet):
        self._check();require(self.bound is None and type(spec) is ClearanceTaskSpec,'source_bound_once_rigid_domain')
        expected=self.spec.to_dict()
        if expected['reference_triangle_index'] is None:expected['reference_triangle_index']=spec.reference_triangle_index
        require(_json(spec.to_dict())==_json(expected),'task_spec_changed')
        require(scope['engine_build_id']=='sha256:'+self.profile['runtime_source_sha256']
            and scope['connector_config_sha256']==self.profile['connector_config_sha256']
            and scope['process_id']==self.host._process.pid
            and scope['initial_capture_sha256']==_digest(packet['capture'])
            and scope['initial_native_sha256']==_digest(packet['native_scene']),'source_binding')
        self.bound=copy.deepcopy(dict(task=spec.to_dict(),scope=scope,packet=packet));self.resolved=spec
        self._publish('SOURCE.json',self.bound)

    def _approve(self,spec,scope):
        require(self.used and not self.approval_used,'approval_once');self.approval_used=True;self._check()
        require(type(spec) is ClearanceTaskSpec and self.bound is not None
            and _json(dict(task=spec.to_dict(),scope=scope))==_json({k:self.bound[k] for k in ('task','scope')}),
            'exact_task_scope_or_wrong_domain')
        self._publish('APPROVAL.json',dict(event_id=self.event_id,task=spec.to_dict(),scope=scope,
            authorization_origin='explicit_operator_launch_not_MCP_form',human_form_verified=False))
        self._check();return TaskApproval(self.event_id,'operator-clearance-approval:'+self.task_id)

    def run(self,host):
        require(self._gate.acquire(blocking=False),'single_flight')
        try:
            require(not self.used,'single_use');self.used=True;self._check();owned_host_counter(host)
            from . import blender_process
            worker=Path(blender_process.__file__).resolve().with_name('blender_worker.py')
            expected=[str(Path(self.profile['blender_executable']).resolve()),'--factory-startup','--disable-autoexec','--background',
                str(Path(self.profile['scene_file']).resolve()),'--python',str(worker),'--',str(worker.parents[1])]
            require(host._process.args==expected,'actual_worker_launch_differs_from_profile');self.host=host
            authority=TrustedTaskAuthority('operator-clearance-'+self.task_id,self._approve)
            self.entry=TrustedTaskEntry(self.profile['connector_config'],host,authority,source_observer=self._bind_source)
            admitted=self.entry.register(self.spec,received_monotonic=self.received)
            self.admitted=admitted;self._publish('ADMISSION.json',admitted)
            require(admitted['live_registration_available'] and admitted['original_started_monotonic']==self.received
                and admitted['original_deadline_monotonic']==self.deadline,'original_registration')
            self._check();self._publish('EXECUTE_PENDING.json',dict(registration_id=admitted['registration_id'],new_setter_count=None))
            self.started_execution=True;result=self.entry.execute(admitted['registration_id'])
            after=self.entry._scheduler._capture();before=self.bound['packet']
            protected=self._protected(before,after);require(protected,'protected_geometry_changed')
            native=inspect_current_clearance(after,self.entry._scheduler._policy(self.resolved,'sha256:'+self.profile['runtime_source_sha256']))
            require(native['decision']!='stop','independent_native_evidence_invalid')
            meter=None;binding=self.entry._scheduler._host_binding
            if binding is not None:
                meter=host.motion_goal_status(admitted['goal_id'])
                meter=validate_owned_motion_report(host,admitted['goal_id'],meter,expected_binding=binding,
                    expected_limits=self.resolved.limits,closed=meter.get('closed') is True)
                if result.get('new_setter_count') is not None:
                    require(meter['physical_meter']['actual_setter_count']==result['new_setter_count'],'physical_count_disagrees')
            if result.get('status')=='completed':
                require(native['decision']=='already_satisfied' and result.get('completion_persistence')=='committed',
                    'final_native_readback_or_persistence')
            require(hashlib.sha256(Path(self.profile['scene_file']).read_bytes()).hexdigest()==self.profile['scene_sha256'],'original_file_changed')
            result.update(operator_task_id=self.task_id,authorization_mode='explicit_operator_rigid_task',
                human_form_verified=False,admission=admitted,independent_readback=native,protected_geometry_unchanged=True,
                independent_physical_meter=meter,
                original_file_saved=False,save_status='not_saved',execution_authority=False,retry_authorized=False)
            result['task_receipt_persistence']='file_flushed_directory_durability_unverified'
            try:self._publish('RESULT.json',dict(result=result,after=after,restart_can_dispatch=False))
            except Exception as exc:
                # A failed metadata receipt does not erase a reconciled kernel
                # count or physical completion. Stop, report both layers, and
                # retain the exclusive task-root claim without another action.
                result.update(kernel_status=result['status'],status='review_required',
                    task_receipt_persistence='unknown',task_receipt_error=type(exc).__name__)
            return result
        except BaseException:
            if self.entry is not None and getattr(self,'admitted',None) is not None:
                try:self.entry.revoke(self.admitted['registration_id'])
                except Exception:pass
            raise
        finally:self.closed=True;self._gate.release()

    def _protected(self,before,after):
        if before['capture']['host_identity']!=after['capture']['host_identity']:return False
        if _json({k:v for k,v in before['capture'].items() if k not in ('revision','meshes')})!=_json({k:v for k,v in after['capture'].items() if k not in ('revision','meshes')}):return False
        captured_old={v['object_id']:v for v in before['capture']['meshes']};captured_new={v['object_id']:v for v in after['capture']['meshes']}
        if set(captured_old)!=set(captured_new):return False
        for key,mesh in captured_old.items():
            current=captured_new[key]
            if key!=self.spec.focal_id:
                if _json(mesh)!=_json(current):return False
            else:
                if _json({k:v for k,v in mesh.items() if k not in ('vertices','pivot_world')})!=_json({k:v for k,v in current.items() if k not in ('vertices','pivot_world')}):return False
                if mesh['pivot_world'][:2]!=current['pivot_world'][:2] or any(a[:2]!=b[:2] for a,b in zip(mesh['vertices'],current['vertices'])):return False
        old={v['object_id']:v for v in before['native_scene']['objects']};new={v['object_id']:v for v in after['native_scene']['objects']}
        if set(old)!=set(new):return False
        for key,value in old.items():
            current=new[key]
            if key!=self.spec.focal_id:
                if _json(value)!=_json(current):return False
                continue
            if _json({k:v for k,v in value.items() if k not in ('world_vertices','matrix')})!=_json({k:v for k,v in current.items() if k not in ('world_vertices','matrix')}):return False
            if any(value['matrix'][r][c]!=current['matrix'][r][c] for r in range(4) for c in range(4) if (r,c)!=(2,3)):return False
            if any(a[:2]!=b[:2] for a,b in zip(value['world_vertices'],current['world_vertices'])):return False
        return True


def main(argv=None):
    p=argparse.ArgumentParser(description='One operator-authorized owned rigid clearance task; never save')
    p.add_argument('--operator-profile',type=Path,required=True);p.add_argument('--operator-task-root',type=Path,required=True)
    p.add_argument('--authorize-task',action='store_true',required=True,help='Explicit operator launch authorization for this exact profile')
    args=p.parse_args(argv);task=None
    try:
        task=OperatorClearanceTask(args.operator_profile,args.operator_task_root)
        from .blender_process import BlenderProcessHost
        with BlenderProcessHost(task.profile['blender_executable'],task.profile['scene_file']) as host:result=task.run(host)
        print(json.dumps(result,allow_nan=False));return 0 if result.get('status')=='completed' else 2
    except Exception as exc:
        print(json.dumps(dict(status='review_required',reason=str(exc)[:500],execution_authority=False,retry_authorized=False,
            new_setter_count=None if task is not None and task.started_execution else 0,
            execution_phase='operator_task_outcome_unknown' if task is not None and task.started_execution else 'not_dispatched')))
        return 1


if __name__=='__main__':raise SystemExit(main())
