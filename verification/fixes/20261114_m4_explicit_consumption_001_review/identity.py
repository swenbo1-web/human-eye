"""Read-only identity and archive checks for the explicit M4 consumer batch."""
from pathlib import Path
import hashlib, json, subprocess

R = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
H = R / 'verification/m4_explicit_observation_consumption_001'
O = Path(__file__).parent
HEAD = '8030a99b081e9e604fe87797c2daf74c2f6618f7'
BASE = '21b2871df70c5fedde4a916c67983ee40c626f89'
PREP = '13b2e62bc01b2f137ee106365d3bdba2df1baa41'
PRODUCT = '7d42bb939c7881a98fe322c10c216398f6c7aecc'
inputs = {}; failures = []; checks = 0

def raw(p):
    p = Path(p); b = p.read_bytes(); inputs[str(p)] = hashlib.sha256(b).hexdigest(); return b
def sha(p): return hashlib.sha256(raw(p)).hexdigest()
def js(p): return json.loads(raw(p))
def ck(name, value):
    global checks
    checks += 1
    if not value: failures.append(name)
def git(*args): return subprocess.check_output(['git', '-C', str(R), *args])
def blobs(commit, paths):
    data = subprocess.check_output(['git', '-C', str(R), 'cat-file', '--batch'],
                                  input=''.join(commit+':'+p+'\n' for p in paths).encode())
    at = 0; result = {}
    for p in paths:
        end = data.index(b'\n', at); header = data[at:end].split()
        assert len(header) == 3 and header[1] == b'blob', (p, header)
        size = int(header[2]); result[p] = data[end+1:end+1+size]; at = end+size+2
    assert at == len(data)
    return result

ck('HEAD', git('rev-parse', 'HEAD').decode().strip() == HEAD)
ck('clean_author', not git('status', '--porcelain', '--untracked-files=all'))
ck('author_branch', git('branch', '--show-current').decode().strip() == 'codex/architecture-arm-correction')
m = js(H/'CONTENT_MANIFEST.json')
ck('manifest_SHA', sha(H/'CONTENT_MANIFEST.json') == '61af12f2d0de877ee865444d661037c1c4a03d037f4410669a7a763d3a4aa921')
paths = [x['path'] for x in m['files']] + [(H/'CONTENT_MANIFEST.json').relative_to(R).as_posix()]
ck('244_paths', len(paths) == 244)
changed = git('diff', '--name-only', BASE, HEAD).decode().splitlines()
ck('changed_exactly_manifest', set(changed) == set(paths))
ck('only_new_namespace', all(p.startswith('verification/m4_explicit_observation_consumption_001/') for p in changed))
for path, data in blobs(HEAD, paths).items(): ck('Git_disk:'+path, data == raw(R/path))
for row in m['files']:
    data = raw(R/row['path'])
    ck('manifest:'+row['path'], hashlib.sha256(data).hexdigest() == row['sha256'] and len(data) == row['bytes'])
f = js(H/'FROZEN.json')
ck('1556_frozen', len(f['files_sha256']) == 1556)
ck('frozen_SHA', sha(H/'FROZEN.json') == 'f3f7b9c1de243e3803d6276b0cf950d5ed4f51c0022bfd665d808436dbabb08d')
repo_frozen = []
for path, want in f['files_sha256'].items():
    ck('frozen:'+path, sha(path) == want)
    if Path(path).is_relative_to(R): repo_frozen.append(Path(path).relative_to(R).as_posix())
tracked = set(git('ls-tree', '-r', '--name-only', PREP).decode().splitlines())
installed_untracked = [p for p in repo_frozen if p not in tracked]
ck('untracked_frozen_are_installed_releases', all(p.startswith('.human-eye/releases/') for p in installed_untracked))
for path, data in blobs(PREP, [p for p in repo_frozen if p in tracked]).items(): ck('preparation_frozen:'+path, data == raw(R/path))
sources = js(H/'inputs/SOURCES.json')
b = js(sources['product_binding']['path'])
ck('product_binding_source_pin',sha(sources['product_binding']['path'])==sources['product_binding']['sha256'])
ck('141_sources', len(b['source_manifest']) == 141)
src = [row['path'] for row in b['source_manifest']]
pb = blobs(PRODUCT, src); hb = blobs(HEAD, src); install = Path(b['install_root'])
for row in b['source_manifest']:
    path = row['path']; data = raw(R/path)
    ck('product:'+path, data == pb[path] == hb[path] == raw(install/path) and hashlib.sha256(data).hexdigest() == row['sha256'])
digest = hashlib.sha256(json.dumps({'base_version': b['base_version'], 'implementation_revision': b['implementation_revision'], 'files': b['source_manifest']}, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
ck('product_digest', digest == b['source_sha256'] == f['product_source_sha256'] == '96d7da8c50680a73f251496406c9f0bbbf6b38bd4dfe848c931e45f094343b76')
old = raw(R/'verification/m4_region_localization_consumption_001/inputs/PROMPT.txt')
new = raw(H/'inputs/PROMPT.txt')
prefix = b'For this diagnostic, first call the available active_observation tool with include_images=true. Use its returned current-session facts and images to complete the inspection below. Use the other tools only when additional evidence is needed. If that tool is unavailable or fails, report the actual failure; completing the task through native tools alone does not establish this diagnostic\'s observation-entry qualification.'
ck('prompt_single_prefix', new == prefix+b'\n\n'+old)
ck('prompt_old_hash', hashlib.sha256(old).hexdigest() == f['original_suffix_sha256'] == '3f848a42070580ad479e3de6507b9ffe09c59b9651c784c17608f0d752c1205a')
ck('prompt_new_hash', hashlib.sha256(new).hexdigest() == f['prompt_sha256'])
for name in ('capture','cameras','scene'):
    row=sources[name]; ck('input:'+name,sha(row['path'])==row['sha256'])
a=js(H/'EXTERNAL_ARCHIVE.json');ck('196_archive_files',len(a['files'])==196)
for row in a['files']:
    data=raw(H/row['archive_path'])
    ck('archive:'+row['archive_path'],len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256'] and data==raw(row['original_path']))
ck('archive_total_bytes',sum(x['bytes'] for x in a['files'])==2957789)
actual={str(p.resolve()) for p in Path('D:/he_explicit_001').rglob('*') if p.is_file()}
ck('archive_complete_original_set',actual=={str(Path(x['original_path']).resolve()) for x in a['files']})
q=js(H/'QUALITY_SEAL.json')
for row in q['inputs']:ck('quality_pin:'+row['path'],sha(H/row['path'])==row['sha256'])
for file,want in [('REPORT.md','998b881fa55c5cc0774ebc4fc4b3744dcba047ed10fd9591204451897ea4e26f'),('QUALITY_SEAL.json','7de89e0a44dff61f530e55330b8f79805fda37b263cd73f1ada4c3403271d34f'),('COST.json','54c211337e1f6114e8527c37e1764c535624dc3062e97e3206a70c53f36c45d3')]:ck(file+'_SHA',sha(H/file)==want)
ck('root_plan_SHA',sha('D:/hefe/docs/M4_EXPLICIT_OBSERVATION_CONSUMPTION_001_PLAN.md')=='a1e2b62ffd853e4e9b795d1852d1bbc60e27f4ba6be01d984acfa083fc07b7ee')
result={'passed':not failures,'checks':checks,'failures':failures,'author_HEAD':HEAD,'preparation':PREP,'product':PRODUCT,'product_source_sha256':digest,'frozen_files':1556,'Git_manifest_paths':244,'archived_originals':196,'root_new_product_model_Blender_raster_benchmark_calls':0}
(O/'IDENTITY.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(O/'IDENTITY_INPUTS.json').write_text(json.dumps(inputs,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
