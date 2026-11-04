"""Protocol-only real reader -> qualified witness view -> persisted delivery QA.

The public question is frozen from cycle006; no truth/acceptable-witness file is
read. Uses independent owned Blender sources, never the shared GUI. Consumer
delivery here is a deterministic protocol driver, not an LLM/model receipt.
"""
from __future__ import annotations
import argparse,copy,hashlib,importlib.util,json,secrets,sys,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('_closure_preflight_helpers',ROOT/'verification/run_deformation_closure_preflight.py')
helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)
SOURCES=helpers.SOURCES;BINARY=helpers.BINARY
save=helpers.save;sha=helpers.sha;blob=helpers.blob


def frozen_question():
    path=ROOT/'verification/fixes/20261103_review_cycle006/PREREGISTERED.json'
    if sha(path)!='50df877c584042586887f7a2906a948fc6aa6ca8e3583b4af5d25e8e7acc1534':
        raise ValueError('public_registration_changed')
    question=json.loads(path.read_bytes())['question']
    if not isinstance(question,str) or not question:raise ValueError('public_question_missing')
    return question


def run(args):
    begin=time.perf_counter_ns();deadline=begin+120_000_000_000
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    guard,manifest=helpers.bootstrap(args.core_root)
    from human_eye_plugin.runtime_identity import runtime_identity
    from human_eye_plugin.deformation_reader import QualifiedReader
    from human_eye_plugin.deformation_delivery import DeliverySession
    from human_eye_plugin.deformation_task_view import task_digest
    identity=runtime_identity();bootstrap_and_imports_ns=time.perf_counter_ns()-begin
    run_nonce=secrets.token_hex(16);condition_id='V21-REFACTOR-002-protocol-QA';reader=None;session=None
    save(output/'CONTRACT.json',dict(schema='deformation-delivery-qa-contract-v1',cycle_id='V21-REFACTOR-002',
        runtime_source_sha256=identity['source_sha256'],runtime_source_count=len(manifest['files']),
        runtime_manifest_sha256=sha(args.core_root/'QA_SOURCE_MANIFEST.json'),
        run_nonce=run_nonce,condition_id=condition_id,task_started_ns=begin,task_deadline_ns=deadline,
        mode='real_owned_source_protocol_driver_no_model',source_files=[dict(label=label,path=str(ROOT/path),sha256=digest,frame=frame)
            for label,path,digest,frame in SOURCES],question=frozen_question(),thresholds=dict(high=1.1,low=.9),
        directory_selection='public unique nonroot HEAD; operator world box halfwidth0.5m',
        logical_facts_are_source_reads_not_triangle_count=True,original_assets_read_only=True,
        no_model_consumption=True,no_paid_calls=True))
    save(output/'RUNTIME_IDENTITY.json',identity)
    try:
        profiles={};preparation=time.perf_counter_ns()
        for label,relative,expected,frame in SOURCES:
            scene=ROOT/relative
            if sha(scene)!=expected:raise ValueError('original_source_changed')
            profile=dict(schema='small-skin-source-operator-profile-v1',blender_executable=str(BINARY),
                blender_sha256=sha(BINARY),scene_file=str(scene),scene_sha256=expected,mesh_name='Cylinder',rig_name='Armature',
                expected_frame=dict(number=frame,subframe=0.),unit_scale_m=1.,runtime_source_sha256=identity['source_sha256'])
            path=output/(label+'_PROFILE.json');save(path,profile);profiles[label]=path
        profile_preparation_ns=time.perf_counter_ns()-preparation
        reader_start=time.perf_counter_ns()
        reader=QualifiedReader(profiles,workspace=output/'reader',task_deadline_ns=deadline)
        for label,catalog in reader.catalogs.items():
            children={bone['name'] for bone in catalog['graph'] if bone['parent'] is not None}
            choices=[anchor for anchor in catalog['anchors'] if anchor['bone_name'] in children
                and anchor['endpoint']=='head' and anchor['state']=='available']
            if len(choices)!=1:raise ValueError('public_nonroot_head_not_unique')
            reader.bind_selection(label,choices[0]['anchor_id'],[.5]*3,selection_origin='public_deterministic_condition')
        directory_and_selection_ns=time.perf_counter_ns()-reader_start
        task_spec=dict(schema='surface-deformation-task-request-v1',question=frozen_question(),
            thresholds=dict(high=1.1,low=.9),sources=copy.deepcopy(reader.source_specs))
        save(output/'TASK_SPEC.json',task_spec);save(output/'DIRECTORY_RECEIPTS.json',reader.directory_receipts)
        session=DeliverySession(task_spec,run_nonce=run_nonce,condition_id=condition_id,deadline_ns=deadline,
            store=output/'delivery',reader=reader,prior_usage=dict(directories=2,facts=0,native_supplements=0))
        started=time.perf_counter_ns();published=session.request('source-pair-facts-1')
        publication_request_ns=time.perf_counter_ns()-started
        if published.get('status')!='published' or published.get('model_received') is not False:
            raise ValueError('unexpected_publication_result')
        reference=published['reference'];view=published['view']
        if view['task_binding']['task_sha256']!=task_digest(task_spec):raise ValueError('task_sha_mismatch')
        if len(view['candidate_witness_trajectories'])>4:raise ValueError('candidate_budget')
        # A published reference is used, never an arbitrary file path. Every
        # candidate is fetched from both source labels through the adapter.
        resolves=[];started=time.perf_counter_ns()
        for trajectory in view['candidate_witness_trajectories']:
            face=trajectory['selected_triangle']
            for label in sorted(task_spec['sources']):
                pointer='/frames/'+label.replace('~','~0').replace('/','~1')+'/rows/'+str(face)
                reply=session.resolve(reference,pointer)
                source_row=reply['value'];public_row=next(row for row in trajectory['frames'] if row['label']==label)
                if source_row['triangle']!=face:raise ValueError('resolved_original_triangle_mismatch')
                if any(source_row[key]!=public_row[key] for key in ('state','reason','principal_stretches','area_ratio')):
                    raise ValueError('resolved_row_fact_mismatch')
                resolves.append(dict(label=label,triangle=face,pointer=pointer,reply=reply))
        resolve_ns=time.perf_counter_ns()-started
        # Refusal is exercised on the actual published-store path, not a mock.
        wrong=copy.deepcopy(reference);wrong['run_nonce']='0'*32 if run_nonce!='0'*32 else '1'*32
        refused=None
        try:session.resolve(wrong,'/frames')
        except ValueError as exc:
            refused=str(exc)
            if refused!='deformation_delivery_reference_binding':raise
        if refused is None:raise ValueError('cross_run_reference_not_rejected')
        started=time.perf_counter_ns();delivered=session.deliver(reference,'protocol-delivery-1');delivery_ns=time.perf_counter_ns()-started
        if delivered.get('model_received') is not False:raise ValueError('model_receipt_fabricated')
        costs=reader.snapshot_costs()
        if costs['physical_inspect_requests']!=4 or costs['directory_inspect_requests']!=2 or costs['fact_inspect_requests']!=2:
            raise ValueError('physical_accounting_mismatch')
        if costs['B2_rows_completed']!=2:raise ValueError('B2_accounting_mismatch')
        if not all(actor.closed and actor.process.poll()==0 for actor in reader.actors.values()):raise ValueError('owned_process_not_closed')
        if not all(sha(ROOT/relative)==expected for _,relative,expected,_ in SOURCES):raise ValueError('source_changed_at_completion')
        guard.verify_loaded()
        save(output/'PUBLICATION_REPLY.json',published);save(output/'RESOLVED_FACTS.json',resolves)
        save(output/'DELIVERY_REPLY.json',delivered);save(output/'REAL_REFUSAL.json',dict(expected='deformation_delivery_reference_binding',actual=refused))
        selected={row['selected_triangle'] for row in view['candidate_witness_trajectories']}
        required=[]
        for summary in view['core_summary_by_frame']:
            if summary['has_confirmed_mixed_witness'] is True:
                face=view['task_witness_selection']['mandatory_mixed_by_label'][summary['label']]
                if face not in selected:raise ValueError('confirmed_core_witness_not_delivered')
                required.append(dict(label=summary['label'],triangle=face))
        result=dict(schema='deformation-delivery-fresh-qa-v1',cycle_id='V21-REFACTOR-002',passed=True,
            mode='real_owned_source_protocol_driver',fresh=True,frozen_snapshot_source_data=False,
            source_count=2,physical_inspect_requests=costs['physical_inspect_requests'],logical_directories=2,
            logical_fact_reads=2,directory_and_selection_ns=directory_and_selection_ns,profile_preparation_ns=profile_preparation_ns,
            publication_request_ns=publication_request_ns,resolver_ns=resolve_ns,protocol_delivery_ns=delivery_ns,
            bootstrap_and_imports_ns=bootstrap_and_imports_ns,
            complete_parent_wall_ns=time.perf_counter_ns()-begin,deadline_ns=deadline,
            original_task_deadline_preserved=True,all_original_files_unchanged=True,all_owned_closed=True,
            source_guard_verified=True,runtime_source_sha256=identity['source_sha256'],runtime_source_count=len(manifest['files']),
            published=True,protocol_delivered=delivered.get('status')=='delivered',model_received=False,
            view_bytes=len(blob(view)),reader_costs=costs,publication_usage=published['usage'],
            resolved_source_rows=len(resolves),cross_run_actual_entry_refused=refused,
            required_confirmed_witnesses_delivered=required,
            global_summary_by_frame=view['global_summary_by_frame'],
            model_tokens=None,model_stages=None,cost_USD=None,net_benefit=None,paid_calls=0,
            stage_boundary='post-anchor explicit adapter; legacy Control remains offline and unchanged',
            timing_semantics='inclusive wall spans, do not add nested publication/source stages')
        if time.perf_counter_ns()>=deadline:raise ValueError('original_task_deadline_before_final_publication')
        save(output/'RESULT.json',result)
        if time.perf_counter_ns()>=deadline:raise ValueError('original_task_deadline_after_final_publication')
        print(json.dumps({k:v for k,v in result.items() if k not in ('reader_costs',)},ensure_ascii=True))
    except BaseException as exc:
        if reader is not None:
            reader.close()
        # A late final write is retained as evidence, never a standalone
        # successful RESULT. This does not undo already committed delivery.
        if (output/'RESULT.json').exists():
            (output/'RESULT.json').rename(output/'UNACCEPTED_RESULT.json')
        save(output/'FAILURE.json',dict(type=type(exc).__name__,reason=str(exc),
            reader_costs=None if reader is None else reader.snapshot_costs(),
            original_task_deadline_ns=deadline,elapsed_ns=time.perf_counter_ns()-begin,no_model_consumption=True,no_auto_retry=True))
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--prepare-runtime',type=Path)
    parser.add_argument('--core-root',type=Path);parser.add_argument('--output',type=Path);args=parser.parse_args()
    if args.prepare_runtime:helpers.prepare_runtime(args.prepare_runtime);return
    if args.core_root is None or args.output is None:parser.error('--core-root and --output are required')
    run(args)
if __name__=='__main__':main()
