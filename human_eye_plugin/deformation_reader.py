"""Owned, fresh post-anchor reads for the finite two-static-source adapter.

The ordinary SmallSkinSourceProcess supplies the operator/worker expectations;
no packet flag or caller-supplied row is source admission. Directory captures,
fact captures and B2 work are counted separately. This reader has no cache or
retry, and it never changes an actor's original worker deadline.
"""
import copy,hashlib,os,time
from pathlib import Path
from . import small_skin_source_process as process
from . import deformation_anchors as anchors,deformation_context as context
from . import deformation_core_facts as corefacts,surface_deformation as surface

r=anchors.r
REQUEST_FIELDS={'schema','request_id','run_nonce','condition_id','task_sha256','label','source_ref','kind',
                'selection','deadline_ns','task_deadline_ns'}
SELECTION_FIELDS={'catalog_sha256','anchor_id','core_half_extents_m','profile_sha256'}


def need(value,reason):r.require(value,'deformation_reader_'+reason)
def digest_bytes(blob):return hashlib.sha256(blob).hexdigest()


class QualifiedReader:
    """Exactly two live owned sources, with explicit public anchor selections.

    Constructing this object performs two logical directory reads and two
    physical inspect requests. Call bind_selection for each directory before
    placing source_specs in a frozen task request. read then performs one new
    physical inspect and a normal complete B2/core calculation per source.
    """
    supported_read_kinds=('facts','targeted')
    def __init__(self,profile_paths,*,workspace,task_deadline_ns,clock_ns=time.perf_counter_ns):
        need(type(profile_paths) is dict and len(profile_paths)==2
             and all(r.text(label) for label in profile_paths),'sources')
        need(type(task_deadline_ns) is int,'deadline')
        self.clock_ns=clock_ns;self.task_deadline_ns=task_deadline_ns
        self.workspace=Path(workspace);need(self.workspace.is_absolute() and self.workspace.resolve()==self.workspace,'workspace')
        self.workspace.mkdir(parents=True,exist_ok=False)
        self.actors={};self.catalogs={};self.source_specs={};self.directory_receipts={};self.selections={}
        self.seen_requests=set();self.session_binding=None;self.closed=False
        self.costs=dict(worker_start_attempts=0,worker_starts=0,physical_inspect_requests=0,
            directory_inspect_requests=0,fact_inspect_requests=0,logical_directory_reads=0,
            fact_read_attempts=0,B2_rows_attempts=0,B2_rows_completed=0,core_calculation_calls=0,
            complete_source_validations=0,cache_hits=0,automatic_retries=0)
        self.events=[];self.started_ns=self.clock_ns();self.close_receipt=None
        try:
            for number,label in enumerate(sorted(profile_paths)):
                self._check();folder=self.workspace/('source_'+str(number));folder.mkdir()
                start=self.clock_ns();self.costs['worker_start_attempts']+=1
                actor=process.SmallSkinSourceProcess(Path(profile_paths[label]).resolve());self.actors[label]=actor
                self.costs['worker_starts']+=1;self._check(actor=actor)
                self._event('worker_started',label=label,elapsed_ns=self.clock_ns()-start,
                    process_id=actor.process.pid,actor_original_deadline_ns=actor.deadline_ns)
                before=actor.sequence;self.costs['logical_directory_reads']+=1
                try:
                    packet=actor.inspect();self.costs['complete_source_validations']+=1
                finally:
                    used=actor.sequence-before;self.costs['physical_inspect_requests']+=used;self.costs['directory_inspect_requests']+=used
                self._check(actor=actor);start=self.clock_ns()
                catalog=actor.describe_anchors(packet,deadline_ns=actor.deadline_ns)
                self.costs['complete_source_validations']+=1;self._check(actor=actor)
                self.catalogs[label]=catalog
                self._persist(folder/'DIRECTORY_PACKET.json',packet)
                self._persist(folder/'CATALOG.json',catalog)
                self.directory_receipts[label]=dict(schema='deformation-directory-read-v1',label=label,status='ok',fresh=True,
                    source_ref=copy.deepcopy(catalog['source_ref']),source_sha256=packet['source_sha256'],
                    catalog_sha256=catalog['catalog_sha256'],profile_sha256=digest_bytes(actor.profile_bytes),
                    actor_original_deadline_ns=actor.deadline_ns,task_deadline_ns=task_deadline_ns,
                    physical_inspect_requests=used,logical_directory_reads=1,
                    costs=dict(physical_inspect_requests=used,logical_directory_reads=1,
                        postcapture_catalog_and_persistence_ns=self.clock_ns()-start),
                    selection_status='unresolved',
                    full_source_capture_not_free_facts=True,post_anchor_fact_read_required=True)
                self._event('directory_read',label=label,source_sha256=packet['source_sha256'],
                    postcapture_catalog_and_persistence_ns=self.clock_ns()-start,physical_inspect_requests=used)
            self._check()
        except BaseException as exc:
            self._event('preparation_failed',error_type=type(exc).__name__,reason=str(exc))
            self._cleanup()
            try:self._persist(self.workspace/'PREPARATION_FAILURE.json',dict(reason=str(exc),costs=self.snapshot_costs()))
            except Exception:pass
            raise

    def _persist(self,path,value):
        blob=context.publication_bytes(value)
        with path.open('xb') as stream:stream.write(blob);stream.flush();os.fsync(stream.fileno())
        return dict(path=path.name,bytes=len(blob),sha256=digest_bytes(blob))

    def _event(self,kind,**values):self.events.append(dict(event=kind,at_ns=self.clock_ns(),**values))

    def _check(self,*,actor=None,request_deadline_ns=None):
        deadline=self.task_deadline_ns
        if actor is not None:deadline=min(deadline,actor.deadline_ns)
        if request_deadline_ns is not None:deadline=min(deadline,request_deadline_ns)
        need(self.clock_ns()<deadline,'original_deadline')

    def bind_selection(self,label,anchor_id,core_half_extents_m,*,selection_origin='existing_model_or_operator'):
        need(not self.closed and label in self.actors and label not in self.selections,'selection_state')
        need(selection_origin in ('existing_model_or_operator','public_deterministic_condition'),'selection_origin')
        actor=self.actors[label];self._check(actor=actor);actor.verify_inputs()
        catalog=self.catalogs[label];anchors.anchor_value(catalog,anchor_id);anchors.half_values(core_half_extents_m)
        policy=dict(schema='surface-deformation-context-policy-v1',source_ref=copy.deepcopy(catalog['source_ref']),
            catalog_sha256=catalog['catalog_sha256'],anchor_id=anchor_id,
            required_core_half_extents_m=core_half_extents_m[:],primary_half_extents_m=core_half_extents_m[:],
            candidate_half_extents_m=[],max_surplus_members=0,min_saved_bytes=256,planning_budget_ms=250)
        context.validate_policy(policy);blob=context.publication_bytes(policy)
        policy_path=self.workspace/('source_'+str(sorted(self.actors).index(label)))/'POLICY.json'
        with policy_path.open('xb') as stream:stream.write(blob);stream.flush();os.fsync(stream.fileno())
        self._check(actor=actor);policy_sha=digest_bytes(blob);actor.set_context_policy(policy_path,policy_sha)
        self._check(actor=actor)
        self.selections[label]=dict(policy=policy,policy_sha256=policy_sha)
        spec=dict(source_ref=copy.deepcopy(catalog['source_ref']),catalog_sha256=catalog['catalog_sha256'],
            anchor_id=anchor_id,core_half_extents_m=core_half_extents_m[:],profile_sha256=digest_bytes(actor.profile_bytes))
        self.source_specs[label]=spec
        self.directory_receipts[label].update(anchor_id=anchor_id,core_half_extents_m=core_half_extents_m[:],
            selection_origin=selection_origin,selection_status='selected',policy_sha256=policy_sha)
        self._event('selection_bound',label=label,selection=copy.deepcopy(spec))
        return copy.deepcopy(spec)

    def snapshot_costs(self):
        return dict(self.costs,B2_rows_passes=self.costs['B2_rows_attempts'],events=copy.deepcopy(self.events),
            actor_sequences={label:actor.sequence for label,actor in self.actors.items()},
            worker_processes={label:dict(pid=actor.process.pid,closed=actor.closed,
                exit_code=actor.process.poll(),original_deadline_ns=actor.deadline_ns) for label,actor in self.actors.items()},
            task_deadline_ns=self.task_deadline_ns,started_ns=self.started_ns,
            elapsed_ns=self.clock_ns()-self.started_ns,spans_are_inclusive_and_not_additive=True)

    def read(self,request):
        need(type(request) is dict and request.get('kind') in ('facts','targeted','joint_supplement'),'request_fields')
        fields=REQUEST_FIELDS|({'targeted_triangle_indices'} if request['kind']=='targeted' else set())
        need(set(request)==fields and request['schema']=='deformation-fact-read-v1','request_fields')
        need(not self.closed and type(request['request_id']) is str and request['request_id'] not in self.seen_requests,'duplicate_or_closed')
        label=request['label'];need(type(label) is str and label in self.source_specs,'source_label')
        need(type(request['deadline_ns']) is int and type(request['task_deadline_ns']) is int
            and request['task_deadline_ns']==self.task_deadline_ns
            and request['deadline_ns']<=self.task_deadline_ns,'request_deadline')
        need(type(request['selection']) is dict and set(request['selection'])==SELECTION_FIELDS,'selection_fields')
        context._source_ref(request['source_ref']);context._half(request['selection']['core_half_extents_m'])
        spec=self.source_specs[label]
        need(request['source_ref']==spec['source_ref'] and request['selection']=={key:spec[key] for key in SELECTION_FIELDS},'request_source_selection')
        need(r.text(request['run_nonce']) and r.text(request['condition_id']) and r.hex_text(request['task_sha256'],64),'request_binding')
        binding=(request['run_nonce'],request['condition_id'],request['task_sha256'])
        need(self.session_binding is None or self.session_binding==binding,'request_run')
        self.session_binding=binding;self.seen_requests.add(request['request_id'])
        self.costs['fact_read_attempts']+=1;before_costs=dict(self.costs);start=self.clock_ns();actor=self.actors[label]
        receipt={key:copy.deepcopy(request[key]) for key in fields if key not in ('schema','selection')}
        receipt.update(schema='deformation-fact-receipt-v1',selection=copy.deepcopy(request['selection']),status='unknown',fresh=True)
        try:
            need(request['kind']!='joint_supplement','joint_native_supplement_not_supported')
            self._check(actor=actor,request_deadline_ns=request['deadline_ns']);before=actor.sequence
            try:
                packet=actor.inspect();self.costs['complete_source_validations']+=1
            finally:
                used=actor.sequence-before;self.costs['physical_inspect_requests']+=used;self.costs['fact_inspect_requests']+=used
            self._check(actor=actor,request_deadline_ns=request['deadline_ns']);at=self.clock_ns()
            proof=process.core.validate(packet,deadline_ns=actor.deadline_ns,
                expected_bindings=actor.bindings,expected_source=actor.source)
            self.costs['complete_source_validations']+=1;validation_ns=self.clock_ns()-at
            proof['source']=dict(proof['source'],source_sha256=packet['source_sha256'],source_schema=process.core.SCHEMA,
                **{key:getattr(actor.bindings,key) for key in ('profile_sha256','runtime_source_sha256','worker_sha256','module_sha256','math_sha256','binary_sha256')})
            validation=dict(schema=process.core.SCHEMA,method='external_binding_full_dependency_FK_and_LBS',
                max_replay_error=proof['max_replay_error'],replay_atol=process.core.POSITION_ATOL,
                animation_curves_checked=proof['animation_curves_checked'],not_coordinate_measurement_error=True)
            self._check(actor=actor,request_deadline_ns=request['deadline_ns'])
            chosen=self.selections[label];policy=chosen['policy'];selection=dict(schema='surface-deformation-context-selection-v1',
                source_ref=spec['source_ref'],catalog_sha256=spec['catalog_sha256'],anchor_id=spec['anchor_id'],policy_sha256=chosen['policy_sha256'])
            query=actor.bind_context_selection(packet,selection,deadline_ns=actor.deadline_ns)
            self.costs['complete_source_validations']+=1
            self._check(actor=actor,request_deadline_ns=request['deadline_ns']);at=self.clock_ns()
            self.costs['B2_rows_attempts']+=1;rows=surface._geometry_rows(proof,deadline_ns=actor.deadline_ns)
            self.costs['B2_rows_completed']+=1;B2_ns=self.clock_ns()-at
            targeted=None
            if request['kind']=='targeted':
                source_selection=dict(schema='surface-deformation-selection-v1',source_ref=spec['source_ref'],
                    triangle_indices=copy.deepcopy(request['targeted_triangle_indices']))
                bound=actor.bind_selection(packet,source_selection,deadline_ns=actor.deadline_ns)
                self.costs['complete_source_validations']+=1
                targeted=surface._report_from_rows(proof,rows,query=bound,deadline_ns=actor.deadline_ns)
                need(targeted.get('task_query',{}).get('triangle_indices')==bound['triangle_indices'],'targeted_report')
            self._check(actor=actor,request_deadline_ns=request['deadline_ns']);at=self.clock_ns()
            self.costs['core_calculation_calls']+=1
            core_report,core_audit=corefacts.plan(proof,query,policy=policy,policy_sha256=chosen['policy_sha256'],
                pins=actor._anchor_pins(),rows=rows,source_validation=validation,deadline_ns=actor.deadline_ns)
            core_ns=self.clock_ns()-at;self._check(actor=actor,request_deadline_ns=request['deadline_ns']);actor.verify_inputs()
            bundle=dict(label=label,proof=proof,rows=rows,membership=core_audit['core_membership'],
                policy=copy.deepcopy(policy),policy_sha256=chosen['policy_sha256'],query=query,
                pins=actor._anchor_pins(),source_validation=validation)
            receipt.update(status='ok',source_sha256=proof['source_sha256'],
                evidence=dict(bound_rows_sha256=digest_bytes(rows.payload),proof_sha256=r.digest(proof),
                    membership_sha256=r.digest(core_audit['core_membership'])),
                costs=dict(physical_inspect_requests=self.costs['physical_inspect_requests']-before_costs['physical_inspect_requests'],
                    B2_rows_passes=1,complete_source_validation_ns=validation_ns,B2_wall_ns=B2_ns,core_wall_ns=core_ns,
                    elapsed_ns=self.clock_ns()-start,cache_hits=0,automatic_retries=0),
                freshness='new_inspect_after_public_anchor_selection',
                deadline_scope='task_and_child_completion_gates; underlying_worker_uses_unchanged_original30s_window',
                targeted_triangle_indices=None if targeted is None else targeted['task_query']['triangle_indices'],
                selection_scope='whole_source_B2_and_complete_core' if targeted is None else 'normal_bound_triangle_query_over_fresh_complete_source_rows',
                fact_scope='complete_source_rows',candidate_selection_stage='after_complete_source_fact_read')
            if targeted is not None:receipt['targeted_report']=targeted
            folder=self.workspace/('source_'+str(sorted(self.actors).index(label)))
            at=self.clock_ns()
            raw_receipt=self._persist(folder/'FACT_PACKET.json',packet)
            receipt['raw_packet_ref']=raw_receipt
            self._check(actor=actor,request_deadline_ns=request['deadline_ns'])
            receipt['costs'].update(raw_packet_persistence_ns=self.clock_ns()-at,elapsed_ns=self.clock_ns()-start)
            self._event('fact_read',label=label,request_id=request['request_id'],status='ok',costs=copy.deepcopy(receipt['costs']))
            self._check(actor=actor,request_deadline_ns=request['deadline_ns']);return dict(bundle=bundle,receipt=receipt)
        except BaseException as exc:
            receipt.update(status='unknown',error_type=type(exc).__name__,reason=str(exc),
                costs=dict(physical_inspect_requests=self.costs['physical_inspect_requests']-before_costs['physical_inspect_requests'],
                    B2_rows_passes=self.costs['B2_rows_attempts']-before_costs['B2_rows_attempts'],
                    elapsed_ns=self.clock_ns()-start,cache_hits=0,automatic_retries=0))
            self._event('fact_read',label=label,request_id=request['request_id'],status='unknown',error_type=type(exc).__name__,reason=str(exc))
            return dict(receipt=receipt)

    def _cleanup(self):
        errors=[]
        for label,actor in reversed(list(self.actors.items())):
            try:
                if not actor.closed:actor.close()
                if not actor.closed or actor.process.poll() is None:errors.append(label+':not_closed')
            except BaseException as exc:errors.append(label+':'+type(exc).__name__+':'+str(exc))
        self.closed=True
        return errors

    def verify_and_close(self):
        need(not self.closed,'already_closed');started=self.clock_ns();verified=[];error=None
        try:
            self._check()
            for label,actor in self.actors.items():
                self._check(actor=actor);actor.verify_inputs();self._check(actor=actor);verified.append(label)
        except BaseException as exc:error=exc
        errors=self._cleanup();self._event('verify_and_close',verified_labels=verified,errors=errors,
            verification_error=None if error is None else dict(type=type(error).__name__,reason=str(error)),
            elapsed_ns=self.clock_ns()-started)
        need(error is None,'close_source_validation');need(not errors,'close_failed')
        need(all(actor.process.poll()==0 for actor in self.actors.values()),'worker_exit')
        for actor in self.actors.values():actor.verify_inputs()
        self._check()
        for actor in self.actors.values():self._check(actor=actor)
        self.close_receipt=dict(schema='deformation-reader-close-v1',sources_unchanged=True,all_owned_closed=True,
            original_deadline_preserved=True,verified_labels=verified,elapsed_ns=self.clock_ns()-started,
            physical_inspect_requests=0,model_received=False,costs=self.snapshot_costs())
        return copy.deepcopy(self.close_receipt)

    def close(self):
        """Failure cleanup only; this does not produce a publishable receipt."""
        return self._cleanup()
