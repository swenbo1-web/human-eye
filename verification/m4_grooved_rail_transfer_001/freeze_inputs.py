"""Freeze the delegated single-asset specification before construction."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PARENT_COMMIT = '6d72118299e9097045673d8354f9de729843ee90'
INPUTS = {
    'docs/M4_GROOVED_RAIL_TRANSFER_001_PLAN.md': ('PLAN.md', '032e18a461b639a16edb096fbc1f4641a7e6f282a85b9b8e7632c899bad447ab'),
    'verification/fixes/20261112_m4_spatial_fact_cost_review/design/REVIEW.md': ('DESIGN.md', '518607a6245cf88267395c7dc39ca73fe6b84521839026d4ddd0866452bc8cb5'),
    'docs/M4_SPATIAL_FACT_CONSUMPTION_001_REVIEW.md': ('PREVIOUS_REVIEW.md', None),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).strip().decode() == 'a44a6138b9d354ecc98a4fbd76095f0536d6973f'
    spec = HERE / 'spec'
    spec.mkdir(exist_ok=True)
    copied = []
    for relative, (name, expected) in INPUTS.items():
        original = Path('D:/hefe') / relative
        data = original.read_bytes()
        assert subprocess.check_output(['git', 'show', PARENT_COMMIT + ':' + relative], cwd=ROOT) == data
        digest = hashlib.sha256(data).hexdigest()
        assert expected is None or digest == expected
        with (spec / name).open('xb') as stream:
            stream.write(data)
        copied.append({'parent_path': relative, 'copy': 'spec/' + name, 'sha256': digest})
    previous = ROOT / 'verification/m4_spatial_fact_consumption_001'
    binding = json.loads((previous / 'preflight/SOURCE_BINDING.json').read_bytes())
    ready = json.loads((previous / 'installations/P_READY.json').read_bytes())
    for row in binding['source_manifest']:
        assert sha(ROOT / row['path']) == row['sha256']
        assert sha(Path(ready['install_root']) / row['path']) == row['sha256']
    protected = [ROOT / 'pyproject.toml', Path('C:/Users/Administrator/.codex/config.toml'),
                 Path('D:/hefe/.codex/config.toml'),
                 previous / 'input/scene.blend',
                 ROOT / 'verification/spatial_task_qualification_001/assets/G508_control.blend']
    save(HERE / 'PROTECTED_BEFORE.json', {str(path): sha(path) for path in protected})
    save(HERE / 'SOURCE_BINDING.json', {'product_commit': ready['commit'],
        'source_count': len(binding['source_manifest']), 'source_sha256': ready['source_sha256'],
        'source_manifest': binding['source_manifest'], 'reused_installation': ready})
    frozen = {'cycle': 'M4-GROOVED-RAIL-TRANSFER-001', 'phase': 'qualification_only',
        'frozen_utc': datetime.now(timezone.utc).isoformat(), 'parent_commit': PARENT_COMMIT,
        'baseline_commit': 'a44a6138b9d354ecc98a4fbd76095f0536d6973f',
        'specifications': copied, 'expected_objects': 4, 'expected_vertices': 26,
        'expected_triangles': 36, 'interbody_triangle_pairs': 288,
        'allowed_Blender_scope': 'Owned private QA construction/export, one asset at fixed geometry.',
        'consumer_allowance': 0, 'product_pretest_allowance': 0, 'images': 0,
        'geometry_selection': 'Exact frozen coordinates, indexing, triangulation and world transform. No parameter search.',
        'implementation_representation': 'Mesh local coordinates in millimetres, matrix_world linear part R/1000 and translation (120,-80,240)/1000. Scene scale_length 1 metre.',
        'AL': {'context_bound': False, 'host_epoch': 5, 'rebind_required': True,
               'task_registered': False, 'borrowed_handle': False},
        'pre_record_events': 'Read-only parent documents and existing QA helper inspection before this freeze.',
        'completion': 'Unique asset, actual snapshot, independent oracle and preparation ledger, then qualification-ready callback and wait.',
    }
    save(HERE / 'FREEZE.json', frozen)
    print(json.dumps({'specifications_frozen': len(copied), 'runtime_sources_verified': len(binding['source_manifest']),
                      'consumer_allowance': 0, 'product_pretest_allowance': 0}))


if __name__ == '__main__':
    main()
