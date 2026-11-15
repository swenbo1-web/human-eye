"""Exercise unmodified prototype entry points in a disposable review directory."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / '_m6tp1/batch'
RUN = HERE.parent / '_m6tp_run/batch'


def main():
    started = time.perf_counter()
    RUN.mkdir(parents=True, exist_ok=True)
    for name in ('prototype.py', 'common.py', 'interfaces.py', 'features.py', 'model.py',
                 'CALIBRATION.json', 'MODEL_IDENTITY_v2.json'):
        shutil.copyfile(BASE / name, RUN / name)
    helper = HERE.parent / 'm6_perception_001_review/snapshot/verification/m6_perception_001/region_common.py'
    reused = json.loads((BASE / 'REUSED_INPUTS.json').read_bytes())['files']
    identity = next(r for r in reused if r['path'].endswith('region_common.py'))
    assert hashlib.sha256(helper.read_bytes()).hexdigest() == identity['sha256']
    helper_copy = RUN.parent / 'm6_perception_001/region_common.py'
    helper_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(helper, helper_copy)
    (RUN / 'private/model').mkdir(parents=True, exist_ok=True)
    shutil.copyfile(BASE / 'private/model/v2_final.pth', RUN / 'private/model/v2_final.pth')
    source = BASE / 'private/consumer_cases/t02/input.npz'
    target = RUN / 'current.npz'
    shutil.copyfile(source, target)
    observations = []

    def call(label, arguments, expected=0):
        before = time.perf_counter()
        result = subprocess.run([sys.executable, '-I', '-B', '-X', 'utf8', str(RUN / 'prototype.py'), *arguments],
                                capture_output=True, text=True, encoding='utf-8')
        (HERE / 'private').mkdir(exist_ok=True)
        (HERE / 'private' / (label+'.stdout')).write_text(result.stdout, encoding='utf-8')
        (HERE / 'private' / (label+'.stderr')).write_text(result.stderr, encoding='utf-8')
        observations.append(dict(label=label, wall_s=time.perf_counter()-before, exit_code=result.returncode))
        assert (result.returncode == 0) == (expected == 0), (label, result.stderr)
        return json.loads(result.stdout) if result.returncode == 0 else result.stderr

    arguments = ['--input', str(target), '--entrypoint', 'inspect']
    cold = call('cold_inspect', arguments)
    warm = call('cached_inspect', arguments)
    assert cold['runtime']['model_called'] and not cold['runtime']['preparation_cached']
    assert not warm['runtime']['model_called'] and warm['runtime']['preparation_cached']
    focus = call('direct_focus', ['--input', str(target), '--entrypoint', 'focus'])
    assert not focus['runtime']['model_called']
    reference = focus['target']['reference']
    directory = focus['runtime']['request_directory']
    resolved = call('resolve_focus', ['--request-directory', directory, '--resolve-reference', reference])
    with np.load(target) as package:
        ids = package['target_ids']
        vertices = package['vertices']
        current = {k: package[k].copy() for k in package.files}
    assert resolved['identity']['source_ids'] == sorted(ids.tolist())
    current['vertices'][int(ids[0]), 0] += 1e-4
    np.savez_compressed(target, **current)
    stale = call('stale_reference_rejected', ['--request-directory', directory, '--resolve-reference', reference], expected=1)
    assert 'changed' in stale or 'mismatch' in stale
    result = dict(status='passed', calls=observations, actual_entrypoint_calls=len(observations),
                  stale_reference_rejected=True, new_training=0, original_asset_edits=0,
                  wall_s=time.perf_counter()-started)
    (HERE / 'RUNTIME_RESULTS.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
