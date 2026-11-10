"""Single in-memory candidate, not an installed/product change or entry benchmark."""
import hashlib
import json
from pathlib import Path
import time
import types
from fractions import Fraction

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
source_path = ROOT / 'human_eye_plugin/surface_proximity.py'
raw = source_path.read_bytes()
identity = json.loads((ROOT / 'verification/scale_diag_001/measurements/D_mid_P/IDENTITY.json').read_bytes())
digest = next(row['sha256'] for row in identity['source_files']
              if row['path'] == 'human_eye_plugin/surface_proximity.py')
assert hashlib.sha256(raw).hexdigest() == digest
module = types.ModuleType('audited_exact_probe')
exec(compile(raw, str(source_path), 'exec'), module.__dict__)
original = module._bounded


def candidate(value):
    if type(value) is int:
        if value.bit_length() > module.MAX_BITS:
            raise module._DomainError('surface_exact_bit_budget')
        return value
    return original(value)


values = [0, 1, -1, True, False, Fraction(0), Fraction(2, 3), Fraction(-2, 3)]
for bits in [1, 52, 53, 1074, 4095, 4096, 4097, 8193]:
    values.extend([1 << (bits - 1), -(1 << (bits - 1)),
                   Fraction(1, 1 << (bits - 1)), Fraction((1 << bits) - 1, 3)])
for value in values:
    outcomes = []
    for function in (original, candidate):
        try:
            result = function(value)
            outcomes.append(('value', result, type(result).__name__, result is value))
        except Exception as exc:
            outcomes.append(('error', type(exc).__name__, str(exc)))
    assert outcomes[0] == outcomes[1], (value, outcomes)

fixture_path = ROOT / 'verification/scale_diag_001/fixtures/G60_D12.json'
fixture = json.loads(fixture_path.read_bytes())
objects = {o['logical_id']: o for o in fixture['objects']}
meshes = [types.SimpleNamespace(vertices=objects[key]['vertices_world'],
                               faces=objects[key]['triangles']) for key in ('target', 'peer')]
runs = []
reference = None
for label in ['baseline', 'candidate', 'candidate', 'baseline', 'baseline', 'candidate']:
    module._bounded = original if label == 'baseline' else candidate
    start = time.perf_counter()
    result = module.measure_surface_proximity(*meshes, lambda *_: None, retain_exact_rank=True)
    elapsed = time.perf_counter() - start
    assert result['measurement_valid']
    if reference is None:
        reference = result
    assert result == reference, label
    runs.append({'variant': label, 'kernel_s': elapsed})
module._bounded = original
report = {'source_sha256': digest, 'fixture_sha256': hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
          'equivalence_values': len(values), 'all_results_identical': True,
          'runs': runs, 'result': reference,
          'limitations': 'one frozen 60x60 pair, six diagnostic replays, noop checkpoint, in-memory candidate; no Blender, installation, source edit or full entry speed claim'}
Path(__file__).with_name('BOUNDED_PROBE.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k: report[k] for k in ('equivalence_values', 'all_results_identical', 'runs', 'limitations')}, indent=2))
