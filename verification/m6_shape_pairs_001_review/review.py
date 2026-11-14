"""Independent equations, saved-output checks and one oracle-localization diagnostic."""
import os
for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[key] = '1'
import hashlib
import inspect
import json
from pathlib import Path
import time
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = HERE / 'snapshot/verification/m6_shape_pairs_001'
PRIVATE = BASE / 'private'
OLD = ROOT / 'verification/m6_real_data_001_review/snapshot/verification/m6_real_data_001'
checks = []


def check(name, ok):
    if not ok:
        raise AssertionError(name)
    checks.append(name)


def jsonread(path):
    return json.loads(path.read_bytes())


def error(ref, output, ids):
    if not len(ids):
        return {'count': 0, 'rmse_m': None, 'p95_m': None, 'max_m': None}
    delta = output[ids] - ref[ids]
    sq = np.einsum('ij,ij->i', delta, delta)
    norms = np.sqrt(sq)
    return {'count': len(ids), 'rmse_m': float(np.sqrt(sq.sum()/len(ids))),
            'p95_m': float(np.percentile(norms, 95)), 'max_m': float(norms.max())}


def shape_quality(ref, output, faces):
    p, q = ref[faces], output[faces]
    a = np.cross(p[:,1]-p[:,0], p[:,2]-p[:,0])
    b = np.cross(q[:,1]-q[:,0], q[:,2]-q[:,0])
    return {'degenerate': int(np.sum(np.linalg.norm(b, axis=1) == 0)),
            'normal_dot_negative': int(np.sum(np.einsum('ij,ij->i', a,b)<0))}


def fem_system(points, faces, free, adjacency):
    """Linear triangular basis gradients give the stiffness, no cotangent code."""
    f = sorted(free)
    rows = sorted(set(f) | {j for i in f for j in adjacency[i]})
    cols = sorted(set(rows) | {j for i in rows for j in adjacency[i]})
    mapping = {v:i for i,v in enumerate(cols)}
    incidence = faces[np.any(np.isin(faces,rows), axis=1)]
    k = np.zeros((len(cols),len(cols)))
    mass = np.zeros(len(cols))
    for tri in incidence:
        p = points[tri]
        c = np.cross(p[1]-p[0],p[2]-p[0])
        twice_area = np.linalg.norm(c)
        assert twice_area > 0
        unit = c/twice_area
        grad = np.cross(unit, np.array([p[2]-p[1],p[0]-p[2],p[1]-p[0]]))/twice_area
        local = [mapping[int(v)] for v in tri]
        k[np.ix_(local,local)] += (twice_area/2) * (grad @ grad.T)
        mass[local] += twice_area/6
    rowpos = [mapping[v] for v in rows]
    b = k[rowpos]/np.sqrt(mass[rowpos,None])
    fixed = [v for v in cols if v not in set(f)]
    left = b[:,[mapping[v] for v in f]]
    right = -b[:,[mapping[v] for v in fixed]] @ points[fixed]
    return left, right, f


def objread(path):
    v, f = [], []
    with path.open() as stream:
        for line in stream:
            if line.startswith('v '): v.append([float(x) for x in line.split()[1:]])
            if line.startswith('f '): f.append([int(x)-1 for x in line.split()[1:]])
    return np.asarray(v), np.asarray(f)


started, cpu = time.perf_counter(), time.process_time()
snapshot = jsonread(HERE/'SNAPSHOT.json')
for row in snapshot['source_files']:
    data = (HERE/'snapshot'/row['relative']).read_bytes()
    check('source '+row['relative'], len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256'])
for row in snapshot['manifest_checks']:
    if row['group']=='private_local_files':
        path = PRIVATE/Path(row['path']).name
        data = path.read_bytes()
        check('private '+path.name, len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256'])
labels = jsonread(PRIVATE/'LABELS.json')
author = jsonread(BASE/'RESULTS.json')
raw = jsonread(OLD/'private/capture_02/raw_selected.json')
reference = np.load(PRIVATE/'reference_vertices.npy', allow_pickle=False)
faces = np.load(PRIVATE/'triangles.npy', allow_pickle=False)
region = sorted(labels['region_ids'])
check('reference equals prior fixed export', np.array_equal(reference,raw['vertices_world']))
check('topology and source polygons equal prior export', np.array_equal(faces,raw['triangles']) and np.array_equal(np.load(PRIVATE/'source_polygon_ids.npy'),raw['polygon_ids_by_triangle']))
check('single source, seven development cases', len(labels['cases'])==7 and all(c['asset_group']==labels['asset_group'] for c in author['cases']))
inside = faces[np.all(np.isin(faces,region),axis=1)]
edge_rows = np.sort(np.concatenate((inside[:,[0,1]],inside[:,[1,2]],inside[:,[2,0]])),axis=1)
edges, counts = np.unique(edge_rows,axis=0,return_counts=True)
boundary = sorted(set(edges[counts==1].flat))
free = sorted(set(region)-set(boundary))
incident = np.flatnonzero(np.any(np.isin(faces,region),axis=1))
outside = sorted(set(range(len(reference)))-set(region))
check('region domain', len(region)==410 and len(boundary)==72 and len(free)==338 and len(incident)==898 and boundary==labels['boundary_ids'])
positions = {v:i for i,v in enumerate(region)}
dist = np.full((410,410),np.inf)
np.fill_diagonal(dist,0)
edge_lengths = np.linalg.norm(reference[edges[:,0]]-reference[edges[:,1]],axis=1)
for (a,b),length in zip(edges,edge_lengths):
    dist[positions[a],positions[b]]=dist[positions[b],positions[a]]=length
for k in range(410):
    dist = np.minimum(dist,dist[:,k,None]+dist[None,k,:])
center = 24205
distance = dist[positions[center]]
depth = float(distance[[positions[v] for v in boundary]].min())
center_tri = faces[np.any(faces==center,axis=1)]
q=reference[center_tri]
normal = np.cross(q[:,1]-q[:,0],q[:,2]-q[:,0]).sum(axis=0)
normal /= np.linalg.norm(normal)
check('independent all-pairs boundary distance and normal', abs(depth-labels['distance_to_boundary_m'])<1e-15 and np.max(np.abs(normal-labels['center_normal']))<1e-15)
check('mean edge normalization', abs(edge_lengths.mean()-labels['reference_mean_region_edge_length_m'])<1e-15)
adjacency = [set() for _ in reference]
for face in faces:
    a,b,c=map(int,face)
    adjacency[a].update((b,c)); adjacency[b].update((a,c)); adjacency[c].update((a,b))
namespace={'__name__':'fixed_author_method'}
exec(compile((BASE/'method.py').read_bytes(),str(BASE/'method.py'),'exec'),namespace)
method=namespace['reconstruct']
check('observations-only signature', list(inspect.signature(method).parameters)==['abnormal_vertices','triangles','allowed_region_ids'])
case_results=[]
oracle=[]
for case, report in zip(labels['cases'],author['cases']):
    cid=case['id']
    observed=np.load(PRIVATE/(cid+'_abnormal.npy'),allow_pickle=False)
    repaired=np.load(PRIVATE/(cid+'_repaired.npy'),allow_pickle=False)
    expected=reference.copy()
    if case['radius_m'] is not None:
        r=case['radius_ratio']*depth
        a=case['amplitude_ratio']*r
        support=[v for v in region if v not in boundary and distance[positions[v]]<r]
        for v in support:
            w=(1-(distance[positions[v]]/r)**2)**2
            expected[v]-=a*w*normal
    else:
        support=[]
    actual=np.flatnonzero(np.any(observed!=reference,axis=1)).tolist()
    check(cid+' independent synthetic labels', support==actual==case['true_support_ids'] and np.max(np.abs(expected-observed))<1e-15 and np.array_equal(np.load(PRIVATE/(cid+'_reference_displacement.npy')),reference-observed))
    check(cid+' boundary outside preservation', np.array_equal(repaired[boundary],reference[boundary]) and np.array_equal(repaired[outside],reference[outside]))
    check(cid+' changed sets', np.flatnonzero(np.any(repaired!=observed,axis=1)).tolist()==free and len(np.flatnonzero(np.any(np.isin(faces,free),axis=1)))==report['repair_actual_incident_faces'])
    errors={}
    for name, output, ids in [('no_op_region_error',observed,region),('repaired_region_error',repaired,region),('no_op_support_error',observed,support),('repaired_support_error',repaired,support)]:
        measured=error(reference,output,ids)
        check(cid+' '+name, all(measured[k]==v if v is None or k=='count' else abs(measured[k]-v)<1e-14 for k,v in report[name].items() if k in measured))
        errors[name]=measured
    q=shape_quality(reference,repaired,faces[incident])
    check(cid+' local triangles', q['degenerate']==report['repair_quality_vs_reference']['degenerate_output_triangles'] and q['normal_dot_negative']==report['repair_quality_vs_reference']['normal_reversal_dot_lt_zero'])
    left,right,free_order=fem_system(observed,faces,free,adjacency)
    residual=left@repaired[free_order]-right
    stationarity=float(np.linalg.norm(left.T@residual)/np.linalg.norm(left.T@right))
    check(cid+' independently assembled stationarity',stationarity<1e-10)
    replay={}
    if cid in ('sample_00','sample_06'):
        solved,_,rank,_=np.linalg.lstsq(left,right,rcond=None)
        check(cid+' independent solve',rank==338 and np.max(np.abs(solved-repaired[free_order]))<1e-11)
        observed.setflags(write=False); faces.setflags(write=False)
        replay_start=time.perf_counter()
        repeated,diagnostics=method(observed,faces,region)
        replay={'method_wall_s':time.perf_counter()-replay_start,'max_abs_difference_m':float(np.abs(repeated-repaired).max()),'rank':diagnostics['rank']}
        check(cid+' fixed author replay',np.max(np.abs(repeated-repaired))<1e-11)
    healthy=sorted(set(region)-set(support))
    healthy_sse=float(np.sum((repaired[healthy]-reference[healthy])**2))
    total_sse=float(np.sum((repaired[region]-reference[region])**2))
    saved_contacts={}
    for stage in ('damage','repair'):
        saved=jsonread(PRIVATE/(cid+'_'+stage+'_contact.json'))
        contact_report=report[stage+'_contact']
        check(cid+' saved '+stage+' query facts', saved['contact_complete']==contact_report['query_complete'] and saved['contact_ok']==contact_report['no_new_extra_pairs'] and len(saved['new_pairs'])==contact_report['new_pairs'] and len(saved['affected_face_ids'])==898)
        saved_contacts[stage]={'complete':saved['contact_complete'],'new_pairs':len(saved['new_pairs']),'shape_ok':saved['shape_ok']}
    case_results.append({'id':cid,'support_count':len(support),**errors,'healthy_region_count':len(healthy),'healthy_repair_rmse_m':error(reference,repaired,healthy)['rmse_m'],'healthy_share_of_final_error_sse':healthy_sse/total_sse,'independent_stationarity_relative':stationarity,'replay':replay,'saved_contacts':saved_contacts})
    # The single predeclared oracle intervention. Labels only select free vertices.
    if support:
        a,b,f=fem_system(observed,faces,support,adjacency)
        solution,_,rank,singular=np.linalg.lstsq(a,b,rcond=None)
        check(cid+' oracle system full rank',rank==len(support))
        output=observed.copy(); output[f]=solution
    else:
        output=observed.copy(); rank=0
    before=errors['no_op_region_error']['rmse_m']; after=error(reference,output,region)
    check(cid+' oracle healthy coordinates unchanged',np.array_equal(output[healthy],observed[healthy]) and np.array_equal(output[outside],observed[outside]))
    oracle.append({'id':cid,'free_vertices':len(support),'rank':int(rank),'region_error':after,'support_error':error(reference,output,support),'region_recovery_fraction':None if before==0 else 1-after['rmse_m']/before,'quality':shape_quality(reference,output,faces[incident]),'contact':'not_evaluated_diagnostic_not_accepted_repair'})
for name in ('reference.obj','sample_06_repaired.obj'):
    obj_vertices,obj_faces=objread(PRIVATE/name)
    expected=reference if name=='reference.obj' else np.load(PRIVATE/'sample_06_repaired.npy')
    check(name+' independent readback',np.array_equal(obj_vertices,expected) and np.array_equal(obj_faces,faces))
result={'cycle_id':'M6-SHAPE-PAIRS-001-REVIEW','fixed_delivery':snapshot['delivery_commit'],'status':'passed_evidence_reproduction_repair_baseline_rejected','checks':checks,'check_count':len(checks),'actual_case_count':7,'independent_assets':1,'center_count':1,'cases':case_results,'oracle_diagnostic':{'label_assisted':True,'deployable_or_learned_result':False,'method':'same position energy, true damaged vertices only free','cases':oracle},'cost':{'wall_s_after_imports':time.perf_counter()-started,'cpu_s_after_imports':time.process_time()-cpu,'performance_benchmark':False},'not_run':['author full 499-assertion program','second reconstruction family','training','cross-asset generalization','oracle contact and path acceptance','Blender or original edits','paid API']}
(HERE/'INDEPENDENT_RESULTS.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')
print(json.dumps({'status':result['status'],'checks':len(checks),'cost':result['cost'],'oracle':[{'id':x['id'],'rmse_mm':x['region_error']['rmse_m']*1000,'recovery':x['region_recovery_fraction']} for x in oracle]}))
