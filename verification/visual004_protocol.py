"""Frozen paired visual/spatial pilot protocol, never an experiment solver."""
from __future__ import annotations
import argparse,hashlib,json,re,sys,time,uuid
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from verification.visual004_native import encoded,load,save,sha,need,IMAGE_LIMITS
from verification.visual004_scoring import public_answer_schema

CYCLE='VISUAL-BENEFIT-004A'
BASELINE='50f20d56f95e5672b213e1247ea00fae9c3a1ee0'
PRODUCT_PIN='6a5375fb5d5577e8de05c043db7523263cf96ad8386ee524a04beb25feb9f382'
P_MODES=[dict(mode='auto',view=view) for view in ('SCENE','XY','XZ')]+[dict(mode='projection',view='SCENE')]
PAIR_ORDER=[('V01',['P','N']),('V02',['N','P']),('V03',['P','N']),('V04',['N','P']),('V05',['N','P']),('V06',['P','N'])]
SOURCE_FILES=('verification/visual004_assets.py','verification/visual004_native.py','verification/visual004_session.py',
    'verification/visual004_product.py','verification/visual004_protocol.py','verification/visual004_scoring.py',
    'verification/test_visual004_assets.py','verification/test_visual004_native.py','verification/test_visual004_session.py',
    'verification/test_visual004_product.py','verification/test_visual004_protocol.py','verification/test_visual004_scoring.py',
    'verification/VISUAL004_NATIVE_README.md','verification/VISUAL004_CONSUMER_README.md')

COMMON_INITIAL_CODE="""import bpy,json,os
scene=bpy.context.scene
scene.render.resolution_x=768;scene.render.resolution_y=768;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'
scene.render.filepath=os.path.join(os.environ['VISUAL004_WORKSPACE'],'renders','initial.png')
bpy.ops.render.render(write_still=True)
print(json.dumps({'objects':[{'name':o.name,'type':o.type} for o in sorted(scene.objects,key=lambda o:o.name) if o.type=='MESH'],'unit_scale_m':scene.unit_settings.scale_length,'camera_matrix_world':[list(r) for r in scene.camera.matrix_world],'image_path':scene.render.filepath},sort_keys=True))
"""

COMMON_RULES='''Solve only the assigned read-only spatial task. You may final or abstain from the first actual input; no forced extra round. Identify the required objects yourself from the same supplied public directory/image and your tools. No correct object pair, core or best view is supplied. Use exact neutral mesh names in the answer. World axes, camera orientation, geometric facts and what a particular image visibly supports are different kinds of evidence.
Use only your own copied Blender asset, owned broker workspace, public task and these allowed tool documents. Do not inspect private truth/specifications, qualification results, another condition, previous answers, project implementation or learning knowledge. Fresh context is soft isolation; filesystem, host/system/tools/skills remain shared and observed tool paths are audited. Do not edit meshes, object transforms, materials, visibility, animation, source files or save .blend files. Only necessary temporary QA camera/light/view/render setup and workspace output are allowed. The transport is not a security sandbox and terminal checks cannot prove that transient changes were never reverted.
You may author ordinary bpy/Python scripts to inspect vertices/matrices/materials, choose viewpoints, zoom, render several views or create a montage and calculate numbers. No task solver is supplied. Use the generic native_run interface in either condition. Script/encoding/render/tool errors can be repaired inside the original budget; all attempts and failures count. Never reset/restart the worker, refresh a deadline, rewrite the original answer after submission or access another task's evidence.
Every generated PNG costs rendering/storage even if not delivered. Actual delivery additionally reserves each display:8 images, width/height<=1024 and area<=1024^2, total<=4*768^2. A montage costs all its actual pixels; repeated display costs again. The common initial768x768 image uses one reservation in both conditions. Paths or broker acknowledgements are not image consumption: forward actual view_image/image blocks using the common wrapper. If stdout or an image is truncated/invalid, retain that failure; do not pretend it was complete.
Return the frozen answer schema, using known or unknown per fact and actual evidence references. Unknown does not mean false. A shell hiding an internal part in an opaque image does not make its complete geometry unknowable. An image-only unknown may be honest but incomplete when the task's geometry is available. Do not claim image causality or physical measurement accuracy from a pixel opportunity, label, API success, replay consistency or correct numeric guess. There is no mutation authority.'''

P_RULES='''P additionally may call only the actual read-only human_eye_scene_observe through the P broker observe operation. All cases allow the same auto SCENE/XY/XZ and explicit projection SCENE choices; choose using task evidence. Projection is the existing fixed Q1-Q4 composition, not a single SCENE/XY/XZ camera. With no object pair, auto can produce projection overview. With a supported chosen pair it can use native multiscale, which is different from analytical Q4 attention. No native/detail/attention success is guaranteed. Use the same generic native fallback if helpful; its scripts, images, failures and time also count. Do not call any transform/restore/execute endpoint. Do not read the product implementation or insert a prepared solver.'''
N_RULES='''N uses only generic native_run and neutral image/session accounting. Do not import, call or read Human Eye capture, validator, facts, renderer, summaries, source or prepared task solvers. Native local scripting, views, numerical inspection and self-maintained in-process state/cache are permitted. You are not limited to one perspective image or a full vertex dump. Common process/time/file/image protections are the same as P.'''

EVIDENCE_REFERENCE_RULES='''Use unique ASCII request_id values matching [A-Za-z0-9_-]{1,64}. For a reply whose text you actually received, use evidence ID text:<request_id>. For an image actually shown from that reply, use image:<request_id>:<reservation_id>:<image_id>, copying those returned identifiers exactly. Example: image:inspect-1:delivery-2:image-3. A redisplay uses the new reserve request and reservation. The common initial input uses its supplied common-initial reply identifiers by the same rule. These public symbols do not attest delivery: the controller admits each only after verifying actual current task/run host event, block slot and text/PNG bytes within the original deadline. Paths, ledger entries and model assertions are not delivery proof. Do not guess host event IDs or later controller-internal IDs.'''

def public_evidence_ids(reply):
    """Public reference symbols only; never attests host receipt or geometry."""
    need(type(reply) is dict,'evidence_reply')
    request=reply.get('request_id')
    need(type(request) is str and re.fullmatch(r'[A-Za-z0-9_-]{1,64}',request),'public_request_id')
    result=dict(text='text:'+request,images=[])
    if reply.get('ok') is not True:return result
    body=reply.get('result')
    need(type(body) is dict,'evidence_reply_result')
    images=body.get('image_refs',[]);need(type(images) is list,'evidence_image_refs')
    seen=set()
    for row in images:
        validate_image_ref(row)
        image_id=row.get('image_id');reservation=row['reservation_id']
        need(type(image_id) is str and re.fullmatch(r'image-[1-9][0-9]*',image_id)
            and re.fullmatch(r'delivery-[1-9][0-9]*',reservation),'public_image_identifiers')
        identity='image:'+request+':'+reservation+':'+image_id
        need(identity not in seen,'duplicate_public_image_reference');seen.add(identity)
        result['images'].append(identity)
    return result

def task_contract(public_task,asset_sha256,*,task_run_id=None):
    need(type(public_task) is dict and public_task.get('schema')=='visual004-public-task-v1','public_task')
    need(public_task.get('case_id') in dict(PAIR_ORDER),'case_id')
    need(type(asset_sha256) is str and len(asset_sha256)==64 and all(c in '0123456789abcdef' for c in asset_sha256),'asset_sha256')
    identifier=uuid.uuid4().hex if task_run_id is None else task_run_id
    need(type(identifier) is str and 1<=len(identifier)<=128,'task_run_id')
    return dict(schema='visual004-score-contract-v1',case_id=public_task['case_id'],task_run_id=identifier,
        asset_sha256=asset_sha256,task_sha256=hashlib.sha256(encoded(public_task)).hexdigest())

def consumer_input(public_task,contract,condition):
    need(condition in ('P','N'),'condition')
    need(contract['case_id']==public_task['case_id'] and contract['task_sha256']==hashlib.sha256(encoded(public_task)).hexdigest(),'public_binding')
    return dict(schema='visual004-public-consumer-input-v1',contract=contract,task=public_task,
        rules=COMMON_RULES,evidence_reference_rules=EVIDENCE_REFERENCE_RULES,tool_rules=P_RULES if condition=='P' else N_RULES,
        answer_schema=public_answer_schema(),
        final_response_envelope=dict(agent_id='own host agent ID',status='final or abstain',answer='frozen answer object or null',reason='optional'),
        task_window_seconds=600,tools='owned neutral broker; no default shared Blender/MCP or external API',
        image_budget=dict(IMAGE_LIMITS,max_width=1024,max_height=1024),
        text_budget=dict(data_bytes=262144,control_bytes=98304,max_total_wire_bytes=360448),max_public_calls=48,
        cold_start_scope='original broker entry before source read/copy to raw final and cleanup; no prepared HE report')

def validate_image_ref(row):
    """Common host-wrapper gate, in addition to the neutral reservation ledger."""
    need(type(row) is dict,'image_ref')
    need(all(type(row.get(key)) is int and row[key]>0 for key in ('width','height','pixels')),'image_dimensions')
    need(row['width']<=1024 and row['height']<=1024 and row['pixels']==row['width']*row['height']
        and row['pixels']<=IMAGE_LIMITS['max_single_pixels'],'single_image_dimensions')
    need(type(row.get('reservation_id')) is str and row['reservation_id']
        and type(row.get('path')) is str and row['path'],'reserved_image_required')
    need(type(row.get('sha256')) is str and len(row['sha256'])==64
        and all(c in '0123456789abcdef' for c in row['sha256']),'image_digest')
    return row

def freeze(root,*,output_dir=None):
    root=Path(root).resolve();assets=root/'assets'
    from verification.visual004_assets import verify
    from human_eye_plugin.runtime_identity import runtime_identity
    verify(assets);identity=runtime_identity()
    need(identity['source_sha256']==PRODUCT_PIN and len(identity['source_files'])==129,'runtime_pin')
    built=load(assets/'BUILD_RESULT.json');by_id={r['case_id']:r for r in built['cases']}
    cases=[]
    for case_id,order in PAIR_ORDER:
        public=load(assets/case_id/'PUBLIC_TASK.json')
        cases.append(dict(case_id=case_id,order=order,public_task_sha256=sha(assets/case_id/'PUBLIC_TASK.json'),
            asset_sha256=sha(assets/case_id/'scene.blend'),qualification_initial_png_sha256=sha(assets/case_id/'initial.png'),
            private_truth_sha256=sha(assets/case_id/'PRIVATE_TRUTH.json'),required_roles=public['required_roles'],
            required_fact_ids=public['required_fact_ids'],question=public['question']))
    plan=dict(schema='visual004-frozen-paired-plan-v1',cycle_id=CYCLE,created_utc=datetime.now(timezone.utc).isoformat(),
        baseline_commit=BASELINE,product_source_sha256=PRODUCT_PIN,product_source_count=129,
        case_spec_sha256=sha(assets/'CASESET_SPEC.json'),cases=cases,formal_consumers_planned=12,formal_consumers_run_in_004A=0,
        balanced_order='3 P-first,3 N-first,serial,all fixed cases including unsupported/refused/timeouts retained',
        P='actual existing observation-tool combination plus equally available generic native fallback',
        N='model-authored generic bpy/Python; no HE capture/validation/summary or prepared solver',P_visual_modes=P_MODES,
        common_rules=COMMON_RULES,evidence_reference_rules=EVIDENCE_REFERENCE_RULES,P_rules=P_RULES,N_rules=N_RULES,common_initial_code=COMMON_INITIAL_CODE,
        common_initial_scope='same copied bytes,public task,neutral names/types/unit/camera pose; freshly render asset camera before consumer inside original window',
        no_hidden_targets_or_best_view=True,source_file_and_geometry_read_only=True,
        per_task_seconds=600,whole_formal_run_seconds=7800,worker_restarts=0,consumer_restarts=0,
        recoverable_script_errors='permitted within original budgets, all costs retained',
        image_limits=dict(IMAGE_LIMITS,max_width=1024,max_height=1024),
        pixel_accounting='actual whole image/montage area on every display including repeats; construction and undelivered images separate',
        public_call_limit=48,text_limits=dict(data_bytes=262144,control_bytes=98304,max_wire_bytes=360448),
        product_subcall_budgets=dict(request_s=20,native_lease_s=10,forwarding='min existing scope and original600s remaining'),
        lifecycle='same neutral persistent owner broker and Blender lifetime; P keeps actual service/host/memo; N keeps own Python namespace/state',
        consumers=dict(fresh=True,fork_turns='none',model='inherit parent no override',reasoning='inherit parent no override',
            actual_backend_configuration='record if observable else unknown',isolation='soft; audit observed paths, do not claim strong isolation'),
        acceptance=dict(correctness='identity,relation,direction/local position/numbers,omission/unknown/evidence fixed by truth and blind review',
            benefit='paired raw results and strata,quality must not be traded invisibly for speed; no six-case statistical generalization',
            claim_threshold='descriptive pilot only; no general module gain or USD net benefit',
            unknown_and_failures_remain_in_denominator=True,raw_answers_never_repaired=True),
        image_proof='actual agent host input_image bytes/hash,own run/thread/event/slot and task gate; not path,API ack,helper shown or hash alone',
        usage='actual per-agent usage cumulative deltas verified against last_usage; image-specific tokens/USD null if unexposed; never pixels->tokens',
        measurement='startup/capture/validation/hash/cache/geometry/render/public PNG/text/consumer/debug/failure/fallback/close; exclusive and full walls; no sum of inclusive spans',
        finite_replay='existing native overview/detail or existing completed projection base/attention call only,not new arm or model-causal ablation',
        script_pins=[dict(path=name,sha256=sha(ROOT/name)) for name in SOURCE_FILES],
        protections=['no product/threshold/source domain/default config/install/push changes','original assets/shared GUI untouched',
            'no Google/key/503/paid API/learning; priorUSD0.02 unchanged'],
        formal_start='004B only after independent review of004A; no further user approval for this already authorized scope')
    destination=root if output_dir is None else Path(output_dir).resolve()
    save(destination/'FORMAL_PLAN.json',plan);save(destination/'FORMAL_PLAN_SEAL.json',dict(sha256=sha(destination/'FORMAL_PLAN.json'),bytes=(destination/'FORMAL_PLAN.json').stat().st_size))
    return plan

def verify_plan(root,*,output_dir=None):
    root=Path(root).resolve();destination=root if output_dir is None else Path(output_dir).resolve()
    plan=load(destination/'FORMAL_PLAN.json');seal=load(destination/'FORMAL_PLAN_SEAL.json')
    need(sha(destination/'FORMAL_PLAN.json')==seal['sha256'],'plan_changed')
    for row in plan['script_pins']:need(sha(ROOT/row['path'])==row['sha256'],'script_changed')
    for row in plan['cases']:
        for filename,key in [('scene.blend','asset_sha256'),('PUBLIC_TASK.json','public_task_sha256'),('PRIVATE_TRUTH.json','private_truth_sha256')]:
            need(sha(root/'assets'/row['case_id']/filename)==row[key],'case_changed')
    return plan

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',required=True,type=Path)
    parser.add_argument('--output-dir',type=Path,help='New immutable protocol generation directory; root still owns the original assets')
    group=parser.add_mutually_exclusive_group(required=True);group.add_argument('--freeze',action='store_true');group.add_argument('--verify',action='store_true')
    args=parser.parse_args();plan=freeze(args.root,output_dir=args.output_dir) if args.freeze else verify_plan(args.root,output_dir=args.output_dir)
    print(json.dumps(dict(cycle_id=plan['cycle_id'],cases=len(plan['cases']),formal_consumers_in_004A=0)))

if __name__=='__main__':main()
