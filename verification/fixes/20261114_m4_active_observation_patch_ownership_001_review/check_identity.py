"""Independent multi-generation bytes/Git/wheel audit, without product execution."""
from pathlib import Path
import ast, base64, csv, hashlib, io, json, subprocess, zipfile

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
H = ROOT / 'verification/m4_active_observation_patch_ownership_001'
OUT = Path(__file__).resolve().parent
HEAD = 'efe7f77aabdab4f8de47fdb4f8714cb25f301503'
BASE = 'cdd2b11693a2586cfea07528c6bca27b93d02499'
checks, inputs, generations = [], {}, []

def raw(path):
    path = Path(path); data = path.read_bytes()
    inputs[str(path)] = hashlib.sha256(data).hexdigest()
    return data

def sha(path): return hashlib.sha256(raw(path)).hexdigest()
def js(path): return json.loads(raw(path))
def ck(name, passed, detail=None): checks.append(dict(name=name, passed=bool(passed), detail=detail))
def git(*args): return subprocess.check_output(['git', '-C', str(ROOT), *args])

def blobs(commit, paths):
    data = subprocess.check_output(['git', '-C', str(ROOT), 'cat-file', '--batch'],
        input=''.join(commit + ':' + p + '\n' for p in paths).encode())
    offset, result = 0, {}
    for p in paths:
        end = data.index(b'\n', offset); header = data[offset:end].split()
        assert len(header) == 3 and header[1] == b'blob', (commit, p, header)
        start, size = end + 1, int(header[2]); result[p] = data[start:start + size]
        offset = start + size + 1
    assert offset == len(data)
    return result

ck('fixed_HEAD', git('rev-parse', 'HEAD').decode().strip() == HEAD)
ck('clean_author_worktree', not git('status', '--porcelain', '--untracked-files=all'))
m = js(H / 'CONTENT_MANIFEST.json')
ck('manifest_247', len(m['files']) == 247)
ck('manifest_SHA', sha(H / 'CONTENT_MANIFEST.json') == '44cbbfa1daf79b804c828aa2091cfd826acf34bf16632031e7053faec7fc2668')
paths = [r['path'] for r in m['files']] + [(H / 'CONTENT_MANIFEST.json').relative_to(ROOT).as_posix()]
ck('exact_changed_scope', set(git('diff', '--name-only', BASE, HEAD).decode().splitlines()) == set(paths))
current_blobs = blobs(HEAD, paths)
for p, data in current_blobs.items(): ck('Git_disk:' + p, raw(ROOT / p) == data)
for r in m['files']:
    ck('manifest:' + r['path'], sha(ROOT / r['path']) == r['sha256'] and (ROOT / r['path']).stat().st_size == r['bytes'])

configs = [
    ('R1', 'FROZEN.json', 1230, '4d5be1cf3afcb786ad72dd7acdfcb60ea425bcbe',
     'a78c877fbaed919874f5b388a82ee4effd74cfb8b53fab97bdbe850050ece2bb',
     {'human_eye_plugin/active_observation.py': 'preparation/R1_active_observation.py',
      'verification/m4_active_observation_patch_ownership_001/run_units.py': 'preparation/R1_run_units.py'}),
    ('R2', 'FROZEN_R2.json', 1243, 'f62090a3dbed620f7b82940658e101814fbbb375',
     '961b9da6f40a90970bb80e65e4fe55f7eb02a3fd6fad7450f2ccffd24f5a0db9',
     {'verification/m4_active_observation_patch_ownership_001/run_units.py': 'preparation/R2_run_units.py'}),
    ('R3', 'FROZEN_R3.json', 1251, '7b3a60d4acb7761e3fc5ac8920f5a9e614ad7db8',
     'af026ac4f732c404ab7e6ab98345b82449b399e997c6f32ecf6b827910b44fd2', {}),
]
freezes = {}
for name, file, count, commit, expected, exceptions in configs:
    f = js(H / file); freezes[name] = f
    ck(name + ':freeze_SHA', sha(H / file) == expected)
    ck(name + ':freeze_count', len(f['files_sha256']) == count)
    historical = blobs(commit, list(exceptions)) if exceptions else {}
    found = []
    for p, expected_hash in f['files_sha256'].items():
        current_hash = sha(p)
        if current_hash == expected_hash:
            ck(name + ':frozen:' + p, True)
        else:
            rel = Path(p).relative_to(ROOT).as_posix()
            found.append(rel)
            ck(name + ':documented_generation:' + rel, rel in exceptions and
                hashlib.sha256(historical.get(rel, b'')).hexdigest() == expected_hash and
                sha(H / exceptions[rel]) == expected_hash,
                dict(frozen=expected_hash, current=current_hash))
    ck(name + ':exact_generation_exceptions', set(found) == set(exceptions))
    generations.append(dict(name=name, count=count, sha256=expected, current_exceptions=found))
ck('R2_refers_R1', freezes['R2']['original_freeze_sha256'] == sha(H / 'FROZEN.json'))
ck('R3_refers_R2', freezes['R3']['product_freeze_sha256'] == sha(H / 'FROZEN_R2.json'))
ck('R2_R3_same_product', freezes['R2']['runtime_manifest'] == freezes['R3']['runtime_manifest'])
ck('R3_product_unchanged_to_final', not git('diff', '--name-only', configs[2][3], HEAD, '--', 'human_eye_plugin'))

archive = js(H / 'EXTERNAL_ARCHIVE.json')
ck('archive_169', len(archive['files']) == archive['file_count'] == 169)
ck('archive_7233396B', sum(r['bytes'] for r in archive['files']) == archive['bytes'] == 7233396)
for r in archive['files']:
    p = ROOT / r['archive_path']
    ck('archive:' + r['original_relative_path'], raw(p) == raw(r['original_path']) and sha(p) == r['sha256'] and p.stat().st_size == r['bytes'])

constants = {}
for n in ast.parse(raw(ROOT / 'human_eye_plugin/runtime_identity.py')).body:
    if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id in ('BASE_VERSION', 'IMPLEMENTATION_REVISION', '_ROOT_MODULES'):
        constants[n.targets[0].id] = ast.literal_eval(n.value)
enumerated = list(constants['_ROOT_MODULES'])
for package in ('human_eye_plugin', 'human_eye_module1_operators'):
    enumerated += [package + '/' + p.name for p in (ROOT / package).glob('*.py')]
package_results = []
for name, folder, expected_wheel, expected_digest in [
    ('R1', 'build', '05c7cf2c7d4d0c74e0056dd0164ef3266751f68c13a44ed312017b021961a1df', '669dc2033e5e1e7ec319f71a8013551c5b12122f7f66596b76d3600ce52eff78'),
    ('R2', 'build_r2', 'c85404e6706c4f4d4e9caed92f9f46d86604d036b4404bcaebcfb572a589049f', '8490ad360d4c52850038ceb7c55576c0118f9f920dcbf5451de6808c141ebb40')]:
    binding, build = js(H / folder / 'RUN_BINDING.json'), js(H / folder / 'BUILD_INSTALL.json')
    source = binding['source_manifest']; install = Path(binding['install_root']); wheel = Path(build['wheel']['file'])
    historical = blobs(binding['preparation_git'], [r['path'] for r in source])
    ck(name + ':141_complete_source', len(source) == 141 and sorted(enumerated) == [r['path'] for r in source])
    ck(name + ':frozen_runtime', source == freezes[name]['runtime_manifest'])
    ck(name + ':wheel_SHA', sha(wheel) == binding['wheel_sha256'] == expected_wheel)
    ck(name + ':wheel_size', wheel.stat().st_size == build['wheel']['bytes'])
    with zipfile.ZipFile(wheel) as z:
        record_path = next(p for p in z.namelist() if p.endswith('.dist-info/RECORD'))
        records = list(csv.reader(io.StringIO(z.read(record_path).decode())))
        installed_records = {r[0]: r[1:] for r in csv.reader(io.StringIO(raw(install / record_path).decode()))}
        ck(name + ':148_RECORD_members', len(records) == 148 and {r[0] for r in records} == set(z.namelist()))
        for path, digest, size in records:
            data = z.read(path)
            if digest:
                expected = 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=')
                ck(name + ':RECORD:' + path, digest == expected and int(size) == len(data))
            else: ck(name + ':RECORD_self', path == record_path and not size)
        for row in source:
            p = row['path']; data = historical[p]
            expected = 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=')
            ck(name + ':Git_wheel_install:' + p, hashlib.sha256(data).hexdigest() == row['sha256'] and data == z.read(p) == raw(install / p))
            ck(name + ':installed_RECORD:' + p, installed_records[p] == [expected, str(len(data))])
            if name == 'R2': ck(name + ':current:' + p, raw(ROOT / p) == data)
    payload = dict(base_version=constants['BASE_VERSION'], implementation_revision=constants['IMPLEMENTATION_REVISION'], files=source)
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
    ck(name + ':recomputed_runtime_digest', digest == binding['source_sha256'] == expected_digest)
    package_results.append(dict(generation=name, digest=digest, wheel_sha256=expected_wheel))

environment = js(H / 'preparation/ENVIRONMENT.json')
ck('1046_dependencies', len(environment['dependencies']) == environment['dependency_files'] == 1046)
for r in environment['dependencies']:
    ck('dependency:' + r['path'], sha(r['path']) == r['sha256'] and Path(r['path']).stat().st_size == r['bytes'])
for name, digest in freezes['R1']['input_sha256'].items():
    ck('unchanged_registered_input:' + name, sha(H / 'inputs' / name) == digest == freezes['R2']['fixture_answers_hashes'][name])
ck('baseline_evidence_retained', not git('diff', '--name-only', BASE, HEAD, '--',
    'verification/m4_active_observation_brief_delivery_001', 'verification/m4_active_observation_host_bridge_001'))
ck('final_audit_SHA', sha(H / 'FINAL_AUDIT.json') == '97741004229056dec9442e037da0cfcebe349e0aee017abdb809acb157e025aa')
ck('report_SHA', sha(H / 'REPORT.md') == '0a8d54772a8b5a47c100bf326563102fce83b09d185b61163798e15f14b6bb58')
result = dict(schema='root-patch-ownership-source-review-v1', commit=HEAD,
    passed=all(r['passed'] for r in checks), check_count=len(checks), checks=checks,
    failures=[r for r in checks if not r['passed']], generations=generations, packages=package_results,
    new_product_model_Blender_raster_calls=0,
    method='Independent filesystem bytes, Git blobs, AST constants, wheel/installed RECORD; old generation deltas matched immutable Git and snapshots.')
for name, value in [('IDENTITY.json', result), ('IDENTITY_INPUTS.json', inputs)]:
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8', newline='\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('checks',)}, ensure_ascii=False))
