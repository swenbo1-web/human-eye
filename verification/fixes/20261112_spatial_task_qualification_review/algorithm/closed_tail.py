"""Diagnostic continuation past pair cap; no product edits or candidate claims."""
import hashlib
import json
from pathlib import Path
import sys
import time
import types

OUT = Path(__file__).resolve().parent
ROOT = Path(r'C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
saved = json.loads((OUT / 'SOURCE_BINDING.json').read_bytes())
expected = {x['path']: x['sha256'] for x in saved['manifest']}
package = types.ModuleType('review_closed_tail')
package.__path__ = []
sys.modules[package.__name__] = package
for name in ('surface_proximity', 'surface_geometry'):
    path = 'human_eye_plugin/' + name + '.py'
    source = (OUT / (name + '.py.snapshot')).read_bytes()
    assert hashlib.sha256(source).hexdigest() == expected[path]
    assert source == (ROOT / path).read_bytes()
    module = types.ModuleType(package.__name__ + '.' + name)
    module.__package__ = package.__name__
    sys.modules[module.__name__] = module
    setattr(package, name, module)
    exec(compile(source, str(OUT / (name + '.py.snapshot')), 'exec'), module.__dict__)
e, c = package.surface_proximity, package.surface_geometry
snapshot_bytes = (ROOT / 'verification/spatial_task_qualification_001/entry/run_01/ACTUAL_SNAPSHOT.json').read_bytes()
assert hashlib.sha256(snapshot_bytes).hexdigest() == saved['snapshot_sha256']
meshes = {x['name']: types.SimpleNamespace(vertices=x['vertices_world'], faces=x['triangles'])
          for x in json.loads(snapshot_bytes)['objects']}
e.MAX_TRIANGLE_PAIRS = 10**9
c.CLOSED_SOLID_MAX_PAIR_TESTS = 10**9
original = e._intersection
rows = []
for candidate in ('Peer_000', 'Competing_001', 'Near_003'):
    stats, diag, checkpoints = {}, {}, {}
    began = time.perf_counter()
    def checkpoint(stage):
        checkpoints[stage] = checkpoints.get(stage, 0) + 1
        if time.perf_counter() - began > 30:
            raise TimeoutError('diagnostic time cap')
    def counted(a, b, na, nb, budget):
        kind = 'cross' if budget.counts['cross_pair_tests'] else 'self'
        stats[kind + '_intersection_calls'] = stats.get(kind + '_intersection_calls', 0) + 1
        # Count exactly the original early plane separation predicate. Extra
        # diagnostic arithmetic is not timing evidence and does not mutate
        # the product's existing work accounting.
        da = [e._dot(na, e._sub(p, a[0])) for p in b]
        db = [e._dot(nb, e._sub(p, b[0])) for p in a]
        excluded = any(all(v * sign > 0 for v in d) for d in (da, db) for sign in (1, -1))
        stats[kind + ('_plane_excluded' if excluded else '_plane_retained')] = stats.get(
            kind + ('_plane_excluded' if excluded else '_plane_retained'), 0) + 1
        result = original(a, b, na, nb, budget)
        stats[kind + ('_has_contact' if result else '_no_contact')] = stats.get(
            kind + ('_has_contact' if result else '_no_contact'), 0) + 1
        return result
    e._intersection = counted
    row = {'candidate': candidate, 'diagnostic_only': True,
           'overrides': {'theoretical_product_cap': 10**9, 'closed_pair_cap': 10**9},
           'closed_work_cap_unchanged': c.CLOSED_SOLID_MAX_WORK,
           'timing_scope': 'includes duplicate diagnostic plane checks; not performance evidence'}
    try:
        row['result'] = c.classify_closed_solids(meshes['Target'], meshes[candidate], checkpoint, diagnostics=diag)
    except Exception as error:
        row['exception'] = repr(error)
    row.update(work=diag, plane_stage_counts=stats, checkpoint_counts=checkpoints,
               elapsed_ms=(time.perf_counter()-began)*1000)
    rows.append(row)
    (OUT / 'CLOSED_TAIL_DIAGNOSTIC.json').write_text(json.dumps({'scope': 'diagnostic only; not candidate', 'rows': rows}, indent=2), encoding='utf8')
    print(json.dumps({'candidate': candidate, 'reason': row.get('result', {}).get('reason'),
                      'work': diag, 'plane_stage_counts': stats}), flush=True)
print('diagnostic complete; original product files unchanged', flush=True)
