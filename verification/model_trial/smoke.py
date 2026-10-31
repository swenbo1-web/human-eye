"""Real owned-host integration preflight, zero model-provider requests.

Uses deterministic schedules, never reported as model episodes.  Run only with
the existing pinned dependency Python -I -B and a fresh run name.
"""
from pathlib import Path
import argparse,base64,copy,hashlib,io,json,math,sys,time,traceback
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from verification.model_trial.native_client import OwnedFixture,DEPENDENCY_PYTHON
from verification.model_trial.plugin_client import PrivatePluginClient
from verification.model_trial.tools import TrialRouter,ToolRejected
from verification.model_trial.compute import RestrictedCompute
from verification.model_trial.oracle import score,independent_gap
from verification.model_trial.loop import SyntheticTransport,run_episode

PHASE = ROOT/'verification/fixes/20261030_model_trial_entry'

def save(path,value):
    with path.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False)

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def canonical(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def snapshots(folder):
    path=folder/'write_snapshots.jsonl'
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []
def wire_body(wire):
    return json.loads(next(c['text'] for c in wire['content'] if c['type']=='text'))
def named(scene,name):return next(o for o in scene['objects'] if o['name']==name)

# This client programme has access only to the common complete raw scene.
# It derives the normal from the raw reference matrix; it never reads owner truth.
RAW_SOLVER = '''base = [o for o in scene['objects'] if o['name'] == 'GreyBase'][0]
blue = [o for o in scene['objects'] if o['name'] == 'BluePart'][0]
n = [base['matrix'][k][2] for k in range(3)]
length = math.sqrt(sum(x*x for x in n))
n = [x/length for x in n]
def project(v):
    return sum(n[k]*v[k] for k in range(3))
gap = min(project(v) for v in blue['world_vertices']) - max(project(v) for v in base['world_vertices'])
dz = (0.001 - gap) / n[2]
step = max(-0.00099, min(0.00099, dz))
result = {'gap_m': gap, 'step_z_m': step, 'object_id': blue['object_id'], 'revision': scene['revision']}
'''

def solve_native(router):
    for _ in range(8):
        calculation=router.call('native_compute',{'code':RAW_SOLVER})['result']
        if abs(calculation['gap_m']-.001)<=1e-6:
            return calculation
        router.call('native_transform',{'object_id':calculation['object_id'],
            'delta_world_m':[0,0,calculation['step_z_m']],'expected_revision':calculation['revision']})
    raise RuntimeError('Deterministic raw baseline did not finish within eight writes')

def solve_plugin(router,pair):
    receipts=[]
    reviews=[]
    baseline=router.call('native_scene_query',{})
    for index in range(8):
        observed=wire_body(router.call('human_eye_scene_observe',{**pair,'include_image':False,
            'query':{'alignment_evidence':False,'support_plane_discovery':{'direction_world':[0,0,1]}}}))
        discovery=observed['support_plane_discovery']
        assert discovery['status']=='complete' and discovery['returned_candidate_count']==1 and not discovery['ambiguous']
        selector=discovery['candidates'][0]['selector']
        request={**pair,**selector,'solver':'support_plane','direction_world':[0,0,1],
            'target_clearance_m':.001,'clearance_tolerance_m':1e-6,
            'max_steps':1 if router.arm=='B' else 8,
            'max_step_translation_m':.001,'max_total_translation_m':.008,'max_duration_s':30}
        receipt=wire_body(router.call('human_eye_clearance_segment',{'request_id':f'preflight-{index}',
            'request':request,'execute':True,'include_image':False}))
        receipts.append(receipt)
        if receipt['status']=='satisfied':return {'receipts':receipts,'review_decisions':reviews}
        assert receipt['status']=='review_required',receipt['status']
        assert set(receipt['reason_codes']) <= {'contact_feature_changed_after_rounded_translation','segment_step_budget_exhausted'}
        assert receipt['steps'] and all(s['state']=='complete' and s['result']['executed'] is True
            and s['result']['execution_verified'] is True for s in receipt['steps'])
        current=router.call('native_scene_query',{})
        blue,old=named(current,'BluePart'),named(baseline,'BluePart')
        assert set(o['name'] for o in current['objects'])==set(o['name'] for o in baseline['objects'])
        assert all(o==named(baseline,o['name']) for o in current['objects'] if o['name']!='BluePart')
        assert all(blue[k]==old[k] for k in ('object_id','name','local_vertices','faces','color'))
        assert all(blue['matrix'][r][c]==old['matrix'][r][c] for r in range(4) for c in range(4) if c!=3 or r==3)
        assert all(blue['matrix'][k][3]==old['matrix'][k][3] for k in (0,1))
        calculation=router.call('native_compute',{'code':RAW_SOLVER})['result']
        assert receipt['residual']['measurement_valid'] is True
        assert abs(calculation['gap_m']-receipt['residual']['current_clearance_m'])<=1e-6
        reviews.append({'after_segment':index,'policy':'deterministic public-facts reviewer; not a model',
            'confirmed_steps':len(receipt['steps']),'reasons':receipt['reason_codes'],
            'raw_gap_m':calculation['gap_m'],'pose_xy_mesh_other_objects_unchanged':True,
            'decision':'new fresh discovery and new request ID; no uncertain retry'})
    raise RuntimeError('Deterministic plugin schedule did not finish')

def run_case(parent,name,arm,case='tilted',kind='goal',mixed=False,quota=False):
    folder=parent/name;folder.mkdir()
    fixture=OwnedFixture(folder/'fixture',case=case,angle_deg=10,gap_m=.004,origin=[.071,-.043,.02])
    plugin=None;result={'name':name,'passed':False,'deterministic_preflight':True,'model_provider_requests':0}
    try:
        fixture.start();assert fixture.port!=9876
        plugin=PrivatePluginClient(folder/'plugin',fixture) if arm!='A' else None
        router=TrialRouter(arm,fixture,plugin)
        initial=fixture.owner_truth();save(folder/'INITIAL_NATIVE.json',initial)
        public=router.call('native_scene_query',{});save(folder/'PUBLIC_INITIAL.json',public)
        assert set(public)=={'unit','coordinate_frame','revision','objects'}
        assert all(set(o)=={'object_id','name','local_vertices','world_vertices','faces','matrix','color'} for o in public['objects'])
        result['public_initial_sha256']=canonical(public)
        pair={'focal_id':named(public,'BluePart')['object_id'],'reference_id':named(public,'GreyBase')['object_id']}
        fixture.begin_episode()
        if case=='tilted' and not mixed and not quota:
            image=router.call('native_look',{'view':'SCENE'})
            png=base64.b64decode(image['image_base64'],validate=True)
            assert png.startswith(b'\x89PNG\r\n\x1a\n')
            (folder/'NATIVE_LOOK.png').write_bytes(png)
            result['native_png_sha256']=hashlib.sha256(png).hexdigest()
            with Image.open(io.BytesIO(png)) as image_data:
                assert image_data.size==(384,384)
                result['native_pixels_sha256']=hashlib.sha256(image_data.convert('RGBA').tobytes()).hexdigest()
            unchanged=fixture.owner_truth()
            assert unchanged['objects']==initial['objects'] and unchanged['scene_state']==initial['scene_state']
        if mixed:
            router.call('native_transform',{'object_id':pair['focal_id'],'delta_world_m':[0,0,-.0005],
                'expected_revision':public['revision']})
            stale_failed=False
            try:
                router.call('native_transform',{'object_id':pair['focal_id'],'delta_world_m':[0,0,-.0005],
                    'expected_revision':public['revision']})
            except Exception as exc:
                stale_failed=getattr(exc,'code',None)=='stale_revision'
            assert stale_failed
            result['stale_write_refused']=True
            result['receipts']=solve_plugin(router,pair)
        elif quota:
            for index in range(8):
                current=router.call('native_scene_query',{})
                router.call('native_transform',{'object_id':pair['focal_id'],
                    'delta_world_m':[0,0,-.0005 if index%2==0 else .0005],
                    'expected_revision':current['revision']})
            before_ninth=fixture.owner_truth();current=router.call('native_scene_query',{})
            rejected=False
            try:
                router.call('native_transform',{'object_id':pair['focal_id'],'delta_world_m':[0,0,-.0005],
                    'expected_revision':current['revision']})
            except Exception as exc:
                rejected=getattr(exc,'code',None)=='write_limit'
            assert rejected
            after_ninth=fixture.owner_truth()
            assert after_ninth['objects']==before_ninth['objects'] and after_ninth['counts']['host_write_events']==8
            result['ninth_write_refused']=True
        elif kind=='unsupported':
            rejected=False
            try:
                router.call('native_transform',{'object_id':pair['focal_id'],'delta_world_m':[0,0,-.0005],
                    'expected_revision':public['revision']})
            except Exception as exc:
                rejected=getattr(exc,'code',None)=='unsupported_open_geometry'
            assert rejected
            if arm!='A':
                observed=wire_body(router.call('human_eye_scene_observe',{**pair,'include_image':False}))
                result['plugin_domain_observation_status']=observed.get('observation_status')
            result['domain_write_refused']=True
        elif kind=='readonly':
            rejected=False
            try:
                router.call('native_transform',{'object_id':pair['focal_id'],'delta_world_m':[0,0,-.0005],
                    'expected_revision':public['revision']})
            except Exception as exc:
                rejected=getattr(exc,'code',None)=='read_only'
            assert rejected
            result['calculation']=router.call('native_compute',{'code':RAW_SOLVER})['result']
            result['readonly_write_refused']=True
        elif arm=='A':
            result['calculation']=solve_native(router)
        else:
            result['receipts']=solve_plugin(router,pair)
        final=fixture.owner_truth();save(folder/'FINAL_NATIVE_BEFORE_CLOSE.json',final)
        rows=snapshots(fixture.folder)
        if quota:
            oracle=score(initial,final,kind='goal',target_m=independent_gap(initial),write_snapshots=rows)
        elif kind=='readonly':
            oracle=score(initial,final,kind=kind,reported_gap_m=result['calculation']['gap_m'],write_snapshots=rows)
        elif kind=='unsupported':
            oracle=score(initial,final,kind=kind,declared_status='unsupported',write_snapshots=rows)
        else:
            oracle=score(initial,final,write_snapshots=rows)
        save(folder/'ORACLE.json',oracle)
        assert oracle['passed'],oracle.get('write_meter',{}).get('errors',oracle.get('checks'))
        assert final['counts']['matrix_assignments']==0 and final['user_file_loaded_or_saved'] is False
        result.update(passed=True,oracle=oracle,counts=final['counts'],native_motion_m=final['native_cumulative_translation_m'],
            owned_pid=fixture.process.pid,plugin_started=bool(plugin and plugin.process),tool_calls=len(router.events))
        save(folder/'ROUTER_TRACE.json',router.events)
    except BaseException as exc:
        result['failure']={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
        raise
    finally:
        errors=[]
        for label,obj in [('plugin',plugin),('fixture',fixture)]:
            if obj is not None:
                try:obj.close()
                except BaseException as exc:errors.append({'component':label,'error':repr(exc)})
        result['cleanup_errors']=errors
        result['fixture_exit_code']=fixture.process.returncode if fixture.process else None
        result['plugin_exit_code']=plugin.process.returncode if plugin and plugin.process else None
        result['passed']=bool(result['passed'] and not errors and result['fixture_exit_code']==0 and result['plugin_exit_code'] in (None,0))
        save(folder/'RESULT.json',result)
    assert result['passed']
    return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--execute',action='store_true');ap.add_argument('--run-name',required=True)
    args=ap.parse_args()
    assert args.execute and args.run_name.isidentifier() and sys.flags.isolated and sys.dont_write_bytecode
    assert Path(sys.executable).resolve()==DEPENDENCY_PYTHON.resolve()
    run=PHASE/'smoke'/args.run_name;run.mkdir(parents=True,exist_ok=False)
    code=Path(__file__).parent
    frozen=[]
    (run/'source').mkdir()
    for path in sorted(code.glob('*.py')):
        raw=path.read_bytes();(run/'source'/path.name).write_bytes(raw)
        frozen.append({'path':str(path),'sha256':hashlib.sha256(raw).hexdigest()})
    save(run/'INPUT_FREEZE.json',{'files':frozen,'provider_calls':0,'production_or_9876_contact':False})
    rows=[];summary={'passed':False,'formal_model_episodes':0,'provider_api_calls':0}
    try:
        for arm in ('A','B','C'):
            rows.append(run_case(run,'tilted_'+arm,arm))
        assert len({r['public_initial_sha256'] for r in rows})==1
        assert len({r['native_pixels_sha256'] for r in rows})==1
        rows.append(run_case(run,'mixed_native_plugin','C',mixed=True))
        rows.append(run_case(run,'eight_native_writes','A',quota=True))
        rows.append(run_case(run,'readonly_native','A',case='readonly',kind='readonly'))
        rows.append(run_case(run,'open_reference','C',case='open_reference',kind='unsupported'))
        rows.append(run_case(run,'open_focal','A',case='open_focal',kind='unsupported'))
        for item in frozen:assert sha(Path(item['path']))==item['sha256'],'Sources changed during smoke'
        summary.update(passed=True,deterministic_cases=len(rows),same_ABC_initial_scene_hash=rows[0]['public_initial_sha256'],
            same_ABC_native_pixels_hash=rows[0]['native_pixels_sha256'],all_sources_unchanged=True,
            owned_processes=[{'blender_pid':r['owned_pid'],'blender_exit':r['fixture_exit_code'],'plugin_exit':r['plugin_exit_code']} for r in rows],
            cases=[{k:v for k,v in r.items() if k not in ('receipts','oracle','calculation')} for r in rows])
    except BaseException as exc:
        summary['failure']={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
        raise
    finally:
        save(run/'SUMMARY.json',summary)
    print(json.dumps({'passed':True,'cases':len(rows),'provider_calls':0,'run':str(run)}))

if __name__=='__main__':main()
