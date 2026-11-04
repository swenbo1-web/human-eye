"""Finite 003 common acquisition and independent A/B/C report preparation.

No model, truth, edit, frame change, default installation or consumer launch.
Owned-worker deadlines end at closure. The later static computation window is
separate and grants no new worker lifetime or fresh-inspect authority.
"""
from __future__ import annotations
import argparse,copy,hashlib,importlib.util,json,os,secrets,sys,tempfile,time,tracemalloc
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PIN='6a5375fb5d5577e8de05c043db7523263cf96ad8386ee524a04beb25feb9f382'
REVISION='v21-cost-snapshot-integrity-candidate-20261104'
CYCLE='V21-REFACTOR-003'
CONDITION='V21-REFACTOR-003-post-anchor'
THRESHOLDS=dict(high=1.1,low=.9)
HELPER=ROOT/'verification/run_deformation_closure_preflight.py'
helper_spec=importlib.util.spec_from_file_location('_v21_trial_acquire_helpers',HELPER)
helpers=importlib.util.module_from_spec(helper_spec);helper_spec.loader.exec_module(helpers)


def need(value,reason):
    if not value:raise ValueError('v21_trial_acquire_'+reason)


def blob(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')+b'\n'


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,
        allow_nan=False).encode('utf8')).hexdigest()


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path):return json.loads(Path(path).read_bytes())
def check(deadline_ns):need(type(deadline_ns) is int and time.perf_counter_ns()<deadline_ns,'deadline')


def save(path,value,*,deadline_ns=None):
    if deadline_ns is not None:check(deadline_ns)
    started=time.perf_counter_ns();path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);raw=blob(value)
    need(len(raw)<=8*1024*1024,'internal_artifact_bytes')
    with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    need(path.read_bytes()==raw,'persisted_readback')
    record=dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),
        persist_and_readback_ns=time.perf_counter_ns()-started)
    if deadline_ns is not None:check(deadline_ns)
    return record


def question():
    path=ROOT/'verification/fixes/20261103_review_cycle006/PREREGISTERED.json'
    need(sha(path)=='50df877c584042586887f7a2906a948fc6aa6ca8e3583b4af5d25e8e7acc1534','public_question_pin')
    value=load(path)['question'];need(type(value) is str and value.strip(),'public_question');return value


def topology(proof):return digest(dict(original=proof['original'],triangles=proof['triangles']))


def _ordinary_summary(report,*,core=False):
    value=report['region_query'] if core else report
    result=dict(triangles_total=value['triangles_total'],states={state:value['triangles_'+state]
        for state in ('measured','collapsed','unknown')},unknown_reasons=copy.deepcopy(value['unknown_reasons']),
        observation_state=value['status'])
    if core:result['core_extrema']={key:None if row is None else row['value']
        for key,row in value['metric_extrema'].items()}
    return result


def _backend_frame(bundle,rows,members,core_summary,global_summary,indices):
    initial_summary=dict(core_states=copy.deepcopy(core_summary['states']),global_states=copy.deepcopy(global_summary['states']))
    if 'core_extrema' in core_summary:initial_summary['core_extrema']=copy.deepcopy(core_summary['core_extrema'])
    if 'has_confirmed_mixed_witness' in core_summary:
        initial_summary['core_confirmation']=core_summary['has_confirmed_mixed_witness']
    return dict(source_ref=copy.deepcopy(bundle['catalog']['source_ref']),anchor_id=bundle['policy']['anchor_id'],
        source_observation_sha256=bundle['proof']['source_sha256'],raw_packet_sha256=bundle['packet_file_sha256'],
        rows=copy.deepcopy(rows),members=members[:],core_summary=copy.deepcopy(core_summary),
        global_summary=copy.deepcopy(global_summary),initial_row_indices=sorted(set(indices)),
        original_topology_sha256=topology(bundle['proof']),initial_summary=initial_summary)


def _backend(common,report,frames):
    return dict(schema='v21-post-anchor-static-backend-v1',task_sha256=common['task_sha256'],
        run_nonce=common['run_nonce'],report_sha256=hashlib.sha256(blob(report)).hexdigest(),
        original_topology_sha256=common['original_topology_sha256'],frames=frames,
        common_original_topology_digest_model='compact_UTF8_JSON_reference_original_vertices_and_original_triangles',
        lookup_scope='hash_bound_complete_static_rows_not_a_fresh_targeted_worker_inspect')


def _prepare_A(common,bundles,out,deadline_ns):
    from human_eye_plugin import deformation_anchors as anchors,deformation_region as region,surface_deformation as surface
    frames={};backend={};metrics=[]
    for b in bundles:
        check(deadline_ns);started=time.perf_counter_ns();rows=surface._geometry_rows(b['proof'],deadline_ns=deadline_ns)
        B2_ns=time.perf_counter_ns()-started;phase=time.perf_counter_ns()
        selection=dict(schema='surface-deformation-anchor-selection-v1',source_ref=b['catalog']['source_ref'],
            catalog_sha256=b['catalog']['catalog_sha256'],anchor_id=b['policy']['anchor_id'],half_extents_m=[.5]*3)
        anchor_query=anchors.bind_selection(b['proof'],selection,pins=b['pins'],deadline_ns=deadline_ns)
        region_query,trace=anchors.resolve(b['proof'],anchor_query,pins=b['pins'],deadline_ns=deadline_ns)
        membership=region.select(b['proof'],region_query,deadline_ns=deadline_ns)
        report=surface._report_from_rows(b['proof'],rows,region_membership=membership,deadline_ns=deadline_ns)
        report['source_validation']=copy.deepcopy(b['source_validation']);report['anchor_query']=trace
        frames[b['label']]=report;values=surface._verified_rows(b['proof'],rows,deadline_ns=deadline_ns)
        backend[b['label']]=_backend_frame(b,values,membership['matched_triangle_indices'],
            _ordinary_summary(report,core=True),_ordinary_summary(report),
            [row['triangle'] for row in report['region_query']['triangles']])
        metrics.append(dict(label=b['label'],B2_rows_passes=1,B2_wall_ns=B2_ns,
            ordinary_anchor_region_and_backend_ns=time.perf_counter_ns()-phase))
    report=dict(schema='v21-ordinary-anchor-region-pair-v1',frames=frames,
        scope='existing ordinary anchor region diagnostics; no task-specific witness selector or new mixed-confirmation field')
    records=[save(out/'REPORT.json',report,deadline_ns=deadline_ns),
        save(out/'BACKEND.json',_backend(common,report,backend),deadline_ns=deadline_ns)]
    return dict(B2_rows_passes=2,source_inspect_requests=0,frames=metrics,storage=records)


def _prepare_B(common,bundles,out,deadline_ns):
    from human_eye_plugin import deformation_core_facts as corefacts,deformation_task_view as view,surface_deformation as surface
    frames=[];metrics=[];rows_by_label={};members_by_label={}
    for b in bundles:
        check(deadline_ns);started=time.perf_counter_ns();rows=surface._geometry_rows(b['proof'],deadline_ns=deadline_ns)
        B2_ns=time.perf_counter_ns()-started;phase=time.perf_counter_ns()
        core_report,audit=corefacts.plan(b['proof'],b['query'],policy=b['policy'],policy_sha256=b['policy_sha256'],
            pins=b['pins'],rows=rows,source_validation=b['source_validation'],deadline_ns=deadline_ns)
        frames.append(dict(label=b['label'],proof=b['proof'],rows=rows,membership=audit['core_membership'],
            policy=b['policy'],policy_sha256=b['policy_sha256'],query=b['query'],pins=b['pins'],source_validation=b['source_validation']))
        rows_by_label[b['label']]=surface._verified_rows(b['proof'],rows,deadline_ns=deadline_ns)
        members_by_label[b['label']]=audit['core_triangle_indices']
        metrics.append(dict(label=b['label'],B2_rows_passes=1,B2_wall_ns=B2_ns,core_plan_ns=time.perf_counter_ns()-phase))
    phase=time.perf_counter_ns();task=dict(spec=common['spec'],task_sha256=common['task_sha256'],
        run_nonce=common['run_nonce'],condition_id=CONDITION)
    report,audit=view.produce(task,frames,max_candidates=4,deadline_ns=deadline_ns)
    producer_ns=time.perf_counter_ns()-phase;backend={}
    for b in bundles:
        label=b['label'];core=next(s for s in report['core_summary_by_frame'] if s['label']==label)
        global_summary=next(s for s in report['global_summary_by_frame'] if s['label']==label)
        summary=dict(triangles_total=core['facts']['core_triangle_count'],states=copy.deepcopy(core['facts']['core_states']),
            unknown_reasons=copy.deepcopy(core['facts']['core_unknown_reasons']),observation_state=core['facts']['core_status'],
            has_confirmed_mixed_witness=core['has_confirmed_mixed_witness'])
        backend[label]=_backend_frame(b,rows_by_label[label],members_by_label[label],summary,global_summary,
            [entry['selected_triangle'] for entry in report['candidate_witness_trajectories']])
    records=[]
    for name,value in [('REPORT.json',report),('AUDIT.json',audit),('EVIDENCE.json',audit['evidence_sidecar']),
        ('BACKEND.json',_backend(common,report,backend))]:records.append(save(out/name,value,deadline_ns=deadline_ns))
    need(sha(out/'EVIDENCE.json')==report['evidence_ref']['sha256'],'B_evidence_binding')
    need(sha(out/'REPORT.json')==audit['published_publication_sha256'],'B_report_binding')
    return dict(B2_rows_passes=2,source_inspect_requests=0,frames=metrics,producer_ns=producer_ns,storage=records,
        model_received=False,publication_scope='static_prepared_artifacts_not_model_transport_attestation')


def _prepare_C(common,bundles,out,deadline_ns):
    from verification import v21_trial_native as native
    frames={};backend={}
    for b in bundles:
        frames[b['label']]=native.prepare_native_frame(b['packet'],b['catalog'],b['policy'],
            deadline_ns=deadline_ns,thresholds=THRESHOLDS)
    pair=native.prepare_native_pair(frames,thresholds=THRESHOLDS,max_candidates=4,deadline_ns=deadline_ns)
    report=pair['report']
    for b in bundles:
        frame=frames[b['label']]
        values=[frame['facts'][i] for i in range(len(frame['facts']))]
        backend[b['label']]=_backend_frame(b,values,frame['members'],frame['report']['core_summary'],
            frame['report']['global_summary'],pair['candidate_triangle_indices'])
    records=[save(out/'REPORT.json',report,deadline_ns=deadline_ns),
        save(out/'BACKEND.json',_backend(common,report,backend),deadline_ns=deadline_ns)]
    reference=dict(schema='v21-independent-numeric-reference-v1',task_sha256=common['task_sha256'],
        run_nonce=common['run_nonce'],original_topology_sha256=common['original_topology_sha256'],frames=frames,
        provenance='complete independent SAT_QR_SVD over common externally qualified snapshots; never a model input')
    records.append(save(out.parent/'NATIVE_REFERENCE.json',reference,deadline_ns=deadline_ns))
    return dict(B2_rows_passes=0,production_B2_calls=0,source_inspect_requests=0,
        frames={label:frame['measurements'] for label,frame in frames.items()},
        pair=pair['measurements'],storage=records)


def _collect(args):
    begun=time.perf_counter_ns();task_deadline=begun+120_000_000_000
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    guard,manifest=helpers.bootstrap(args.core_root)
    from human_eye_plugin import small_skin_source_process as process
    from human_eye_plugin import deformation_task_view as view
    from human_eye_plugin.runtime_identity import runtime_identity
    identity=runtime_identity();need(identity['source_sha256']==PIN and identity['implementation_revision']==REVISION
        and len(manifest['files'])==129,'runtime_pin')
    # Verification modules stay in the workspace; production imports stay behind
    # the verified isolated source loader installed above.
    sys.path.insert(1,str(ROOT));actors=[];bundles=[];source_metrics=[];validations=[]
    current_operation={};original_validate=process.core.validate
    def counted_validate(*values,**kwargs):
        started=time.perf_counter_ns();event=dict(current_operation,started_ns=started,status='unknown')
        validations.append(event)
        try:
            result=original_validate(*values,**kwargs);event['status']='completed';return result
        finally:event['elapsed_ns']=time.perf_counter_ns()-started
    process.core.validate=counted_validate
    source_ok=False
    try:
        save(out/'RUNTIME_IDENTITY.json',identity,deadline_ns=task_deadline)
        binary_sha=sha(helpers.BINARY);check(task_deadline)
        for label,relative,expected,frame in helpers.SOURCES:
            folder=out/'common'/label;folder.mkdir(parents=True);scene=ROOT/relative
            check(task_deadline);need(sha(scene)==expected,'original_file_changed');source_start=time.perf_counter_ns()
            profile=dict(schema='small-skin-source-operator-profile-v1',blender_executable=str(helpers.BINARY),
                blender_sha256=binary_sha,scene_file=str(scene),scene_sha256=expected,mesh_name='Cylinder',rig_name='Armature',
                expected_frame=dict(number=frame,subframe=0.),unit_scale_m=1.,runtime_source_sha256=PIN)
            storage=[save(folder/'PROFILE.json',profile,deadline_ns=task_deadline)]
            started=time.perf_counter_ns();actor=process.SmallSkinSourceProcess((folder/'PROFILE.json').resolve());actors.append(actor)
            startup_ns=time.perf_counter_ns()-started;current_operation.update(label=label,operation='directory_inspect')
            started=time.perf_counter_ns();first=actor.inspect();directory_inspect_ns=time.perf_counter_ns()-started
            current_operation['operation']='describe_anchors';started=time.perf_counter_ns()
            catalog=actor.describe_anchors(first,deadline_ns=actor.deadline_ns);describe_ns=time.perf_counter_ns()-started
            children={bone['name'] for bone in catalog['graph'] if bone['parent'] is not None}
            choices=[a for a in catalog['anchors'] if a['bone_name'] in children and a['endpoint']=='head' and a['state']=='available']
            need(len(choices)==1,'public_unique_nonroot_head');chosen=choices[0]
            policy=dict(schema='surface-deformation-context-policy-v1',source_ref=catalog['source_ref'],
                catalog_sha256=catalog['catalog_sha256'],anchor_id=chosen['anchor_id'],required_core_half_extents_m=[.5]*3,
                primary_half_extents_m=[.5]*3,candidate_half_extents_m=[],max_surplus_members=0,min_saved_bytes=256,planning_budget_ms=250)
            storage.append(save(folder/'POLICY.json',policy,deadline_ns=min(task_deadline,actor.deadline_ns)))
            started=time.perf_counter_ns();actor.set_context_policy((folder/'POLICY.json').resolve(),sha(folder/'POLICY.json'))
            policy_bind_ns=time.perf_counter_ns()-started;check(task_deadline)
            current_operation['operation']='post_anchor_fact_inspect';started=time.perf_counter_ns();packet=actor.inspect()
            fact_inspect_ns=time.perf_counter_ns()-started
            need(packet['source_sha256']==first['source_sha256'] and packet['audit']==first['audit'],'fixed_source_changed')
            current_operation['operation']='explicit_external_full_validation';started=time.perf_counter_ns()
            proof=process.core.validate(packet,deadline_ns=actor.deadline_ns,expected_bindings=actor.bindings,expected_source=actor.source)
            validation_ns=time.perf_counter_ns()-started
            proof['source']=dict(proof['source'],source_sha256=packet['source_sha256'],source_schema=process.core.SCHEMA,
                **{key:getattr(actor.bindings,key) for key in ('profile_sha256','runtime_source_sha256','worker_sha256','module_sha256','math_sha256','binary_sha256')})
            validation=dict(schema=process.core.SCHEMA,method='external_binding_full_dependency_FK_and_LBS',
                max_replay_error=proof['max_replay_error'],replay_atol=process.core.POSITION_ATOL,
                animation_curves_checked=proof['animation_curves_checked'],not_coordinate_measurement_error=True)
            selection=dict(schema='surface-deformation-context-selection-v1',source_ref=catalog['source_ref'],
                catalog_sha256=catalog['catalog_sha256'],anchor_id=chosen['anchor_id'],policy_sha256=sha(folder/'POLICY.json'))
            current_operation['operation']='bind_context_selection';started=time.perf_counter_ns()
            query=actor.bind_context_selection(packet,selection,deadline_ns=actor.deadline_ns);query_bind_ns=time.perf_counter_ns()-started
            pins=actor._anchor_pins();deadline=min(task_deadline,actor.deadline_ns)
            for name,value in [('DIRECTORY_PACKET.json',first),('PACKET.json',packet),('PROOF.json',proof),('CATALOG.json',catalog),
                ('QUERY.json',query),('PINS.json',pins),('SOURCE_VALIDATION.json',validation)]:
                storage.append(save(folder/name,value,deadline_ns=deadline))
            started=time.perf_counter_ns();actor.verify_inputs();actor.close()
            need(actor.closed and actor.process.poll()==0,'worker_not_closed_exit0');actor.verify_inputs();check(deadline)
            close_ns=time.perf_counter_ns()-started
            bundles.append(dict(label=label,packet=packet,proof=proof,catalog=catalog,policy=policy,
                policy_sha256=sha(folder/'POLICY.json'),query=query,pins=pins,source_validation=validation,
                packet_file_sha256=sha(folder/'PACKET.json')))
            source_metrics.append(dict(label=label,source_ref=catalog['source_ref'],profile_sha256=sha(folder/'PROFILE.json'),
                started_ns=source_start,complete_source_ns=time.perf_counter_ns()-source_start,startup_ns=startup_ns,
                directory_inspect_ns=directory_inspect_ns,describe_anchors_ns=describe_ns,policy_bind_ns=policy_bind_ns,
                post_anchor_inspect_ns=fact_inspect_ns,explicit_external_validation_ns=validation_ns,
                context_query_bind_ns=query_bind_ns,verify_and_close_ns=close_ns,physical_inspect_requests=actor.sequence,
                logical_directory_reads=1,logical_fact_reads=1,production_B2_calls=0,storage=storage,
                worker=dict(pid=actor.process.pid,closed=actor.closed,exit_code=actor.process.poll(),
                    original_deadline_ns=actor.deadline_ns,closed_before_original_deadline=True),
                actual_source_file_sha256=sha(scene),original_source_file_sha256=expected))
        check(task_deadline);need(all(a.closed and a.process.poll()==0 for a in actors),'owned_workers')
        need(len({topology(b['proof']) for b in bundles})==1,'original_topology')
        need(all(sha(ROOT/rel)==expected for _,rel,expected,_ in helpers.SOURCES),'original_files_changed')
        guard.verify_loaded();check(task_deadline);source_ok=True
    except BaseException as exc:
        save(out/'ACQUISITION_FAILURE.json',dict(cycle_id=CYCLE,type=type(exc).__name__,reason=str(exc),
            elapsed_ns=time.perf_counter_ns()-begun,source_metrics=source_metrics,actual_validations=validations,
            physical_inspect_requests=sum(a.sequence for a in actors),no_model_consumption=True));raise
    finally:
        process.core.validate=original_validate
        cleanup=[]
        for actor in reversed(actors):
            try:
                if not actor.closed:actor.close()
            except BaseException as exc:cleanup.append(dict(pid=actor.process.pid,error=type(exc).__name__,reason=str(exc)))
        if not source_ok:save(out/'FAILED_CLEANUP.json',dict(errors=cleanup,
            workers=[dict(pid=a.process.pid,closed=a.closed,exit_code=a.process.poll()) for a in actors]))
    shared=dict(schema='v21-common-source-costs-v1',cycle_id=CYCLE,started_ns=begun,completed_ns=time.perf_counter_ns(),
        original_task_deadline_ns=task_deadline,original_task_and_worker_deadlines_preserved=True,
        physical_inspect_requests=sum(a.sequence for a in actors),logical_directory_reads=2,logical_fact_reads=2,
        production_B2_calls=0,complete_source_validation_attempts=len(validations),
        complete_source_validations=sum(v['status']=='completed' for v in validations),actual_validation_calls=validations,
        validation_instrumentation='transparent wrapper around unchanged complete external validator, restored before analysis',
        sources=source_metrics,all_owned_closed_exit0=True,original_files_unchanged=True,automatic_retries=0,
        cache_hits=0,geometry_setters=0,original_file_saved=False,paid_calls=0,peak_RSS_bytes=None,
        cost_scope='one common trusted acquisition prefix, not repeated or allocated as free per condition',
        timing_scope='inclusive actual spans; nested phases not additive; source storage records include serialization/fsync/readback')
    save(out/'SOURCE_COSTS.json',shared,deadline_ns=task_deadline)
    spec=dict(schema='surface-deformation-task-request-v1',question=question(),thresholds=copy.deepcopy(THRESHOLDS),sources={})
    for b in bundles:
        spec['sources'][b['label']]=dict(source_ref=copy.deepcopy(b['catalog']['source_ref']),
            catalog_sha256=b['catalog']['catalog_sha256'],anchor_id=b['policy']['anchor_id'],
            core_half_extents_m=[.5]*3,profile_sha256=b['pins']['profile_sha256'])
    common=dict(schema='v21-post-anchor-common-v1',cycle_id=CYCLE,spec=spec,task_sha256=view.task_digest(spec),
        run_nonce=secrets.token_hex(16),sources=copy.deepcopy(spec['sources']),source_runtime_sha256=PIN,
        implementation_revision=REVISION,source_runtime_count=129,original_topology_sha256=topology(bundles[0]['proof']),
        common_acquisition_ref=dict(path='SOURCE_COSTS.json',sha256=sha(out/'SOURCE_COSTS.json')),
        original_topology_digest_model='compact_UTF8_JSON_reference_original_vertices_and_original_triangles',
        common_prefix='directory_selection_completed_public_unique_nonroot_HEAD_world_core_halfwidth0.5m',
        source_scope='two_current_saved_static_frames_of_one_familiar_case_not_full_animation_or_heldout_generalization',
        source_observations={b['label']:dict(source_observation_sha256=b['proof']['source_sha256'],
            raw_packet_sha256=b['packet_file_sha256']) for b in bundles},model_received=False)
    save(out/'COMMON.json',common,deadline_ns=task_deadline)
    shared['complete_common_acquisition_wall_ns']=time.perf_counter_ns()-begun
    return common,bundles,guard,shared,begun


def prepare(args):
    common,bundles,guard,shared,begun=_collect(args);out=args.output.resolve()
    analysis_start=time.perf_counter_ns();analysis_deadline=analysis_start+120_000_000_000;metrics={}
    try:
        for label,function in [('A',_prepare_A),('B',_prepare_B),('C',_prepare_C)]:
            start=time.perf_counter_ns();tracemalloc.start()
            try:
                metric=function(common,bundles,out/label,analysis_deadline)
                traced_current,traced_peak=tracemalloc.get_traced_memory()
            finally:tracemalloc.stop()
            check(analysis_deadline)
            metric.update(started_ns=start,completed_ns=time.perf_counter_ns(),
                complete_prepare_wall_ns=time.perf_counter_ns()-start,python_traced_current_bytes=traced_current,
                python_traced_peak_bytes=traced_peak,peak_RSS_bytes=None,model_received=False)
            metrics[label]=metric
        guard.verify_loaded();check(analysis_deadline)
        result=dict(schema='v21-post-anchor-prepare-costs-v1',cycle_id=CYCLE,passed=True,conditions=metrics,
            source_runtime_sha256=PIN,source_runtime_count=129,common_acquisition_ref=common['common_acquisition_ref'],
            common_acquisition_complete_wall_ns=shared['complete_common_acquisition_wall_ns'],
            analysis_started_ns=analysis_start,analysis_deadline_ns=analysis_deadline,analysis_completed_ns=time.perf_counter_ns(),
            complete_prepare_wall_ns=time.perf_counter_ns()-begun,production_B2_passes=dict(A=2,B=2,C=0),
            complete_prepare_wall_scope='entry through final cost receipt construction; its own final persistence excluded; caller command wall includes it',
            common_prefix_counted_once=True,worker_deadlines_not_reopened=True,no_model_consumption=True,
            actual_model_tokens=None,cost_USD=None,net_benefit=None,paid_calls=0,
            timing_scope='measured separate common acquisition and static report preparation; cached reports precede consumer experiment, no synthetic cold-start-to-answer timing',
            resource_scope='tracemalloc measured Python allocations per condition, not process RSS or whole-collector peak')
        save(out/'PREPARE_COSTS.json',result,deadline_ns=analysis_deadline);check(analysis_deadline)
        print(json.dumps(dict(passed=True,output=str(out),task_sha256=common['task_sha256'],run_nonce=common['run_nonce'],
            physical_inspect_requests=shared['physical_inspect_requests'],B2_passes=result['production_B2_passes'],
            complete_prepare_wall_ns=time.perf_counter_ns()-begun),ensure_ascii=True))
    except BaseException as exc:
        save(out/'PREPARE_FAILURE.json',dict(cycle_id=CYCLE,type=type(exc).__name__,reason=str(exc),
            metrics=metrics,elapsed_ns=time.perf_counter_ns()-begun,no_model_consumption=True));raise


def self_check():
    """Public authored unit triangle; no Blender, real asset or model call."""
    sys.path.insert(0,str(ROOT))
    from verification.test_small_skin_source import packet as authored,binding,rehash
    from human_eye_plugin import small_skin_source as core,deformation_anchors as anchors,deformation_context as context
    from human_eye_plugin import deformation_task_view as view
    deadline=time.perf_counter_ns()+15_000_000_000;bundles=[]
    for label,number in [('authored_one',1),('authored_two',2)]:
        packet=authored();packet['inputs']['frame']['number']=number;packet['identity']['scene_sha256']=str(number)*64;rehash(packet)
        external=binding(packet);proof=core.validate(packet,deadline_ns=deadline,expected_bindings=external)
        proof['source'].update(source_sha256=packet['source_sha256'],source_schema=core.SCHEMA,
            **{key:getattr(external,key) for key in ('profile_sha256','runtime_source_sha256','worker_sha256','module_sha256','math_sha256','binary_sha256')})
        pins={key:getattr(external,key) for key in core.PIN_FIELDS};catalog=anchors.catalog(proof,pins=pins,deadline_ns=deadline)
        policy=dict(schema='surface-deformation-context-policy-v1',source_ref=catalog['source_ref'],
            catalog_sha256=catalog['catalog_sha256'],anchor_id=catalog['anchors'][0]['anchor_id'],
            required_core_half_extents_m=[.5]*3,primary_half_extents_m=[.5]*3,candidate_half_extents_m=[],
            max_surplus_members=0,min_saved_bytes=256,planning_budget_ms=250)
        policy_sha=hashlib.sha256(blob(policy)).hexdigest()
        selection=dict(schema='surface-deformation-context-selection-v1',source_ref=catalog['source_ref'],
            catalog_sha256=catalog['catalog_sha256'],anchor_id=policy['anchor_id'],policy_sha256=policy_sha)
        query=context.bind_selection(proof,selection,policy=policy,policy_sha256=policy_sha,pins=pins,deadline_ns=deadline)
        bundles.append(dict(label=label,packet=packet,proof=proof,catalog=catalog,policy=policy,policy_sha256=policy_sha,
            query=query,pins=pins,packet_file_sha256=hashlib.sha256(blob(packet)).hexdigest(),
            source_validation=dict(schema=core.SCHEMA,method='external_binding_full_dependency_FK_and_LBS',
                max_replay_error=proof['max_replay_error'],replay_atol=core.POSITION_ATOL,
                animation_curves_checked=proof['animation_curves_checked'],not_coordinate_measurement_error=True)))
    spec=dict(schema='surface-deformation-task-request-v1',question='Public authored same-face fixture only',
        thresholds=copy.deepcopy(THRESHOLDS),sources={b['label']:dict(source_ref=b['catalog']['source_ref'],
            catalog_sha256=b['catalog']['catalog_sha256'],anchor_id=b['policy']['anchor_id'],
            core_half_extents_m=[.5]*3,profile_sha256=b['pins']['profile_sha256']) for b in bundles})
    common=dict(spec=spec,task_sha256=view.task_digest(spec),run_nonce='c'*32,original_topology_sha256=topology(bundles[0]['proof']))
    with tempfile.TemporaryDirectory(prefix='v21-trial-acquire-authored-') as folder:
        out=Path(folder);measurements={}
        for label,function in [('A',_prepare_A),('B',_prepare_B),('C',_prepare_C)]:
            measurements[label]=function(common,bundles,out/label,deadline)
            report=load(out/label/'REPORT.json');backend=load(out/label/'BACKEND.json')
            need(backend['report_sha256']==sha(out/label/'REPORT.json'),'selfcheck_report_hash')
            need(set(backend['frames'])==set(spec['sources']),'selfcheck_labels')
            need(all(f['initial_row_indices']==[0] for f in backend['frames'].values()),'selfcheck_initial_rows')
            need(all(f['original_topology_sha256']==common['original_topology_sha256'] for f in backend['frames'].values()),'selfcheck_topology')
            if label=='A':
                for name,f in backend['frames'].items():
                    need('has_confirmed_mixed_witness' not in f['initial_summary'],'selfcheck_A_no_new_answer')
                    need('core_confirmation' not in f['initial_summary'],'selfcheck_A_no_fabricated_confirmation')
                    need(f['initial_summary']['core_extrema']['max_principal_stretch']==
                        report['frames'][name]['region_query']['metric_extrema']['max_principal_stretch']['value'],'selfcheck_A_extrema')
            else:
                for name,f in backend['frames'].items():
                    raw=next(row for row in report['core_summary_by_frame'] if row['label']==name)
                    need(f['initial_summary']['core_confirmation'] is raw['has_confirmed_mixed_witness'],
                        'selfcheck_core_confirmation_mapping')
        need([measurements[label]['B2_rows_passes'] for label in ('A','B','C')]==[2,2,0],'selfcheck_B2')
        need(load(out/'NATIVE_REFERENCE.json')['original_topology_sha256']==common['original_topology_sha256'],'selfcheck_reference')
        try:save(out/'EXPIRED.json',{},deadline_ns=time.perf_counter_ns()-1)
        except ValueError:pass
        else:raise ValueError('selfcheck expired save accepted')
        need(not (out/'EXPIRED.json').exists(),'selfcheck_expired_not_written')
    print(json.dumps(dict(passed=True,scope='public authored static unit triangle only',real_source_reads=0,
        model_calls=0,B2_passes=dict(A=2,B=2,C=0),A_no_fabricated_confirmation=True)))


def main():
    parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare-runtime',type=Path);mode.add_argument('--prepare',action='store_true')
    mode.add_argument('--self-check',action='store_true')
    parser.add_argument('--core-root',type=Path);parser.add_argument('--output',type=Path);args=parser.parse_args()
    if args.prepare_runtime:
        helpers.prepare_runtime(args.prepare_runtime);return
    if args.self_check:self_check();return
    need(args.core_root is not None and args.output is not None,'prepare_paths');prepare(args)


if __name__=='__main__':main()
