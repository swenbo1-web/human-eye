"""Root review: inspect sealed bytes and receipts without importing product code."""
from pathlib import Path
import ast
import base64
import csv
import hashlib
import io
import json
import subprocess
import zipfile

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BATCH = ROOT / 'verification/m4_active_observation_core_integration_001'
OUT = Path(__file__).resolve().parent
COMMIT = 'cd863183b18e35d2ca38f75c0756e1c46e1a1ccb'
checks = []
inputs = {}

def read(path):
    path = Path(path)
    raw = path.read_bytes()
    inputs[str(path)] = hashlib.sha256(raw).hexdigest()
    return raw

def sha(path):
    return hashlib.sha256(read(path)).hexdigest()

def js(path):
    return json.loads(read(path))

def check(name, condition, detail=None):
    checks.append({'name': name, 'passed': bool(condition), 'detail': detail})

def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])

check('fixed_commit', git('rev-parse', 'HEAD').decode().strip() == COMMIT)
check('clean_author_worktree', not git('status', '--porcelain', '--untracked-files=all'))
manifest = js(BATCH / 'CONTENT_MANIFEST.json')
check('manifest_digest', sha(BATCH/'CONTENT_MANIFEST.json') == '26a139ca1f49caba11d9e4509352d9c5fa288006a1c10dec93b536f0efff236c')
check('manifest_count', manifest['file_count'] == len(manifest['files']) == 136)
paths = [r['path'] for r in manifest['files']] + [(BATCH/'CONTENT_MANIFEST.json').relative_to(ROOT).as_posix()]
changed = set(git('diff', '--name-only', manifest['baseline_git'], COMMIT, '-z').decode().rstrip('\0').split('\0'))
check('exact_git_change_scope', changed == set(paths), len(changed))
blobs = git('cat-file', '--batch', *[]) if False else subprocess.check_output(
    ['git', '-C', str(ROOT), 'cat-file', '--batch'], input=''.join(COMMIT+':'+p+'\n' for p in paths).encode())
offset = 0
for p in paths:
    end = blobs.index(b'\n', offset)
    header = blobs[offset:end].split()
    size = int(header[2]); start = end + 1
    check('git_disk:'+p, header[1] == b'blob' and blobs[start:start+size] == read(ROOT/p))
    offset = start + size + 1
check('all_git_blobs_consumed', offset == len(blobs))
for row in manifest['files']:
    p = ROOT / row['path']
    check('manifest:'+row['path'], p.stat().st_size == row['bytes'] and sha(p) == row['sha256'])

correction = js(BATCH/'review/document_correction/CORRECTION.json')
before = read(correction['original_preserved_at'])
after = read(correction['path'])
check('document_correction_exact', before.replace(b'BlenderReadonlyHost', b'BlenderSceneHost') == after)
check('document_original_digest', hashlib.sha256(before).hexdigest() == correction['original_frozen_sha256'])
check('document_current_digest', hashlib.sha256(after).hexdigest() == correction['final_sha256'])
freeze_counts = {}
for name, count in [('FROZEN.json',1233),('FROZEN_R2.json',1596)]:
    frozen = js(BATCH/name)
    check(name+':count', len(frozen['files_sha256']) == count)
    deviations = []
    for path, expected in frozen['files_sha256'].items():
        if sha(path) != expected:
            deviations.append(path)
            okay = path == correction['path'] and expected == correction['original_frozen_sha256']
        else:
            okay = True
        check(name+':'+path, okay)
    check(name+':only_doc_exception', deviations == [correction['path']])
    freeze_counts[name] = {'entries':count,'document_exceptions':deviations,'sha256':sha(BATCH/name)}
check('freeze_r2_binds_original', js(BATCH/'FROZEN_R2.json')['original_freeze_sha256'] == sha(BATCH/'FROZEN.json'))

archive = js(BATCH/'EXTERNAL_ARCHIVE.json')
check('archive_count', len(archive['files']) == 39)
for row in archive['files']:
    check('external:'+row['source'], sha(row['source']) == sha(ROOT/row['archive']) == row['sha256']
          and Path(row['source']).stat().st_size == row['bytes'])

binding = js(BATCH/'build/RUN_BINDING_R2.json')
initial_binding = js(BATCH/'build/RUN_BINDING.json')
check('repair_preserves_product_manifest', binding['source_manifest'] == initial_binding['source_manifest'])
check('runtime_source_count', len(binding['source_manifest']) == 140)
wheel = BATCH/'build'/binding['wheel_name']
check('wheel_sha', sha(wheel) == binding['wheel_sha256'] == '27f649e96728f84b72638ccce49575f21d71c15cbc3824a6c3f1b6e30d6c93d8')
check('wheel_size', wheel.stat().st_size == 1143492)
with zipfile.ZipFile(wheel) as z:
    record_path = next(n for n in z.namelist() if n.endswith('.dist-info/RECORD'))
    records = list(csv.reader(io.StringIO(z.read(record_path).decode())))
    check('record_count', len(records) == 147)
    check('record_matches_wheel_members', {r[0] for r in records} == set(z.namelist()))
    for path, encoded, size in records:
        raw = z.read(path)
        if encoded:
            calculated = 'sha256='+base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip('=')
            check('record:'+path, encoded == calculated and len(raw) == int(size))
        else:
            check('record_self:'+path, path == record_path and not size)
    for row in binding['source_manifest']:
        path = row['path']; raw = read(ROOT/path)
        check('product:'+path, hashlib.sha256(raw).hexdigest() == row['sha256'] and raw == z.read(path)
              == read(Path(binding['install_root'])/path) == read(Path('D:/he_core_001/failed_install_site')/path))

source_constants = {}
for node in ast.parse(read(ROOT/'human_eye_plugin/runtime_identity.py')).body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        if node.targets[0].id in ('BASE_VERSION','IMPLEMENTATION_REVISION','_ROOT_MODULES'):
            source_constants[node.targets[0].id] = ast.literal_eval(node.value)
enumerated = list(source_constants['_ROOT_MODULES'])
for pkg in ('human_eye_plugin','human_eye_module1_operators'):
    enumerated += [pkg+'/'+p.name for p in (ROOT/pkg).glob('*.py')]
check('complete_source_manifest', sorted(enumerated) == [r['path'] for r in binding['source_manifest']])
digest_payload={'base_version':source_constants['BASE_VERSION'],'implementation_revision':source_constants['IMPLEMENTATION_REVISION'],'files':binding['source_manifest']}
digest=hashlib.sha256(json.dumps(digest_payload,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
check('runtime_digest_recomputed', digest == binding['runtime_source_sha256'])
deps=js(BATCH/'preparation/ENVIRONMENT.json')['dependency_files']
check('dependency_count',len(deps)==1046)
for row in deps:
    path=Path(binding['dependency_root'])/row['relative']
    check('dependency:'+row['relative'],sha(path)==row['sha256'] and path.stat().st_size==row['bytes'])

repair=js(BATCH/'preparation/INSTALL_LAYOUT_REPAIR.json')
check('ordinary_pth',sha(repair['pth']['path'])==repair['pth']['sha256'] and Path(read(repair['pth']['path']).decode().strip()).resolve()==Path(binding['install_root']).resolve())
worker1=read(BATCH/'isolated_worker.py').decode();worker2=read(BATCH/'isolated_worker_r2.py').decode()
check('worker_repair_only_dependency_assertions',worker1.replace("Path(binding['install_root']).resolve()", "Path(binding['dependency_root']).resolve()") == worker2,
      'Separate precise diff checked below if false; no candidate calls.')
for phase in ('source_check_r2','qualify_r2','observe_r2','benchmark_r2'):
    result=js(BATCH/'external/run'/phase/'RESULTS.json')
    check(phase+':passed',result['passed'])
    check(phase+':binding',result['binding_sha256']==sha(BATCH/'build/RUN_BINDING_R2.json'))
    check(phase+':worker',result['worker_source_sha256']==sha(BATCH/'isolated_worker_r2.py'))
    check(phase+':payload',result['payload_manifest_sha256']==sha(BATCH/'external/payload_r2/PAYLOAD_MANIFEST.json'))
    check(phase+':bootstrap',result['bootstrap_source_sha256']==sha(BATCH/'verified_bootstrap.py'))
    env=result['environment']
    check(phase+':module_sources',env['core_sha256']==sha(ROOT/'human_eye_plugin/active_observation.py') and env['image_sha256']==sha(ROOT/'human_eye_plugin/active_observation_images.py'))
    access=[json.loads(line) for line in read(BATCH/'external/run'/phase/'ACCESS.jsonl').splitlines()]
    check(phase+':no_denied_reads',not result['access']['denied'] and all(r['allowed'] for r in access))
    check(phase+':no_repo_runtime_reads',all(not Path(r['path']).is_relative_to(ROOT) and not Path(r['path']).is_relative_to(Path('D:/hefe')) for r in access))
check('original_failure_retained',read(BATCH/'external/run/source_check/RESULTS.json')==read(BATCH/'failures/source_check_01/RESULTS.json'))
old_changed=git('diff','--name-only',manifest['baseline_git'],COMMIT,'--','human_eye_plugin').decode().splitlines()
check('only_two_new_product_modules',old_changed==['human_eye_plugin/active_observation.py','human_eye_plugin/active_observation_images.py'])
out={'commit':COMMIT,'passed':all(r['passed'] for r in checks),'checks':checks,'check_count':len(checks),'failures':[r for r in checks if not r['passed']], 'freezes':freeze_counts,'runtime_digest':digest,'new_product_model_render_test_calls':0,'method':'Independent bytes, Git blobs, ZIP/RECORD, AST constants and recorded access reads; product not imported or rerun.'}
(OUT/'IDENTITY.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(OUT/'IDENTITY_INPUTS.json').write_text(json.dumps(inputs,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:v for k,v in out.items() if k not in ('checks','freezes')},ensure_ascii=False))
