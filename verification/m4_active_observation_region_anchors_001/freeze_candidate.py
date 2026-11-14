"""Freeze source, input answers and the complete acceptance harness before execution."""

import ast
import hashlib
import json
from pathlib import Path
import subprocess
import time


ROOT = Path(__file__).resolve().parents[2]
TASK = Path(__file__).resolve().parent
EXTERNAL = Path('D:/he_anchor_001')
BASELINE = 'efe7f77aabdab4f8de47fdb4f8714cb25f301503'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip() == BASELINE
    assert not (TASK / 'FROZEN.json').exists()
    previous = ROOT / 'verification/m4_active_observation_patch_ownership_001/build_r2/RUN_BINDING.json'
    accepted = json.loads(previous.read_bytes())
    manifest = [{'path': row['path'], 'sha256': digest(ROOT / row['path'])}
                for row in accepted['source_manifest']]
    assert len(manifest) == 141
    files = {ROOT / row['path'] for row in manifest}
    files.update(path for path in TASK.rglob('*') if path.is_file())
    files.update(ROOT.glob('verification/test_active_observation*.py'))
    files.update([ROOT / 'verification/test_live_spatial_mcp.py'])
    for path in sorted(files):
        if path.suffix == '.py':
            ast.parse(path.read_text(encoding='utf8'), filename=str(path))
    environment = json.loads((TASK / 'preparation/ENVIRONMENT.json').read_bytes())
    files.add(previous)
    files.update((previous.parent).glob('*.whl'))
    files.add(Path(environment['base_python']))
    files.add(Path('D:/Tools/blender5.2/blender.exe'))
    files.add(EXTERNAL / 'venv/Scripts/python.exe')
    files.add(EXTERNAL / 'venv/pyvenv.cfg')
    files.add(EXTERNAL / 'venv/Lib/site-packages/human_eye_owned_product.pth')
    files.update(Path(row['path']) for row in environment['dependencies'])
    assert not list((EXTERNAL / 'run').glob('render_budget/attempt_*/INTENT.json'))
    record = {'task': 'M4-ACTIVE-OBSERVATION-REGION-ANCHORS-001',
              'baseline': BASELINE, 'closed_before_publication_ns': time.perf_counter_ns(),
              'runtime_manifest': manifest,
              'files_sha256': {str(path): digest(path) for path in sorted(files)},
              'candidate_functions_tests_rasters_model_calls_before_freeze': 0,
              'independent_reference_construction': 'Historical source, PNG and NPZ only. Product-free NumPy/PIL/stdlib script separately recorded.',
              'new_raster_hard_cap': 4, 'benchmark_pair_count': 5,
              'benchmark_warmups': 0, 'text_gate_bytes': 48162,
              'history_F_E_review': 'Administrator closed the duplicated historical reply and instructed continuation on the current baseline.'}
    raw = (json.dumps(record, sort_keys=True, indent=2) + '\n').encode()
    with (TASK / 'FROZEN.json').open('xb') as stream:
        stream.write(raw)
    print(json.dumps({'files': len(files), 'runtime_files': len(manifest),
                      'freeze_sha256': hashlib.sha256(raw).hexdigest()}))


if __name__ == '__main__':
    main()
