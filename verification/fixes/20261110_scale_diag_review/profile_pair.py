"""One attribution-only profile of audited source bytes on a frozen pair."""
import cProfile
import hashlib
import json
from pathlib import Path
import pstats
import types

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
SOURCE = ROOT / 'human_eye_plugin/surface_proximity.py'
FIXTURE = ROOT / 'verification/scale_diag_001/fixtures/G60_D12.json'
source = SOURCE.read_bytes()
identity = json.loads((ROOT / 'verification/scale_diag_001/measurements/D_mid_P/IDENTITY.json').read_bytes())
expected = next(row['sha256'] for row in identity['source_files']
                if row['path'] == 'human_eye_plugin/surface_proximity.py')
assert hashlib.sha256(source).hexdigest() == expected
module = types.ModuleType('audited_surface_proximity')
exec(compile(source, str(SOURCE), 'exec'), module.__dict__)
data = json.loads(FIXTURE.read_bytes())
objects = {row['logical_id']: row for row in data['objects']}
meshes = [types.SimpleNamespace(vertices=objects[key]['vertices_world'],
                               faces=objects[key]['triangles']) for key in ('target', 'peer')]
profile = cProfile.Profile()
profile.enable()
result = module.measure_surface_proximity(*meshes, lambda *_: None, retain_exact_rank=True)
profile.disable()
assert result['measurement_valid']
stats = pstats.Stats(profile)
rows = []
for (filename, line, name), (primitive, calls, self_s, inclusive_s, callers) in stats.stats.items():
    rows.append(dict(file=filename, line=line, function=name, calls=calls,
                     primitive_calls=primitive, self_s=self_s, inclusive_s=inclusive_s))
rows.sort(key=lambda item: item['self_s'], reverse=True)
output = dict(source_sha256=expected, fixture_sha256=hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
              pair=['target', 'peer'], product_result=result, profile_total_s=stats.total_tt,
              functions=rows,
              limitations='one cProfile-instrumented 60x60 pair; no latency claim or full-scene extrapolation; no Blender/LLM; audited bytes compiled without pyc')
out = Path(__file__).with_name('PAIR_PROFILE.json')
out.write_text(json.dumps(output, indent=2) + '\n', encoding='utf-8')
print(json.dumps(dict(total_s=stats.total_tt, work=result['work'], top_self=rows[:12]), indent=2))
