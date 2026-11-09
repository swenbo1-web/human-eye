"""Frozen 20-pair AB/BA full public observe comparison; one batch only."""
from __future__ import annotations
import argparse
from collections import Counter
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

START = time.perf_counter()
OUT = Path(__file__).resolve().parent
BASELINE = Path('D:/hefe/verification/fixes/20261109_adoption_entry/review_990/source').resolve()
CANDIDATE = OUT.parents[1]
PAIRS = 20
BASE_HASH = '3b424a7f26abf614949513178e3c295b1658928d6f0eed9234409f818e2e6ec1'
CANDIDATE_HASH = '9df00f3f3327d221b9b36d9e52995cbff6fb7311a7520d27191bbc124c0e3735'
QUERY = {'mode': 'task', 'target': {'id': 'part'}, 'candidates': [{'id': 'base'}],
         'requested_facts': ['closed_solid_relation', 'surface_proximity', 'aabb']}

def encode(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
def digest(value): return hashlib.sha256(encode(value)).hexdigest()
def normalized(value, ids=None):
    if ids is None: ids = {}
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in ('config_fingerprint', 'trace_id', 'runtime_source_sha256', 'estimated_compute_ms_avoided'):
                continue
            if key == 'observation_id' and isinstance(item, str):
                item = ids.setdefault(item, 'observation_' + str(len(ids)))
            elif key == 'context_text' and isinstance(item, str) and item.startswith('{'):
                item = json.loads(item)
            result[key] = normalized(item, ids)
        return result
    if isinstance(value, list): return [normalized(item, ids) for item in value]
    return value
def forbidden(*a, **kw): raise AssertionError('External host/network/subprocess forbidden in timing child')

def one(label, index):
    source = BASELINE if label == 'baseline' else CANDIDATE
    sys.path.insert(0, str(source))
    from human_eye_plugin import auto_router as ar, host_runtime as hr, live_service as ls, task_query as tq
    from human_eye_plugin.runtime_identity import runtime_identity
    from verification.test_live_service import SelfLockingHost
    identity = runtime_identity()
    assert identity['source_sha256'] == (BASE_HASH if label == 'baseline' else CANDIDATE_HASH)
    class Host(SelfLockingHost):
        apply_transform = forbidden
    imported = time.perf_counter()
    counts = Counter()
    with tempfile.TemporaryDirectory(prefix='he_task_cleanup_') as temp, ExitStack() as stack:
        clock = SimpleNamespace(value=1000.)
        stack.enter_context(patch.object(ar, 'time', SimpleNamespace(time=lambda: clock.value)))
        stack.enter_context(patch.object(socket, 'socket', forbidden))
        stack.enter_context(patch.object(socket, 'create_connection', forbidden))
        stack.enter_context(patch.object(subprocess, 'Popen', forbidden))
        folder = Path(temp)
        config = folder / 'connector.json'
        config.write_bytes(encode({'schema_version': '1.0', 'project_root': str(source),
            'state_file': str(folder / 'state.json'), 'audit_file': str(folder / 'audit.jsonl'),
            'quad_size': 64, 'max_sessions': 4, 'enabled': True}))
        host = Host()
        service = ls.LiveSpatialService(config, host=host)
        for sid in ('history_a', 'history_b', 'current'):
            host.scene['revision'] = 'scene_' + sid
            assert service.observe(sid, focal_id='part', reference_id='base', include_image=False)['status'] == 'observed'
        before = json.loads(service.state_path.read_bytes())
        for obj, name, key in ((ar, '_validated_scene', 'historical_validate'),
                              (ls, '_validated_scene', 'capture_validate'),
                              (tq, 'task_result', 'task_result'),
                              (hr.GuardedHostRuntime, 'import_state', 'runtime_import'),
                              (hr.GuardedHostRuntime, 'export_state', 'runtime_export')):
            original = getattr(obj, name)
            def wrapped(*a, _original=original, _key=key, **kw):
                counts[_key] += 1
                return _original(*a, **kw)
            stack.enter_context(patch.object(obj, name, wrapped))
        prepared = time.perf_counter()
        captures = host.captures
        started = time.perf_counter_ns()
        answer = service.observe('current', query=QUERY, include_image=False)
        elapsed = time.perf_counter_ns() - started
        assert answer['status'] == 'observed'
        assert host.captures - captures == 1 and host.calls == 0
        assert counts == {'historical_validate': 6 if label == 'baseline' else 3, 'capture_validate': 1,
                          'task_result': 1, 'runtime_import': 2 if label == 'baseline' else 1,
                          'runtime_export': 2 if label == 'baseline' else 1}, counts
        after = json.loads(service.state_path.read_bytes())
        before['runtime']['sessions'] = [row for row in before['runtime']['sessions'] if row[0] != 'current']
        assert after == before
        # UUID identities are consistently renamed, nested context JSON is
        # decoded, and measured cache cost estimates are excluded across runs.
        # Within each run the full saved state must equal the original state
        # with only the current prepared context removed (asserted above).
        return {'label': label, 'pair_index': index, 'observe_ns': elapsed,
                'imports_ms': (imported - START) * 1000, 'preparation_ms': (prepared - imported) * 1000,
                'source_sha256': identity['source_sha256'], 'counts': dict(counts),
                'state_sha256': digest(normalized(after)), 'result_sha256': digest(normalized(answer))}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--one', choices=('baseline', 'candidate'))
    parser.add_argument('--index', type=int, default=0)
    args = parser.parse_args()
    if args.one:
        print(json.dumps(one(args.one, args.index)))
        return
    assert not (OUT / 'timing_samples.jsonl').exists(), 'This batch may only run once'
    plan = {'pairs': PAIRS, 'orders': [('AB' if i % 2 == 0 else 'BA') for i in range(PAIRS)],
            'A': str(BASELINE), 'B': str(CANDIDATE), 'clock': 1000., 'query': QUERY,
            'baseline_source_sha256': BASE_HASH, 'candidate_source_sha256': CANDIDATE_HASH,
            'normalization': 'exclude config fingerprint/source hash/trace UUID/cache cost estimate; consistently rename observation UUIDs; decode nested context JSON',
            'fixture': 'three public observations using SelfLockingHost; same root fixture',
            'scope': 'complete service.observe including identity/load/restore/capture/validation/task/cleanup/save/audit',
            'startup_and_preparation_excluded_and_separately_reported': True,
            'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (OUT / 'TIMING_PLAN.json').write_bytes((json.dumps(plan, indent=2) + '\n').encode())
    samples = []
    with (OUT / 'timing_samples.jsonl').open('x', encoding='utf8') as log:
        for index in range(PAIRS):
            order = ('baseline', 'candidate') if index % 2 == 0 else ('candidate', 'baseline')
            for label in order:
                start = time.perf_counter()
                process = subprocess.run([sys.executable, '-I', '-B', str(Path(__file__).resolve()),
                    '--one', label, '--index', str(index)], capture_output=True, text=True)
                row = {'pair_index': index, 'label': label, 'process_wall_ms': (time.perf_counter() - start) * 1000,
                       'exit_code': process.returncode, 'stdout': process.stdout, 'stderr': process.stderr}
                if process.returncode == 0: row.update(json.loads(process.stdout))
                log.write(json.dumps(row) + '\n'); log.flush()
                samples.append(row)
                assert process.returncode == 0, row
            a, b = samples[-2:]
            assert a['state_sha256'] == b['state_sha256'], (index, 'state', a, b)
            assert a['result_sha256'] == b['result_sha256'], (index, 'result', a, b)
    summary = {}
    for label in ('baseline', 'candidate'):
        values = sorted(row['observe_ns'] / 1e6 for row in samples if row['label'] == label)
        summary[label] = {'n': len(values), 'median_ms': statistics.median(values),
                          'p95_nearest_rank_ms': values[18], 'all_ms': values}
    summary['median_reduction_pct'] = 100 * (1 - summary['candidate']['median_ms'] / summary['baseline']['median_ms'])
    summary['full_batch_wall_ms'] = (time.perf_counter() - START) * 1000
    summary['all_pairs_correct'] = True
    (OUT / 'TIMING_RESULTS.json').write_bytes((json.dumps(summary, indent=2) + '\n').encode())
    print(json.dumps(summary, indent=2))

if __name__ == '__main__': main()
