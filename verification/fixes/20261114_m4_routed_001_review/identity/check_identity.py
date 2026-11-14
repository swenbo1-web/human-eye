"""Independent saved-data audit. Stdlib only; imports no product/test modules."""
from pathlib import Path
import ast
import hashlib
import json
import subprocess
import zipfile

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
NS = 'verification/m4_routed_task_benefit_001'
HERE = ROOT / NS
OUT = Path(__file__).resolve().parent
FINAL = '6e1e65c6eba0545ef7d3a4280e914b76c99a3f38'
BASE = 'a7632563fa8631176816100ff4bef778bdbce318'
PREP = '3689ab0726fb05f1dd45e7f8fd628c3081d6835a'
PRODUCT = '99fa034ee6074a9b674c1bb05b3328b91e9d93fe'
INSTALL = Path('D:/he_consume_001/product')
groups, failures, inputs = {}, [], {}

def sha(b):
    return hashlib.sha256(b).hexdigest()

def read(path):
    path = Path(path)
    b = path.read_bytes()
    inputs[str(path)] = {'bytes': len(b), 'sha256': sha(b)}
    return b

def js(path):
    return json.loads(read(path).decode('utf-8-sig'))

def check(group, label, passed, actual=None):
    g = groups.setdefault(group, {'checks': 0, 'passed': 0, 'failed': 0})
    g['checks'] += 1
    g['passed' if passed else 'failed'] += 1
    if not passed:
        failures.append({'group': group, 'label': label, 'actual': actual})

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

def blobs(refs):
    result = git('cat-file', '--batch') if not refs else subprocess.run(
        ['git', 'cat-file', '--batch'], cwd=ROOT, input=('\n'.join(refs)+'\n').encode(),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout
    offset, answer = 0, {}
    for ref in refs:
        stop = result.index(b'\n', offset)
        header = result[offset:stop].split()
        if len(header) != 3 or header[1] != b'blob':
            raise ValueError((ref, header))
        size = int(header[2]); offset = stop + 1
        answer[ref] = result[offset:offset+size]
        offset += size + 1
    assert offset == len(result)
    return answer

manifest = js(HERE / 'CONTENT_MANIFEST.json')
frozen = js(HERE / 'FROZEN.json')
seal = js(HERE / 'QUALITY_SEAL.json')
archive = js(HERE / 'EXTERNAL_ARCHIVE.json')
cost = js(HERE / 'COST.json')
binding_path = ROOT / 'verification/m4_consumable_observation_001/inputs/PRODUCT_BINDING.json'
binding = js(binding_path)
changed = git('diff', '--name-only', BASE, FINAL).decode().splitlines()
expected = [row['path'] for row in manifest['files']] + [NS+'/CONTENT_MANIFEST.json']
check('git', 'changed paths exactly manifest plus self', set(changed)==set(expected), len(changed))
check('git', 'all changed paths new namespace', all(p.startswith(NS+'/') for p in changed))
check('git', 'all namespace additions', all(line.startswith('A\t') for line in git('diff','--name-status',BASE,FINAL).decode().splitlines()))
check('git', 'prepared commit ancestor', subprocess.run(['git','merge-base','--is-ancestor',PREP,FINAL],cwd=ROOT).returncode==0)
refs = [FINAL+':'+p for p in expected] + [PRODUCT+':'+row['path'] for row in binding['source_manifest']]
data = blobs(refs)
for p in expected:
    check('git_blobs', p, read(ROOT/p)==data[FINAL+':'+p])
for row in manifest['files']:
    b = read(ROOT/row['path'])
    check('content_manifest', row['path'], len(b)==row['bytes'] and sha(b)==row['sha256'])
check('content_manifest', 'listed byte total', sum(x['bytes'] for x in manifest['files'])==manifest['listed_bytes'])
check('content_manifest', 'counts', len(manifest['files'])==manifest['listed_files'] and len(expected)==manifest['total_files_including_manifest'])
for p, expected_sha in frozen['files_sha256'].items():
    check('frozen', p, sha(read(p))==expected_sha)
for row in seal['inputs']:
    check('quality_seal', row['path'], sha(read(HERE/row['path']))==row['sha256'])
for p, expected_sha in cost['inputs_sha256'].items():
    check('cost_input_hashes', p, sha(read(p))==expected_sha)
archive_bytes = 0
for row in archive['files']:
    original, copy = read(row['original_path']), read(HERE/row['archive_path'])
    check('external_archive', row['original_path'], original==copy and len(copy)==row['bytes'] and sha(copy)==row['sha256'])
    archive_bytes += len(copy)
check('external_archive', 'totals', len(archive['files'])==archive['file_count'] and archive_bytes==archive['bytes'])
for row in binding['source_manifest']:
    p = row['path']; original = data[PRODUCT+':'+p]
    check('product_source', p, sha(original)==row['sha256'] and read(ROOT/p)==original and read(INSTALL/p)==original)
tree = ast.parse(read(ROOT/'human_eye_plugin/runtime_identity.py').decode())
constants = {}
for node in tree.body:
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in ('BASE_VERSION','IMPLEMENTATION_REVISION','_ROOT_MODULES'):
                constants[target.id]=ast.literal_eval(node.value)
actual_names = set(constants['_ROOT_MODULES'])
for package in ('human_eye_plugin','human_eye_module1_operators'):
    actual_names.update(package+'/'+p.name for p in (ROOT/package).glob('*.py'))
check('product_source', 'runtime enumeration', actual_names=={x['path'] for x in binding['source_manifest']})
canonical = {'base_version':constants['BASE_VERSION'], 'implementation_revision':constants['IMPLEMENTATION_REVISION'], 'files':binding['source_manifest']}
digest = sha(json.dumps(canonical,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
check('product_source','canonical digest',digest==binding['source_sha256']==frozen['product_source_sha256'])
wheel_path = ROOT/'verification/m4_consumable_observation_001/build/human_eye_spatial_plugin-9.7.2+m4.consumable.observation.r1-py3-none-any.whl'
check('wheel', 'wheel hash', sha(read(wheel_path))==binding['wheel_sha256'])
with zipfile.ZipFile(wheel_path) as wheel:
    for row in binding['source_manifest']:
        check('wheel',row['path'],sha(wheel.read(row['path']))==row['sha256'])
correction = js(HERE/'IMAGE_DELIVERY_COUNT_CORRECTION.json')
for p, digest in correction['inputs_sha256'].items():
    check('correction_inputs',p,sha(read(p))==digest)
normalizer = js(HERE/'admin/NORMALIZATION_FAILURE_01.json')
for p in ['COST_R1.md','review/SOURCE_ENTRY_LIFECYCLE_ENTAILMENT_R1.json','review/SOURCE_ENTRY_LIFECYCLE_ENTAILMENT_R1.md','admin/NORMALIZATION_FAILURE_01.json']:
    check('old_failures_retained',p,NS+'/'+p in expected)
check('old_failures_retained','normalization failure happened before scorer according to retained receipt',normalizer['normalized_file_published'] is False and normalizer['frozen_scorer_executed'] is False)
result = {'schema':'independent-routed001-identity-v1','final_commit':FINAL,'baseline_commit':BASE,'preparation_commit':PREP,
          'observed_head':git('rev-parse','HEAD').decode().strip(),'groups':groups,'failures':failures,
          'changed_paths':len(changed),'manifest_rows':len(manifest['files']),'frozen_rows':len(frozen['files_sha256']),
          'quality_seal_rows':len(seal['inputs']),'cost_input_rows':len(cost['inputs_sha256']),
          'archive_files':len(archive['files']),'archive_bytes':archive_bytes,
          'source_files':len(binding['source_manifest']),'source_digest':binding['source_sha256'],
          'new_product_model_blender_raster':0,'all_passed':not failures,
          'limits':'Static byte/identity audit and preserved receipts only; no product behavior or provider backend validation.'}
(OUT/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(OUT/'INPUTS.json').write_text(json.dumps(inputs,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
