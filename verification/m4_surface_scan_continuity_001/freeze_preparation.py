"""Freeze preparation bytes before either owned engineering episode starts."""

import ast
import difflib
import hashlib
import json
from pathlib import Path
import subprocess
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = ROOT / 'verification/m4_surface_scan_compact_consumption_001'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert not (HERE / 'ENGINEERING_STARTED.json').exists()
    started = time.perf_counter_ns()
    prior = json.loads((OLD / 'PLAN.json').read_bytes())
    work = json.loads((HERE / 'WORK_ORDER.json').read_bytes())
    assert sha(HERE / 'inputs/ROOT_PLAN.md') == '9e8adc0eac4dea5ce5d1afd40c8e484a72d79ab99564cbc5f81af80d58e8d4bc'
    for row in work['inputs']:
        assert sha(HERE / row['local']) == row['sha256'] == sha(Path(row['path']))
    assert (HERE / 'inputs/PROMPT_T2_T3.txt').read_bytes() == '请重新检查当前场景。'.encode('utf8') + (HERE / 'inputs/PROMPT_T1.txt').read_bytes()
    ready = json.loads((HERE / 'inputs/C_READY.json').read_bytes())
    assert ready['commit'] == '452b44d2dcf231d6675bef54e568db0431a29261'
    assert ready['source_sha256'] == '4067c864c3db1ba586cd7179e6430db5acc4d71675b5295416d471632851a9f6'
    assert ready['source_count'] == 138
    external = dict(prior['external_input_sha256'])
    for folder in ('m4_surface_scan_001_opt1/engineering', 'native_plugin_complex_003', 'm4_surface_scan_compact_consumption_001/runtime', 'm4_surface_scan_compact_facts_001/engineering'):
        for path in (ROOT / 'verification' / folder).glob('*.py'):
            external[str(path)] = sha(path)
    for path in (ROOT / 'verification/native_plugin_complex_003/reused').glob('*.py'):
        external[str(path)] = sha(path)
    for name in ('assembly.blend', 'BASE_SNAPSHOT.json', 'EDIT_SNAPSHOT.json', 'BASE_TRUTH.json', 'EDIT_TRUTH.json', 'export_snapshot.py'):
        path = ROOT / 'verification/m4_surface_scan_001/qualification' / name
        external[str(path)] = sha(path)
    for name in ('pose_native.py', 'POSE_PATCH.json'):
        path = ROOT / 'verification/m4_surface_scan_001/worker' / name
        external[str(path)] = sha(path)
    external[str(OLD / 'PLAN.json')] = sha(OLD / 'PLAN.json')
    external[str(OLD / 'DELIVERY_MANIFEST.json')] = sha(OLD / 'DELIVERY_MANIFEST.json')
    for path, digest in external.items():
        assert sha(Path(path)) == digest, path
    diff = []
    for name in ('actor.py', 'consumer_transport.py'):
        diff.extend(difflib.unified_diff((OLD / 'runtime' / name).read_text(encoding='utf8').splitlines(keepends=True),
                                        (HERE / 'runtime' / name).read_text(encoding='utf8').splitlines(keepends=True),
                                        fromfile='previous/runtime/' + name, tofile='continuity/runtime/' + name, n=0))
    (HERE / 'HARNESS.diff').write_text(''.join(diff), encoding='utf8', newline='\n')
    files = []
    for path in sorted(HERE.rglob('*')):
        if not path.is_file() or path.name == 'PREPARATION.json':
            continue
        assert '__pycache__' not in path.parts and path.suffix != '.pyc'
        raw = path.read_bytes()
        if path.suffix == '.json':
            json.loads(raw)
        if path.suffix == '.py':
            ast.parse(raw.decode('utf8'), filename=str(path))
        files.append({'path': path.relative_to(HERE).as_posix(), 'bytes': len(raw), 'sha256': sha(path)})
    result = {'cycle': work['cycle'], 'preparation_parent_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'admin_commit': work['admin_commit'], 'root_plan_sha256': sha(HERE / 'inputs/ROOT_PLAN.md'),
              'product_commit': ready['commit'], 'product_source_sha256': ready['source_sha256'],
              'scene_sha256': sha(ROOT / 'verification/m4_surface_scan_001/qualification/assembly.blend'),
              'fixed_groups': ['N', 'C'], 'fixed_turns': ['BASE', 'REPEAT', 'EDIT'], 'maximum_episodes': 2,
              'planned_business': 6, 'episode_seconds': 590, 'tool_seconds': 30, 'new_model_API_calls': 0,
              'files': files, 'external_sha256': external,
              'freeze_checks_before_publication_ns': time.perf_counter_ns() - started,
              'scope': 'Preparation only. The preparation commit is recorded by the exclusive engineering reservation after commit.'}
    (HERE / 'PREPARATION.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8', newline='\n')
    print(json.dumps({'frozen_files': len(files), 'external_files': len(external), 'preparation_sha256': sha(HERE / 'PREPARATION.json'), 'new_model_API_calls': 0}))


if __name__ == '__main__':
    main()
