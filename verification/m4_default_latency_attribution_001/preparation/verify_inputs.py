"""Read installed files, saved wheels and fixed input bytes without starting them."""

import argparse
import ast
import hashlib
import json
from pathlib import Path
import time
import zipfile


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def verify():
    began = time.perf_counter_ns()
    work = read(BATCH / 'WORK_ORDER.json')
    schedule_raw = (BATCH / 'SCHEDULE.json').read_bytes()
    assert sha(schedule_raw) == work['schedule_sha256']
    schedule = json.loads(schedule_raw)
    assert [row['version'] for row in schedule['sessions']] == ['B', 'C', 'C', 'B']
    assert work['maximum_owned_starts'] == 4 and not work['failed_session_replacement']
    asset = ROOT / work['asset']
    assert sha(asset.read_bytes()) == work['asset_sha256']
    versions, pins = {}, {str(asset): work['asset_sha256']}
    for role, expected in work['versions'].items():
        ready_path = ROOT / expected['ready']
        ready_raw = ready_path.read_bytes()
        ready = json.loads(ready_raw)
        assert ready['commit'] == expected['commit'] and ready['source_sha256'] == expected['source_sha256']
        assert ready['source_count'] == expected['source_count'] == 137 and ready['no_default_activation']
        receipt_path = Path(ready['receipt'])
        receipt_raw = receipt_path.read_bytes()
        receipt = json.loads(receipt_raw)
        assert receipt['fixed_commit'] == expected['commit'] and receipt['source_sha256'] == expected['source_sha256']
        assert receipt['source_commit_wheel_install_equal'] and not receipt['default_activation_changed']
        copied = Path(receipt['source_root'])
        fixed_path = copied.parent / 'FIXED_BUILD_INPUTS.json'
        fixed_raw = fixed_path.read_bytes()
        fixed = json.loads(fixed_raw)
        assert fixed['commit'] == expected['commit'] and len(fixed['manifest']) == 137
        identity = ast.parse((copied / 'human_eye_plugin/runtime_identity.py').read_bytes())
        constants = {node.targets[0].id: ast.literal_eval(node.value) for node in identity.body
                     if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                     and node.targets[0].id in ('BASE_VERSION', 'IMPLEMENTATION_REVISION')}
        canonical = dict(base_version=constants['BASE_VERSION'],
                         implementation_revision=constants['IMPLEMENTATION_REVISION'], files=fixed['manifest'])
        digest = sha(json.dumps(canonical, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode())
        assert digest == expected['source_sha256']
        wheels = list(Path(receipt['bundle']).glob('*.whl'))
        assert len(wheels) == 1 and sha(wheels[0].read_bytes()) == ready['wheel_sha256']
        with zipfile.ZipFile(wheels[0]) as archive:
            for row in fixed['manifest']:
                installed = Path(ready['install_root']) / row['path']
                original = copied / row['path']
                raw = installed.read_bytes()
                assert sha(raw) == row['sha256'] and raw == original.read_bytes() == archive.read(row['path'])
                pins[str(installed)] = row['sha256']
        admin = Path(ready['release']) / 'admin'
        assert sha(Path(ready['entry']).read_bytes()) == ready['launcher_sha256']
        assert sha((admin / 'installed_release.py').read_bytes()) == receipt['admin_sha256']
        assert sha((admin / 'RUNTIME_BINDING.json').read_bytes()) == ready['binding_sha256']
        binding = read(admin / 'RUNTIME_BINDING.json')
        assert binding['identity']['source_sha256'] == expected['source_sha256']
        for path in (ready_path, receipt_path, fixed_path, wheels[0], Path(ready['entry']),
                     admin / 'installed_release.py', admin / 'RUNTIME_BINDING.json', Path(ready['dependency_python'])):
            pins[str(path)] = sha(path.read_bytes())
        versions[role] = ready
    assert versions['B']['dependency_python'] == versions['C']['dependency_python']
    return {'versions': versions, 'checked_files_sha256': pins,
            'schedule_sha256': sha(schedule_raw), 'work_order_sha256': sha((BATCH / 'WORK_ORDER.json').read_bytes()),
            'verification_elapsed_ns': time.perf_counter_ns() - began,
            'scope': 'file/hash/AST/wheel reading only', 'new_installations': 0,
            'product_processes': 0, 'Blender_sessions': 0, 'model_consumers': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = verify()
    with args.output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'versions': list(result['versions']), 'files': len(result['checked_files_sha256']),
                      'output': str(args.output), 'Blender_sessions': 0}))
