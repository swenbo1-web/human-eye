"""Review-only, offline admission diagnostic; never a product candidate.

Executes manifest-verified source bytes in an isolated synthetic package.
The only diagnostic change is an in-memory multiplier cap override; all
closed work/bit/ray bounds and all original geometry formulas stay intact.
No Blender, model, network, installed entry, or product file is invoked/edited.
"""
import hashlib
import json
from pathlib import Path
import sys
import time
import types

ROOT = Path(r'C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
OUT = Path(__file__).resolve().parent
QUAL = ROOT / 'verification/spatial_task_qualification_001'
EXPECTED = {
    'surface_proximity': '2c471262b29101439293a172820c7d9183f840492d6ca2250f72122c5548cce3',
    'surface_geometry': 'cbbf523e3db8f0150953344f39179ac8fb4cb6fc4b9469d054601ad2e43a2fb2',
}


def load(path):
    return json.loads(path.read_bytes())


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf8')


binding = load(QUAL / 'INSTALLATION_BINDING.json')
manifest = binding['ROOT_SOURCE']['manifest']
installed = Path(binding['READY']['install_root'])
assert len(manifest) == 137
verified = []
for row in manifest:
    source_bytes = (ROOT / row['path']).read_bytes()
    installed_bytes = (installed / row['path']).read_bytes()
    assert sha(source_bytes) == row['sha256'], row['path']
    assert source_bytes == installed_bytes, row['path']
    verified.append({'path': row['path'], 'sha256': row['sha256']})
source_hash = binding['ROOT_SOURCE']['source_sha256']
assert source_hash == '6acb3ac7f014a590a279994f44be07c581af53a2da4dafae8dba9cd58eaea0bb'
entry = Path(binding['READY']['entry'])
assert sha(entry.read_bytes()) == binding['READY']['launcher_sha256']
save('SOURCE_BINDING.json', {
    'scope': 'review-only offline diagnostic, not candidate/public entry evidence',
    'product': binding['READY']['commit'], 'source_sha256': source_hash,
    'root_and_installed_source_files_verified': len(verified), 'manifest': verified,
    'entry_path': str(entry), 'entry_sha256': sha(entry.read_bytes()),
    'snapshot_sha256': sha((QUAL / 'entry/run_01/ACTUAL_SNAPSHOT.json').read_bytes()),
    'diagnostic_script_sha256': sha(Path(__file__).read_bytes()),
    'new_Blender_calls': 0, 'new_model_calls': 0, 'product_files_modified': 0,
})

# The package initializer and other product imports are deliberately not run.
package = types.ModuleType('review_geometry_snapshot')
package.__path__ = []
sys.modules[package.__name__] = package
for name, expected in EXPECTED.items():
    path = ROOT / ('human_eye_plugin/' + name + '.py')
    source = path.read_bytes()
    assert sha(source) == expected
    (OUT / (name + '.py.snapshot')).write_bytes(source)
    module = types.ModuleType(package.__name__ + '.' + name)
    module.__package__ = package.__name__
    module.__file__ = str(OUT / (name + '.py.snapshot'))
    sys.modules[module.__name__] = module
    setattr(package, name, module)
    exec(compile(source, str(path), 'exec'), module.__dict__)
exact, closed = package.surface_proximity, package.surface_geometry
snapshot = load(QUAL / 'entry/run_01/ACTUAL_SNAPSHOT.json')
meshes = {row['name']: types.SimpleNamespace(
    vertices=[tuple(point) for point in row['vertices_world']],
    faces=[tuple(face) for face in row['triangles']]) for row in snapshot['objects']}
rows = []


class DiagnosticDeadline(Exception):
    pass


def run(label, name, *, cap, kind):
    exact.MAX_TRIANGLE_PAIRS = cap
    diagnostics, checkpoints = {}, {}
    holder = {}
    begin = time.perf_counter()
    def checkpoint(stage):
        checkpoints[stage] = checkpoints.get(stage, 0) + 1
        if time.perf_counter() - begin > 30:
            raise DiagnosticDeadline('30 second diagnostic-only ceiling')
    record = {'label': label, 'candidate': name, 'kind': kind,
              'diagnostic_only_cap': cap, 'pair_faces': [len(meshes['Target'].faces), len(meshes[name].faces)],
              'closed_limits_unchanged': [closed.CLOSED_SOLID_MAX_WORK,
                  closed.CLOSED_SOLID_MAX_PAIR_TESTS, closed.CLOSED_SOLID_MAX_RAY_TESTS]}
    try:
        if kind == 'closed':
            result = closed.classify_closed_solids(meshes['Target'], meshes[name], checkpoint,
                                                   diagnostics=diagnostics, prepared_holder=holder)
        else:
            result = exact.measure_surface_proximity(meshes['Target'], meshes[name], checkpoint,
                                                    diagnostics=diagnostics, retain_exact_rank=True)
        record['result'] = result
        record['completed_call'] = True
    except DiagnosticDeadline as error:
        record.update(completed_call=False, diagnostic_timeout=str(error))
    except Exception as error:
        record.update(completed_call=False, exception=repr(error))
    record.update(elapsed_ms=(time.perf_counter() - begin) * 1000,
                  work=dict(diagnostics), checkpoint_counts=checkpoints,
                  holder_has_pair='pair' in holder, holder_has_contact='boundary_contact' in holder)
    rows.append(record)
    save('ADMISSION_DIAGNOSTIC.json', {'scope': 'cap removal in memory only; not candidate or acceptance', 'rows': rows})
    print(json.dumps({k: record.get(k) for k in ('label', 'candidate', 'kind', 'elapsed_ms', 'completed_call')}
                     | {'reason': record.get('result', {}).get('reason'), 'work': diagnostics}), flush=True)


for name in ('Peer_000', 'Competing_001', 'Near_003'):
    for kind in ('closed', 'surface'):
        run('fixed_product_baseline', name, cap=16384, kind=kind)
for name in ('Peer_000', 'Competing_001', 'Near_003'):
    for kind in ('closed', 'surface'):
        run('diagnostic_pre_gate_removed_only', name, cap=10**9, kind=kind)
exact.MAX_TRIANGLE_PAIRS = 16384
print('review offline diagnostic complete; no product candidate created', flush=True)
