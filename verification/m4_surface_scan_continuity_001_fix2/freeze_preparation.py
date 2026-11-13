"""Freeze only the FIX2 runner phase change and its bounded regression."""

import ast
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = ROOT / 'verification/m4_surface_scan_continuity_001_fix1'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert not (HERE / 'ENGINEERING_STARTED.json').exists()
    work = json.loads((HERE / 'WORK_ORDER.json').read_bytes())
    for row in work['inputs']:
        assert sha(HERE / row['path']) == row['sha256'] == sha(Path(row['source']))
    assert sha(HERE / 'inputs/ROOT_PLAN.md') == '272fbe3d0982fda46fbcf936de3dd76ff7af516e6728b957fb32f01acd77a243'
    reuse = json.loads((HERE / 'REUSE.json').read_bytes())
    for path, digest in reuse['external_sha256'].items():
        assert sha(Path(path)) == digest, path
    runner_path = HERE / 'engineering/run_candidate.py'
    diff = difflib.unified_diff((OLD / 'engineering/run_candidate.py').read_text(encoding='utf8').splitlines(keepends=True),
                                runner_path.read_text(encoding='utf8').splitlines(keepends=True),
                                fromfile='fix1/engineering/run_candidate.py', tofile='fix2/engineering/run_candidate.py', n=0)
    (HERE / 'RUNNER.diff').write_text(''.join(diff), encoding='utf8', newline='\n')
    records = []
    for path in sorted(HERE.rglob('*'), key=lambda item: item.relative_to(HERE).as_posix()):
        if not path.is_file() or path.name == 'PREPARATION.json':
            continue
        assert '__pycache__' not in path.parts and path.suffix != '.pyc'
        raw = path.read_bytes()
        if path.suffix == '.json':
            json.loads(raw)
        if path.suffix == '.py':
            ast.parse(raw.decode('utf-8-sig'), filename=str(path))
        records.append({'path': path.relative_to(HERE).as_posix(), 'bytes': len(raw), 'sha256': sha(path)})
    result = {'cycle': work['cycle'], 'admin_commit': work['admin_commit'],
              'preparation_parent_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'batch_relative': HERE.relative_to(ROOT).as_posix(), 'root_plan_sha256': sha(HERE / 'inputs/ROOT_PLAN.md'),
              'product_commit': '452b44d2dcf231d6675bef54e568db0431a29261',
              'product_source_sha256': '4067c864c3db1ba586cd7179e6430db5acc4d71675b5295416d471632851a9f6',
              'scene_sha256': sha(ROOT / 'verification/m4_surface_scan_001/qualification/assembly.blend'),
              'fixed_groups': ['C'], 'fixed_turns': ['BASE', 'REPEAT', 'EDIT'], 'maximum_episodes': 1,
              'planned_business': 3, 'episode_seconds': 590, 'tool_seconds': 30, 'model_consumer_enabled': False,
              'new_model_API_calls': 0, 'files': records, 'external_sha256': reuse['external_sha256'],
              'scope': 'Collect three fixed turns, finish once, then qualify using the unchanged WIRE reader.'}
    target = HERE / 'PREPARATION.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8', newline='\n')
    spec = importlib.util.spec_from_file_location('_fix2_preparation_runner', runner_path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    runner.validate_preparation(result, require_committed=False)
    print(json.dumps({'files': len(records), 'external_files': len(reuse['external_sha256']),
                      'batch_relative': result['batch_relative'], 'preparation_sha256': sha(target), 'prelaunch_selfcheck': True}))


if __name__ == '__main__':
    main()
