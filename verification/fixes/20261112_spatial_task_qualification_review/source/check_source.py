"""Root independent fixed-commit artifact and runtime byte checks. No product import."""
import hashlib
import json
from pathlib import Path
import subprocess

REPO = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
HERE = Path(__file__).resolve().parent
EVIDENCE = '93121974595badc90944d5353d23ae7897feda54'
PRODUCT = 'fac9b4373575d653cc96f39f1dcb225300cd5977'
PREVIOUS = 'c0134088796d47a982edfc838aa6704c8e052d57'
BASE = 'verification/spatial_task_qualification_001/'
PLAN_SHA = '7814883016b30c94e4ede6aa9dcf5ceb9d3f4f9656c592e42919995a43845e87'
INDEX_SHA = '4d1f26e2632aef535ea9e4b887e218f447edd12c83763bf87886d34f324a2963'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(['git', '-C', str(REPO), *args])


reader = subprocess.Popen(['git', '-C', str(REPO), 'cat-file', '--batch'],
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE)


def blob(commit, path):
    reader.stdin.write((commit + ':' + path + '\n').encode('utf-8'))
    reader.stdin.flush()
    header = reader.stdout.readline().split()
    assert len(header) == 3 and header[1] == b'blob', (commit, path, header)
    data = reader.stdout.read(int(header[2]))
    assert reader.stdout.read(1) == b'\n'
    return data


rows = []
try:
    assert git('rev-parse', 'HEAD').decode().strip() == EVIDENCE
    assert git('status', '--porcelain') == b''
    index_raw = blob(EVIDENCE, BASE + 'INDEX.json')
    assert sha(index_raw) == INDEX_SHA
    index = json.loads(index_raw)
    assert index['file_count'] == len(index['files']) == 123
    for item in index['files']:
        data = blob(EVIDENCE, item['path'])
        assert len(data) == item['bytes'] and sha(data) == item['sha256'], item['path']
        assert (REPO / item['path']).read_bytes() == data, item['path']
        rows.append({'path': item['path'], 'sha256': sha(data), 'bytes': len(data)})
    assert sum(row['bytes'] for row in rows) == index['bytes']
    for name in ('INDEX.json', 'COMPLETE.json'):
        data = blob(EVIDENCE, BASE + name)
        assert (REPO / (BASE + name)).read_bytes() == data
        rows.append({'path': BASE + name, 'sha256': sha(data), 'bytes': len(data)})
    assert sha(blob(EVIDENCE, BASE + 'ROOT_PLAN.md')) == PLAN_SHA
    binding = json.loads(blob(EVIDENCE, BASE + 'INSTALLATION_BINDING.json'))
    manifest = binding['ROOT_SOURCE']['manifest']
    installed = Path(binding['READY']['install_root'])
    assert binding['READY']['commit'] == PRODUCT
    assert binding['READY']['source_count'] == len(manifest) == 137
    runtime = []
    for item in manifest:
        data = blob(PRODUCT, item['path'])
        assert sha(data) == item['sha256'], item['path']
        assert blob(EVIDENCE, item['path']) == data
        assert (REPO / item['path']).read_bytes() == data
        assert (installed / item['path']).read_bytes() == data
        runtime.append(item)
    changed = git('diff', '--name-only', PREVIOUS, EVIDENCE).decode().splitlines()
    assert changed and all(path.startswith(BASE) for path in changed), changed
    complete = json.loads(blob(EVIDENCE, BASE + 'COMPLETE.json'))
    assert complete['INDEX_sha256'] == sha(index_raw)
    assert complete['report_sha256'] == sha(blob(EVIDENCE, BASE + 'REPORT.md'))
    assert complete['formal_result_sha256'] == sha(blob(EVIDENCE, BASE + 'entry/run_01/RESULTS.json'))
    assert complete['formal_oracle_sha256'] == sha(blob(EVIDENCE, BASE + 'oracle/formal_replay_01/ORACLE.json'))
    result = {
        'passed': True, 'evidence_commit': EVIDENCE, 'product_commit': PRODUCT,
        'plan_sha256': PLAN_SHA, 'index_sha256': INDEX_SHA,
        'indexed_artifacts': 123, 'evidence_files_with_index_complete': len(rows),
        'runtime_source_files_git_worktree_install_equal': len(runtime),
        'qualification_changed_files_only': changed, 'evidence_files': rows,
        'runtime_manifest': runtime,
        'scope': 'Independent byte checks and source diff; not a new Blender run, dependency reinstall or model trial.',
        'new_Blender_calls': 0, 'new_product_calls': 0, 'new_model_calls': 0,
    }
    (HERE / 'RESULTS.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('passed', 'indexed_artifacts',
          'evidence_files_with_index_complete', 'runtime_source_files_git_worktree_install_equal')}))
finally:
    reader.stdin.close()
    reader.stdout.close()
    assert reader.wait(timeout=20) == 0
