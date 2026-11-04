"""QA-only fresh dual-static source connection for the closure candidate.

Uses the unchanged owned SmallSkinSourceProcess and source/B2/core functions.
No independent/native oracle, private witness list, model, edit, frame setter,
or original-file save is involved. Production Control is not adapted by this QA.
"""
from __future__ import annotations
import argparse, ast, copy, hashlib, importlib.util, json, os, shutil, sys, time, tracemalloc
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCES=(
 ('author_frame1','verification/fixes/20261102_m4_task_qualification/external_assets/RiggedSimple/derived_test_snapshot.blend',
  '9e6978ff0b3894a4abce5dbfd2df08f949ebe980e5a4188a078362cfe2622499',1),
 ('author_frame25','verification/fixes/20261102_m4_b3_source_qualification/heldout_frame25_r1/fixture.blend',
  '348f8356581519549eff857fe95c276cef4c25c2abd773655741701b972ac386',25))
BINARY=Path('D:/Tools/blender5.2/blender.exe')
ROOT_MODULES=('human_eye_hook.py','human_eye_foveated_renderer.py','native_3d_spatial_scratchpad.py',
 'module_2_low_token_mcp_scene_bridge.py','module_3_1_mcp_protocol_ipc_engine.py',
 'module_3_2_vlm_grounding_closed_loop_agent.py','module_3_3_closed_loop_control_engine.py')

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def blob(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')+b'\n'
def save(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('xb') as f:f.write(blob(value));f.flush();os.fsync(f.fileno())
def load(path):return json.loads(Path(path).read_bytes())
def now():return datetime.now(timezone.utc).isoformat()

def runtime_paths(root):
 paths=[root/name for name in ROOT_MODULES]
 for package in ('human_eye_plugin','human_eye_module1_operators'):paths.extend((root/package).glob('*.py'))
 return sorted(paths,key=lambda p:p.relative_to(root).as_posix())

def prepare_runtime(destination):
 destination=destination.resolve()
 if not destination.is_absolute() or destination.exists():raise ValueError('new absolute QA runtime directory required')
 destination.mkdir(parents=True)
 manifest=[]
 for path in runtime_paths(ROOT):
  target=destination/path.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
  if sha(path)!=sha(target):raise ValueError('runtime_copy_changed')
  manifest.append({'path':path.relative_to(ROOT).as_posix(),'sha256':sha(path)})
 shutil.copyfile(ROOT/'pyproject.toml',destination/'pyproject.toml')
 for row in manifest:
  if sha(ROOT/row['path'])!=row['sha256'] or sha(destination/row['path'])!=row['sha256']:
   raise ValueError('source_changed_during_runtime_copy')
 save(destination/'QA_SOURCE_MANIFEST.json',dict(schema='closure-qa-source-manifest-v1',created_utc=now(),
  source_root=str(ROOT),runtime_root=str(destination),files=manifest,pyproject_sha256=sha(destination/'pyproject.toml')))
 print(json.dumps(dict(prepared=str(destination),files=len(manifest))))

def bootstrap(root):
 root=root.resolve();manifest=load(root/'QA_SOURCE_MANIFEST.json')
 if manifest['runtime_root']!=str(root):raise ValueError('runtime_root_changed')
 for row in manifest['files']:
  if sha(root/row['path'])!=row['sha256']:raise ValueError('snapshot_changed')
 if [p.relative_to(root).as_posix() for p in runtime_paths(root)]!=[r['path'] for r in manifest['files']]:
  raise ValueError('snapshot_membership_changed')
 path=root/'human_eye_plugin/verified_source_loader.py'
 spec=importlib.util.spec_from_file_location('_closure_qa_source_loader',path);module=importlib.util.module_from_spec(spec)
 sys.modules[spec.name]=module;spec.loader.exec_module(module)
 guard=module.install(root,manifest['files'],bootstrap_module=module)
 sys.path.insert(0,str(root));return guard,manifest

def field_bytes(value):
 total=len(blob(value))
 pieces={k:len(blob(k))-1+1+len(blob(v))-1 for k,v in value.items()}
 framing=2+max(0,len(value)-1)+1
 assert sum(pieces.values())+framing==total
 return {'serialized_bytes':total,'top_level_key_colon_value_bytes':pieces,'object_comma_and_terminal_LF_bytes':framing,
  'accounted_bytes':sum(pieces.values())+framing,'semantics':'disjoint canonical ASCII key/colon/value pieces plus object/commas/LF; sums exactly to publication bytes'}

def row_field_bytes(rows):
 result={}
 for row in rows:
  for key,value in row.items():result[key]=result.get(key,0)+len(blob(key))-1+1+len(blob(value))-1
 return dict(rows=len(rows),per_field_key_colon_value_bytes=result,
  coordinates_not_in_geometry_state_fields=True,reference_geometry_values=sorted({row['reference_geometry'] for row in rows}),
  current_geometry_values=sorted({row['current_geometry'] for row in rows}),
  semantics='sums each field key/colon/value over all complete B2 rows; row/list framing not included')

def run(args):
 output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
 guard,manifest=bootstrap(args.core_root)
 from human_eye_plugin import small_skin_source_process as process
 from human_eye_plugin import deformation_anchors as anchors,deformation_context as context
 from human_eye_plugin import deformation_core_facts as corefacts,surface_deformation as surface
 from human_eye_plugin.runtime_identity import runtime_identity,check_source_drift
 identity=runtime_identity();assert check_source_drift()['compatible']
 contract=dict(schema='deformation-closure-fresh-qa-contract-v1',created_utc=now(),
  source_files=[dict(label=label,path=str(ROOT/rel),sha256=digest,saved_frame=frame) for label,rel,digest,frame in SOURCES],
  baseline_commit='56ed427687976521524ca29d5d408c184f9032e6',
  task='existing public unique nonroot bone HEAD, world closed box halfwidth0.5m; mixed same-face >=1.1 and <=0.9',
  candidate_rule='normal public core extrema witness IDs union; stable numeric sort capped4; never private truth',
  snapshots_per_source=2,ordinary_actor_analyze_calls_per_source=1,internal_qualified_core_pipeline_calls_per_source=1,
  no_model_consumption=True,no_Control_adapter=True,source_runtime_sha256=identity['source_sha256'],
  source_manifest_sha256=sha(args.core_root/'QA_SOURCE_MANIFEST.json'))
 save(output/'CONTRACT.json',contract);save(output/'RUNTIME_IDENTITY.json',identity)
 actors=[];bundles=[];source_metrics=[];began=time.perf_counter_ns();finished=False
 try:
  for label,relative,expected,file_frame in SOURCES:
   folder=output/label;folder.mkdir();scene=ROOT/relative
   assert sha(scene)==expected,'original source bytes changed'
   profile=dict(schema='small-skin-source-operator-profile-v1',blender_executable=str(BINARY),blender_sha256=sha(BINARY),
    scene_file=str(scene),scene_sha256=expected,mesh_name='Cylinder',rig_name='Armature',
    expected_frame=dict(number=file_frame,subframe=0.),unit_scale_m=1.,runtime_source_sha256=identity['source_sha256'])
   save(folder/'PROFILE.json',profile)
   source_start=time.perf_counter_ns();actor=process.SmallSkinSourceProcess(folder/'PROFILE.json');actors.append(actor)
   first=actor.inspect();second=actor.inspect()
   assert first['source_sha256']==second['source_sha256'] and first['audit']==second['audit']
   catalog=actor.describe_anchors(second,deadline_ns=actor.deadline_ns)
   children={v['name'] for v in catalog['graph'] if v['parent'] is not None}
   choices=[a for a in catalog['anchors'] if a['bone_name'] in children and a['endpoint']=='head' and a['state']=='available']
   assert len(choices)==1,'public unique nonroot HEAD condition failed'
   chosen=choices[0]
   policy=dict(schema='surface-deformation-context-policy-v1',source_ref=catalog['source_ref'],catalog_sha256=catalog['catalog_sha256'],
    anchor_id=chosen['anchor_id'],required_core_half_extents_m=[.5]*3,primary_half_extents_m=[.5]*3,
    candidate_half_extents_m=[],max_surplus_members=0,min_saved_bytes=256,planning_budget_ms=250)
   save(folder/'POLICY.json',policy);actor.set_context_policy(folder/'POLICY.json',sha(folder/'POLICY.json'))
   selection=dict(schema='surface-deformation-context-selection-v1',source_ref=catalog['source_ref'],
    catalog_sha256=catalog['catalog_sha256'],anchor_id=chosen['anchor_id'],policy_sha256=sha(folder/'POLICY.json'))
   query=actor.bind_context_selection(second,selection,deadline_ns=actor.deadline_ns)
   # The same independent complete consumer as actor.analyze, with the actual
   # operator/handshake bindings; no packet self-description grants admission.
   started=time.perf_counter_ns()
   proof=process.core.validate(second,deadline_ns=actor.deadline_ns,
    expected_bindings=actor.bindings,expected_source=actor.source)
   validation_ns=time.perf_counter_ns()-started
   proof['source']=dict(proof['source'],source_sha256=second['source_sha256'],source_schema=process.core.SCHEMA,
    **{key:getattr(actor.bindings,key) for key in ('profile_sha256','runtime_source_sha256','worker_sha256','module_sha256','math_sha256','binary_sha256')})
   validation=dict(schema=process.core.SCHEMA,method='external_binding_full_dependency_FK_and_LBS',
    max_replay_error=proof['max_replay_error'],replay_atol=process.core.POSITION_ATOL,
    animation_curves_checked=proof['animation_curves_checked'],not_coordinate_measurement_error=True)
   pins=actor._anchor_pins();started=time.perf_counter_ns()
   rows=surface._geometry_rows(proof,deadline_ns=actor.deadline_ns)
   B2_ns=time.perf_counter_ns()-started;started=time.perf_counter_ns()
   core_report,core_audit=corefacts.plan(proof,query,policy=policy,policy_sha256=sha(folder/'POLICY.json'),
    pins=pins,rows=rows,source_validation=validation,deadline_ns=actor.deadline_ns)
   core_plan_ns=time.perf_counter_ns()-started
   anchor_selection=dict(schema='surface-deformation-anchor-selection-v1',source_ref=catalog['source_ref'],
    catalog_sha256=catalog['catalog_sha256'],anchor_id=chosen['anchor_id'],half_extents_m=[.5]*3)
   anchor_query=actor.bind_anchor_selection(second,anchor_selection,deadline_ns=actor.deadline_ns)
   baseline_start=time.perf_counter_ns();ordinary=actor.analyze(second,deadline_ns=actor.deadline_ns,anchor_query=anchor_query)
   baseline_ns=time.perf_counter_ns()-baseline_start
   values=surface._verified_rows(proof,rows,deadline_ns=actor.deadline_ns)
   bundle=dict(label=label,proof=proof,rows=rows,membership=core_audit['core_membership'],core_report=core_report,
    core_audit=core_audit,catalog=catalog,policy=policy,policy_sha256=sha(folder/'POLICY.json'),query=query,pins=pins,
    source_validation=core_report['source_validation'])
   bundles.append(bundle)
   for name,value in [('SNAPSHOTS.json',dict(first=first,second=second,capabilities=actor.capabilities)),
       ('CATALOG.json',catalog),('SELECTION.json',selection),('BOUND_QUERY.json',query),('QUALIFIED_PROOF.json',proof),
       ('FULL_BOUND_ROWS.json',values),('CORE_REPORT.json',core_report),('CORE_AUDIT.json',core_audit),('ORDINARY_REPORT.json',ordinary)]:
    process.r.check_time(actor.deadline_ns);save(folder/name,value);process.r.check_time(actor.deadline_ns)
   source_metrics.append(dict(label=label,actor_original_deadline_ns=actor.deadline_ns,physical_inspect_requests=actor.sequence,
    actor_analyze_calls=1,internal_qualified_core_pipeline_calls=1,B2_rows_passes=2,
    explicit_complete_source_validation_ns=validation_ns,core_pipeline_B2_ns=B2_ns,core_plan_wall_ns=core_plan_ns,
    spans_are_inclusive_and_not_additive=True,ordinary_analyze_wall_ns=baseline_ns,
    through_all_fact_publication_ns=time.perf_counter_ns()-source_start,
    ordinary_fields=field_bytes(ordinary),core_fields=field_bytes(core_report),
    complete_B2_row_field_breakdown=row_field_bytes(values),
    reference_geometry_and_current_geometry_values='state strings, retained in complete bound rows sidecar; no coordinate matrices',
    geometry_setters=0,original_file_saved=False))
  # Parent owns the versioned product API; this function is filled once agreed.
  view,audit=closure_projection(bundles,actors,output)
  for actor in actors:actor.verify_inputs()
  for actor in reversed(actors):actor.close()
  for actor in actors:process.r.check_time(actor.deadline_ns)
  assert all(actor.closed and actor.process.poll()==0 for actor in actors)
  assert all(sha(ROOT/relative)==expected for _,relative,expected,_ in SOURCES)
  guard.verify_loaded();save(output/'MODEL_VIEW.json',view);save(output/'PROJECTION_AUDIT.json',audit)
  process.r.check_time(min(actor.deadline_ns for actor in actors))
  result=dict(schema='deformation-closure-fresh-qa-result-v1',passed=True,refreshed_sources=True,
   frozen_data_only=False,source_count=2,physical_inspect_requests=sum(actor.sequence for actor in actors),
   product_actor_analyze_calls=2,internal_qualified_core_pipeline_calls=2,core_B2_rows_passes=2,ordinary_comparison_B2_rows_passes=2,
   no_model_consumption=True,model_tokens=None,model_rounds=None,USD=None,paid_calls=0,
   source_metrics=source_metrics,view_fields=field_bytes(view),projection_audit_fields={k:v for k,v in audit.items() if k!='evidence_sidecar'},
   complete_parent_wall_ns=time.perf_counter_ns()-began,
   all_owned_processes_closed=True,all_original_files_unchanged=True,
   original_deadline_preserved=True,source_guard_verified=True,
   implementation_boundary='normal owned collector + complete external-bound independent source consumer + existing product B2/core functions; no formal Control prefetch/product adapter',
   source_runtime_sha256=identity['source_sha256'],runtime_manifest_sha256=sha(args.core_root/'QA_SOURCE_MANIFEST.json'))
  save(output/'RESULT.json',result);finished=True
  print(json.dumps({k:v for k,v in result.items() if k not in ('source_metrics','projection_audit_fields')},ensure_ascii=True))
 except BaseException as exc:
  save(output/'FAILURE.json',dict(schema='deformation-closure-fresh-qa-failure-v1',type=type(exc).__name__,reason=str(exc),
   source_metrics=source_metrics,physical_inspect_requests=sum(a.sequence for a in actors),
   elapsed_ns=time.perf_counter_ns()-began,no_model_consumption=True,paid_calls=0))
  raise
 finally:
  for actor in reversed(actors):
   if not actor.closed:actor.close()
  if not finished:save(output/'FAILED_CLEANUP.json',dict(all_owned_closed=all(a.closed and a.process.poll() is not None for a in actors),
   original_source_files_unchanged=all(sha(ROOT/relative)==expected for _,relative,expected,_ in SOURCES)))

def closure_projection(bundles,actors,output):
 from human_eye_plugin import deformation_closure as closure
 task=dict(task_sha256=hashlib.sha256(blob(dict(public_question='same original triangle across saved static frames',
  threshold_high=1.1,threshold_low=.9,sources={b['label']:b['policy']['source_ref'] for b in bundles}))).hexdigest(),
  condition_id='deterministic-closure-isolated-QA',sources={b['label']:dict(source_ref=b['policy']['source_ref'],
   catalog_sha256=b['catalog']['catalog_sha256'],anchor_id=b['policy']['anchor_id'],policy_sha256=b['policy_sha256']) for b in bundles})
 candidates={b['label']:sorted({v for v in b['core_report']['core_witnesses'].values() if v is not None}) for b in bundles}
 # The public deterministic selector does not read private scoring witnesses.
 keep=sorted({i for ids in candidates.values() for i in ids})[:4]
 selected={label:[i for i in ids if i in keep] for label,ids in candidates.items()}
 frames=[{key:b[key] for key in ('label','proof','rows','membership','policy','policy_sha256','query','pins','source_validation')} for b in bundles]
 deadline=min(a.deadline_ns for a in actors)
 save(output/'PROJECTION_TASK.json',task);save(output/'PUBLIC_CANDIDATE_SELECTION.json',dict(
  rule='normal core extrema witness union, integer-order cap4',per_source_observed_candidates=candidates,
  retained_triangle_indices=keep,candidates_by_label=selected))
 started=time.perf_counter_ns();tracemalloc.start()
 try:
  view,audit=closure.project(task,frames,candidates_by_label=selected,
   threshold_high=1.1,threshold_low=.9,deadline_ns=deadline)
  current,peak=tracemalloc.get_traced_memory()
 finally:tracemalloc.stop()
 elapsed=time.perf_counter_ns()-started
 if 'evidence_sidecar' in audit:save(output/'EVIDENCE_SIDECAR.json',audit['evidence_sidecar'])
 # Mechanical equality with the complete normal product facts, independent of
 # the new view's own completeness claims. This is not a geometry truth oracle
 # or a model-reasoning score.
 by_label={b['label']:b for b in bundles};comparison=[]
 for summary in view['core_summary_by_frame']:
  source=by_label[summary['label']]
  assert summary['facts']==source['core_report']['facts']
  assert summary['core_witnesses']==source['core_report']['core_witnesses']
 for trajectory in view['candidate_witness_trajectories']:
  index=trajectory['selected_triangle'];assert type(index) is int
  assert len(trajectory['frames'])==len(bundles)
  for entry in trajectory['frames']:
   label=entry['label'];source=by_label[label]
   values=__import__('human_eye_plugin.surface_deformation',fromlist=['_verified_rows'])._verified_rows(
    source['proof'],source['rows'],deadline_ns=deadline)
   row=values[index];members=source['core_audit']['core_triangle_indices']
   has_mixed=any(values[i]['state']=='measured' and values[i]['principal_stretches'][0]>=1.1
    and values[i]['principal_stretches'][1]<=.9 for i in members)
   confirmation=True if has_mixed else None if any(values[i]['state']=='unknown' for i in members) else False
   wanted=dict(label=label,file_sha256=source['policy']['source_ref']['scene_sha256'],
    principal_stretches=row['principal_stretches'],area_ratio=row['area_ratio'],state=row['state'],reason=row['reason'],
    in_core=index in members,has_confirmed_mixed_witness=confirmation)
   assert entry==wanted,'candidate row differs from complete normal facts'
   comparison.append(dict(label=label,triangle=index,all_eight_fields_exact=True))
 if 'evidence_sidecar' in audit:assert sha(output/'EVIDENCE_SIDECAR.json')==view['evidence_ref']['sha256']
 save(output/'FACT_COMPARISON.json',dict(mechanical_equality=True,source='complete normal externally-qualified product facts',
  compared_candidate_rows=comparison,complete_core_summaries_compared=len(bundles),
  no_rounding=True,no_geometry_oracle_claim=True,model_interpretation_review='not_run_no_model_consumption'))
 save(output/'PROJECTION_MEASUREMENT.json',dict(extraction_and_projection_wall_ns=elapsed,
  tracemalloc_current_bytes=current,tracemalloc_peak_bytes=peak,measurement_includes_tracemalloc_overhead=True,
  original_deadline_ns=deadline,complete_rows_provided=sum(len(b['proof']['triangles']) for b in bundles),
  original_source_process_reads=sum(a.sequence for a in actors),new_source_reads_in_projection=0,
  model_tokens=None,model_rounds=None,USD=None))
 return view,audit

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepare-runtime',type=Path);p.add_argument('--core-root',type=Path);p.add_argument('--output',type=Path)
 a=p.parse_args()
 if a.prepare_runtime:prepare_runtime(a.prepare_runtime)
 else:
  if not a.core_root or not a.output:p.error('--core-root and --output required')
  run(a)
