"""043 ordinary-GUI functional checks. Freeze is offline; run needs root window."""
from __future__ import annotations
import argparse
from fractions import Fraction as Q
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import traceback

HERE=Path(__file__).resolve().parent
VER=HERE.parents[1]
ROOT=Path('D:/HumanEye/runs/M6-043-R3-REGION-ATTRIBUTION')
RAW=ROOT/'live/checks'
OLD=ROOT.parent/'M6-041-KERNEL-HOOK'
CYCLE=ROOT.name
PYTHON=Path('D:/he_m3_bvh032_private_654c1f69/venv/Scripts/python.exe')
PLAN=RAW/'PLAN.json'
sys.path.insert(0,str(HERE))
from check_geometry import bits,leases,need,region


def read(p):return json.loads(Path(p).read_bytes())


def pin(p):
    p=Path(p).resolve(strict=True);b=p.read_bytes();return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}


def dump(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf8',newline='\n')as f:json.dump(v,f,ensure_ascii=False,allow_nan=False,indent=2);f.write('\n')


def load(name,p):
    spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m


def freeze():
    """Small metadata/source reads only; no full binary read, GUI or solver."""
    RAW.mkdir(parents=True,exist_ok=True)
    pins=read(OLD/'install/PINS.json');cpins=read(ROOT/'candidate/PINS.json')
    source034=read(VER/'m6_same_frame_scoped_batch_034/private/inputs/FROZEN.json')
    data029=read(VER/'m6_bvh_witness_projection_029/private/inputs/INPUTS.json')
    scene=next(s for s in data029['scenes']if s['id']=='m4_independent')
    original_case=next(c for c in data029['cases']if c['id']=='m4_independent_heavy')
    truth_path=VER/'m6_bvh_work_credit_031/private/ORACLE_FOR_ENTRY.json';truth=read(truth_path)['m4_independent_heavy']
    need(original_case['pair']==['Obj_014','Obj_003']and original_case['input_triangle_pair_count']==128*28,'preselected_only_family')
    need(truth['canonical_native_source_triangle_pair']==[16,24],'preselected_independent_native_pair')
    bindings={'A':pins['binding']['032'],'C':cpins['binding']};arms={}
    for arm,ref in bindings.items():
        need(pin(ref['path'])==ref,'binding_identity');binding=read(ref['path']);entry=Path(ref['path']).with_name('target_runtime_entry.py')
        arms[arm]={'source_sha256':binding['identity']['source_sha256'],'version':binding['identity']['distribution_version'],
            'role':'043 functional pure-return observer; not a timing sample','site_packages':binding['site_packages'],
            'command_prefix':[str(PYTHON),'-I','-B',str(HERE/'observed_entry.py'),str(entry)],
            'binding':ref,'entry':pin(entry),'source_count':len(binding['source_files'])}
    shift=Q(1,64);old=Q(source034['regions']['high']['distance_exact_m'])
    plan={'schema':'m6-043-live-functional-check-plan-v1','cycle_id':CYCLE,'contract':'46ae1484',
        'support':read(OLD/'s1/PLAN_recovery_01.json')['support'],'arms':arms,
        'Yanyite_asset':read(OLD/'s1/warm_diagnostic/PLAN.json')['asset_pins']['Yanyite'],
        'M4_scene':scene,'M4_original_case':original_case,
        'M4_independent_truth':truth,'M4_truth_source':pin(truth_path),
        'M4_043_selection':pin(ROOT/'quality/prepared_004/ARCHIVE_BINDING.json'),
        'M4_043_independent_truth':pin(ROOT/'quality/prepared_004/ARCHIVE_ORACLE.json'),
        'low_geometry':pin(ROOT/'holdouts/inputs/Yanyite_low.json'),
        'high_geometry':pin(ROOT/'holdouts/inputs/Yanyite_high.json'),
        'low_request':source034['requests_A'][1],'high_request':source034['requests_A'][0],
        'M4_request':{'name':'human_eye_scene_observe','arguments':{'session_id':'043-fixed-m4-functional',
            'include_image':False,'response_detail':'full','query':original_case['query']}},
        'case_order':['same_asset_low','fixed_M4_pair','real_Cube_edit'],
        'arm_order':['C','A'],'read_sequence':{'same_asset_low':{'C':['first','warm'],'A':['reference']},
            'fixed_M4_pair':{'C':['first','warm'],'A':['reference']},
            'real_Cube_edit':{'C':['old_first','old_warm','actual_edit','after_edit','after_edit_warm'],'A':['edited_reference']}},
        'edit':{'object':'Cube','property':'location.z','delta_m_exact':str(shift),
            'old_distance_exact_m':str(old),'new_distance_exact_m':str(old+shift),
            'canonical_native_pair':[49114,0],'save_mode':'save_as_mainfile(copy=True) private new file only',
            'same_C_service_required':True,'source_asset_unchanged_required':True},
        'cache_acceptance':'actual full/ack native replies and connector return work; old→edit changes payload, after-warm reuses new lease; never infer lease from latency',
        'observer':'sys.setprofile read-only returns; no method, argument or source patch; same original bootstrap/stdio/addon; functional only',
        'formal_timing_samples':0,'no_launch_until_coordinator_window':True,
        'sources':{p.name:pin(p)for p in HERE.glob('*.py')},
        'reused_sources':{str(p):pin(p)for p in (OLD/'s1/s1.py',VER/'m6_post032_profile_036/run.py',
            VER/'m6_post032_profile_036/snapshot.py',VER/'m6_post032_profile_036/gui.py',VER/'m6_post032_profile_036/gui_worker.py')}}
    dump(PLAN,plan);print(pin(PLAN))


def api(plan):
    s1=load('_043_live_checks_s1',OLD/'s1/s1.py');gui,svc=s1.api()
    gui.PRIVATE=RAW;gui.CYCLE=CYCLE
    gui.ASSET_SHAS={plan['Yanyite_asset']['sha256']:'Yanyite',plan['M4_scene']['blend']['sha256']:'M4'}
    svc.CYCLE=CYCLE
    return gui,svc


def snap(owner,folder,label):
    packet=owner.run((VER/'m6_post032_profile_036/snapshot.py').read_text(encoding='utf8'))
    need(packet['response']['status']=='success','actual_native_snapshot')
    text=packet['response']['result']['result'];line,=[x for x in text.splitlines()if x.startswith('M6_036_SNAPSHOT:')]
    value=json.loads(line.split(':',1)[1]);need(value['pid']==owner.pid and value['main_thread']and not value['background'],'actual_owned_GUI_snapshot')
    need(Path(value['asset']).resolve()==owner.workspace/'input.blend','owned_input_copy')
    dump(folder/(label+'.json'),value);return value


def before_source(value,asset,svc):
    need(value['frame']==1 and value['subframe']==0 and value['scale']==1,'fixed_native_frame_units')
    if asset=='Yanyite':
        expected=svc.fixture('Yanyite')['expected']
        need({n for n,r in value['geometry'].items()if r['type']=='MESH'}==set(expected),'original_mesh_set')
        for name,checks in expected.items():
            for key,v in checks.items():need(svc.binary(value['geometry'][name][key])==svc.binary(v),'original_Yanyite_native_'+key)


def ask(client,request,folder,label):
    answer=client.observe(request);dump(folder/(label+'.json'),answer)
    need(not answer['tool_error']and not answer['rpc_error'],'actual_complete_business_'+label)
    return answer


def captures(folder):
    index=read(folder/'RETURN_OBSERVER/INDEX.json');need(index['error']is None,'return_observer_no_failure')
    need(index['methods_or_arguments_modified']is False,'pure_return_observer')
    values=[]
    for ref in index['captures']:
        need(pin(ref['path'])==ref,'actual_return_capture_identity');values.append(read(ref['path']))
    return values,read(folder/'RETURN_OBSERVER/TREES.json')


def actual_edit(owner,folder):
    destination=owner.workspace/'043_reference_edit.blend'
    code=("import bpy,json,os,hashlib,struct\n"
          "cube=bpy.data.objects['Cube']\n"
          "before=float(cube.location.z)\n"
          "local_before=hashlib.sha256(b''.join(struct.pack('<3d',*v.co) for v in cube.data.vertices)).hexdigest()\n"
          "cube.location.z=before+1/64\nbpy.context.view_layer.update()\n"
          "bpy.context.preferences.filepaths.save_version=0\n"
          f"saved=bpy.ops.wm.save_as_mainfile(filepath={str(destination)!r},copy=True,check_existing=False)\n"
          "local_after=hashlib.sha256(b''.join(struct.pack('<3d',*v.co) for v in cube.data.vertices)).hexdigest()\n"
          "print(json.dumps({'pid':os.getpid(),'background':bpy.app.background,'before_z':before,'after_z':float(cube.location.z),'delta':float(cube.location.z)-before,'matrix':[[float(x)for x in row]for row in cube.matrix_world],'local_before':local_before,'local_after':local_after,'save_status':sorted(saved),'open_filepath':bpy.data.filepath}))")
    dump(folder/'EDIT_INTENT.json',{'object':'Cube','delta_exact_m':'1/64','destination':str(destination),'code':code,'at_most_once':True})
    reply=owner.run(code);dump(folder/'EDIT_REPLY.json',reply)
    need(reply['response']['status']=='success','actual_Cube_edit')
    text=reply['response']['result']['result'];data=json.loads(text.strip().splitlines()[-1])
    need(data['pid']==owner.pid and data['background']is False and data['delta']==1/64 and data['local_before']==data['local_after'],'actual_native_dyadic_edit')
    need(data['save_status']==['FINISHED']and destination.is_file(),'actual_private_save_copy')
    dump(folder/'EDIT.json',{'actual':data,'saved_file':pin(destination),'same_owner_PID':True});return data


def check_m4(plan,bodies,client_folders):
    source=read(plan['M4_scene']['snapshot']['path']);objects={o['name']:o for o in source['objects']}
    expected={}
    for name in ('Obj_014','Obj_003'):
        obj=objects[name];matrix=obj['matrix_world'];world=obj.get('vertices_world')
        if world is None:world=[[((m[0]*p[0]+m[1]*p[1])+m[2]*p[2])+m[3]for m in matrix[:3]]for p in obj['vertices_local']]
        expected[name]={'vertices':world,'faces':obj.get('triangles',obj.get('faces'))}
    truth=plan['M4_independent_truth'];sq=Q(truth['distance_squared']);wanted=truth['correctly_rounded_distance_m']
    for body in bodies:
        fact=body['facts']['surface_proximity'];need(fact['status']=='measured','M4_actual_surface_fact')
        need(fact['value']['distance_m'].hex()==wanted.hex(),'M4_actual_independent_distance')
    def geometry(body):
        value=body['facts']['surface_proximity']['value'];w=value['nearest_witness']
        return {'distance_m':value['distance_m'],'topology':value.get('topology'),
            'points':[w['a'],w['b']],'direction':w['direction_a_to_b']}
    need(geometry(bodies[0])==geometry(bodies[1])==geometry(bodies[2]),'M4_C_warm_A_full_geometry_answer')
    evidence=[]
    for folder in client_folders:
        observed=read(folder/'RETURN_OBSERVER/TASK_CAPTURES.json')
        need(bool(observed),'actual_M4_task_capture_observed')
        for packet in observed:
            capture=packet['capture'];mesh={m['name']:m for m in capture['meshes']}
            need(set(mesh)==set(expected),'actual_explicit_M4_pair_scope')
            for name,exp in expected.items():
                need(mesh[name]['faces']==exp['faces']and bits(mesh[name]['vertices'])==bits(exp['vertices']),'actual_M4_full_geometry_'+name)
        trees=read(folder/'RETURN_OBSERVER/TREES.json')
        need(all(t['contained_zero_fifo']is False for t in trees if t['contained_zero_fifo']is not None),'actual_M4_not_triggered')
        need(trees and list(trees[0]['best_pair'])==truth['canonical_native_source_triangle_pair'],'actual_M4_canonical_pair')
        surfaces=read(folder/'RETURN_OBSERVER/SURFACE_RETURNS.json')
        for measured in surfaces:
            pts=measured['exact_world_points'];need(pts is not None,'M4_actual_exact_original_points')
            a,b=[tuple(map(Q,p))for p in pts];need(sum((x-y)**2 for x,y in zip(a,b))==sq,'M4_actual_independent_exact_squared_distance')
        evidence.append({'capture_returns':len(observed),'tree_returns':len(trees),'canonical_native_pair':truth['canonical_native_source_triangle_pair']})
    return {'status':'pass','input_triangles':[128,28],'full_actual_geometry_exact':True,
            'distance_squared_exact':str(sq),'canonical_native_pair':truth['canonical_native_source_triangle_pair'],
            'candidate_branch_activated':False,'evidence':evidence}


def run_case(name,folder,plan,window,gui,svc):
    folder.mkdir();asset=plan['M4_scene']['blend']if name=='fixed_M4_pair'else plan['Yanyite_asset']
    kind='M4'if name=='fixed_M4_pair'else'Yanyite';owner=None;row={'case':name,'status':'failed','arms':{},'errors':[]}
    request=plan['M4_request']if kind=='M4'else plan['low_request']if name=='same_asset_low'else plan['high_request']
    try:
        owner=gui.Owned(folder/'native',asset,plan['support'],window);row['pid']=owner.pid
        before=snap(owner,folder,'BEFORE');before_source(before,kind,svc)
        for arm in plan['arm_order']:
            path=folder/arm;path.mkdir();client=None;answers=[];ar={'rows':answers,'errors':[]}
            try:
                client=svc.Client(path/'client',owner,kind,plan['arms'][arm]);client.open(kind)
                if arm=='C':
                    labels=['old_first','old_warm','after_edit','after_edit_warm']if name=='real_Cube_edit'else['first','warm']
                else:labels=['edited_reference'if name=='real_Cube_edit'else'reference']
                for label in labels:
                    if label=='after_edit':
                        row['actual_edit']=actual_edit(owner,folder)
                        row['edit_snapshot']=snap(owner,folder,'AFTER_EDIT')
                    answers.append(ask(client,request,path,label))
            except BaseException:ar['errors'].append(traceback.format_exc())
            finally:
                if client is not None:
                    try:
                        code=client.close();ar['close']=read(path/'client/CLOSE.json')
                        need(code==0 and ar['close']['method']=='eof'and not client.reader.is_alive(),'ordinary_product_EOF_close')
                    except BaseException:ar['errors'].append(traceback.format_exc())
                row['arms'][arm]=ar;dump(path/'RESULT.json',ar)
            need(not ar['errors'],'functional_arm_failure')
        after=snap(owner,folder,'AFTER')
        if name!='real_Cube_edit':need(svc.binary(before['geometry'])==svc.binary(after['geometry']),'unchanged_live_source_geometry')
        else:
            for obj in before['geometry']:
                a,b=before['geometry'][obj],after['geometry'][obj]
                if obj!='Cube':need(svc.binary(a)==svc.binary(b),'only_reference_Cube_changed')
                else:
                    for key in ('local_sha256','triangles_sha256','vertices','triangles'):need(a[key]==b[key],'Cube_local_geometry_unchanged')
                    matrix=[list(v)for v in a['matrix']];matrix[2][3]+=1/64
                    need(b['matrix']==matrix,'actual_Cube_world_translation_only')
        c=[x['result']for x in row['arms']['C']['rows']];a=row['arms']['A']['rows'][0]['result']
        if kind=='M4':row['qualification']=check_m4(plan,[*c,a],[folder/'C/client',folder/'A/client'])
        else:
            source=read(plan['low_geometry']['path']if name=='same_asset_low'else plan['high_geometry']['path'])
            cc,tree=captures(folder/'C/client');ac,atree=captures(folder/'A/client')
            need(len(cc)==len(c)and len(ac)==1,'actual_one_capture_per_region_request')
            qualified=[]
            for i,value in enumerate(cc):qualified.append(region(value['capture'],source,c[i],reference_shift=Q(1,64)if name=='real_Cube_edit'and i>=2 else Q(0)))
            qualified.append(region(ac[0]['capture'],source,a,reference_shift=Q(1,64)if name=='real_Cube_edit'else Q(0)))
            need(all(t['contained_zero_fifo']is True for t in tree),'actual_candidate_region_guard_triggered')
            need(c[-1]==a and c[-1]==c[-2],'current_complete_C_warm_A_public_answer')
            row['qualification']=qualified
            if name=='real_Cube_edit':row['lease_invalidation']=leases(cc)
        row['status']='pass'
    except BaseException:row['errors'].append(traceback.format_exc())
    finally:
        if owner is not None:
            try:row['GUI_close']=owner.close()
            except BaseException:row['errors'].append(traceback.format_exc())
        row['valid']=row['status']=='pass'and not row['errors']and row.get('GUI_close',{}).get('status')=='pass'
        dump(folder/'RESULT.json',row)
    return row


def run(window_path,output,plan_path=PLAN):
    plan=read(plan_path);window=read(window_path);output=Path(output);output.mkdir(exist_ok=False)
    need(window['cycle_id']==CYCLE and window['status']=='available'and window['token'],'root_exclusive_live_window_required')
    for ref in [*plan['sources'].values(),*plan['reused_sources'].values()]:need(pin(ref['path'])==ref,'frozen_live_check_source')
    gui,svc=api(plan);report={'status':'failed','plan':pin(plan_path),'window':pin(window_path),'cases':[],
        'functional_only':True,'formal_timing_samples':0,'model_calls':0}
    try:
        for name in plan['case_order']:
            row=run_case(name,output/name,plan,window,gui,svc);report['cases'].append(row)
            need(row['valid'],'functional_case_or_cleanup_failure')
        report['status']='pass'
    except BaseException:report['error']=traceback.format_exc()
    dump(output/'RESULT.json',report);print({'status':report['status'],'result':pin(output/'RESULT.json')},flush=True)
    return 0 if report['status']=='pass'else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('freeze','run'));parser.add_argument('--window');parser.add_argument('--output');parser.add_argument('--plan',default=str(PLAN));args=parser.parse_args()
    if args.action=='freeze':freeze()
    else:raise SystemExit(run(args.window,args.output,args.plan))
