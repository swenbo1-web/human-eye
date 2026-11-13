"""Freeze the six-episode model batch without starting any consumer or worker."""

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert not (HERE / 'FORMAL_STARTED.json').exists()
    work = json.loads((HERE / 'WORK_ORDER.json').read_bytes())
    plan = json.loads((HERE / 'PLAN.json').read_bytes())
    mapping = json.loads((HERE / 'private/ANON_MAP.json').read_bytes())
    assert plan['cycle'] == work['cycle'] == 'M4-SURFACE-SCAN-CONTINUOUS-CONSUMPTION-001'
    assert [row['cell'] for row in mapping['rows']] == ['N1', 'C1', 'C2', 'N2', 'N3', 'C3']
    assert len({row['anonymous_episode_id'] for row in mapping['rows']}) == 6
    assert len({name for row in mapping['rows'] for name in row['anonymous_turn_ids']}) == 18
    assert plan['anonymous_map_sha256'] == sha(HERE / 'private/ANON_MAP.json')
    assert plan['model_consumer_enabled'] is True and plan['image_count'] == plan['new_images'] == 0
    for item in work['inputs']:
        assert sha(HERE / item['path']) == item['sha256'] == sha(Path(item['source']))
    assert sha(HERE / 'inputs/ROOT_PLAN.md') == '95a334c39672a72ac771beba0f02e6c17735771a5e0f8411203d46e2769feba5'
    reuse = json.loads((HERE / 'REUSE.json').read_bytes())
    for path, expected in reuse['external_sha256'].items():
        assert sha(Path(path)) == expected, path
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
    frozen = {'cycle': plan['cycle'], 'admin_commit': work['admin_commit'],
              'preparation_parent_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'batch_relative': HERE.relative_to(ROOT).as_posix(), 'root_plan_sha256': sha(HERE / 'inputs/ROOT_PLAN.md'),
              'plan_sha256': sha(HERE / 'PLAN.json'), 'anonymous_map_sha256': sha(HERE / 'private/ANON_MAP.json'),
              'maximum_episodes': 6, 'maximum_model_turns': 18,
              'files': files, 'external_sha256': reuse['external_sha256'],
              'quality_before_cost': True, 'new_live_pretests': 0}
    (HERE / 'PREPARATION.json').write_text(json.dumps(frozen, ensure_ascii=False, indent=2) + '\n', encoding='utf8', newline='\n')
    spec = importlib.util.spec_from_file_location('_continuous_preparation_driver', HERE / 'runtime/driver.py')
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    driver.validate_preparation(frozen, require_committed=False)
    print(json.dumps({'files': len(files), 'external_files': len(reuse['external_sha256']),
                      'preparation_sha256': sha(HERE / 'PREPARATION.json'), 'new_live_pretests': 0}))


if __name__ == '__main__':
    main()
