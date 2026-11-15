"""Independent saved-wire/geometry/pixel audit; never imports the product."""
from pathlib import Path
from fractions import Fraction as Q
import base64, copy, hashlib, io, json
import numpy as np
from PIL import Image

AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m4-camera-001/hefe/verification/m4_target_camera_reliability_001')
RUNTIME = Path('D:/he_m4_camera_001')
OUT = Path(__file__).parent
manifest = json.loads((AUTHOR/'RUNTIME_ARCHIVE.json').read_bytes())
archive = {str(Path(r['original_path'])): r for r in manifest['files']}
pins, checks, slots = {}, [], {}
sha = lambda b: hashlib.sha256(b).hexdigest()
fp = lambda x: sha(json.dumps(x, sort_keys=True, separators=(',',':'), default=str).encode())

def read(path):
    p=Path(path); b=p.read_bytes(); pins[str(p)]={'sha256':sha(b),'bytes':len(b)}
    if str(p) in archive:
        row=archive[str(p)]; assert sha(b)==row['sha256'] and len(b)==row['bytes']
        assert (AUTHOR/row['archive_path']).read_bytes()==b
    return b

def load(path): return json.loads(read(path))
def check(label, yes, details=None):
    checks.append({'label':label,'passed':bool(yes),'details':details})
    assert yes,label

def source_geometry_identity(meshes):
    keys=[]; ordered=[]
    for m in meshes:
        v=[tuple(map(Q,p)) for p in m['vertices']]; f=m['faces']
        tris=[]
        for t in f:
            p=tuple(v[i] for i in t)
            tris.append(min(p,p[1:]+p[:1],p[2:]+p[:2]))
        keys.append((tuple(sorted(v)),tuple(sorted(tris)))); ordered.append((v,f))
    return fp(tuple(sorted(keys))),fp(tuple(keys)),ordered

def ndc(pose, points):
    values=[]
    for p in points:
        camera=[sum(Q(c)*x for c,x in zip(row,[*map(Q,p),Q(1)])) for row in pose['view_matrix']]
        clip=[sum(Q(c)*x for c,x in zip(row,camera)) for row in pose['projection_matrix']]
        values.append([x/clip[3] for x in clip[:3]])
    return values

for asset in ('extreme','origin','peripheral'):
    for arm in ('OLD','NEW'):
        name=arm+'_'+asset; root=RUNTIME/'controls'/name
        result=load(root/'RESULT.json'); owner=load(root/'OWNER_BINDING.json')
        public=load(root/'PUBLIC_01.json'); response=load(root/'RESPONSE_01.json')
        raw_responses=[json.loads(read(p)) for p in sorted((root/'stdio').glob('*/RX.bin'))]
        check(name+': delivered response matches raw stdio',response in raw_responses)
        check(name+': public matches actual text',json.loads(response['result']['content'][0]['text'])==public)
        for i in (2,3,4):
            reply=load(root/f'RESPONSE_{i:02}.json')
            check(name+f': subsequent request {i} returned successfully',reply in raw_responses and 'error' not in reply and not reply.get('result',{}).get('isError',False))
        resources={}; decoded=[]
        for p in sorted((root/'native/WIRE').glob('*/RESPONSE.bin')):
            w=json.loads(read(p)); text=w.get('result',{}).get('result','')
            if 'HUMAN_EYE_BLENDER_MCP:' not in text: continue
            inner=json.loads(text.split('HUMAN_EYE_BLENDER_MCP:',1)[1]); delta=inner.get('result',{})
            if delta.get('schema')!='human-eye-scene-delta-v1': continue
            for resource in delta['resources']: resources[(resource['id'],resource['revision'])]=resource
            capture=copy.deepcopy(delta['capture'])
            for m in capture['meshes']:
                ref=m.pop('_scene_resource'); resource=resources[(ref['id'],ref['revision'])]
                matrix,scale=ref['matrix'],ref['scale']
                m['vertices']=[[(sum(matrix[r][k]*point[k] for k in range(3))+matrix[r][3])*scale for r in range(3)] for point in resource['vertices_local']]
                m['faces']=resource['faces'];m['edges']=resource['edges']
            decoded.append((inner['id'],capture))
        for saved in owner['captures']:
            capture=load(saved['capture'])
            check(name+': actual native resource expansion '+saved['role'],(saved['command']['id'],capture) in decoded and sha(read(saved['capture']))==saved['capture_sha256'])
        images=[base64.b64decode(c['data']) for c in response['result']['content'] if c['type']=='image']
        if name=='NEW_extreme':
            check(name+': precise unknown and no action',public['status']=='unknown' and public['observation_status']=='numeric_insufficient' and response['result']['isError'] is True and public['executed'] is False and public['verified'] is False and public['automatic_retry'] is False)
            check(name+': no fabricated main capture/pose/frame/witness',owner['main_capture_count']==0 and len(decoded)==1 and owner['post_main_readback_count']==1 and len(images)==0 and all(k not in public for k in ('binding','frames','facts','producer_frames')) and not (root/'MAIN_CAPTURE_01.json').exists())
            readback=load(owner['captures'][0]['capture'])
            slots[name]={'unknown':public,'readback_vertices':readback['meshes'][0]['vertices'],'frames':[]}
            continue
        capture=load(root/'MAIN_CAPTURE_01.json'); meshes=capture['meshes']; meta=capture['observation_target']; cp=meta['camera_plan']; binding=public['binding']
        target=meta['target_object_index']; mesh=meshes[target]; poses={p['name']:p for p in cp['views']}
        check(name+': main separate from readback',owner['main_capture_count']==1 and owner['post_main_readback_count']==1)
        normals=[]
        for face in mesh['faces']:
            p,q,r=[tuple(map(Q,mesh['vertices'][i])) for i in face]
            u=[b-a for a,b in zip(p,q)];v=[b-a for a,b in zip(p,r)]
            normals.append((u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]))
        check(name+': actual triangle normals support front direction',all(n[0]<0 and n[1]==n[2]==0 for n in normals) and public['facts']['regions'][0]['front_direction_world']==[-1,0,0])
        geometry,meshorder,ordered=source_geometry_identity(meshes)
        check(name+': geometry and camera identities',geometry==binding['geometry_identity'] and fp([{k:p[k] for k in ('name','direction_rational','view_matrix','projection_matrix','size_px')} for p in cp['views']])==binding['camera_identity'] and fp(cp)==binding['observation_target']['camera_plan_sha256'])
        clean_binding={k:v for k,v in binding.items() if k not in ('runtime_source_sha256','source_status','disk_status','source_check_scope','binding_sha256')}
        clean_binding['camera_specification']=cp
        check(name+': complete host binding rebuilt with actual camera',fp(clean_binding)==binding['binding_sha256'])
        check(name+': source revision bound to capture',binding['scene_revision']==capture['revision'] and binding['capture_state']==capture['capture_state'])
        frames=public['frames']; rows=[]
        check(name+': actual image count',len(frames)==len(images)==(2 if asset=='origin' else 1))
        for seq,(frame,png) in enumerate(zip(frames,images),1):
            png_file=read(frame['image_path']); npz=read(frame['arrays_path'])
            check(name+': producer byte receipts '+frame['view_name'],png==png_file and sha(png)==frame['image_sha256'] and sha(npz)==frame['arrays_sha256'])
            with np.load(io.BytesIO(npz),allow_pickle=False) as z: a={k:z[k].copy() for k in z.files}
            decoded_png=np.asarray(Image.open(io.BytesIO(png)).convert('RGB'))
            check(name+': PNG RGB equals NPZ '+frame['view_name'],np.array_equal(decoded_png,a['color']))
            offsets=np.cumsum([0]+[len(m['faces']) for m in meshes],dtype=np.int64)
            face_patch=np.full(int(offsets[-1]),-1,dtype=np.int32);face_patch[offsets[target]:offsets[target+1]]=0
            roiids=[r['roi_id'] for r in public['facts']['regions']]
            check(name+': raw face and ROI mapping '+frame['view_name'],np.array_equal(a['face_patch_offsets'],offsets) and np.array_equal(a['face_patch_ids'],face_patch) and a['patch_roi_ids'].tolist()==roiids)
            patch_id=fp({'version':'active-patch-owner-v1','roi_ids':roiids,'ordered_geometry':ordered,'face_patch_ids':[face_patch[i:j].tolist() for i,j in zip(offsets[:-1],offsets[1:])]})
            owner_id=fp(('active-dual-owner-v1','zero-based-global-source-triangles-in-mesh-order',patch_id,offsets.tolist()))
            check(name+': patch and owner digests '+frame['view_name'],patch_id==a['patch_mapping_identity'].item()==frame['patch_mapping_identity'] and owner_id==a['owner_mapping_identity'].item()==frame['owner_mapping_identity'])
            fid=fp(((geometry,binding['camera_identity']),'active-dual-owner-v1',owner_id,frame['view_name'],seq,sha(png)))
            image_ref='active-host-image:'+fp((binding['binding_sha256'],frame['view_name'],sha(png),patch_id,'active-dual-owner-v1',owner_id,fid))
            check(name+': frame/source/image reference '+frame['view_name'],fid==frame['frame_identity'] and image_ref==frame['image_ref'] and geometry==frame['scene_identity'] and meshorder==frame['mesh_order_identity'] and frame['host_binding_sha256']==binding['binding_sha256'] and frame['source_revision']==capture['revision'])
            foreground=a['owners']>=0; ids=a['triangle_ids'][foreground]
            check(name+': raw owners/source triangles/depth '+frame['view_name'],bool(np.all((ids>=0)&(ids<offsets[-1]))) and np.array_equal(np.searchsorted(offsets[1:],ids,side='right'),a['owners'][foreground]) and np.array_equal(face_patch[ids],a['patch_owners'][foreground]) and np.all(np.isfinite(a['depth'][foreground])&(a['depth'][foreground]>0)) and np.all(np.isposinf(a['depth'][~foreground])) and np.all(a['triangle_ids'][~foreground]==-1))
            patch=a['patch_owners']; color=a['color'].astype(np.int32); edges=np.zeros(patch.shape,dtype=bool)
            vertical=(patch[1:]!=patch[:-1])&(np.sum((color[1:]-color[:-1])**2,axis=2)>=576)
            horizontal=(patch[:,1:]!=patch[:,:-1])&(np.sum((color[:,1:]-color[:,:-1])**2,axis=2)>=576)
            edges[1:]|=vertical;edges[:-1]|=vertical;edges[:,1:]|=horizontal;edges[:,:-1]|=horizontal
            mask=patch==0; yy,xx=np.nonzero(mask)
            bounds=[int(xx.min()),int(yy.min()),int(xx.max()),int(yy.max())]
            dist=(2*xx-bounds[0]-bounds[2])**2+(2*yy-bounds[1]-bounds[3])**2;i=int(np.argmin(dist));anchor=[int(xx[i]),int(yy[i])]
            pixel=next(o for o in public['facts']['observations'] if o['view_name']==frame['view_name'])['pixel_rows'][0]
            front=sum(Q(x)*Q(y) for x,y in zip(public['facts']['regions'][0]['front_direction_world'],poses[frame['view_name']]['direction_rational']))>0
            detail={'view':frame['view_name'],'surface':len(xx),'boundary':int(np.count_nonzero(edges&mask)),'bounds':bounds,'anchor':anchor,'front':front}
            check(name+': independent pixel localization/readability '+frame['view_name'],pixel['visible_surface_pixels']==len(xx) and pixel['contrasting_boundary_pixels']==detail['boundary'] and pixel['visible_pixel_bounds']==bounds and pixel['visible_pixel_anchor']==anchor and pixel['front_facing']==front and pixel['readable']==(front and len(xx)>=16 and detail['boundary']>=4),detail)
            rows.append({'frame':frame,'pixels':detail,'arrays':a})
        if asset=='origin':
            left=ndc(poses['LEFT'],mesh['vertices'])
            check(name+': unobstructed origin inside final LEFT matrix',len(meshes)==1 and all(all(abs(c)<=1 for c in p) for p in left) and len(mesh['vertices'])==4 and mesh['faces']==[[0,2,1],[0,3,2]])
            evidence=public['facts']['region_evidence'][0]['complete_witness']
            check(name+': actual complete witness',public['facts']['inspection']['counts']['covered']==1 and evidence=={'pixel_row_index':0,'view_name':'LEFT'} and rows[1]['pixels']['front'])
        else:
            check(name+': correct unresolved target',public['facts']['inspection']['counts']['covered']==0 and public['facts']['region_evidence'][0]['complete_witness'] is None)
        if asset=='extreme':
            left=ndc(poses['LEFT'],mesh['vertices']); ymin=min(p[1] for p in left); ymax=max(p[1] for p in left)
            check(name+': actual exact matrix clipping',max(abs(ymin),abs(ymax))>1 and next(iter(public['target_view_classifications']['LEFT'].values()))['status']=='outside_frustum',{'min_y':str(ymin),'max_y':str(ymax),'min_y_float':float(ymin),'max_y_float':float(ymax)})
        if asset=='peripheral':
            near=next(m for m in meshes if m['name']=='M4_Near');d=Q(near['vertices'][0][0]); area=d*d/2
            check(name+': fixed target grid and blocker',mesh['name']=='M4_Far_00' and len(mesh['vertices'])==289 and len(mesh['faces'])==512 and set(map(tuple,mesh['vertices']))=={(1.,i/16,j/16) for i in range(17) for j in range(17)} and set(map(tuple,near['vertices']))=={(float(d),0.,0.),(float(d),1.,0.),(float(d),0.,1.)})
            check(name+': target area and unique triangles',sum(-n[0]/2 for n in normals)==1 and len({tuple(sorted(face)) for face in mesh['faces']})==512)
            blocker=next(iter(public['target_view_classifications']['LEFT'].values()))['first_blocker']
            p=tuple(tuple(map(Q,near['vertices'][i])) for i in near['faces'][0]);tri=min(p,p[1:]+p[:1],p[2:]+p[:2])
            check(name+': exact LEFT positive occlusion',area==Q(73786983304225,9223372036854775808) and str(area)==blocker['overlap_area_screen_exact'] and fp(tri)==blocker['triangle_geometry_id'])
        slots[name]={'capture':capture,'public':public,'frames':rows}

for asset in ('origin','peripheral'):
    old,new=slots['OLD_'+asset],slots['NEW_'+asset]
    check(asset+': identical ordered captured geometry',old['capture']['meshes']==new['capture']['meshes'])
    check(asset+': classifications unchanged',old['public']['target_view_classifications']==new['public']['target_view_classifications'])
    for a,b in zip(old['frames'],new['frames']):
        check(asset+': identical producer arrays and pixels '+a['frame']['view_name'],all(np.array_equal(a['arrays'][k],b['arrays'][k]) for k in a['arrays']) and a['pixels']==b['pixels'] and a['frame']['arrays_sha256']==b['frame']['arrays_sha256'] and a['frame']['frame_identity']==b['frame']['frame_identity'])
frozen=load(AUTHOR/'INPUTS.json')['camera_cases'][0]
extreme=slots['OLD_extreme']['capture'];actual=extreme['meshes'][0]['vertices']
check('extreme actual and post-error independent readback match frozen world',actual==frozen['world_vertices']==slots['NEW_extreme']['readback_vertices'])
offset=[r[3] for r in frozen['matrix_world'][:3]]
check('origin is same captured quantized geometry minus common origin',[[x-o for x,o in zip(p,offset)] for p in actual]==slots['OLD_origin']['capture']['meshes'][0]['vertices'])
tight=load('D:/hefe/verification/fixes/20261115_m4_target_001_review/source/camera_reachable.json')['world']['camera_plan']
cp=extreme['observation_target']['camera_plan'];ol=next(v for v in tight['views'] if v['name']=='LEFT');al=next(v for v in cp['views'] if v['name']=='LEFT')
directory=extreme['observation_target']['scene_directory'][0]['bounds_world_m']
check('tight vs actual span same; outward directory and eye/depth differ',al['span']==ol['span'] and al['eye']!=ol['eye'] and directory!=frozen['world_bounds'][0] and all(directory[0][k]<=min(p[k] for p in actual)<=max(p[k] for p in actual)<=directory[1][k] for k in range(3)))
summary={n:{'frame_count':len(s['frames']),'pixels':[r['pixels'] for r in s['frames']]} for n,s in slots.items()}
check('seven actual frames total',sum(s['frame_count'] for s in summary.values())==7)
result={'schema':'independent-camera-six-slot-quality-v1','checks':checks,'check_count':len(checks),'passed':all(c['passed'] for c in checks),'slots':summary,'pins':pins,'new_Blender_raster_model_product_calls':0,'limitations':['No independent re-rasterization of depth winners.','Saved raw producer receipts bind arrays to delivery; this is not a claim of continuous non-mutation.','Extreme capability remains unknown, not recovered.']}
(OUT/'RESULT.json').write_text(json.dumps(result,indent=2,default=str)+'\n',encoding='utf8')
print(json.dumps({'passed':result['passed'],'checks':len(checks),'pins':len(pins),'slots':summary}))
