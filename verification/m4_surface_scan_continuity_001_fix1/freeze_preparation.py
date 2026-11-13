"""Freeze FIX1 preparation before its single C engineering episode."""

import ast
import difflib
import hashlib
import json
from pathlib import Path
import subprocess


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = ROOT / 'verification/m4_surface_scan_continuity_001'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert not (HERE / 'ENGINEERING_STARTED.json').exists()
    work = json.loads((HERE / 'WORK_ORDER.json').read_bytes())
    for row in work['inputs']:
        assert sha(HERE / row['path']) == row['sha256'] == sha(Path(row['source']))
    assert sha(HERE / 'inputs/ROOT_PLAN.md') == '7f73de9c8e8ef3b4a0a616d23cb54e8a4050a9ec9d226ec1b1b8eb734e75e3c4'
    assert (HERE / 'runtime/actor.py').read_bytes() == (OLD / 'runtime/actor.py').read_bytes()
    reuse = json.loads((HERE / 'REUSE.json').read_bytes())
    for path, digest in reuse['external_sha256'].items():
        assert sha(Path(path)) == digest, path
    diff = []
    for previous, current in [('qualification/verify_continuity.py', 'qualification/verify_continuity.py'),
                              ('engineering/run_episodes.py', 'engineering/run_candidate.py')]:
        diff.extend(difflib.unified_diff((OLD / previous).read_text(encoding='utf8').splitlines(keepends=True),
                                        (HERE / current).read_text(encoding='utf8').splitlines(keepends=True),
                                        fromfile='continuity_001/' + previous, tofile='fix1/' + current, n=0))
    (HERE / 'HARNESS.diff').write_text(''.join(diff), encoding='utf8', newline='\n')
    files = []
    for path in sorted(HERE.rglob('*'), key=lambda item: item.relative_to(HERE).as_posix()):
        if not path.is_file() or path.name == 'PREPARATION.json':
            continue
        assert '__pycache__' not in path.parts and path.suffix != '.pyc'
        raw = path.read_bytes()
        if path.suffix == '.json':
            json.loads(raw)
        if path.suffix == '.py':
            ast.parse(raw.decode('utf-8-sig'), filename=str(path))
        files.append({'path': path.relative_to(HERE).as_posix(), 'bytes': len(raw), 'sha256': sha(path)})
    value = {'cycle': work['cycle'], 'preparation_parent_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
             'admin_commit': work['admin_commit'], 'root_plan_sha256': sha(HERE / 'inputs/ROOT_PLAN.md'),
             'product_commit': '452b44d2dcf231d6675bef54e568db0431a29261',
             'product_source_sha256': '4067c864c3db1ba586cd7179e6430db5acc4d71675b5295416d471632851a9f6',
             'scene_sha256': sha(ROOT / 'verification/m4_surface_scan_001/qualification/assembly.blend'),
             'fixed_groups': ['C'], 'fixed_turns': ['BASE', 'REPEAT', 'EDIT'], 'maximum_episodes': 1,
             'planned_business': 3, 'episode_seconds': 590, 'tool_seconds': 30, 'model_consumer_enabled': False,
             'new_model_API_calls': 0, 'files': files, 'external_sha256': reuse['external_sha256'],
             'actor_sha256': sha(HERE / 'runtime/actor.py'),
             'scope': 'Preparation fixed before the single exclusive C engineering reservation; original N evidence reused.'}
    (HERE / 'PREPARATION.json').write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8', newline='\n')
    print(json.dumps({'files': len(files), 'external_files': len(reuse['external_sha256']), 'preparation_sha256': sha(HERE / 'PREPARATION.json')}))


if __name__ == '__main__':
    main()
