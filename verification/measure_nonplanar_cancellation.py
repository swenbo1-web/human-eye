"""Expire a monotonic injected clock after valid independent replay starts.

The clock jumps forward once on a selected internal operation, then advances at
wall-clock rate. Overshoot uses the untouched real wall/CPU clocks. This is a
cooperative cancellation measurement, not a host/MCP or task-ledger benchmark.
"""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import statistics
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

def process_memory():
    """Current-process OS snapshot; lifetime peak, never a per-request peak."""
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)] + [
                (name,ctypes.c_size_t) for name in ('PeakWorkingSetSize','WorkingSetSize',
                'QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage',
                'QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]
        kernel = ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        kernel.K32GetProcessMemoryInfo.argtypes = [ctypes.c_void_p,ctypes.POINTER(Counters),wintypes.DWORD]
        data = Counters(); data.cb = ctypes.sizeof(data)
        if not kernel.K32GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(data),data.cb):
            raise OSError(ctypes.get_last_error(), 'GetProcessMemoryInfo')
        return {'working_set_bytes': data.WorkingSetSize,'lifetime_peak_bytes': data.PeakWorkingSetSize}
    import resource
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {'working_set_bytes': None, 'lifetime_peak_bytes': value*(1 if sys.platform == 'darwin' else 1024)}


def run(source: Path, repetitions: int) -> dict:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(source.resolve()))
    from human_eye_plugin import nonplanar_focus as producer, nonplanar_replay as consumer
    from human_eye_plugin.runtime_identity import runtime_identity
    from verification.nonplanar_dense_fixtures import dense_case, dense_source, local_limit_source
    rows = []
    admission = []
    memory = []
    cases = [('dense1808', 30, 1., 0.), ('millimetric', 12, .001, 0.),
             ('kilometric', 12, 1000., 0.), ('large_origin', 12, 1., 1e6), ('local128', None, 1., 0.)]
    for name, n, scale, origin in cases:
        native, edges = local_limit_source() if n is None else dense_source(dense_case(n))
        for obj in native['objects']:
            obj['world_vertices'] = [[v*scale+origin for v in p] for p in obj['world_vertices']]
        try:
            plan = producer.choose(native, 'target', edges, time.perf_counter_ns()+30_000_000_000,
                                   locality_policy='visual_nearplanar', acceleration='auto')
            assert plan['search_complete'] and (plan['selected'] is not None or name == 'local128')
            baseline = consumer.decision(plan, native, 'target', edges, 'nonplanar_dense_v1',
                                         time.perf_counter_ns()+30_000_000_000)
        except (ValueError, AssertionError) as exc:
            admission.append({'case': name, 'admitted': False, 'reason': str(exc)})
            continue
        admission.append({'case': name, 'admitted': True, 'faces': len(native['objects'][0]['faces']),
                          'max_local_visited': max(p['visited_face_count'] for r in plan['candidates'] for p in r['local_surfaces'])})
        frozen = copy.deepcopy(plan)
        # Always keep these original functions; mocks must not recursively call themselves.
        operations = {'replay': (consumer, 'replay'), 'projection': (consumer, 'Fraction'),
                      'local': (consumer.ExactLocalIndex, 'reconstruct'), 'ray': (consumer, 'ray')}
        for stage, (owner, attribute) in operations.items():
            original = getattr(owner, attribute)
            for repeat in range(repetitions):
                deadline = time.perf_counter_ns()+30_000_000_000
                expiry = None
                offset = 0
                started_cpu = None
                def clock():
                    return time.perf_counter_ns()+offset
                def operation(*args, **kwargs):
                    nonlocal expiry, offset, started_cpu
                    if expiry is None:
                        now = time.perf_counter_ns()
                        expiry = now+1_000_000
                        offset = deadline-expiry
                        started_cpu = time.process_time_ns()
                    return original(*args, **kwargs)
                reason = None
                with patch.object(consumer, 'time', SimpleNamespace(perf_counter_ns=clock)), \
                     patch.object(owner, attribute, operation):
                    try:
                        consumer.decision(plan, native, 'target', edges, 'nonplanar_dense_v1', deadline)
                    except ValueError as exc:
                        reason = str(exc)
                    end = time.perf_counter_ns()
                    end_cpu = time.process_time_ns()
                assert frozen == plan, 'consumer changed plan/accounting on cancellation'
                rows.append({'case': name, 'stage': stage, 'repeat': repeat,
                             'armed': expiry is not None, 'reason': reason,
                             'overshoot_ms': None if expiry is None else max(0, end-expiry)/1e6,
                             'cpu_after_arm_ms': None if started_cpu is None else (end_cpu-started_cpu)/1e6,
                             'expired_result_refused': reason is not None and 'deadline' in reason})
        # A cancelled call must not make subsequent validation accept an invalid plan.
        assert consumer.decision(plan, native, 'target', edges, 'nonplanar_dense_v1',
                                 time.perf_counter_ns()+30_000_000_000) == baseline
        memory.append({'after_case': name, **process_memory()})
    groups = []
    for name, *_ in cases:
        for stage in ('replay', 'projection', 'local', 'ray'):
            selected = [r for r in rows if r['case'] == name and r['stage'] == stage]
            values = sorted(r['overshoot_ms'] for r in selected if r['armed'])
            groups.append({'case': name, 'stage': stage, 'samples': len(selected),
                           'median_ms': statistics.median(values) if values else None,
                           'p95_ms': values[(95*len(values)+99)//100-1] if values else None,
                           'max_ms': max(values) if values else None,
                           'all_expired_results_refused': bool(selected) and all(r['expired_result_refused'] for r in selected)})
    return {'runtime_identity': runtime_identity(), 'method': __doc__, 'admission': admission,
            'groups': groups, 'rows': rows, 'process_memory': memory,
            'memory_scope': 'current process snapshot after case; cumulative lifetime peaks include admission and all earlier cases',
            'task_or_host_budget_claim': False,
            'latency_passed': all(g['all_expired_results_refused'] and g['p95_ms'] <= 5 and g['max_ms'] <= 20 for g in groups)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--repetitions', type=int, default=10)
    args = parser.parse_args()
    result = run(args.source, args.repetitions)
    args.output.parent.mkdir(exist_ok=True, parents=True)
    with args.output.open('x', encoding='utf8') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({'admission': result['admission'], 'groups': result['groups'], 'latency_passed': result['latency_passed']}))
