"""Capture a candidate's exact runtime sources before its isolated build."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('initial', 'final'), required=True)
    parser.add_argument('--A-qualification', type=Path, required=True)
    args = parser.parse_args()
    qualification = json.loads(args.A_qualification.read_bytes())
    if qualification.get('passed_checked_scope', qualification.get('passed')) is not True:
        raise ValueError('accepted_A_qualification_required')
    destination = HERE / ('SOURCE_FREEZE_' + args.phase.upper() + '.json')
    if destination.exists():
        raise FileExistsError('product_freeze_is_write_once')
    source = ROOT / 'human_eye_plugin/runtime_identity.py'
    spec = importlib.util.spec_from_file_location('_m5_freeze_runtime_identity', source)
    identity = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(identity)
    manifest = identity._source_manifest(ROOT)
    baseline = json.loads((HERE / 'A_RUN_BINDING.json').read_bytes())
    old = {row['path']: row['sha256'] for row in baseline['source_manifest']}
    current = {row['path']: row['sha256'] for row in manifest}
    if not set(old) <= set(current):
        raise ValueError('unexpected_removed_runtime_source')
    changed = [path for path, digest in current.items() if old.get(path) != digest]
    value = dict(schema='m5-observe-measure-product-freeze-v1', phase=args.phase,
        captured_ns=time.perf_counter_ns(), before_candidate_commit=True,
        preceding_git=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(),
        A_source_sha256=baseline['source_sha256'], base_version=identity.BASE_VERSION,
        implementation_revision=identity.IMPLEMENTATION_REVISION, runtime_manifest=manifest,
        product_changed_paths=changed,
        plan_sha256=sha(HERE / 'PLAN.json'), requests_sha256=sha(HERE / 'REQUESTS.json'),
        state_requests_sha256=sha(HERE / 'STATE_REQUESTS.json'),
        A_qualification=dict(path=str(args.A_qualification.resolve()), sha256=sha(args.A_qualification)),
        source_enumerator=dict(path='human_eye_plugin/runtime_identity.py', sha256=sha(source)),
        new_Blender_raster_model_paid_calls=0)
    with destination.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps(dict(phase=args.phase, runtime_sources=len(manifest),
                         changed_paths=changed, freeze_sha256=sha(destination))))


if __name__ == '__main__':
    main()
