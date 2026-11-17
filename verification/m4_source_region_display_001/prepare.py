"""Register the display-participation repair and fixed real-asset inputs."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRIOR = HERE.with_name('m4_real_asset_region_qualification_001')
RUNTIME = Path('D:/he_m4_source_region_display_001')
PLANNING = '0e9247cb7a75440e511db1ca16f9b2ac764b1190'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    RUNTIME.mkdir(exist_ok=False)
    (HERE / 'inputs').mkdir(exist_ok=False)
    (HERE / 'oracle').mkdir(exist_ok=False)
    (HERE / 'public_schema').mkdir(exist_ok=False)
    for name in ('ARM_REGION.json', 'raw_selected.json', 'evaluated_selected.json'):
        shutil.copyfile(PRIOR / 'inputs' / name, HERE / 'inputs' / name)
    shutil.copyfile(PRIOR / 'oracle/source_oracle.py', HERE / 'oracle/source_oracle.py')
    shutil.copyfile(PRIOR / 'SHARED_DEPENDENCY.json', HERE / 'SHARED_DEPENDENCY.json')
    for name in ('M4_REAL_ASSET_REGION_QUALIFICATION_001_INDEPENDENT_REVIEW.md',
                 'M4_SOURCE_REGION_DISPLAY_001_PLAN.md', 'M1_M5_M6_COORDINATION_REVIEW_20261116.md'):
        raw = subprocess.check_output(['git', 'show', PLANNING + ':docs/' + name], cwd=ROOT)
        (HERE / 'inputs' / name).write_bytes(raw)
    assert sha(HERE / 'inputs/M4_SOURCE_REGION_DISPLAY_001_PLAN.md') == '0aae5bab1c23559fc76d399772825f77857b2edcf6a9cba02717676adf4ba4b3'
    old = json.loads((PRIOR / 'BASELINE.json').read_bytes())
    assert sha(old['asset']['path']) == old['asset']['sha256']
    pins = [PRIOR / name for name in ('CONTENT_MANIFEST.json', 'DECISION.json', 'R1_RUN_BINDING.json')]
    baseline = {'task': 'M4-SOURCE-REGION-DISPLAY-001',
        'baseline_git': '828d1265a3434fd1b5fb97e4759acaedd9253bc0', 'planning_git': PLANNING,
        'accepted_product_git': '2292c3d79e9996fb29b0c3351102998923113d56',
        'accepted_source_sha256': '8d8d3d60e99b5e039e6711c168f95d648124e96eea03b0a061b2796c5a690600',
        'asset': old['asset'],
        'direct_pins': [{'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size} for path in pins],
        'limits': {'owned': 2, 'rasters': 8, 'preparation_Blender': 0, 'models': 0,
                   'public_s': 30, 'owned_s': 600, 'fixture_visibility_setters': 4},
        'fixed_scope': 'source_region active-view-layer participation and direct insufficient-image feedback',
        'source_region_indices': 'same fixed 748 current evaluated triangles', 'camera': 'original SCENE unchanged',
        'agent_learning': {'task_writes': 0, 'status': 'pending_no_current_context_handle'}}
    with (HERE / 'BASELINE.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(baseline, stream, sort_keys=True, indent=2)
        stream.write('\n')


if __name__ == '__main__':
    main()
