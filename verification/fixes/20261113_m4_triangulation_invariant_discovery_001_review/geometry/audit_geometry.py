"""Independent data-only geometric certificates, recorded indices and actual pixels."""
from collections import Counter, defaultdict
from fractions import Fraction as F
import hashlib
import io
import json
from pathlib import Path
import numpy as np
from PIL import Image

B = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_triangulation_invariant_discovery_001')
O = Path(__file__).resolve().parent
INPUTS = {}
CHECKS = []


def raw(path):
    p = Path(path)
    if not p.is_absolute(): p = B / p
    data = p.read_bytes()
    INPUTS[str(p)] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    return data


def read(p): return json.loads(raw(p))
def sha(b): return hashlib.sha256(b).hexdigest()
def check(name, ok, details=None): CHECKS.append({'name': name, 'passed': bool(ok), 'details': details})
def vec(x): return tuple(map(F, x))
def sub(a, b): return tuple(x-y for x, y in zip(a, b))
def dot(a, b): return sum(x*y for x, y in zip(a, b))
def cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def det2(a, b, c): return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
def fp(x): return sha(json.dumps(x, default=str, sort_keys=True, separators=(',', ':')).encode())


def original_quad(mesh):
    vs = list(map(vec, mesh['vertices']))
    edge = Counter((t[i], t[(i+1)%3]) for t in mesh['triangles'] for i in range(3))
    boundary = [(a,b) for a,b in edge if (b,a) not in edge]
    assert len(boundary) == 4
    nxt = dict(boundary); first = min(nxt, key=lambda i: vs[i]); cycle = [first]
    for _ in range(3): cycle.append(nxt[cycle[-1]])
    assert nxt[cycle[-1]] == first
    q = tuple(vs[i] for i in cycle)
    assert dot(sub(q[1],q[0]), sub(q[3],q[0])) == 0
    assert sub(q[2],q[1]) == sub(q[3],q[0])
    return q


def certificate(mesh, q, n, hole=False):
    vs = list(map(vec, mesh['vertices'])); faces = mesh['triangles']
    u, v = sub(q[1],q[0]), sub(q[3],q[0]); normal = cross(u,v)
    uv = [(dot(sub(p,q[0]),u)/dot(u,u), dot(sub(p,q[0]),v)/dot(v,v)) for p in vs]
    assert all(tuple(q[0][k]+a*u[k]+b*v[k] for k in range(3))==p for p,(a,b) in zip(vs,uv))
    assert set(uv)=={(F(i,n), F(j,n)) for i in range(n+1) for j in range(n+1)}
    assert len(vs)==(n+1)**2 and len(set(uv))==len(vs)
    groups = defaultdict(list); incidence = defaultdict(list); area_vector=[F(0)]*3
    for t in faces:
        p = [uv[i] for i in t]
        assert len(set(t))==3 and all(0<=i<len(vs) for i in t)
        coords=[(int(a*n),int(b*n)) for a,b in p]
        cell=(min(x for x,y in coords), min(y for x,y in coords))
        assert max(x for x,y in coords)-cell[0] == max(y for x,y in coords)-cell[1] == 1
        assert det2(*p) == F(1,n*n)
        groups[cell].append(coords)
        c = cross(sub(vs[t[1]],vs[t[0]]),sub(vs[t[2]],vs[t[0]]))
        for k in range(3): area_vector[k]+=c[k]/2
        for i in range(3):
            a,b=t[i],t[(i+1)%3]; incidence[tuple(sorted((a,b)))].append((a,b))
    wanted={(i,j) for i in range(n) for j in range(n)}-({(1,1)} if hole else set())
    assert set(groups)==wanted
    for (i,j), triangles in groups.items():
        assert len(triangles)==2
        e=Counter((t[k],t[(k+1)%3]) for t in triangles for k in range(3))
        boundary={(a,b) for a,b in e if (b,a) not in e}
        a,b,c,d=(i,j),(i+1,j),(i+1,j+1),(i,j+1)
        assert boundary=={(a,b),(b,c),(c,d),(d,a)}
    bd=[]
    for edges in incidence.values():
        assert len(edges) in (1,2)
        if len(edges)==2: assert edges[0]==tuple(reversed(edges[1]))
        else: bd.append(edges[0])
    remaining=set(bd); loops=0
    while remaining:
        a,b=next(iter(remaining)); start=a
        while True:
            remaining.remove((a,b))
            if b==start:break
            successors=[edge for edge in remaining if edge[0]==b]
            assert len(successors)==1
            a,b=successors[0]
        loops+=1
    fraction=F(len(wanted),n*n)
    assert tuple(area_vector)==tuple(x*fraction for x in normal)
    assert loops==(2 if hole else 1)
    return {'vertices_verified':len(vs),'triangles_verified':len(faces),'cells_verified':len(groups),
            'unique_edges':len(incidence),'boundary_edges':len(bd),'boundary_loops':loops,
            'euler_characteristic':len(vs)-len(incidence)+len(faces),
            'filled_area_fraction_of_original':str(fraction),'filled_parameter_area':str(fraction),
            'oriented_area_vector':list(map(str,area_vector)), 'surface_equals_expected_quad':not hole,
            'all_shared_edges_oppositely_oriented':True,'all_referenced_points_coplanar':True,'front_unchanged':True}


manifest=read('INPUT_MANIFEST.json'); expected=read('proof/EXPECTED.json'); proof=read('proof/PROOF.json')
scenes={k:read(v['path']) for k,v in manifest['scenes'].items()}
controls={k:read(v['path']) for k,v in manifest['controls'].items()}
original=scenes['original']; cameras=read('inputs/CAMERAS.json')
sourcebase=B.parent/'m4_active_coverage_003/inputs'
check('original_source_bytes',raw('inputs/scene_original.json')==raw(sourcebase/'SCENE_GEOMETRY_RATIONAL.json'))
check('camera_source_bytes',raw('inputs/CAMERAS.json')==raw(sourcebase/'CAMERAS.json'))
quads={m['name']:original_quad(m) for m in original['objects'][:6]}
canon=[]
for oi,m in enumerate(original['objects'][:6]):
    q=quads[m['name']]; normal=cross(sub(q[1],q[0]),sub(q[3],q[0]))
    canon.append({'object_name':m['name'],'object_index':oi,'vertices':[list(map(str,p)) for p in q],
                  'normal':list(map(str,normal)),'roi_id':'roi_'+fp(q)[:24]})
canon.sort(key=lambda r:r['roi_id'])
check('canonical_regions_from_original',canon==expected['canonical_regions'])
certificates=[]
for key,scene in scenes.items():
    n=1 if key=='original' else (16 if '16' in key else 4)
    check(key+':counts',manifest['scenes'][key]['counts']=={'objects':len(scene['objects']),'vertices':sum(len(m['vertices']) for m in scene['objects']),'triangles':sum(len(m['triangles']) for m in scene['objects'])})
    check(key+':22_occluder_dictionaries',scene['objects'][6:]==original['objects'][6:])
    for mesh in scene['objects'][:6]:
        c=certificate(mesh,quads[mesh['name']],n)
        report=proof['reports'][key]['objects'][mesh['name']]
        check(key+':certificate:'+mesh['name'],all(report[k]==v for k,v in c.items()),c)
        certificates.append({'scene':key,'object':mesh['name'],**c})
rot=tuple(tuple(map(F,row)) for row in proof['proper_rotation']['matrix'])
check('rotation_exact_orthogonal',all(dot(rot[i],rot[j])==int(i==j) for i in range(3) for j in range(3)))
check('rotation_positive_determinant',dot(rot[0],cross(rot[1],rot[2]))==1)
baseq=quads['Obj_001']; rotatedq=tuple(tuple(dot(row,p) for row in rot) for p in baseq)
for key,q,hole in [('rotated_grid4',rotatedq,False),('hole_grid4',baseq,True)]:
    mesh=controls[key]['objects'][0]; c=certificate(mesh,q,4,hole)
    report=proof['reports'][key]
    check(key+':certificate',all(report[k]==v for k,v in c.items()),c)
    certificates.append({'scene':key,'object':mesh['name'],**c})
    if not hole:
        r={'object_name':mesh['name'],'object_index':0,'vertices':[list(map(str,p)) for p in q],
           'normal':list(map(str,cross(sub(q[1],q[0]),sub(q[3],q[0])))),
           'roi_id':'roi_'+fp(q)[:24],'triangle_indices':list(range(32))}
        check('rotated_control_expected_region',expected['controls'][key]['expected_regions']==[r])


def hull(points):
    pts=sorted(set(points)); lo=[]; hi=[]
    for seq,out in [(pts,lo),(list(reversed(pts)),hi)]:
        for p in seq:
            while len(out)>1 and det2(out[-2],out[-1],p)<=0:out.pop()
            out.append(p)
    return lo[:-1]+hi[:-1]


def axis_clip(poly,axis,value,sign):
    if not poly:return []
    out=[]
    for p,q in zip(poly,poly[1:]+poly[:1]):
        a,b=sign*(p[axis]-value),sign*(q[axis]-value)
        if a>=0:out.append(p)
        if (a<0<b) or (b<0<a):
            t=a/(a-b);out.append(tuple(p[k]+t*(q[k]-p[k]) for k in range(2)))
    return out


visibility={}
for pose in cameras['views']:
    dx,dy,dz=map(F,pose['direction_rational']);assert dz>0
    visibility[pose['name']]={}
    for r in canon:
        q=list(map(vec,r['vertices']));assert all(p[2]==0 for p in q)
        bbox=[(min(p[k] for p in q),max(p[k] for p in q)) for k in (0,1)]
        blocked=False
        for mesh in original['objects'][6:]:
            verts=list(map(vec,mesh['vertices']));assert all(p[2]>0 for p in verts)
            poly=hull([(p[0]-p[2]*dx/dz,p[1]-p[2]*dy/dz) for p in verts])
            for axis in (0,1):
                poly=axis_clip(poly,axis,bbox[axis][0],1);poly=axis_clip(poly,axis,bbox[axis][1],-1)
            if len(poly)>=3 and sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(poly,poly[1:]+poly[:1]))!=0:
                blocked=True;break
        value={'complete':not blocked,'status':'positive_area_occlusion' if blocked else 'complete'}
        visibility[pose['name']][r['roi_id']]=value
        exp=expected['geometry_by_view'][pose['name']][r['roi_id']]
        check('independent_visibility:'+pose['name']+':'+r['roi_id'],all(exp[k]==v for k,v in value.items()))

correct=read('runs/correctness/RESULTS.json');bench=read('runs/benchmark/RESULTS.json')
index_count=classification_count=region_count=0


def check_index(index,scene,label):
    global index_count,classification_count,region_count
    index_count+=1
    check(label+':region_count',len(index['regions'])==6)
    for got,want in zip(index['regions'],canon):
        region_count+=1
        check(label+':region:'+want['roi_id'],all(got[k]==v for k,v in want.items()) and got['triangle_indices']==list(range(len(scene['objects'][want['object_index']]['triangles']))))
    for name,rows in visibility.items():
        for rid,want in rows.items():
            got=index['classifications'][name][rid];classification_count+=1
            check(label+':visibility:'+name+':'+rid,all(got[k]==v for k,v in want.items()))
        mask=sum(1<<i for i,r in enumerate(canon) if rows[r['roi_id']]['complete'])
        check(label+':mask:'+name,index['view_masks'][name]==mask)


check('correctness_fourteen_rows',len(correct['rows'])==14)
for i,row in enumerate(correct['rows']):
    if 'index' in row:check_index(row['index'],scenes[row['scene']],'correctness_'+str(i))
    else:check('control_record:'+str(i),row['regions']==expected['controls'][row['control']]['expected_regions'])
for i,row in enumerate(bench['rows']):
    check_index(row['index'],scenes['grid16_permuted_alternating'],'benchmark_'+str(i))
check('benchmark_ten_rows',len(bench['rows'])==10)
legacy=read('runs/legacy/RESULTS.json')
for row in legacy['rows']:
    check('legacy_scope:'+row['scene'],row['discovered_count']==(6 if row['scene']=='original' else 0))

frames={};pixel_facts=[];chains=[]
for folder in sorted((B/'runs').glob('observe_*')):
    result=read(folder/'RESULTS.json'); scene=scenes[result['scene']]
    check_index(result['index'],scene,folder.name)
    check(folder.name+':two_new_frames',set(result['frames'])=={'SCENE','BACK'} and result['actual_chain_render_attempts']==2)
    covered=set()
    for step in result['steps']:
        view=step['view']; frame=result['frames'][view]
        file_record=read(Path(frame['PNG']).parent/'FRAME.json')
        check(folder.name+':'+view+':record_copy',frame==file_record)
        png=raw(frame['PNG']);npz=raw(frame['NPZ'])
        check(folder.name+':'+view+':PNG_binding',len(png)==frame['PNG_bytes'] and sha(png)==frame['PNG_sha256'])
        check(folder.name+':'+view+':NPZ_binding',len(npz)==frame['NPZ_bytes'] and sha(npz)==frame['NPZ_sha256'])
        with np.load(io.BytesIO(npz),allow_pickle=False) as z:arrays={k:z[k].copy() for k in z.files}
        rgb,owner,depth=arrays['color'],arrays['owners'],arrays['depth']
        check(folder.name+':'+view+':PNG_equals_RGB',np.array_equal(np.asarray(Image.open(io.BytesIO(png)).convert('RGB')),rgb))
        for k,a in arrays.items():
            row=frame['arrays'][k]
            check(folder.name+':'+view+':array:'+k,list(a.shape)==row['shape'] and str(a.dtype)==row['dtype'] and a.nbytes==row['nbytes'] and sha(a.tobytes())==row['sha256'])
        check(folder.name+':'+view+':depth',np.all(np.isfinite(depth[owner>=0])) and np.all(depth[owner>=0]>0) and np.all(np.isposinf(depth[owner<0])))
        color=rgb.astype(np.int64); boundary=np.zeros(owner.shape,dtype=bool)
        h=(owner[:,:-1]!=owner[:,1:]) & (np.sum((color[:,:-1]-color[:,1:])**2,axis=2)>=576)
        v=(owner[:-1,:]!=owner[1:,:]) & (np.sum((color[:-1,:]-color[1:,:])**2,axis=2)>=576)
        boundary[:,:-1]|=h;boundary[:,1:]|=h;boundary[:-1,:]|=v;boundary[1:,:]|=v
        readable=set()
        for r in canon:
            mask=owner==r['object_index'];surface=int(mask.sum());edge=int((mask&boundary).sum())
            counts={'visible_surface_pixels':surface,'contrasting_boundary_pixels':edge}
            claimed=next(p for p in frame['pixel_rows'] if p['roi_id']==r['roi_id'])
            check(folder.name+':'+view+':pixels:'+r['roi_id'],counts==frame['independent_counts'][r['roi_id']] and all(claimed[k]==value for k,value in counts.items()))
            pixel_facts.append({'chain':folder.name,'view':view,'roi_id':r['roi_id'],**counts})
            if surface>=16 and edge>=4:readable.add(r['roi_id'])
        complete={rid for rid,x in visibility[view].items() if x['complete']}
        delivered=complete&readable;added=delivered-covered;covered|=delivered
        receipt=step['receipt'];update=step['update']
        check(folder.name+':'+view+':current_receipt',receipt['image_sha256']==sha(png) and receipt['image_path']==frame['PNG'] and receipt['scene_identity']==result['index']['scene_identity'] and receipt['candidate_identity']==result['index']['candidate_identity'])
        check(folder.name+':'+view+':feedback',set(receipt['readable_roi_ids'])==readable and set(update['new_roi_ids'])==added and set(update['covered_roi_ids'])==covered and set(step['geometrically_complete_roi_ids'])==complete)
        frames[(result['scene'],result['variant'],view)]={'arrays':arrays,'png':png}
    allids={r['roi_id'] for r in canon};possible={rid for rows in visibility.values() for rid,x in rows.items() if x['complete']}
    final=result['final_state']
    check(folder.name+':final_state',final['observed_views']==['SCENE','BACK'] and final['state_updates']==2 and len(covered)==5 and set(final['covered_roi_ids'])==covered and set(final['unresolved_roi_ids'])==allids-covered and set(final['candidate_pool_uncovered_roi_ids'])==allids-possible)
    check(folder.name+':steps',[(s['view'],len(s['update']['new_roi_ids']),s['next_view']) for s in result['steps']]==[('SCENE',2,'BACK'),('BACK',3,None)])
    chains.append({'chain':folder.name,'covered':sorted(covered),'unresolved':sorted(allids-covered)})
depth_differences=[]
for scene in ('grid4_permuted_alternating','grid16_permuted_alternating'):
    for view in ('SCENE','BACK'):
        a,b=frames[(scene,'reference',view)],frames[(scene,'candidate',view)]
        check(scene+':'+view+':R_C_identical',a['png']==b['png'] and all(np.array_equal(a['arrays'][k],b['arrays'][k]) for k in a['arrays']))
for view in ('SCENE','BACK'):
    a,b=frames[('grid4_permuted_alternating','candidate',view)],frames[('grid16_permuted_alternating','candidate',view)]
    check(view+':density_RGB_owner_PNG_same',a['png']==b['png'] and all(np.array_equal(a['arrays'][k],b['arrays'][k]) for k in ['color','owners']))
    x,y=a['arrays']['depth'],b['arrays']['depth']; finite=np.isfinite(x)&np.isfinite(y)
    differences=int(np.sum(x[finite]!=y[finite]));max_abs=float(np.max(np.abs(x[finite]-y[finite])))
    check(view+':density_depth_finite_mask',np.array_equal(np.isfinite(x),np.isfinite(y)))
    depth_differences.append({'view':view,'different_finite_pixels':differences,'maximum_absolute_difference':max_abs})
check('geometry_and_pixel_denominators',len(certificates)==32 and index_count==24 and classification_count==864 and region_count==144 and len(pixel_facts)==48 and len(frames)==8)
result={'candidate_commit':'b638c499c049604902415965f500f50a9947d34f','checks':CHECKS,'total':len(CHECKS),
        'passed':sum(c['passed'] for c in CHECKS),'failed':[c for c in CHECKS if not c['passed']],
        'certificates':certificates,'independent_visibility':visibility,'complete_indices':index_count,
        'classification_rows':classification_count,'ROI_rows':region_count,'pixel_facts':pixel_facts,
        'chains':chains,'depth_differences':depth_differences,'new_model_CLI_actor_Blender_raster_calls':0,
        'candidate_or_author_validator_execution':0,'AL_binding':'own child bound, parent_read_only',
        'limitations':['Fixed grid construction certificates, not a general mesh-admission proof.',
        'Read actual depth arrays; did not reconstruct all pixel ray intersections or render again.',
        'Historical execution inferred from retained evidence and source identity reviewed by parent.']}
for name,value in [('RESULTS.json',result),('INPUTS.json',INPUTS)]:
    (O/name).write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode())
print(json.dumps({k:result[k] for k in ['total','passed','failed','complete_indices','classification_rows','ROI_rows','depth_differences']},ensure_ascii=False))
