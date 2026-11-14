"""Root byte/Git/install audit. Does not import or call product code."""
from pathlib import Path
import ast, base64, csv, hashlib, io, json, subprocess, zipfile

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
H = ROOT / 'verification/m4_active_observation_brief_delivery_001'
OUT = Path(__file__).resolve().parent
COMMIT = 'cdd2b11693a2586cfea07528c6bca27b93d02499'
BASE = '32a1c6eb47cfa84133d92199387339d407a33cb5'
checks, inputs = [], {}

def raw(path):
    path = Path(path)
    data = path.read_bytes()
    inputs[str(path)] = hashlib.sha256(data).hexdigest()
    return data

def sha(path):
    return hashlib.sha256(raw(path)).hexdigest()

def js(path):
    return json.loads(raw(path))

def ck(name, passed, detail=None):
    checks.append(dict(name=name, passed=bool(passed), detail=detail))

def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])

ck('author_HEAD', git('rev-parse', 'HEAD').decode().strip() == COMMIT)
ck('author_clean', not git('status', '--porcelain', '--untracked-files=all'))
m = js(H / 'CONTENT_MANIFEST.json')
ck('manifest_sha', sha(H / 'CONTENT_MANIFEST.json') == '32d1ba995eac5cd84d05a00f16e5fc0ec7da8ae3976ee30cc1d8a52a053fff52')
ck('manifest_235_plus_self', len(m['files']) == 235)
paths = [r['path'] for r in m['files']] + [(H / 'CONTENT_MANIFEST.json').relative_to(ROOT).as_posix()]
changed = git('diff', '--name-only', BASE, COMMIT, '-z').decode().rstrip('\0').split('\0')
ck('exact_changed_scope', set(paths) == set(changed))
blob_data = subprocess.check_output(['git', '-C', str(ROOT), 'cat-file', '--batch'],
    input=''.join(COMMIT + ':' + p + '\n' for p in paths).encode())
offset = 0
for path in paths:
    end = blob_data.index(b'\n', offset)
    header = blob_data[offset:end].split()
    size, start = int(header[2]), end + 1
    ck('git_disk:' + path, header[1] == b'blob' and blob_data[start:start + size] == raw(ROOT / path))
    offset = start + size + 1
ck('batch_consumed', offset == len(blob_data))
for row in m['files']:
    ck('manifest:' + row['path'], sha(ROOT / row['path']) == row['sha256'] and
       (ROOT / row['path']).stat().st_size == row['bytes'])
frozen = js(H / 'FROZEN.json')
ck('freeze_sha', sha(H / 'FROZEN.json') == 'fac63d76e41d4c1778fc8302f9009e38497fc74c5cf39a7e41b4848f5b278a4e')
ck('freeze_1223', len(frozen['files_sha256']) == 1223)
for path, digest in frozen['files_sha256'].items():
    ck('frozen:' + path, sha(path) == digest)
archive = js(H / 'EXTERNAL_ARCHIVE.json')
ck('archive_183', len(archive['files']) == archive['file_count'] == 183)
ck('archive_bytes', sum(r['bytes'] for r in archive['files']) == archive['bytes'] == 2156934)
for row in archive['files']:
    path = ROOT / row['archive_path']
    ck('archive:' + row['original_relative_path'], raw(path) == raw(row['original_path']) and
       sha(path) == row['sha256'] and path.stat().st_size == row['bytes'])
binding, build = js(H / 'build/RUN_BINDING.json'), js(H / 'build/BUILD_INSTALL.json')
source, install, wheel = binding['source_manifest'], Path(binding['install_root']), Path(build['wheel']['file'])
ck('source_141', len(source) == 141)
ck('source_freeze_same', source == frozen['runtime_manifest'])
ck('wheel_sha', sha(wheel) == binding['wheel_sha256'] == '67aaa5acfa8b7009d9d3f83bab743328c7d5686208458207fd453cc57f517334')
ck('wheel_bytes', wheel.stat().st_size == build['wheel']['bytes'] == 1159061)
with zipfile.ZipFile(wheel) as z:
    record_path = next(p for p in z.namelist() if p.endswith('.dist-info/RECORD'))
    records = list(csv.reader(io.StringIO(z.read(record_path).decode())))
    installed_records = {r[0]: r[1:] for r in csv.reader(io.StringIO(raw(install / record_path).decode()))}
    ck('wheel_RECORD_148', len(records) == 148 and {r[0] for r in records} == set(z.namelist()))
    for path, digest, size in records:
        data = z.read(path)
        if digest:
            expected = 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=')
            ck('wheel_RECORD:' + path, digest == expected and int(size) == len(data))
        else:
            ck('wheel_RECORD_self', path == record_path and not size)
    for row in source:
        path, data = row['path'], raw(ROOT / row['path'])
        expected = 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=')
        ck('runtime:' + path, hashlib.sha256(data).hexdigest() == row['sha256'] and data == z.read(path) == raw(install / path))
        ck('installed_RECORD:' + path, installed_records[path] == [expected, str(len(data))])
constants = {}
for node in ast.parse(raw(ROOT / 'human_eye_plugin/runtime_identity.py')).body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in ('BASE_VERSION', 'IMPLEMENTATION_REVISION', '_ROOT_MODULES'):
        constants[node.targets[0].id] = ast.literal_eval(node.value)
enumerated = list(constants['_ROOT_MODULES'])
for package in ('human_eye_plugin', 'human_eye_module1_operators'):
    enumerated += [package + '/' + p.name for p in (ROOT / package).glob('*.py')]
ck('manifest_complete', sorted(enumerated) == [r['path'] for r in source])
payload = dict(base_version=constants['BASE_VERSION'], implementation_revision=constants['IMPLEMENTATION_REVISION'], files=source)
digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
ck('runtime_digest', digest == binding['source_sha256'] == '2a478a6290943c0daff2f9aa0b53a57a563ca61ef7a1f8d558e756c606a82688')
environment = js(H / 'preparation/ENVIRONMENT.json')
ck('dependencies_1046', len(environment['dependencies']) == environment['dependency_files'] == 1046)
for row in environment['dependencies']:
    ck('dependency:' + row['path'], sha(row['path']) == row['sha256'] and Path(row['path']).stat().st_size == row['bytes'])
ck('one_runtime_file_changed', frozen['runtime_source_changed_from_baseline'] == ['human_eye_plugin/live_spatial_mcp.py'])
ck('prepared_product_is_tested_product', not git('diff', '--name-only', binding['preparation_git'], COMMIT, '--', 'human_eye_plugin', 'verification/test_active_observation_brief.py'))
ck('previous_host_evidence_unchanged', not git('diff', '--name-only', BASE, COMMIT, '--', 'verification/m4_active_observation_host_bridge_001'))
ck('previous_core_evidence_unchanged', not git('diff', '--name-only', BASE, COMMIT, '--', 'verification/m4_active_observation_core_integration_001'))
contract = js(H / 'SEMANTIC_CONTRACT.json')
ck('contract_sha', sha(H / 'SEMANTIC_CONTRACT.json') == frozen['semantic_contract_sha256'])
ck('decoder_sha', sha(H / 'semantic_contract.py') == frozen['independent_decoder_sha256'] == contract['independent_source_sha256'])
ck('final_audit_sha', sha(H / 'FINAL_AUDIT.json') == '96ffb796d9b6ae22f5e6d377ef164c8deb89d39a2b55374cf317884c36f3a7fe')
ck('report_sha', sha(H / 'REPORT.md') == 'c323692a3e76a25f4ea47ef6bd51e51311fb98396485317c1f8ee7fcec4fea7c')
stale_static = dict(field='SEMANTIC_CONTRACT.static_product_review.product_source_sha256',
    recorded=contract['static_product_review']['product_source_sha256'], actual=sha(ROOT / 'human_eye_plugin/live_spatial_mcp.py'),
    interpretation='Pre-freeze static snapshot is not final source. FROZEN, preparation Git, final Git, wheel and install are the actual same-byte authority.')
result = dict(schema='root-brief-delivery-source-review-v1', commit=COMMIT,
    passed=all(c['passed'] for c in checks), check_count=len(checks), checks=checks,
    failures=[c for c in checks if not c['passed']], runtime_digest=digest,
    stale_static_annotation=stale_static, new_product_model_Blender_raster_calls=0,
    method='Independent bytes/Git/AST literals/ZIP RECORD; no product import.')
for name, value in [('IDENTITY.json', result), ('IDENTITY_INPUTS.json', inputs)]:
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8', newline='\n')
print(json.dumps({k: v for k, v in result.items() if k not in ('checks',)}, ensure_ascii=False))
