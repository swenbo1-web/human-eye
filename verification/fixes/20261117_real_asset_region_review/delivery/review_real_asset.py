"""Independent saved-byte, current-source and explicitly sampled ray review."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
import base64
import copy
from fractions import Fraction as F
import hashlib
from io import BytesIO
import importlib.util
import json
from pathlib import Path
import sys

sys.path.insert(0,'D:/he_anchor_001/venv/Lib/site-packages')
import numpy as np
from PIL import Image

OUT=Path(__file__).resolve().parent
ROOT=Path('D:/he_m4_real_asset_region_001/sessions')
PREVIOUS=Path('D:/hefe/verification/fixes/20261117_source_region_review/delivery/review_source_region.py')
EXPECTED='18c55ae0b370c8fff8411914cce600cf02ab2f9a5962e70d277662cc9a2a0ce4'
assert hashlib.sha256(PREVIOUS.read_bytes()).hexdigest()==EXPECTED
spec=importlib.util.spec_from_file_location('_root_source_review_helpers',PREVIOUS)
S=importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)
CHECKS,PINS,FRAMES,RAY_CACHE=[],{str(PREVIOUS):EXPECTED},{},{}
S.H.CHECKS,S.H.PINS=CHECKS,PINS
require,read,raw,rows,sha=S.require,S.read,S.raw,S.rows,S.sha


def prepare_triangles(capture):
    triangles=[];owners=[];offsets=[0]
    for oi,mesh in enumerate(capture['meshes']):
        vertices=np.asarray(mesh['vertices'],dtype=float)
        faces=np.asarray(mesh['faces'],dtype=int)
        triangles.append(vertices[faces]);owners.extend([oi]*len(faces));offsets.append(offsets[-1]+len(faces))
    return np.concatenate(triangles),np.asarray(owners),np.asarray(offsets)


def pixel_rays(xs,ys,pose):
    inverse=np.linalg.inv(np.asarray(pose['view_matrix']))
    projection=np.asarray(pose['projection_matrix'])
    ndc_x=2*(np.asarray(xs)+.5)/511-1
    ndc_y=1-2*(np.asarray(ys)+.5)/511
    origins=inverse[:3,3]+(ndc_x/projection[0,0])[:,None]*inverse[:3,0]+(ndc_y/projection[1,1])[:,None]*inverse[:3,1]
    return origins,-inverse[:3,2],(np.abs(ndc_x)<=1)&(np.abs(ndc_y)<=1)


def nearest_samples(origins,direction,triangles,near,far):
    """World plane intersections and barycentric gradients, no rasterization."""
    a=triangles[:,0];e=triangles[:,1]-a;f=triangles[:,2]-a
    normal=np.cross(e,f);squared=np.einsum('ij,ij->i',normal,normal)
    denominator=normal@direction
    inverse_d=np.divide(1.,denominator,out=np.zeros_like(denominator),where=denominator!=0)
    gu=np.divide(np.cross(f,normal),squared[:,None],out=np.zeros_like(normal),where=squared[:,None]!=0)
    gv=np.divide(np.cross(normal,e),squared[:,None],out=np.zeros_like(normal),where=squared[:,None]!=0)
    plane=np.einsum('ij,ij->i',normal,a);au=np.einsum('ij,ij->i',a,gu);av=np.einsum('ij,ij->i',a,gv)
    du,dv=gu@direction,gv@direction
    best=np.full(len(origins),np.inf);winner=np.full(len(origins),-1,dtype=int);ambiguous=np.zeros(len(origins),dtype=bool)
    for start in range(0,len(origins),16):
        stop=min(start+16,len(origins));o=origins[start:stop]
        t=(plane-o@normal.T)*inverse_d
        u=o@gu.T-au+t*du;v=o@gv.T-av+t*dv
        minimum=np.minimum(np.minimum(u,v),1-u-v)
        valid=(denominator!=0)&(minimum>=-1e-8)&(t>=near)&(t<=far)&np.isfinite(t)
        candidates=np.where(valid,t,np.inf)
        indices=np.argmin(candidates,axis=1);ids=np.arange(stop-start);depth=candidates[ids,indices]
        best[start:stop]=depth;winner[start:stop]=np.where(np.isfinite(depth),indices,-1)
        close=np.zeros_like(valid)
        np.less_equal(np.abs(candidates-depth[:,None]),1e-8,out=close,where=np.isfinite(candidates)&np.isfinite(depth[:,None]))
        ambiguous[start:stop]=(np.count_nonzero(close,axis=1)>1)|(minimum[ids,indices]<=1e-8)
    return best,winner,ambiguous


def evidence_rays(full,capture,arrays):
    frame=full['frames'][0];pose=frame['pose']
    triangles,objects,offsets=prepare_triangles(capture)
    key=sha(([(m['vertices'],m['faces']) for m in capture['meshes']],pose,frame['arrays_sha256']))
    if key in RAY_CACHE:return RAY_CACHE[key]
    cube=next(i for i,m in enumerate(capture['meshes']) if m['name']=='Cube')
    region=next(i for i,m in enumerate(capture['meshes']) if m['object_id']==full['region_ref']['host_id'])
    owners,ids,depth=arrays['owners'],arrays['triangle_ids'],arrays['depth'];fg=owners>=0
    require(int(fg.sum())==261121 and np.all(owners[fg]==cube),'every delivered foreground belongs to Cube')
    yy,xx=np.indices((512,512))
    require(np.array_equal(fg,(xx<511)&(yy<511)),'exact511by511foreground pixel-center domain')
    ys,xs=np.nonzero(fg);origins,direction,inside=pixel_rays(xs,ys,pose)
    claimed=ids[fg];chosen=triangles[claimed]
    a=chosen[:,0];e=chosen[:,1]-a;f=chosen[:,2]-a;n=np.cross(e,f)
    denominator=n@direction
    t=np.einsum('ij,ij->i',a-origins,n)/denominator
    delta=origins+t[:,None]*direction-a
    squared=np.einsum('ij,ij->i',n,n)
    u=np.einsum('ij,ij->i',np.cross(f,n),delta)/squared
    v=np.einsum('ij,ij->i',np.cross(n,e),delta)/squared
    minimum=np.minimum(np.minimum(u,v),1-u-v)
    require(np.all(inside)&np.all(denominator!=0)&np.all(minimum>=-1e-8),'all declared source pixel memberships by independent plane/Gram')
    error=float(np.max(np.abs(t-depth[fg])))
    require(error<=1e-8 and np.all(t>=pose['near']) and np.all(t<=pose['far']),'all declared source pixel depths')
    light=np.asarray([.4,-.5,1.]);light/=np.linalg.norm(light)
    shade=.45+.55*np.abs(n@light)/np.linalg.norm(n,axis=1)
    expected_rgb=np.clip(shade[:,None]*[180,190,205],0,255).astype(np.uint8)
    require(np.array_equal(expected_rgb,arrays['color'][fg]),'all declared source normals match saved RGB')
    grid=np.floor((np.arange(16)+.5)*512/16).astype(int)
    gx=np.tile(grid,16);gy=np.repeat(grid,16)
    go,gd,gin=pixel_rays(gx,gy,pose)
    grid_depth,grid_face,grid_ambiguous=nearest_samples(go,gd,triangles,pose['near'],pose['far'])
    require(len(go)==256 and gin.all() and np.isfinite(grid_depth).all(),'256 fixed-grid all-scene ray hits')
    require(np.all(objects[grid_face]==cube) and np.max(np.abs(grid_depth-depth[gy,gx]))<=1e-8,'fixed-grid nearest depths and Cubeowner')
    certainty=~grid_ambiguous
    require(np.array_equal(grid_face[certainty],ids[gy,gx][certainty]),'fixed-grid unambiguous nearest source rows')
    selected=full['region_ref']['source_triangle_indices']
    centers=triangles[offsets[region]+np.array(selected)].mean(axis=1)
    view=np.asarray(pose['view_matrix']);inverse=np.linalg.inv(view)
    target_depth=-(centers@view[2,:3]+view[2,3])
    center_origins=centers+target_depth[:,None]*inverse[:3,2]
    cd,cf,ca=nearest_samples(center_origins,-inverse[:3,2],triangles,pose['near'],pose['far'])
    blocked=np.isfinite(cd)&(objects[cf]==cube)&(cd<target_depth-1e-8)
    require(len(centers)==748 and blocked.all(),'748 selected source centroids occluded by Cube all-scene nearest samples')
    box=np.asarray(capture['meshes'][cube]['vertices']);low,high=box.min(axis=0),box.max(axis=0)
    selected_vertices=np.asarray(full['facts']['region']['vertices_world_m'])
    require(np.all(selected_vertices>low)&np.all(selected_vertices<high),'all selected vertices strictly inside original Cube')
    result=dict(declared_source_member_pixels=len(xs),max_declared_source_depth_residual_m=error,
        fixed_grid_rays=256,grid_ambiguous=int(grid_ambiguous.sum()),selected_centroid_rays=748,
        occluded_centroids=int(blocked.sum()),nearest_sample_ray_triangle_pairs=(256+748)*len(triangles),
        all_scene_triangles=len(triangles),full_foreground_nearest_surface_claim=False)
    RAY_CACHE[key]=result
    return result


def check_frame(full,capture,label):
    frame=full['frames'][0];b=full['binding']
    require(frame['host_binding_sha256']==b['binding_sha256'] and frame['source_revision']==b['scene_revision']
            and frame['scene_identity']==b['geometry_identity'] and frame['candidate_identity']==b['camera_identity'],label+'/frame current source camera')
    png,npz=raw(frame['image_path']),raw(frame['arrays_path'])
    require(hashlib.sha256(png).hexdigest()==frame['image_sha256'] and hashlib.sha256(npz).hexdigest()==frame['arrays_sha256'],label+'/PNG NPZ SHA')
    with np.load(BytesIO(npz),allow_pickle=False) as z:arrays={k:z[k] for k in z.files}
    require(np.array_equal(np.asarray(Image.open(BytesIO(png))),arrays['color']),label+'/PNG equals saved RGB')
    for name,meta in frame['arrays'].items():
        a=arrays[name]
        require(meta==dict(dtype=str(a.dtype),shape=list(a.shape),nbytes=a.nbytes,sha256=hashlib.sha256(a.tobytes()).hexdigest()),label+'/array '+name)
    triangles,objects,offsets=prepare_triangles(capture)
    require(np.array_equal(arrays['face_patch_offsets'],offsets) and arrays['patch_roi_ids'].size==0
            and np.all(arrays['face_patch_ids']==-1) and np.all(arrays['patch_owners']==-1),label+'/generic empty patch/source offsets')
    fg=arrays['owners']>=0;t=arrays['triangle_ids'][fg];o=arrays['owners'][fg]
    require(np.array_equal(arrays['triangle_ids']>=0,fg) and np.all(t>=offsets[o]) and np.all(t<offsets[o+1]),label+'/all actual source indices')
    geometry=[(tuple(tuple(F(v) for v in p) for p in m['vertices']),tuple(tuple(f) for f in m['faces'])) for m in capture['meshes']]
    mapping=sha(dict(version='active-patch-owner-v1',roi_ids=(),ordered_geometry=geometry,
        face_patch_ids=[[-1]*len(m['faces']) for m in capture['meshes']]))
    owner=sha(('active-dual-owner-v1','zero-based-global-source-triangles-in-mesh-order',mapping,offsets.tolist()))
    require(frame['patch_mapping_identity']==mapping==arrays['patch_mapping_identity'].item()
            and frame['owner_mapping_identity']==owner==arrays['owner_mapping_identity'].item(),label+'/mapping hash preimages')
    fid=sha(((frame['scene_identity'],frame['candidate_identity']),frame['owner_schema'],owner,'SCENE',1,frame['image_sha256']))
    require(fid==frame['frame_identity'] and frame['image_ref']=='source-region-image:'+sha((full['region_ref']['region_id'],fid,frame['image_sha256'])),label+'/frame and source image ref preimages')
    pose=next(v for v in b['camera_specification']['views'] if v['name']=='SCENE')
    require(pose==frame['pose'],label+'/actual current camera')
    selected=np.asarray(full['facts']['region']['vertices_world_m']);center=(selected.min(axis=0)+selected.max(axis=0))/2
    view=np.asarray(pose['view_matrix']);projection=np.asarray(pose['projection_matrix'])
    require(np.array_equal(center,np.asarray(pose['target'])) and abs(pose['half_span_m']-np.max(np.abs((selected-center)@view[:2,:3].T))*1.1)<=1e-12,label+'/selected source local camera fit')
    camera=np.column_stack((selected,np.ones(len(selected))))@view.T
    ndc=camera@projection.T
    require(np.all(np.abs(ndc[:,:2])<1),label+'/all selected vertices in local XY viewport')
    vis=full['facts']['visibility']
    require(vis['selected_surface_pixels']==0 and vis['visible_source_triangle_indices']==[]
            and vis['unseen_source_triangle_indices']==full['region_ref']['source_triangle_indices']
            and vis['visible_pixel_bounds'] is None and vis['complete_witness'] is None
            and vis['unknown']==['complete_surface_visibility'],label+'/actual zero region visibility facts')
    require(full['status']=='complete' and full['observation_status']=='locally_observed' and vis['status']=='observed_samples',label+'/preserved misleading zero-sample status counterexample')
    record=evidence_rays(full,capture,arrays)
    FRAMES[frame['image_path']]=dict(frame_identity=fid,image_ref=frame['image_ref'],image_sha256=frame['image_sha256'],
        arrays_sha256=frame['arrays_sha256'],source_visibility='zero_selected_samples',ray_review=record)
    return record


def fresh_source_checks(capture,fresh,label):
    by_name={o['name']:o for o in fresh['objects']}
    require(fresh['source_sha256']=='614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d',label+'/fresh export original blend SHA')
    for mesh in capture['meshes']:
        source=by_name[mesh['name']];evaluated=source['evaluated'];matrix=source['matrix_world'];scale=fresh['unit_scale']
        world=[[(((matrix[k][0]*p[0]+matrix[k][1]*p[1])+matrix[k][2]*p[2])+matrix[k][3])*scale for k in range(3)] for p in evaluated['vertices']]
        require(world==mesh['vertices'] and evaluated['triangles']==mesh['faces'],label+'/fresh local+matrix reconstruct exact product binary64 '+mesh['name'])
        require(source['instance_id']==capture['host_identity']['object_instances'][mesh['object_id']],label+'/fresh current instance '+mesh['name'])
        if mesh['name']=='Cube':
            require(source['display']['hide_get'] is True and source['display']['hide_render'] is True
                    and source['display']['visible_get'] is False,label+'/original hidden Cube actual flags')
    return by_name


def review_session(session):
    captures=S.H.wire_captures(session);calls=rows(session/'PUBLIC_REQUESTS.jsonl');index={r['index']:r for r in rows(session/'product_full/INDEX.jsonl')}
    result=[]
    for c in calls:
        ordinal=c['internal_public_call_index'];label=session.name+'/'+str(ordinal)
        tx,rx=read(c['actual_TX_path']),read(c['actual_RX_path'])
        require(tx==c['request']==read(c['request_path']) and rx==c['response']==read(c['response_path']),label+'/actual TX RX unchanged')
        require(hashlib.sha256(raw(c['actual_TX_path'])).hexdigest()==c['actual_TX_sha256']
                and hashlib.sha256(raw(c['actual_RX_path'])).hexdigest()==c['actual_RX_sha256'],label+'/original actual wire SHA fields')
        require(sha(tx)==sha(c['request']) and rx['id']==tx['id'],label+'/response original request id')
        blocks=rx['result']['content'];public=json.loads(blocks[0]['text'])
        if rx['result']['isError']:
            require(session.name=='state' and ordinal in (2,4) and len(blocks)==1
                    and c.get('producer_archive') is None and c['producer_archive_index'] is None and ordinal not in index
                    and c['archive_before_sha256']==c['archive_after_sha256'] and public['error']=='source_region_ref_capture_generation_changed'
                    and public['automatic_retry'] is False and public['executed'] is False,label+'/stale exact error no image no archive no retry')
            result.append(dict(index=ordinal,error=public['error'],native=0,new_rasters=0))
            continue
        a=c['producer_archive'];require(a==index[a['index']] and hashlib.sha256(raw(a['path'])).hexdigest()==a['sha256'],label+'/same producer archive exact')
        full=read(a['path']);capture=S.current_capture(full,captures,label)
        require(len(capture['meshes'])==2 and sum(len(m['faces']) for m in capture['meshes'])==53276,label+'/complete current character and hidden Cube')
        S.binding_ref(full,capture,label);S.public_check(full,public,blocks,label)
        region=full['facts']['region']
        require(len(region['source_triangle_indices'])==748 and len(region['source_vertex_indices'])==410,label+'/whole748face410vertex selected range')
        state='initial' if session.name=='main' or ordinal==1 else 'moved' if ordinal==3 else 'restored'
        fresh=read(session/('SOURCE_'+state+'.json'));by_name=fresh_source_checks(capture,fresh,label)
        ray=check_frame(full,capture,label)
        result.append(dict(index=ordinal,full=full,capture=capture,native=1,new_rasters=full['work']['raster_attempts'],
            declared_source_members=ray['declared_source_member_pixels'],grid_rays=ray['fixed_grid_rays'],centroid_rays=ray['selected_centroid_rays']))
    return result


def main():
    main=review_session(ROOT/'main');state=review_session(ROOT/'state')
    public_first=json.loads(read(ROOT/'main/product_calls/call_001/RESPONSE.json')['result']['content'][0]['text'])
    repeat=read(ROOT/'main/product_calls/call_002/REQUEST.json')['params']['arguments']['query']
    require(repeat['region_ref']==public_first['region_ref'],'actual main repeat uses original public reference')
    for field in ('binding','region_ref','frames','facts','source_mapping'):
        require(main[0]['full'][field]==main[1]['full'][field],'main unchanged repeat '+field)
    require(main[1]['new_rasters']==0 and main[1]['full']['work']['frame_reuses']==1
            and main[1]['full']['work']['task_query']['result_cache_hit'] is True,'main repeat actual image and M3 cache hit')
    require([c['new_rasters'] for c in state]==[1,0,1,0,1],'state exact five request construction sequence')
    initial,moved,restored=[c for c in state if 'full' in c]
    for error in (state[1],state[3]):
        tx=read(ROOT/'state/product_calls'/('call_%03d'%error['index'])/'REQUEST.json')
        require(tx['params']['arguments']['query']['region_ref']==initial['full']['region_ref'],'old initial actual ref preserved in stale TX')
    for i,m in enumerate(initial['capture']['meshes']):
        n=moved['capture']['meshes'][i];r=restored['capture']['meshes'][i]
        expected=[[p[0]+.25,p[1],p[2]] if m['name']!='Cube' else p for p in m['vertices']]
        require(n['vertices']==expected and n['faces']==m['faces'],'actual only character moved +.25 '+m['name'])
        require(r['vertices']==m['vertices'] and r['faces']==m['faces'],'actual restored full geometry '+m['name'])
    require([c['full']['region_ref']['capture_generation']['revision'] for c in (initial,moved,restored)]==[1,2,3],'actual ref generations1/2/3')
    require(initial['full']['region_ref']['ordered_geometry_sha256']==restored['full']['region_ref']['ordered_geometry_sha256']
            and initial['full']['region_ref']['region_id']!=restored['full']['region_ref']['region_id'],'restore same geometry new current ref')
    calls=main+state
    totals=dict(public_requests=len(calls),native=sum(c['native'] for c in calls),new_rasters=sum(c['new_rasters'] for c in calls),
        unique_frame_files=len(FRAMES),stale=sum('error' in c for c in calls),declared_source_members=sum(c.get('declared_source_members',0) for c in calls),
        fixed_grid_rays=sum(c.get('grid_rays',0) for c in calls),selected_centroid_rays=sum(c.get('centroid_rays',0) for c in calls))
    require(totals==dict(public_requests=7,native=5,new_rasters=4,unique_frame_files=4,stale=2,
            declared_source_members=1305605,fixed_grid_rays=1280,selected_centroid_rays=3740),'exact delivery and sampled verification denominators')
    result=dict(status='passed_saved_delivery_source_state_with_real_image_gap',fixed_commit='828d1265a3434fd1b5fb97e4759acaedd9253bc0',
        checks=len(CHECKS),totals=totals,new_live=0,new_rasters=0,new_models=0,
        full_foreground_nearest_surface_claim=False,unique_ray_groups=len(RAY_CACHE),
        executed_unique_geometry_counts=dict(declared_source_members=sum(r['declared_source_member_pixels'] for r in RAY_CACHE.values()),
            fixed_grid_rays=sum(r['fixed_grid_rays'] for r in RAY_CACHE.values()),
            selected_centroid_rays=sum(r['selected_centroid_rays'] for r in RAY_CACHE.values()),
            sampled_ray_triangle_pairs=sum(r['nearest_sample_ray_triangle_pairs'] for r in RAY_CACHE.values())),frames=FRAMES,
        zero_sample_status_counterexample=dict(status='complete',observation_status='locally_observed',visibility='observed_samples',selected_surface_pixels=0),
        input_pins=PINS,assertions=CHECKS)
    (OUT/'RESULT.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf8')
    print(json.dumps(dict(status=result['status'],checks=result['checks'],totals=totals,unique_ray_groups=len(RAY_CACHE))))


if __name__=='__main__':
    try:main()
    except Exception as error:
        (OUT/'CURRENT_FAILURE.json').write_text(json.dumps(dict(error=repr(error),passed_checks=len(CHECKS),last_checks=CHECKS[-6:]),indent=2),encoding='utf8')
        raise
