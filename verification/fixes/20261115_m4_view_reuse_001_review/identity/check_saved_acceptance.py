"""Independent saved NPZ/receipt readback with standard library only."""
import ast, hashlib, json, math, struct, zipfile
from pathlib import Path
BASE=Path('C:/Users/Administrator/.codex/worktrees/m4-view-reuse-001/hefe/verification/m4_view_reuse_001')
RUN=Path('D:/he_view_reuse_001/run/integration_01')
OUT=Path(__file__).resolve().parent
checks=[]; inputs={}; frames=[]
def read(p):
    p=Path(p); data=p.read_bytes(); inputs[str(p)]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()};return data
def load(p):return json.loads(read(p).decode('utf-8-sig'))
def check(name,value):checks.append({'name':name,'passed':bool(value)})
def npz(p):
    read(p); result={}
    with zipfile.ZipFile(p) as z:
        for name in z.namelist():
            data=z.read(name)
            if data[:6]!=b'\x93NUMPY':raise ValueError('not NPY')
            pos=10 if data[6]==1 else 12
            n=struct.unpack('<H' if pos==10 else '<I',data[8:pos])[0]
            h=ast.literal_eval(data[pos:pos+n].decode('latin1'))
            payload=data[pos+n:]
            if h['fortran_order']:raise ValueError('fortran outside saved scope')
            result[name[:-4]]=(h,payload)
    return result
def vals(a):
    h,b=a
    return memoryview(b).cast({'<i4':'i','<i8':'q','<f8':'d','|u1':'B'}[h['descr']])
def dual(label,p,size):
    a=npz(p); raw,patch,owner,depth=[vals(a[n]) for n in ('triangle_ids','patch_owners','owners','depth')]
    mapping,offsets=vals(a['face_patch_ids']),vals(a['face_patch_offsets'])
    check(label+'_shape',all(a[n][0]['shape']==(size,size) for n in ('triangle_ids','patch_owners','owners','depth')))
    check(label+'_int32',all(a[n][0]['descr']=='<i4' for n in ('triangle_ids','patch_owners','owners')))
    check(label+'_same_winner_relation',all((r==-1 and p==-1 and o==-1 and math.isinf(d) and d>0) if r<0 else
         (0<=o<len(offsets)-1 and offsets[o]<=r<offsets[o+1] and p==mapping[r] and math.isfinite(d) and d>0)
         for r,p,o,d in zip(raw,patch,owner,depth)))
    check(label+'_metadata',all(n in a for n in ('owner_schema','owner_mapping_identity','triangle_id_scope')))
    frames.append({'label':label,'pixels':size*size,'foreground':sum(r>=0 for r in raw),'raw_ids':sorted(set(raw))})
    return a

cases=('subdivided_patch','multi_object_near_far_unsupported','equal_depth_first_winner','clipped_triangle_fan','all_background')
for name in cases:
    frame=load(BASE/'product_checks_01/cases'/f'{name}_FRAME.json')
    a=dual(name,frame['arrays_path'],64)
    check(name+'_file_hash',inputs[str(Path(frame['arrays_path']))]['sha256']==frame['arrays_sha256'])
    ids=set(vals(a['triangle_ids'])); owners=vals(a['owners']); raw=vals(a['triangle_ids']); patch=vals(a['patch_owners'])
    if name=='subdivided_patch':check('subdivided_eight_raw_one_patch',ids-{-1}==set(range(8)) and set(patch)-{-1}=={0})
    elif name=='multi_object_near_far_unsupported':
        check('three_objects_visible',set(owners)-{-1}=={0,1,2})
        check('unsupported_raw_preserved',all(r==2 and p==-1 for r,p,o in zip(raw,patch,owners) if o==1))
    elif name in ('equal_depth_first_winner','clipped_triangle_fan'):check(name+'_raw0',ids-{-1}=={0})
    else:check('background_all',ids=={-1})

oldobs=load('D:/he_consume_001/formal/P1/o/OBSERVATIONS.json')
oldframes={r['view_name']:r for r in oldobs['frames'] if r['origin']=='product'}
newobs=load(RUN/'product_then_reuse/o/OBSERVATIONS.json')
check('three_new_frames',len(newobs['frames'])==3 and {r['view_name'] for r in newobs['frames']}=={'SCENE','BACK','LEFT'})
for row in newobs['frames']:
    a=dual('installed_'+row['view_name'],row['NPZ'],512)
    old=npz(oldframes[row['view_name']]['NPZ'])
    for k in ('color','depth','owners','patch_owners'):
        check(row['view_name']+'_old_'+k,a[k]==old[k])
    check(row['view_name']+'_npz_hash',inputs[str(Path(row['NPZ']))]['sha256']==row['NPZ_sha256'])
    if row['view_name']=='SCENE':
        native=npz('D:/he_consume_001/formal/P1/o/frames/04/SCENE.npz')
        check('installed_scene_saved_independent_raw',a['triangle_ids']==native['triangle_ids'])

integration=load(RUN/'INTEGRATION_RESULT.json')
check('installed_denominators',integration['registered_case_denominator']==12 and len(integration['owners'])==4 and integration['actual_rasters']==13)
owner_results=[]
for row in integration['owners']:
    name=row['name']; worker=load(row['worker_result_path']); obs=load(RUN/name/'o/OBSERVATIONS.json')
    check(name+'_worker_hash',inputs[str(Path(row['worker_result_path']))]['sha256']==row['worker_result_sha256'])
    check(name+'_errors',worker['passed'] and not worker['errors'] and not worker['close_errors'])
    check(name+'_shutdown',row['process_cleanup']['confirmed'] and row['process_cleanup']['exit_code']==0 and row['process_cleanup']['process_handle_closed'])
    counts=[r['snapshot']['owner_metrics']['render_attempts'] for r in worker['requests']]
    errors=[r['is_error'] for r in worker['requests']]
    owner_results.append({'name':name,'render_attempts_at_each_request':counts,'request_error_flags':errors,'outcome':worker['outcome']})
    if name=='product_then_reuse':
        check('product_three_reads_no_raster',counts==[3,3,3,3])
        check('product_one_scene',sum(r['view_name']=='SCENE' for r in obs['render_attempts'])==1)
    elif name=='publication_failure':
        check('failed_fresh_charged_and_recovery',counts==[1,2,2,3,3] and errors==[False,True,False,False,False])
        check('failed_attempt_ledger',len(obs['render_attempts'])==3 and obs['render_attempts'][1]['status']=='postprocess_failed')
        check('only_good_frames_registered',len(obs['frames'])==2)
    elif name=='legacy_capability':check('legacy_one_construct_then_hit',counts==[1,1])
    else:check('native_six_attempts',counts[:8]==[1,1,1,2,3,4,5,6] and all(c==6 for c in counts[8:]))

before=load(BASE/'no_ref_before_01/RESULT.json'); after=load(BASE/'no_ref_after_02/RESULT.json')
check('identical_saved_bytes_before_after',before['protected_saved_bytes']==after['protected_saved_bytes'])
out={'schema':'independent-view-reuse-saved-acceptance-v1','checks':len(checks),'passed':sum(c['passed'] for c in checks),
     'failures':[c for c in checks if not c['passed']],'details':checks,'frames':frames,'owners':owner_results,
     'new_product_model_Blender_raster':0,
     'limits':'Saved 64px/512px arrays and original receipts rechecked; not new renderer or dynamic cache execution. 128px is invalidation-only; fixture non512 rejects.'}
(OUT/'ACCEPTANCE_RESULT.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
(OUT/'ACCEPTANCE_INPUTS.json').write_text(json.dumps(inputs,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'checks':len(checks),'passed':out['passed'],'failures':out['failures']}))
if out['failures']:raise SystemExit(1)
