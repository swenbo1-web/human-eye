"""Check existing topology/labels and one analytic normal-offset counterexample."""
import os
for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[key] = '1'
from collections import defaultdict, deque, Counter
import hashlib
import json
from pathlib import Path
import time
import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'm6_shape_observe_001_review' / 'snapshot' / 'verification'
START, CPU = time.perf_counter(), time.process_time()
READS = {}
def load_json(path):
    data = path.read_bytes()
    READS[str(path.relative_to(BASE))] = hashlib.sha256(data).hexdigest()
    return json.loads(data)
def arrays(path):
    READS[str(path.relative_to(BASE))] = hashlib.sha256(path.read_bytes()).hexdigest()
    with np.load(path, allow_pickle=False) as data:
        return {k: data[k].copy() for k in data.files}

dev = load_json(BASE / 'm6_shape_data_001/DATASET_INDEX.json')['cases']
val = [c for c in load_json(BASE / 'm6_shape_train_001/PUBLIC_DATASET_INDEX.json')['cases'] if c['purpose'] == 'validation']
cal = load_json(BASE / 'm6_shape_opt_001/LOC_CALIBRATION.json')
old_outputs = load_json(BASE / 'm6_shape_opt_001/EVAL_FINAL_HARD.json')
previous = {c['id']: c for c in old_outputs['development']['cases']}
cases = sorted(dev + val, key=lambda c: c['id'])
all_adjacency, rings, records, metadata = {}, {}, [], []
patches = {}
for case in cases:
    if case['normal_control']:
        continue
    source = case['source']
    if source not in all_adjacency:
        rel = ('m6_shape_train_001/private/public_data/sources/Stanford_Armadillo/snapshot.npz'
               if case['purpose'] == 'validation' else f'm6_shape_data_001/private/{source}/snapshot.npz')
        data = arrays(BASE / rel)
        adj = [set() for _ in data['vertices']]
        for a, b, c in data['triangles']:
            a, b, c = int(a), int(b), int(c)
            adj[a].update((b, c)); adj[b].update((a, c)); adj[c].update((a, b))
        all_adjacency[source] = adj
        metadata.append({'source': source, 'vertices': len(adj), 'triangles': len(data['triangles'])})
    patch = case['patch_id']
    folder = (BASE / ('m6_shape_train_001/private/public_data/patches' if case['purpose'] == 'validation' else 'm6_shape_data_001/private/patches')) / patch
    if patch not in patches:
        patches[patch] = arrays(folder / 'mapping.npz')['context_source_ids']
    ids = patches[patch]
    labels = arrays(folder / 'labels' / (case['id'].split('/')[-1] + '.npz'))
    damaged = np.flatnonzero(labels['damaged_mask'])
    support = set(int(x) for x in ids[damaged])
    # Label-selected central witness is an audit, never an online detector.
    energy = np.sum(labels['target_normalized'][damaged].astype(float)**2, axis=1)
    center = int(ids[damaged[np.argmax(energy)]])
    fractions, contaminated, center_record = [], 0, None
    for i in sorted(support):
        key = (source, i)
        if key not in rings:
            distances = {i: 0}; queue = deque([i]); adj = all_adjacency[source]
            while queue:
                j = queue.popleft(); hop = distances[j]
                if hop == 10:
                    continue
                for k in adj[j]:
                    if k not in distances:
                        distances[k] = hop + 1; queue.append(k)
            rings[key] = frozenset(k for k, hop in distances.items() if 6 <= hop <= 10)
        ring = rings[key]
        hits = len(ring & support)
        fractions.append(hits / len(ring) if ring else None)
        contaminated += hits > 0
        if i == center:
            center_record = {'source_vertex': i, 'ring_points': len(ring), 'damaged_ring_points': hits, 'fraction': fractions[-1]}
    valid = [x for x in fractions if x is not None]
    records.append({'case': case['id'], 'source': source, 'position': case.get('position_group', 'center'), 'support_points': len(support), 'contaminated_rings': contaminated, 'empty_rings': len(fractions)-len(valid), 'contamination_fraction_max': max(valid) if valid else None, 'central_witness': center_record})

cluster_records = []
for case in sorted([c for c in dev if c['normal_control']], key=lambda c: c['id']):
    folder = BASE / 'm6_shape_data_001/private/patches' / case['patch_id']
    graph = arrays(folder / 'graph.npz')
    relative = Path(previous[case['id']]['component_path']).relative_to(Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification'))
    p = arrays(BASE / relative)['p']
    free = np.flatnonzero(graph['free_mask'])
    # Calibration files store free scores only; tolerate full arrays by explicit shape.
    if len(p) == len(free):
        selected = set(int(i) for i in free[p > cal['tau']])
    elif len(p) == len(graph['free_mask']):
        selected = set(int(i) for i in np.flatnonzero(graph['free_mask'] & (p > cal['tau'])))
    else:
        raise ValueError(('unexpected calibration shape', case['id'], p.shape, len(free)))
    adj = defaultdict(set)
    for i, j in graph['edge_index'].T:
        if int(i) in selected and int(j) in selected:
            adj[int(i)].add(int(j)); adj[int(j)].add(int(i))
    unseen = set(selected); sizes = []
    while unseen:
        start = min(unseen); unseen.remove(start); queue = [start]; size = 0
        while queue:
            i = queue.pop(); size += 1
            for j in adj[i]:
                if j in unseen: unseen.remove(j); queue.append(j)
        sizes.append(size)
    cluster_records.append({'case': case['id'], 'selected_points': len(selected), 'component_sizes': sorted(sizes, reverse=True)})
assert sum(c['selected_points'] for c in cluster_records) == cal['pooled_selected_control_points'] == 53

v = np.array([[-1., 0., 1.], [1., 0., 1.], [0., 1., 0.]])
n = np.stack((-2*v[:, 0], np.zeros(3), np.ones(3)), axis=1)
n /= np.linalg.norm(n, axis=1, keepdims=True)
original_cross = np.cross(v[1]-v[0], v[2]-v[0])
examples = []
for step in (np.sqrt(5)/2, np.sqrt(5)):
    new = v + step*n
    cross = np.cross(new[1]-new[0], new[2]-new[0])
    examples.append({'uniform_normal_step': step, 'vertices': new.tolist(), 'double_area': float(np.linalg.norm(cross)), 'cross_dot_original': float(cross @ original_cross)})
assert examples[0]['double_area'] < 1e-12 and examples[1]['cross_dot_original'] < 0

by_group = {}
for group, use in [('development', [r for r in records if r['source'] != 'Stanford_Armadillo']), ('validation_center', [r for r in records if r['source'] == 'Stanford_Armadillo' and r['position'] == 'center']), ('validation_offcenter', [r for r in records if r['position'] == 'offcenter'])]:
    by_group[group] = {'cases': len(use), 'support_queries': sum(r['support_points'] for r in use), 'contaminated_support_rings': sum(r['contaminated_rings'] for r in use), 'cases_with_any_contaminated_ring': sum(r['contaminated_rings'] > 0 for r in use), 'central_witness_contaminated': sum(r['central_witness']['damaged_ring_points'] > 0 for r in use), 'max_contamination_fraction': max(r['contamination_fraction_max'] for r in use)}
out = {'status': 'completed', 'scope': 'topology and old threshold audit only; no annular fitting, AUC prediction, model forward or repair', 'sources': metadata, 'annular_groups': by_group, 'annular_cases': records, 'normal_calibration': {'threshold': cal['tau'], 'free_points': cal['free_point_count'], 'selected': 53, 'controls': len(cluster_records), 'component_size_histogram': dict(sorted(Counter(x for r in cluster_records for x in r['component_sizes']).items())), 'cases': cluster_records}, 'normal_offset_counterexample': {'surface': 'z=x*x', 'vertices': v.tolist(), 'exact_smooth_unit_normals': n.tolist(), 'original_cross': original_cross.tolist(), 'steps': examples}, 'input_sha256': READS, 'unique_topology_queries': len(rings), 'wall_s': time.perf_counter()-START, 'CPU_s': time.process_time()-CPU}
(HERE / 'RESULTS.json').write_bytes((json.dumps(out, ensure_ascii=False, indent=2)+'\n').encode('utf-8'))
print(json.dumps({'annular_groups': by_group, 'normal_cluster_histogram': out['normal_calibration']['component_size_histogram'], 'normal_offset_steps': examples, 'wall_s': out['wall_s'], 'CPU_s': out['CPU_s']}, ensure_ascii=False))
