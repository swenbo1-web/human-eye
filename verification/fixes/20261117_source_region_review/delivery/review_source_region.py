"""Saved-only source-region delivery, source mapping and camera review."""
import base64
import copy
from fractions import Fraction as F
import hashlib
from io import BytesIO
import importlib.util
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, 'D:/he_anchor_001/venv/Lib/site-packages')
import numpy as np
from PIL import Image

OUT=Path(__file__).resolve().parent
ROOT=Path('D:/he_m4_m5_source_region_001/sessions')
HELPER=Path('D:/hefe/verification/fixes/20261117_m4_cross_scale_review/delivery/review_delivery.py')
HELPER_SHA='d8160a56b7c5012ded4a338af9ec3cd1572be400a876ecfbfbf82cbf5fff3320'
assert hashlib.sha256(HELPER.read_bytes()).hexdigest()==HELPER_SHA
spec=importlib.util.spec_from_file_location('_prior_root_delivery_helpers',HELPER)
H=importlib.util.module_from_spec(spec)
spec.loader.exec_module(H)
CHECKS,PINS,FRAMES=[],{str(HELPER):HELPER_SHA},{}
H.CHECKS,H.PINS=CHECKS,PINS
read,raw,rows,sha,require=H.read,H.raw,H.rows,H.sha,H.require
SCOPE='complete_selected_source_triangle_union_to_reference_triangle_surface'


def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])


def exact_membership(point,vertices,face):
    a,b,c=[tuple(map(F,vertices[i])) for i in face]
    e,f,d=sub(b,a),sub(c,a),sub(point,a)
    n=cross(e,f)
    area=dot(n,n)
    if not area or dot(n,d):return False
    u=dot(cross(f,n),d)
    v=dot(cross(n,e),d)
    return u>=0 and v>=0 and u+v<=area


def current_capture(full,captures,label):
    b=full['binding']
    found=[c for _,c in captures if c['revision']==b['scene_revision']
           and ('capture_state' not in b or c['capture_state']==b['capture_state'])]
    require(bool(found),label+'/actual current wire capture')
    require(len({sha(c) for c in found})==1,label+'/current capture unambiguous')
    return found[0]


def binding_ref(full,capture,label):
    b,ref=full['binding'],full['region_ref']
    appended={'runtime_source_sha256','source_status','disk_status','source_check_scope'}
    core={k:v for k,v in b.items() if k not in appended}
    require(sha({k:v for k,v in core.items() if k!='binding_sha256'})==b['binding_sha256'],label+'/binding hash preimage')
    excluded={'source_binding_sha256','binding_sha256','geometry_identity','camera_identity','camera_specification','ordered_geometry_sha256'}
    require(sha({k:v for k,v in core.items() if k not in excluded})==b['source_binding_sha256'],label+'/source hash preimage')
    require(sha(b['camera_specification'])==b['camera_identity'],label+'/complete camera identity')
    expected_objects=[dict(object_index=i,host_id=m['object_id'],object_name=m['name'],
        instance_id=capture['host_identity']['object_instances'][m['object_id']]) for i,m in enumerate(capture['meshes'])]
    require(b['objects']==expected_objects and b['document_epoch']==capture['host_identity']['document_epoch'],label+'/current ordered host instances')
    ordered=sha([dict(host_id=r['host_id'],instance_id=r['instance_id'],vertices=m['vertices'],faces=m['faces'])
        for r,m in zip(b['objects'],capture['meshes'])])
    require(ref['ordered_geometry_sha256']==b['ordered_geometry_sha256']==ordered,label+'/complete scene ordered geometry digest')
    require(ref['region_id']=='source-region:'+sha({k:v for k,v in ref.items() if k!='region_id'}),label+'/self contained ref identity')
    require(ref['document_epoch']==b['document_epoch'] and ref['capture_generation']=={k:b['capture_state'][k]
        for k in ('instance_id','epoch','revision')},label+'/ref current document generation')
    index=next(i for i,m in enumerate(capture['meshes']) if m['object_id']==ref['host_id'])
    require(ref['instance_id']==b['objects'][index]['instance_id'],label+'/ref current instance')
    mesh=capture['meshes'][index]
    faces=ref['source_triangle_indices']
    require(faces==sorted(set(faces)) and all(0<=i<len(mesh['faces']) for i in faces),label+'/canonical source triangles')
    source_faces=[mesh['faces'][i] for i in faces]
    vertex_indices=sorted({i for f in source_faces for i in f})
    compact={source:i for i,source in enumerate(vertex_indices)}
    mapping=dict(index_domain='zero_based_object_local_current_evaluated_capture_triangle_rows',
        submesh_to_source_triangle_indices=faces,submesh_to_source_vertex_indices=vertex_indices,
        triangles_source_vertices=source_faces,triangles_submesh_vertices=[[compact[i] for i in f] for f in source_faces])
    require(full['source_mapping']==mapping,label+'/complete subset/source triangle and vertex reverse map')
    fact=full['facts']['region']
    require(fact['source_triangle_indices']==faces and fact['source_vertex_indices']==vertex_indices
            and fact['triangles_source_vertices']==source_faces and fact['vertices_world_m']==[mesh['vertices'][i] for i in vertex_indices],
            label+'/public region actual captured arrays')
    return index,mesh,mapping


def measure(full,capture,label):
    task=full['task_result'] if full['result_kind']=='source_region' else full
    fact=task['facts']['surface_proximity']
    require(fact['status']=='measured' and fact['method']=='exact_binary64_triangle_surface_hulls_v3',label+'/measured M3 fact')
    value=fact['value'];witness=value['nearest_witness']
    a,b=tuple(map(F,witness['a'])),tuple(map(F,witness['b']))
    squared=dot(sub(b,a),sub(b,a))
    require(abs(value['distance_m']-math.sqrt(float(squared)))<=math.ulp(value['distance_m']),label+'/distance equals exact witness squared length')
    direction=np.array(witness['direction_a_to_b'])
    require(np.allclose(direction,np.array([float(x) for x in sub(b,a)])/value['distance_m'],rtol=0,atol=1e-15),label+'/A to B unit direction')
    if full['result_kind']=='source_region':
        require(task['region_ref']==full['region_ref'] and task['binding']==full['binding'] and task['measurement_scope']==SCOPE,label+'/whole selected surface scope and current source')
        left=next(m for m in capture['meshes'] if m['object_id']==full['region_ref']['host_id'])
        right=capture['meshes'][task['reference']['object_index']]
        require(task['reference']['object_id']==right['object_id'],label+'/reference current object')
        left_faces=full['region_ref']['source_triangle_indices']
        require(task['source_mapping']['region']==full['source_mapping'],label+'/measurement same source reverse map')
        for side,point,mesh,allowed in [('a',a,left,left_faces),('b',b,right,list(range(len(right['faces']))))]:
            members=[i for i in allowed if exact_membership(point,mesh['vertices'],mesh['faces'][i])]
            vertices=[i for i in {v for j in allowed for v in mesh['faces'][j]} if tuple(map(F,mesh['vertices'][i]))==point]
            source=task['source_mapping']['nearest_witness'][side]
            require(source['status']=='measured' and source['exact_membership'] is True
                    and source['source_triangle_indices']==members and sorted(source['source_vertex_indices'])==sorted(vertices)
                    and bool(members),label+'/exact all source membership '+side)
        reference=right['name']
        expected_sq=F(25,16) if reference=='Ref_B' else F(137,16)
        if full['binding']['capture_state']['revision']==2:expected_sq=F(5,4)
        require(squared==expected_sq,label+'/independent selected expected squared distance')
    else:
        expected_sq=F(1,1024) if task['binding']['objects'][1]['name']=='Ref_B' else F(2305,1024)
        require(squared==expected_sq,label+'/independent whole object expected squared distance')
    return dict(distance=value['distance_m'],witness_squared=str(squared),witness=witness)


def public_check(full,public,blocks,label):
    if public.get('schema')=='source-region-brief-v1':
        require(public['region_ref']==full['region_ref'] and public['task_result']==full['task_result'],label+'/brief exact ref measurement')
        require(public['region']==full['facts']['region'] and public['visibility']==full['facts']['visibility'],label+'/brief exact selected geometry visibility')
        require(public['binding']=={k:v for k,v in full['binding'].items() if k!='camera_specification'},label+'/brief current binding projection')
        require(public['measurement_scope']==SCOPE,label+'/brief selected complete measurement scope')
        expected_images=[dict(**{k:f[k] for k in ('image_ref','view_name','frame_identity','image_sha256','camera_identity','host_binding_sha256') if k in f},
                              image_block_index=i+1) for i,f in enumerate(full['frames'])]
        require(public['images']==expected_images,label+'/brief actual image indices')
        require({'scope':'actual_frame_visibility','reason':'complete_surface_visibility'} in public['unknowns'],label+'/curved complete visibility unknown')
    elif full['result_kind']=='source_region':
        compare=copy.deepcopy(public);compare.pop('image_delivery',None)
        original=copy.deepcopy(full);original.pop('image_delivery',None)
        require(compare==original,label+'/full returned original with delivery metadata only')
    elif full['result_kind']=='task_query':
        require(public==full,label+'/whole object control exact original task result')
    else:
        require(public['schema']=='active-observation-brief-v5',label+'/legacy actual v5')
    images=[x for x in blocks if x['type']=='image']
    require(len(images)==len(full.get('frames',[])),label+'/actual native count')
    for image,frame in zip(images,full.get('frames',[])):
        require(base64.b64decode(image['data'],validate=True)==raw(frame['image_path']),label+'/actual native equals saved PNG')


def frame_check(frame,full,capture,sequence,label):
    binding=full['binding']
    source=full['result_kind']=='source_region'
    require(frame['host_binding_sha256']==binding['binding_sha256'] and frame['source_revision']==binding['scene_revision']
            and frame['scene_identity']==binding['geometry_identity'] and frame['candidate_identity']==binding['camera_identity'],label+'/frame parent source camera')
    pose=next(p for p in binding['camera_specification']['views'] if p['name']==frame['view_name'])
    require(frame['pose']==pose,label+'/frame published pose')
    if source and 'qualification_R0/' not in label:
        points=np.asarray(full['facts']['region']['vertices_world_m'])
        center=(points.min(axis=0)+points.max(axis=0))/2
        require(np.array_equal(center,np.asarray(binding['camera_specification']['common_center_world_m'])),label+'/local center from selected source bounds')
        for camera in binding['camera_specification']['views']:
            view=np.asarray(camera['view_matrix']);projection=np.asarray(camera['projection_matrix'])
            corners=np.column_stack((points,np.ones(len(points))))
            xyz=(view@corners.T).T
            ndc=(projection@xyz.T).T
            expected_half=float(np.max(np.abs((points-center)@view[:2,:3].T)))*1.1
            require(np.array_equal(camera['target'],center) and abs(camera['half_span_m']-expected_half)<=2e-15,
                    label+'/selected-source fitted half span '+camera['name'])
            require(np.all(np.abs(ndc[:,:2])<1) and np.all(-xyz[:,2]>camera['near'])
                    and np.all(-xyz[:,2]<camera['far']),label+'/every selected vertex inside local frustum '+camera['name'])
            all_depths=[]
            for mesh in capture['meshes']:
                v=np.asarray(mesh['vertices']);low,high=v.min(axis=0),v.max(axis=0)
                bounds=np.array([[x,y,z,1] for x in (low[0],high[0]) for y in (low[1],high[1]) for z in (low[2],high[2])])
                all_depths.extend((-bounds@view[2]).tolist())
            require(min(all_depths)>camera['near'] and max(all_depths)<camera['far'],label+'/all88scene bounds corners within depth '+camera['name'])
    png,npz=raw(frame['image_path']),raw(frame['arrays_path'])
    require(hashlib.sha256(png).hexdigest()==frame['image_sha256'] and hashlib.sha256(npz).hexdigest()==frame['arrays_sha256'],label+'/actual PNG NPZ digest')
    with np.load(BytesIO(npz),allow_pickle=False) as z:arrays={k:z[k] for k in z.files}
    require(np.array_equal(np.array(Image.open(BytesIO(png))),arrays['color']),label+'/PNG decoded RGB exact')
    for name,meta in frame['arrays'].items():
        a=arrays[name]
        require(meta==dict(dtype=str(a.dtype),shape=list(a.shape),nbytes=a.nbytes,sha256=hashlib.sha256(a.tobytes()).hexdigest()),label+'/actual array '+name)
    meshes=capture['meshes'];offsets=np.cumsum([0]+[len(m['faces']) for m in meshes])
    regions=[] if source else full['facts']['scope']['patch_support']['regions']
    patch=np.full(offsets[-1],-1,dtype=np.int32)
    for i,r in enumerate(regions):patch[offsets[r['object_index']]+np.array(r['triangle_indices'])]=i
    require(np.array_equal(offsets,arrays['face_patch_offsets']) and np.array_equal(patch,arrays['face_patch_ids'])
            and arrays['patch_roi_ids'].tolist()==[r['roi_id'] for r in regions],label+'/frame independent source patch map')
    geometry=[(tuple(tuple(F(v) for v in p) for p in m['vertices']),tuple(tuple(f) for f in m['faces'])) for m in meshes]
    mapping=sha(dict(version='active-patch-owner-v1',roi_ids=tuple(r['roi_id'] for r in regions),ordered_geometry=geometry,
            face_patch_ids=[patch[offsets[i]:offsets[i+1]].tolist() for i in range(len(meshes))]))
    owner=sha(('active-dual-owner-v1','zero-based-global-source-triangles-in-mesh-order',mapping,offsets.tolist()))
    require(mapping==frame['patch_mapping_identity']==arrays['patch_mapping_identity'].item()
            and owner==frame['owner_mapping_identity']==arrays['owner_mapping_identity'].item(),label+'/frame mapping hash preimages')
    frameid=sha(((frame['scene_identity'],frame['candidate_identity']),frame['owner_schema'],owner,frame['view_name'],sequence,frame['image_sha256']))
    require(frameid==frame['frame_identity'],label+'/frame identity preimage')
    if source:ref='source-region-image:'+sha((full['region_ref']['region_id'],frameid,frame['image_sha256']))
    else:ref='active-host-image:'+sha((binding['binding_sha256'],frame['view_name'],frame['image_sha256'],mapping,frame['owner_schema'],owner,frameid))
    require(frame['image_ref']==ref,label+'/frame source image reference preimage')
    fg=arrays['owners']>=0;o=arrays['owners'][fg];t=arrays['triangle_ids'][fg]
    require(np.array_equal(arrays['triangle_ids']>=0,fg) and np.all(t>=offsets[o]) and np.all(t<offsets[o+1])
            and np.array_equal(arrays['patch_owners'][fg],patch[t]),label+'/all foreground source index scope')
    ray=H.rays(frame,meshes,arrays)
    visibility=None
    if source:
        ref=full['region_ref'];oi=next(i for i,m in enumerate(meshes) if m['object_id']==ref['host_id'])
        global_ids=offsets[oi]+np.array(ref['source_triangle_indices'])
        counts={int(face):int(np.count_nonzero(arrays['triangle_ids']==offsets[oi]+face)) for face in ref['source_triangle_indices']}
        mask=np.isin(arrays['triangle_ids'],global_ids)
        v=full['facts']['visibility'];seen=[i for i,c in counts.items() if c]
        require(v['selected_surface_pixels']==int(mask.sum()) and v['visible_source_triangle_indices']==seen
                and v['unseen_source_triangle_indices']==sorted(set(ref['source_triangle_indices'])-set(seen)),label+'/actual selected face pixel samples')
        require(v['complete_witness'] is None and v['unknown']==['complete_surface_visibility']
                and v['visibility_scope']=='actual_frame_source_triangle_samples',label+'/curved visibility remains unknown')
        require(v['frame_identity']==frameid and v['image_ref']==frame['image_ref'],label+'/visibility current frame')
        ys,xs=np.nonzero(mask)
        require(v['visible_pixel_bounds']==[int(xs.min()),int(ys.min()),int(xs.max()),int(ys.max())],label+'/actual selected pixel bounds')
        visibility=dict(counts=counts,total=int(mask.sum()),complete_witness=None,unknown=v['unknown'])
        require(arrays['patch_roi_ids'].size==0 and np.all(arrays['patch_owners']==-1),label+'/generic frame has zero rectangular patch dependency')
    FRAMES[frame['image_path']]=dict(frame_identity=frameid,PNG=frame['image_sha256'],NPZ=frame['arrays_sha256'],
        camera=pose,ray_review=ray,source_visibility=visibility)
    return arrays


def review_session(session):
    captures=H.wire_captures(session);calls=rows(session/'PUBLIC_REQUESTS.jsonl');index=rows(session/'product_full/INDEX.jsonl')
    by_index={i['index']:i for i in index}
    results=[]
    for call in calls:
        ordinal=call['internal_public_call_index'];label=session.name+'/'+str(ordinal)
        tx,rx=read(call['actual_TX_path']),read(call['actual_RX_path'])
        require(tx==call['request']==read(call['request_path']) and rx==call['response']==read(call['response_path']),label+'/actual public original objects')
        require(hashlib.sha256(raw(call['actual_TX_path'])).hexdigest()==call['actual_TX_sha256']
                and hashlib.sha256(raw(call['actual_RX_path'])).hexdigest()==call['actual_RX_sha256'],label+'/original wire SHA')
        require(tx['id']==rx['id'],label+'/original response id')
        blocks=rx['result']['content'];public=json.loads(blocks[0]['text'])
        archive=call.get('producer_archive')
        if rx['result']['isError']:
            require(ordinal in (6,8) and session.name=='state' and archive is None
                    and call['producer_archive_index'] is None and len(blocks)==1
                    and public['error']=='source_region_ref_capture_generation_changed'
                    and public['automatic_retry'] is False and public['executed'] is False,label+'/original stale error zero images no archive no retry')
            require(call['archive_before_sha256']==call['archive_after_sha256'] and ordinal not in by_index,label+'/stale no producer archive appended')
            results.append(dict(index=ordinal,error=public['error'],native_count=0,new_rasters=0))
            continue
        require(archive==by_index[call['producer_archive_index']] and archive['sha256']==hashlib.sha256(raw(archive['path'])).hexdigest(),label+'/same producer independent archive')
        full=read(archive['path']);capture=current_capture(full,captures,label)
        public_check(full,public,blocks,label)
        if full['result_kind']=='source_region':
            require(len(capture['meshes'])==11 and sum(len(m['vertices']) for m in capture['meshes'])==64
                    and sum(len(m['faces']) for m in capture['meshes'])==62,label+'/complete11objects64points62faces')
            binding_ref(full,capture,label)
            measured=measure(full,capture,label)
        elif full['result_kind']=='task_query':measured=measure(full,capture,label)
        else:measured=None
        for number,frame in enumerate(full.get('frames',[]),1):
            if frame['image_path'] not in FRAMES:frame_check(frame,full,capture,number,label)
        results.append(dict(index=ordinal,full=full,capture=capture,distance=measured,
            native_count=sum(b['type']=='image' for b in blocks),new_rasters=full.get('work',{}).get('raster_attempts',0)))
    return dict(session=session.name,calls=results)


def main():
    sessions=[review_session(p) for p in sorted(ROOT.iterdir()) if p.is_dir()]
    lookup={s['session']:s['calls'] for s in sessions}
    for name,calls in lookup.items():
        if name=='state':continue
        a,b=calls
        tx=read(ROOT/name/'product_calls/call_002/REQUEST.json')
        original_public=json.loads(read(ROOT/name/'product_calls/call_001/RESPONSE.json')['result']['content'][0]['text'])
        require(tx['params']['arguments']['query']['region_ref']==original_public['region_ref'],name+'/second actual request uses public returned ref')
        require(a['full']['region_ref']==b['full']['region_ref'] and a['full']['frames']==b['full']['frames']
                and a['full']['binding']==b['full']['binding'],name+'/reference switch preserves region camera image identity')
        require(a['new_rasters']==1 and b['new_rasters']==0 and b['full']['work']['frame_reuses']==1,name+'/cold1 hot0 frame construction')
    pairs=[]
    for i in (1,2,3):
        for j in (0,1):
            a,b=lookup[f'pair{i}_R0'][j],lookup[f'pair{i}_R1'][j]
            require(a['distance']==b['distance'],f'pair{i}/{j}/exact selected measurement and witness')
            fa,fb=a['full']['frames'][0],b['full']['frames'][0]
            require(fa['pose']==fb['pose'] and raw(fa['image_path'])==raw(fb['image_path']),f'pair{i}/{j}/exact selected camera PNG')
            with np.load(fa['arrays_path'],allow_pickle=False) as za,np.load(fb['arrays_path'],allow_pickle=False) as zb:
                require(za.files==zb.files and all(np.array_equal(za[k],zb[k]) for k in za.files),f'pair{i}/{j}/all actual NPZ fields equal')
        pairs.append(dict(pair=i,passed=True))
    original=lookup['qualification_R0'][0]['full']
    require(original['facts']['visibility']['selected_surface_pixels']==13
            and original['frames'][0]['pose']['span']>40,'original R0 global camera actual13px failure preserved')
    corrected=lookup['pair1_R0'][0]['full'];p=corrected['frames'][0]['pose']
    require(p['target']==[4.375,4.375,1.0625] and p['span']==1.1667261889578036,'corrected exact local center/span')
    require(FRAMES[corrected['frames'][0]['image_path']]['source_visibility']['counts']=={0:8427,1:13108,2:1869,3:2808},'corrected four source triangle counts')
    state=lookup['state']
    require([c['new_rasters'] for c in state]==[6,1,0,0,1,0,1,0,1,0,0],'state complete11request raster sequence')
    for j in (2,3):
        require(state[j]['full']['frames']==state[1]['full']['frames'],f'state{j+1}/full or changed reference same actual frame')
    base,moved,restored=[{m['name']:m for m in state[i]['capture']['meshes']} for i in (1,6,8)]
    for name in base:
        expected=[[p[0]+.25,p[1],p[2]] if name=='Obj_07' else p for p in base[name]['vertices']]
        require(moved[name]['vertices']==expected and moved[name]['faces']==base[name]['faces'],'actual only A moved +.25 '+name)
        require(restored[name]['vertices']==base[name]['vertices'] and restored[name]['faces']==base[name]['faces'],'actual restored geometry '+name)
    require([state[i]['full']['region_ref']['capture_generation']['revision'] for i in (1,6,8)]==[1,2,3], 'actual source ref generations1/2/3')
    require(state[1]['full']['region_ref']['region_id']!=state[8]['full']['region_ref']['region_id']
            and state[1]['full']['region_ref']['ordered_geometry_sha256']==state[8]['full']['region_ref']['ordered_geometry_sha256'], 'restored geometry new current ref identity')
    totals=dict(requests=sum(len(s['calls']) for s in sessions),native=sum(c['native_count'] for s in sessions for c in s['calls']),
        new_rasters=sum(c['new_rasters'] for s in sessions for c in s['calls']),frames=len(FRAMES),stale_errors=sum('error' in c for s in sessions for c in s['calls']))
    require(totals==dict(requests=25,native=26,new_rasters=17,frames=17,stale_errors=2),'total25RPC26native17constructed2stale')
    result=dict(status='passed',checks=len(CHECKS),fixed_commit='de884a2a44557fb3d01407c5e7c2883cc4aa749c',totals=totals,
        new_live=0,new_rasters=0,new_model_calls=0,paired=pairs,
        state=[dict(index=c['index'],new_rasters=c['new_rasters'],native=c['native_count'],error=c.get('error'),distance=c.get('distance')) for c in state],
        frames=FRAMES,unique_ray_checks=len(H.RAY_CACHE),input_pins=PINS,assertions=CHECKS)
    (OUT/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(status=result['status'],checks=result['checks'],totals=totals,unique_ray_checks=result['unique_ray_checks'])))


if __name__=='__main__':
    try:main()
    except Exception as error:
        (OUT/'CURRENT_FAILURE.json').write_text(json.dumps(dict(error=repr(error),passed_checks=len(CHECKS),last_checks=CHECKS[-6:]),indent=2),encoding='utf8')
        raise
