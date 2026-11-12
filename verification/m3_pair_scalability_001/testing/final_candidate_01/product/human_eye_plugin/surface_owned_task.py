"""One explicit operator launch authorizes one exact owned reference task.

Not a reusable auto-approve switch or an MCP form response. Persisted files are
receipts only. An existing task directory always refuses another live issuance.
The trusted local launcher must have the operator's authority for this task;
arbitrary Python running under the same OS account is outside this boundary.
"""
import copy,os,threading,time,uuid
from pathlib import Path
from . import surface_owned as s


def source_identity(source):
    return {k:v for k,v in source.items() if k!='capture_id'}


class OperatorReferenceTask:
    def __init__(self,config_path,selected,task_root,*,clock=time.perf_counter_ns):
        self.clock=clock;self.received_ns=clock();self.deadline_ns=self.received_ns+s.LIMITS['duration_ns']
        self.selected=s.indices(selected);self.config_path=Path(config_path)
        self.config,self.config_sha=s.load_config(config_path)
        self.reference=s.decode(s.pinned_file(self.config['reference_file'],self.config['reference_sha256'],65536))
        self.root=Path(task_root)
        s.require(self.root.is_absolute() and self.root.resolve()==self.root,'operator_task_path')
        # mkdir is the exclusive durable claim. Even a crash before INTAKE is
        # published leaves a non-reusable root. Nothing ever loads a grant.
        self.root.mkdir(exist_ok=False)
        self.task_id=uuid.uuid4().hex;self._lock=threading.Lock();self.actor=None
        self.claimed=False;self.approval_used=False;self.closed=False;self.event_id=None
        self.intake=dict(schema='owned-reference-operator-task-v1',task_id=self.task_id,
            authorization_origin='explicit_operator_launch_not_MCP_form',human_form_verified=False,
            config_sha256=self.config_sha,runtime_source_sha256=self.config['runtime_source_sha256'],
            scene_sha256=self.config['scene_sha256'],reference_sha256=self.config['reference_sha256'],
            indices=self.selected,received_ns=self.received_ns,deadline_ns=self.deadline_ns,
            maximum_setter_attempts=2*len(self.selected),maximum_displacement_m=s.LIMITS['displacement_m'],
            original_file_will_be_saved=False,restart_can_dispatch=False,execution_authority=False)
        self._publish('INTAKE.json',self.intake)

    def _publish(self,name,value):
        blob=s.encoded(value);s.require(len(blob)<=s.MAX_MESSAGE,'operator_record_budget')
        with (self.root/name).open('xb') as f:f.write(blob);f.flush();os.fsync(f.fileno())

    def _check(self):
        s.require(not self.closed and self.clock()<self.deadline_ns,'operator_task_closed_or_expired')
        config,checksum=s.load_config(self.config_path)
        s.require(config==self.config and checksum==self.config_sha,'operator_task_config_changed')
        s.pinned_file(config['reference_file'],config['reference_sha256'],65536)

    def attach(self,actor):
        with self._lock:
            s.require(self.actor is None and not self.claimed,'operator_task_attach_once');self._check()
            s.require(actor.config_sha==self.config_sha,'operator_task_actor_config')
            before=actor.inspect();self._check()
            s.require(before.get('quarantined') is False and before['journal']['unknown'] is False
                and before['source']['object_id']==self.config['object_id'],'operator_task_unknown_or_target')
            self.before=copy.deepcopy(before);self.actor=actor
            predicted=copy.deepcopy(before['raw_snapshot'])
            for index in self.selected:
                s.require(index<len(predicted['vertices']) and index<len(self.reference['raw']['vertices']),'operator_task_vertex')
                predicted['vertices'][index]=copy.deepcopy(self.reference['raw']['vertices'][index])
            self.predicted=copy.deepcopy(predicted)
            self.expected=dict(indices=self.selected,received_ns=self.received_ns,deadline_ns=self.deadline_ns,
                maximum_setter_attempts=2*len(self.selected),max_displacement_m=s.LIMITS['displacement_m'],
                source=source_identity(before['source']),reference_source=self.reference['source'],
                proposed_raw_sha256=s.digest(predicted),matrix_world=before['raw_snapshot']['matrix_world'],
                unit_scale_m=before['raw_snapshot']['unit_scale'],semantic_target=self.config['reference_intent']['semantic_target'],
                schema='owned-reference-patch-restore-v1',motion_certification='discrete_vertex_endpoints_only_not_swept_surface',
                coordinate_frame='local_blender_units_with_source_matrix_and_unit_scale',
                vertex_changes=[dict(vertex=i,before_local=before['raw_snapshot']['vertices'][i],
                    target_local=predicted['vertices'][i]) for i in self.selected])
            self._publish('BOUND.json',dict(intake=self.intake,before=before,expected_scope=self.expected))

    def _approve(self,scope):
        with self._lock:
            s.require(self.claimed and not self.approval_used,'operator_task_approval_once')
            self.approval_used=True;self._check()
            observed=copy.deepcopy(scope)
            observed['source']=source_identity(observed['source'])
            expected=dict(self.expected,event_id=self.event_id)
            s.require(s.encoded(observed)==s.encoded(expected),'operator_task_exact_scope')
            # Durable evidence precedes the actual affirmative worker message.
            self._publish('SCOPE.json',dict(task_id=self.task_id,scope=scope,scope_sha256=s.digest(scope),
                authorization_origin=self.intake['authorization_origin'],human_form_verified=False))
            self._check();return True

    def execute(self,actor,selected,*,event_id,client_received_ns,cancelled):
        with self._lock:
            s.require(actor is self.actor and not self.claimed,'operator_task_once')
            self.claimed=True;self._check()
            s.require(s.indices(selected)==self.selected,'operator_task_exact_indices')
            s.require(type(client_received_ns) is int and self.received_ns<=client_received_ns<=self.clock(),
                'operator_task_client_intake')
            s.require(not cancelled(),'operator_task_cancelled')
            self.event_id=event_id
            self._publish('REQUEST.json',dict(task_id=self.task_id,event_id=event_id,client_received_ns=client_received_ns,
                original_received_ns=self.received_ns,original_deadline_ns=self.deadline_ns))
        # The worker keeps its existing strict scope/hash, geometry, setter and
        # journal gates. Passing the original launch time cannot renew 30s.
        try:
            result=actor.goal(self.selected,event_id=event_id,received_ns=self.received_ns,
                approve=self._approve,cancelled=cancelled)
            after=actor.inspect()  # read-only; never another action window
            kernel=result.get('kernel_result')
            if type(kernel) is dict and kernel.get('status') in ('completed','failed_checkpoint_restored'):
                expected=self.predicted if kernel['status']=='completed' else self.before['raw_snapshot']
                s.require(after['raw_snapshot']==expected and all(after['source'][key]==self.before['source'][key]
                    for key in ('object_id','object_instance','document_epoch')),'operator_task_final_readback')
            s.require(after['physical_RNA_attempts']==result['worker_physical_RNA_attempts'],'operator_task_final_counter')
            result.update(authorization_mode='explicit_operator_task',operator_task_id=self.task_id,
                operator_received_ns=self.received_ns,operator_deadline_ns=self.deadline_ns,
                human_form_verified=False,task_readback_verified=type(kernel) is dict and kernel.get('status') in ('completed','failed_checkpoint_restored'))
            self._publish('RESULT.json',dict(result=result,after=after,execution_authority=False,restart_can_dispatch=False))
            return result
        except BaseException:
            # Failure after dispatch may include a completed write. Never let
            # the MCP wrapper turn a lost receipt into a known zero refusal.
            actor.poisoned=True;actor.close();raise
        finally:self.closed=True

    def close(self):self.closed=True
