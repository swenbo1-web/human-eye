"""Independent fixture/capture geometry review; never imports product or author oracle."""
from pathlib import Path
from fractions import Fraction as F
from collections import defaultdict, Counter
import hashlib, json, time

ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
TASK=ROOT/'verification/m4_active_observation_patch_ownership_001'
OUT=Path(__file__).resolve().parent
checks=[]; inputs={}; start=time.perf_counter_ns()
def js(p):
    b=Path(p).read_bytes();inputs[str(p)]=hashlib.sha256(b).hexdigest();return json.loads(b)
def ck(name,ok,detail=None):checks.append(dict(name=name,passed=bool(ok),detail=detail))
def vec(x):return tuple(F(v) for v in x)
def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def canonical(q):
    first=min(range(4),key=lambda i:q[i]);return q[first:]+q[:first]
def roi_id(q):return 'roi_'+hashlib.sha256(json.dumps(q,default=str,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:24]
archive=js(TASK/'EXTERNAL_ARCHIVE.json')
paths={r['original_relative_path']:ROOT/r['archive_path'] for r in archive['files']}
def archived(suffix):return js(next(v for k,v in paths.items() if k.endswith(suffix)))
split=js(TASK/'inputs/SPLIT.json');joined=js(TASK/'inputs/JOINED.json');expected=js(TASK/'inputs/EXPECTED_PATCHES.json')
captures=[archived('/server/CAPTURE_%02d.json'%i) for i in range(1,6)]
indexes=[archived('/server/INDEX_%02d.json'%i) for i in (1,2)]
objects=[];global_vertices=[];global_faces=[];regions=[];unsupported=[];offset=0
for oi,obj in enumerate(split['objects']):
    vertices=list(map(vec,obj['vertices']));faces=[tuple(f) for f in obj['triangles']]
    objects.append((vertices,faces));vo=len(global_vertices);global_vertices.extend(vertices)
    global_faces.extend(tuple(vo+i for i in f) for f in faces)
    groups=defaultdict(list)
    for fi,face in enumerate(faces):
        a,b,c=(vertices[i] for i in face);n=cross(sub(b,a),sub(c,a));axes=[i for i,v in enumerate(n) if v]
        ck(f'axis_plane:{oi}:{fi}',len(axes)==1)
        axis=axes[0];groups[(axis,a[axis])].append((fi,n))
    for (axis,plane),members in groups.items():
        ids=[fi for fi,_ in members];label=f'component:{oi}:{axis}:{plane}'
        if len(ids)==1:
            unsupported.append((oi,ids[0],offset+ids[0]));continue
        incidence=defaultdict(list)
        for fi in ids:
            f=faces[fi]
            for i in range(3):incidence[tuple(sorted((f[i],f[(i+1)%3])))].append((f[i],f[(i+1)%3],fi))
        neighbors={fi:set() for fi in ids};boundary=[]
        for edge,occ in incidence.items():
            ck(label+':edge_manifold:'+str(edge),len(occ) in (1,2))
            if len(occ)==2:
                ck(label+':edge_opposed:'+str(edge),occ[0][:2]==occ[1][1::-1])
                neighbors[occ[0][2]].add(occ[1][2]);neighbors[occ[1][2]].add(occ[0][2])
            else:boundary.append(occ[0][:2])
        seen={ids[0]};todo=[ids[0]]
        while todo:
            for fi in neighbors[todo.pop()]-seen:seen.add(fi);todo.append(fi)
        ck(label+':connected',seen==set(ids))
        points={vertices[i] for fi in ids for i in faces[fi]};a,b=((1,2),(2,0),(0,1))[axis]
        lo=[min(p[i] for p in points) for i in range(3)];hi=[max(p[i] for p in points) for i in range(3)]
        q=[]
        for u,v in [(lo[a],lo[b]),(hi[a],lo[b]),(hi[a],hi[b]),(lo[a],hi[b])]:
            p=list(lo);p[a]=u;p[b]=v;q.append(tuple(p))
        if members[0][1][axis]<0:q.reverse()
        q=canonical(q);normal=cross(sub(q[1],q[0]),sub(q[3],q[0]))
        ck(label+':same_winding',all(n[axis]*normal[axis]>0 for _,n in members))
        ck(label+':area',sum(n[axis] for _,n in members)==2*normal[axis])
        ck(label+':corners_exist',set(q)<=points)
        ck(label+':rectangular_boundary',all((vertices[i][a] in (lo[a],hi[a]) and vertices[j][a]==vertices[i][a]) or (vertices[i][b] in (lo[b],hi[b]) and vertices[j][b]==vertices[i][b]) for i,j in boundary))
        outgoing=Counter(i for i,j in boundary);incoming=Counter(j for i,j in boundary)
        ck(label+':boundary_cycle_degrees',outgoing==incoming and set(outgoing.values())=={1})
        regions.append(dict(roi_id=roi_id(q),object_index=oi,object_name=obj['name'],triangle_indices=ids,
            joined_triangle_indices=[offset+i for i in ids],vertices=q,normal=normal,axis=axis,plane=plane))
    offset+=len(faces)
regions.sort(key=lambda r:r['roi_id']);by_id={r['roi_id']:r for r in regions}
ck('independent_regions_138',len(regions)==138 and len(by_id)==138)
ck('independent_supported_3336',sum(len(r['triangle_indices']) for r in regions)==3336)
ck('independent_unknown_1',unsupported==[(4,0,48)])
ck('split_29_joined_1',len(split['objects'])==29 and len(joined['objects'])==1)
ck('flattened_vertices_1913',list(map(vec,joined['objects'][0]['vertices']))==global_vertices and len(global_vertices)==1913)
ck('flattened_triangles_3337',[tuple(f) for f in joined['objects'][0]['triangles']]==global_faces and len(global_faces)==3337)
for i,cap in enumerate(captures):
    fixture=split if i<2 else joined
    ck(f'capture{i+1}:object_count',len(cap['meshes'])==len(fixture['objects']))
    for oi,(mesh,obj) in enumerate(zip(cap['meshes'],fixture['objects'])):
        ck(f'capture{i+1}:geometry{oi}',list(map(vec,mesh['vertices']))==list(map(vec,obj['vertices'])) and mesh['faces']==obj['triangles'] and mesh['name']==obj['name'])
for case,index in zip(('split','joined'),indexes):
    ck(case+':ROI_set',[r['roi_id'] for r in index['regions']]==list(by_id))
    all_ids=[]
    for actual in index['regions']:
        row=by_id[actual['roi_id']];ids=row['triangle_indices'] if case=='split' else row['joined_triangle_indices']
        ck(case+':ROI:'+row['roi_id'],tuple(map(vec,actual['vertices']))==tuple(row['vertices']) and vec(actual['normal'])==row['normal'] and actual['triangle_indices']==ids and actual['object_index']==(row['object_index'] if case=='split' else 0))
    for support in index['patch_scope']:
        oi=support['object_index'];valid=[i for r in regions if case=='joined' or r['object_index']==oi for i in (r['joined_triangle_indices'] if case=='joined' else r['triangle_indices'])]
        unknown=[i for object_id,local,glob in unsupported if case=='joined' or object_id==oi for i in [glob if case=='joined' else local]]
        stated_unknown=[i for c in support['unsupported_components'] for i in c['triangle_indices']]
        total=len(global_faces) if case=='joined' else len(objects[oi][1])
        ck(case+':partition:'+str(oi),sorted(valid)==support['supported_triangle_indices'] and sorted(unknown)==sorted(stated_unknown) and support['source_triangle_count']==total and support['supported_triangle_count']==len(valid) and support['unsupported_triangle_count']==len(unknown) and sorted(valid+unknown)==list(range(total)))
for row in expected['regions']:
    own=by_id[row['roi_id']]
    ck('registered_expected:'+row['roi_id'],tuple(map(vec,row['quad']))==tuple(own['vertices']) and row['split_triangle_indices']==own['triangle_indices'] and row['joined_triangle_indices']==own['joined_triangle_indices'])

# Independent occlusion model: use independently proven complete planar polygons,
# project along the view direction onto each target's axis plane, and clip to its
# 2-D rectangle. This does not use product projected triangles/shadow/clip helpers.
def clip(poly,distance):
    result=[]
    for a,b in zip(poly,poly[1:]+poly[:1]):
        da,db=distance(a),distance(b)
        if da>=0:result.append(a)
        if (da<0 and db>0) or (da>0 and db<0):
            t=da/(da-db);result.append(tuple(x+t*(y-x) for x,y in zip(a,b)))
    return result
def positive_area(poly):
    return len(poly)>=3 and sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(poly,poly[1:]+poly[:1]))!=0
polygons=[(r['roi_id'],r['vertices']) for r in regions]
for oi,fi,glob in unsupported:polygons.append(('unknown_'+str(glob),[objects[oi][0][i] for i in objects[oi][1][fi]]))
visibility={};tests=0
for pose in indexes[0]['cameras']['views']:
    name=pose['name'];direction=vec(pose['direction_rational']);rows={}
    for row in regions:
        facing=dot(row['normal'],direction)
        if facing<=0:rows[row['roi_id']]='back_facing' if facing<0 else 'edge_on';continue
        axis=row['axis'];other=[i for i in range(3) if i!=axis];plane=row['plane'];denom=direction[axis]
        lower=[min(p[i] for p in row['vertices']) for i in other];upper=[max(p[i] for p in row['vertices']) for i in other]
        blocked=False
        for identity,polygon in polygons:
            if identity==row['roi_id']:continue
            ts=[(p[axis]-plane)/denom for p in polygon]
            if max(ts)<=0:continue
            points=clip(polygon,lambda p:(p[axis]-plane)/denom) if min(ts)<0 else polygon
            projected=[tuple(p[i]-direction[i]*((p[axis]-plane)/denom) for i in other) for p in points]
            if any(max(p[k] for p in projected)<lower[k] or min(p[k] for p in projected)>upper[k] for k in (0,1)):continue
            tests+=1
            for k in (0,1):
                projected=clip(projected,lambda p,k=k:p[k]-lower[k])
                projected=clip(projected,lambda p,k=k:upper[k]-p[k])
            if positive_area(projected):blocked=True;break
        rows[row['roi_id']]='positive_area_occlusion' if blocked else 'complete'
    visibility[name]=rows
    for case,index in zip(('split','joined'),indexes):
        for rid,status in rows.items():
            actual=index['classifications'][name][rid]
            ck(f'visibility:{case}:{name}:{rid}',actual['status']==status and actual['complete']==(status=='complete'),None if actual['status']==status else {'expected':status,'actual':actual})
        expected_mask=sum(1<<i for i,r in enumerate(regions) if rows[r['roi_id']]=='complete')
        ck(f'mask:{case}:{name}',index['view_masks'][name]==expected_mask)
ck('camera_policy_same',indexes[0]['cameras']==indexes[1]['cameras'])
ck('grouping_source_changes',indexes[0]['scene_identity']!=indexes[1]['scene_identity'])
front=by_id[expected['checkpoints']['SCENE_visible_front']['roi_id']];rear=by_id[expected['checkpoints']['SCENE_hidden_same_object_rear']['roi_id']]
ck('front_global_max_z',all(p[2]==max(v[2] for v in global_vertices) for p in front['vertices']))
ck('rear_at_z0',all(p[2]==0 for p in rear['vertices']))
front_obj=objects[front['object_index']][0];zmin=min(p[2] for p in front_obj);shift=(zmin*F(4,3),zmin*F(-4,3))
ck('strict_positive_depth_proof',zmin==F(237,2048) and shift==(F(79,512),F(-79,512)) and all(min(p[i] for p in front_obj)<v[i]+shift[i]<max(p[i] for p in front_obj) for v in rear['vertices'] for i in (0,1)))
ck('front_complete_rear_occluded',visibility['SCENE'][front['roi_id']]=='complete' and visibility['SCENE'][rear['roi_id']]=='positive_area_occlusion')
result=dict(schema='root-patch-geometry-independent-v1',passed=all(x['passed'] for x in checks),check_count=len(checks),failures=[x for x in checks if not x['passed']],checks=checks,
    regions=138,supported_triangles=3336,unsupported_triangles=1,visibility_rows=6*138*2,polygon_clips_tested=tests,
    method='Own exact Fraction axis-plane construction and view-direction projection/clipping of independently proved rectangle polygons. No product or author oracle imported.',
    new_product_Blender_raster_model_calls=0,input_sha256=inputs,elapsed_ns=time.perf_counter_ns()-start)
(OUT/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:v for k,v in result.items() if k not in ('checks','input_sha256')},ensure_ascii=False))
