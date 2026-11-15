"""Independent numeric review; imports no author experiment/evaluation code."""
import os
for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[name] = '1'
import collections
import hashlib
import json
from pathlib import Path
import time
import numpy as np

START, CPU = time.perf_counter(), time.process_time()
HERE = Path(__file__).resolve().parent
SNAP = HERE / 'snapshot'
V = SNAP / 'verification'
B = V / 'm6_shape_objective_001'
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')
checks = 0
max_distance_error = 0.0

def read(p):
    return json.loads(Path(p).read_bytes())

def mapped(p):
    return SNAP / Path(p).relative_to(AUTHOR)

def arrays(p):
    with np.load(p, allow_pickle=False) as z:
        return {k: z[k].copy() for k in z.files}

def check(value, name):
    global checks
    checks += 1
    if not value:
        raise AssertionError(name)

def near(a, b, name, tolerance=2e-12):
    check(np.allclose(a, b, atol=tolerance, rtol=tolerance, equal_nan=False), name)

def edge_counts(faces):
    return collections.Counter(tuple(sorted((int(a), int(b))))
        for t in faces for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])))

def segment_min(q, vertices, edges):
    if not len(edges):
        return np.full(len(q), np.inf)
    e = np.asarray(edges, dtype=np.int64)
    a, d = vertices[e[:, 0]], vertices[e[:, 1]] - vertices[e[:, 0]]
    l2 = np.sum(d*d, axis=1)
    w = q[:, None] - a
    t = np.divide(np.sum(w*d, axis=2), l2, out=np.zeros(w.shape[:2]), where=l2>0)
    closest = a + np.clip(t, 0, 1)[..., None]*d
    return np.min(np.sum((q[:, None]-closest)**2, axis=2), axis=1)

def nearest(q, vertices, faces):
    """Voronoi-region closest point (vertex, edge, face); independent of projection/edge minimum meter."""
    tri = vertices[faces]
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    ab, ac = b-a, c-a
    deg = np.sum(np.cross(ab, ac)**2, axis=1) == 0
    out_d, out_c = [], []
    for start in range(0, len(q), 32):
        p = q[start:start+32, None]
        d1, d2 = np.sum((p-a)*ab, axis=2), np.sum((p-a)*ac, axis=2)
        d3, d4 = np.sum((p-b)*ab, axis=2), np.sum((p-b)*ac, axis=2)
        d5, d6 = np.sum((p-c)*ab, axis=2), np.sum((p-c)*ac, axis=2)
        va, vb, vc = d3*d6-d5*d4, d5*d2-d1*d6, d1*d4-d3*d2
        point = np.full(p.shape[:1]+(len(faces), 3), np.nan)
        done = np.broadcast_to(deg, d1.shape).copy()
        def put(condition, value):
            mask = condition & ~done
            point[mask] = np.broadcast_to(value, point.shape)[mask]
            done[mask] = True
        put((d1<=0)&(d2<=0), a)
        put((d3>=0)&(d4<=d3), b)
        t = np.divide(d1, d1-d3, out=np.zeros_like(d1), where=d1!=d3)
        put((vc<=0)&(d1>=0)&(d3<=0), a+t[..., None]*ab)
        put((d6>=0)&(d5<=d6), c)
        t = np.divide(d2, d2-d6, out=np.zeros_like(d2), where=d2!=d6)
        put((vb<=0)&(d2>=0)&(d6<=0), a+t[..., None]*ac)
        den = (d4-d3)+(d5-d6)
        t = np.divide(d4-d3, den, out=np.zeros_like(den), where=den!=0)
        put((va<=0)&(d4-d3>=0)&(d5-d6>=0), b+t[..., None]*(c-b))
        den = va+vb+vc
        v = np.divide(vb, den, out=np.zeros_like(den), where=den!=0)
        w = np.divide(vc, den, out=np.zeros_like(den), where=den!=0)
        put(~done, a+v[..., None]*ab+w[..., None]*ac)
        if np.any(deg):
            ids = np.flatnonzero(deg)
            best = np.full((len(p), len(ids)), np.inf)
            result = np.zeros(best.shape+(3,))
            for i, j in ((0, 1), (1, 2), (2, 0)):
                x, y = tri[ids, i], tri[ids, j]
                e = y-x
                l = np.sum(e*e, axis=1)
                t = np.divide(np.sum((p-x)*e, axis=2), l, out=np.zeros(best.shape), where=l>0)
                cp = x+np.clip(t, 0, 1)[..., None]*e
                dd = np.sum((p-cp)**2, axis=2)
                use = dd<best
                result[use], best[use] = cp[use], dd[use]
            point[:, ids] = result
        dd = np.sum((p-point)**2, axis=2)
        chosen = np.argmin(dd, axis=1)
        rows = np.arange(len(p))
        out_d.append(dd[rows, chosen]); out_c.append(point[rows, chosen])
    return np.concatenate(out_d), np.concatenate(out_c)

def stats(d2, saved, name):
    check(saved['requested_points']==len(d2) and saved['valid_points']==len(d2)
          and saved['invalid_points']==0 and saved['complete'], name+'_counts')
    if len(d2):
        near([np.mean(d2), np.sqrt(np.mean(d2)), np.quantile(np.sqrt(d2), .95), np.sqrt(max(d2))],
             [saved[k] for k in ('mean_squared_distance', 'RMSE', 'p95', 'max')], name, 2e-11)
    else:
        check(all(saved[k] is None for k in ('mean_squared_distance','RMSE','p95','max')), name+'_empty')

# Reconcile reused bytes against the previous independent snapshots, not only author-supplied SHA.
old_matches = collections.Counter(); missing = []
for row in read(B/'REUSED_INPUTS.json')['reused_input_files']:
    rel = Path(row['path']).relative_to(AUTHOR)
    found = False
    for name in ('m6_shape_observe_001_review', 'm6_shape_opt_001_review', 'm6_shape_train_001_review', 'm6_shape_data_001_review'):
        candidate = HERE.parent/name/'snapshot'/rel
        if candidate.is_file():
            check(hashlib.sha256(candidate.read_bytes()).hexdigest()==row['sha256'], 'old_identity_'+str(rel))
            old_matches[name] += 1; found = True; break
    if not found: missing.append(rel.as_posix())

# Independent meter closed forms and invariances.
tri = np.array([[0.,0,0], [1.,0,0], [0.,1,0]])
face = np.array([[0,1,2]])
q = np.array([[.2,.3,2], [.75,.75,0], [-1.,-1,0], [.3,.2,0], [.4,0,0]])
d2, _ = nearest(q, tri, face)
near(d2, [4,.125,2,0,0], 'closed_form_meter', 2e-11)
rot = np.array([[0.,-1,0], [1.,0,0], [0.,0,1]])
near(nearest(q@rot.T+[17,-8,3], tri@rot.T+[17,-8,3], face)[0], d2, 'common_rigid_meter', 2e-11)
perm = np.array([2,0,1]); inv = np.argsort(perm)
near(nearest(q, tri[perm], inv[face[:, ::-1]])[0], d2, 'reorder_meter', 2e-11)
near(nearest(np.array([[.5,1,0.]]), np.array([[0.,0,0],[1.,0,0],[2.,0,0]]), face)[0], [1], 'degenerate_segment')
near(nearest(np.array([[0.,0,1]]), np.zeros((3,3)), face)[0], [1], 'degenerate_point')

# All 306 targets from original inputs, with comparison against every private component.
decomp = read(B/'DECOMPOSITION.json')
data = read(V/'m6_shape_data_001/DATASET_INDEX.json')['cases']
public = read(V/'m6_shape_train_001/PUBLIC_DATASET_INDEX.json')['cases']
cases = {r['id']:r for r in data+[r for r in public if r['purpose']=='validation']}
check(len(cases)==348 and len(decomp['cases'])==306, 'observation_denominators')
energies = {}
for row in decomp['cases']:
    cid = row['id']; case = cases[cid]
    root = V/('m6_shape_data_001/private/patches' if case['purpose']=='development_train_pool' else 'm6_shape_train_001/private/public_data/patches')/case['patch_id']
    sample = cid.split('/')[-1]
    ref, obs = np.load(root/'reference_local.npy'), np.load(root/'observed'/(sample+'.npy'))
    support = arrays(root/'labels'/(sample+'.npz'))['damaged_mask']
    scale = float(arrays(root/'inputs'/(sample+'.npz'))['scale_m'])
    n = arrays(root/'inputs/sample_00.npz')['normals'].astype(np.float64)[support]
    n /= np.sqrt(np.sum(n*n, axis=1))[:, None]
    d = (ref-obs)[support]/scale
    dn = np.sum(d*n, axis=1)[:, None]*n
    dt = d-dn
    en = [float(np.sum(x*x)) for x in (d, dn, dt)]
    check(np.isfinite(n).all() and np.isfinite(d).all(), cid+'_valid')
    near(en, [row['total_target_energy'],row['normal_energy'],row['tangent_energy']], cid+'_energy')
    near(en[1]+en[2], en[0], cid+'_closure')
    near(en[2]/en[0], row['tangent_fraction_of_decomposable_target'], cid+'_fraction')
    counts = row['denominators']
    check(all(counts[k]==int(support.sum()) for k in ('support_points','valid_normal_points','finite_target_points','decomposable_points')), cid+'_counts')
    check(all(v==0 for k,v in counts.items() if k not in ('support_points','valid_normal_points','finite_target_points','decomposable_points')), cid+'_invalid_zero')
    saved = arrays(mapped(row['private_point_components']['path']))
    for key,value in [('target_normalized_float64',d),('reference_unit_normal',n),('normal_component',dn),('tangent_component',dt),('target_energy',np.sum(d*d,axis=1))]:
        near(saved[key], value, cid+'_'+key)
    source_ids = arrays(root/'mapping.npz')['context_source_ids'][support]
    check(np.array_equal(saved['source_vertex_ids'], source_ids), cid+'_source_ids')
    for k in ('valid_normal','finite_target','decomposable'):
        check(saved[k].shape==support[support].shape and saved[k].all(), cid+'_'+k)
    energies[cid] = en+[int(support.sum())]
for name, row in decomp['summaries'].items():
    e = np.array([energies[cid] for cid in row['case_ids']])
    check(row['case_count']==len(e) and row['denominators']['support_points']==int(e[:,3].sum()), name+'_counts')
    near(e[:,:3].sum(axis=0), [row['total_target_energy'],row['normal_energy'],row['tangent_energy']], name+'_energy')
    near(e[:,2].sum()/e[:,0].sum(), row['tangent_fraction_of_decomposable_target'], name+'_fraction')
    ratios = e[:,2]/e[:,0]
    dist = row['per_case_tangent_fraction']
    near([min(ratios),np.median(ratios),np.quantile(ratios,.95),max(ratios)], [dist[k] for k in ('minimum','median','p95','maximum')], name+'_distribution')

# Six fixed witness outputs, their legacy errors and full saved triangle surfaces.
surface = read(B/'SURFACE_RESULTS.json')
evidence = read(V/'m6_shape_observe_001/EVIDENCE_PLAN.json')['evidence']
check([c['case_id'] for c in surface['cases']]==[c['case_id'] for c in evidence], 'fixed_witness_selection')
training, optimized = read(V/'m6_shape_train_001/RESULTS.json'), read(V/'m6_shape_opt_001/RESULTS.json')
train = {r['id']:r for r in training['model_cases']}; opt = {r['id']:r for r in optimized['model_cases']}
base = {r['id']:r for r in training['baseline_cases']}
method_names = ('no_op','mls','train_final','opt_final_hard')
source_edges = {}; results = []; query_count = 0; cut_hits = 0; natural_hits = 0
for case in surface['cases']:
    cid = case['case_id']; original = train[cid]
    records = {'no_op':base[cid]['no_op'], 'mls':base[cid]['mls'], 'train_final':original, 'opt_final_hard':opt[cid]}
    obs, ref = np.load(mapped(original['observed_path'])), np.load(mapped(original['reference_path']))
    g, mapping = arrays(mapped(original['graph_path'])), arrays(mapped(original['mapping_path']))
    allowed, free, boundary = g['allowed_mask'], g['free_mask'], g['boundary_mask']
    folder = mapped(original['graph_path']).parent; sample = cid.split('/')[-1]
    if original['normal_control']:
        check(np.array_equal(obs,ref),cid+'_normal_control_zero_target')
        support = np.zeros(len(obs),dtype=bool)
    else:
        support = arrays(folder/'labels'/(sample+'.npz'))['damaged_mask']
    inp = arrays(folder/'inputs'/(sample+'.npz')); scale, origin = float(inp['scale_m']), inp['origin_world_m']
    faces = mapping['context_triangles']; source_ids = mapping['context_source_ids']
    edge_count = edge_counts(faces)
    edges = sorted(e for e,n in edge_count.items() if n==1)
    source = case['source']
    if source not in source_edges:
        with np.load(mapped(case['source_snapshot_used_only_for_boundary_topology'])) as z:
            source_edges[source] = edge_counts(z['triangles'])
    domains = {'all_context_boundary':edges, 'cut':[], 'natural_open':[], 'unknown':[]}
    for edge in edges:
        cnt = source_edges[source][tuple(sorted(int(source_ids[v]) for v in edge))]
        domains['cut' if cnt>1 else 'natural_open' if cnt==1 else 'unknown'].append(edge)
    check({k:len(v) for k,v in domains.items()}==case['boundary_edges'], cid+'_boundary_domain')
    incident_ids = mapping['incident_source_face_ids']
    incident_sel = np.isin(mapping['context_source_face_ids'], incident_ids)
    check(set(mapping['context_source_face_ids'][incident_sel])==set(incident_ids), cid+'_all_incident_covered')
    incident_faces = faces[incident_sel]
    actual_incident_ids = mapping['context_source_face_ids'][incident_sel]
    current_norm = np.cross(obs[incident_faces[:,1]]-obs[incident_faces[:,0]],obs[incident_faces[:,2]]-obs[incident_faces[:,0]])
    coord, surf, normal_fail, flips = {}, {}, {}, {}
    for method in method_names:
        m = case['methods'][method]; old = records[method]; legacy = m['legacy']
        candidate = np.load(mapped(m['candidate_path']))
        check(m['candidate_path']==old['candidate_path'], cid+'_'+method+'_candidate_identity')
        for key in ('errors','incident_quality','fixed_bitwise_preserved','boundary_bitwise_preserved','outside_allowed_bitwise_preserved','actual_changed_vertices','actual_changed_free_vertices','actual_changed_fixed_vertices','fallback_noop','fallback_reason','support_rmse_ratio_to_noop','allowed_improvement_to_noop'):
            check(legacy[key]==old[key], cid+'_'+method+'_legacy_'+key)
        err = np.sqrt(np.sum((candidate-ref)**2,axis=1))
        for name, mask in {'A':allowed,'S':support,'N':allowed&~support,'N_F':free&~support}.items():
            e = err[mask]/scale; record = legacy['errors'][name]
            check(record['count']==len(e), cid+'_'+method+'_'+name+'_count')
            if len(e): near([np.sqrt(np.mean(e*e)),np.quantile(e,.95),max(e)], [record[k] for k in ('rmse_over_scale','p95_over_scale','max_over_scale')], cid+'_'+method+'_'+name)
        changed = np.any(candidate!=obs, axis=1)
        for name, mask in [('fixed',~free),('boundary',boundary),('outside_allowed',~allowed)]:
            check(legacy[name+'_bitwise_preserved']==bool(np.array_equal(candidate[mask],obs[mask])), cid+'_'+method+'_'+name)
        check(legacy['actual_changed_vertices']==int(changed.sum()), cid+'_'+method+'_changed')
        normals = np.cross(candidate[incident_faces[:,1]]-candidate[incident_faces[:,0]],candidate[incident_faces[:,2]]-candidate[incident_faces[:,0]])
        reversed_ids = actual_incident_ids[np.sum(normals*current_norm,axis=1)<0]
        new_degenerate = actual_incident_ids[(np.sum(normals*normals,axis=1)==0)&(np.sum(current_norm*current_norm,axis=1)>0)]
        check(set(reversed_ids)==set(legacy['incident_quality']['reversed_source_face_ids']), cid+'_'+method+'_reversals')
        check(set(new_degenerate)==set(legacy['incident_quality']['new_degenerate_source_face_ids']), cid+'_'+method+'_degeneration')
        coord[method] = float(np.sqrt(np.mean((err[allowed]/scale)**2)))
        normal_fail[method] = not legacy['original_normal_point_preservation_passed']
        flips[method] = len(reversed_ids)
        cn, rn = (candidate-origin)/scale, (ref-origin)/scale
        means = []
        for direction,q,vertices in [('candidate_to_reference',cn[allowed],rn),('reference_to_candidate',rn[allowed],cn)]:
            record = m[direction]; saved = arrays(mapped(record['detail_path']))
            d2, closest = nearest(q,vertices,faces)
            max_distance_error = max(max_distance_error,float(np.max(np.abs(d2-saved['distance2']))))
            near(d2,saved['distance2'],cid+'_'+method+'_'+direction+'_all_distances',2e-11)
            near(q,saved['query_normalized'],cid+'_'+method+'_query')
            check(np.array_equal(saved['query_source_ids'],source_ids[allowed]) and saved['valid'].all(),cid+'_query_ids_valid')
            # Verify saved witness feasibility independently of triangle-ID tie choices.
            bary = saved['barycentric']; chosen = vertices[faces[saved['triangle_id']]]
            near(np.sum(chosen*bary[:,:,None],axis=1),saved['closest_normalized'],cid+'_barycentric_point',2e-11)
            check(float(np.min(bary))>=-2e-12,cid+'_triangle_membership')
            near(np.sum(bary,axis=1),1,cid+'_barycentric_sum')
            near(np.sum((q-saved['closest_normalized'])**2,axis=1),d2,cid+'_witness_distance',2e-11)
            stats(d2,record['distance'],cid+'_surface_stats')
            means.append(float(np.mean(d2))); query_count += len(q)
            tolerance=64*np.finfo(float).eps*max(1,float(np.abs(vertices).max()))
            near(tolerance,record['boundary_length_tolerance'],cid+'_boundary_tol')
            for kind,e in domains.items():
                hits=segment_min(closest,vertices,e)<=tolerance**2
                check(np.array_equal(hits,saved[kind+'_nearest_point_flag']),cid+'_'+method+'_'+direction+'_'+kind+'_hits')
                bstats=record['boundary_classification'][kind]
                check(int(hits.sum())==bstats['nearest_point_on_boundary_count'],cid+'_boundary_count')
                stats(d2[hits],bstats['query_distance_for_boundary_hits'],cid+'_boundary_subset')
                if kind=='cut': cut_hits+=int(hits.sum())
                if kind=='natural_open': natural_hits+=int(hits.sum())
            diag=record['metric_domain_diagnostics']
            tri=vertices[faces]; cross=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
            check(diag['query_count']==len(q) and diag['triangle_count']==len(faces) and diag['available_query_count']==len(q),cid+'_metric_denominator')
            check(diag['degenerate_triangle_count']==int(np.count_nonzero(np.sum(cross*cross,axis=1)==0)),cid+'_metric_degenerate')
            check(all(diag[k]==0 for k in ('invalid_query_count','numeric_unavailable_query_count','nonfinite_surface_vertex_count','numeric_nonfinite_triangle_count')),cid+'_metric_nonfinite')
        surf[method]=float(np.sqrt(np.mean(means)))
        near(surf[method],m['symmetric_RMSE'],cid+'_'+method+'_symmetric',2e-11)
    coord_best={k for k,v in coord.items() if v==min(coord.values())}
    surf_best={k for k,v in surf.items() if v==min(surf.values())}
    check(coord_best==surf_best,cid+'_best_sets')
    results.append({'case':cid,'coordinate_A':coord,'symmetric_surface_RMSE':surf,'best_methods':sorted(coord_best),'normal_protection_failures':normal_fail,'reversed_faces':flips})

check(query_count==18432 and cut_hits==0,'surface_denominators_cut')
result={'status':'passed_independent_numeric_review','assertions':checks,'target_cases':306,'support_points':sum(v[3] for v in energies.values()),
        'decomposition_groups':len(decomp['summaries']),'reference_normals':'42 saved sample00 patches; supervision only',
        'previous_snapshot_identity_matches':dict(old_matches),'previous_snapshot_identity_missing':missing,
        'witnesses':6,'saved_candidates':24,'directed_queries':query_count,'cut_boundary_hits':cut_hits,'natural_boundary_hits':natural_hits,
        'maximum_squared_distance_absolute_difference':max_distance_error,'metric_QA_assertions':5,'cases':results,
        'training':0,'model_forwards':0,'new_repair_candidates':0,'Bunny_arrays':0,
        'body_wall_s_before_write':time.perf_counter()-START,'body_CPU_s_before_write':time.process_time()-CPU,
        'limits':['six old witnesses only; not future loss training','finite query vertices and saved context triangle domains','full task cost not measured']}
(HERE/'INDEPENDENT_RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k not in ('cases','previous_snapshot_identity_missing')},ensure_ascii=False))
