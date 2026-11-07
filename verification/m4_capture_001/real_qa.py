"""Prepared real BlenderMCP comparison. Run only in a separately granted window.

The explicit --run flag and pinned source hash are required. --help is safe.
No package installation, original asset save, or model/API invocation.
"""
import argparse
import hashlib
import json
from fractions import Fraction as F
from pathlib import Path
import sys
import time
import traceback


def main():
    turn_start = time.perf_counter_ns()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', help='Execute in an already granted exclusive real Blender window')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--baseline-root', type=Path, required=True,
                        help='Read-only export of baseline human_eye_plugin/blender_host.py from 82ef6eb')
    parser.add_argument('--port', type=int, default=9876)
    parser.add_argument('--expected-source-sha256', required=True)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    if not args.run: parser.error('--run requires a separately granted real QA window')
    root = args.root.resolve()
    baseline_root = args.baseline_root.resolve()
    baseline_host_sha = '5d2605d9cac66b0755bb5c68af37d852f49285f109448c7dd9220d4d3494a307'
    if hashlib.sha256((baseline_root/'human_eye_plugin/blender_host.py').read_bytes()).hexdigest() != baseline_host_sha:
        raise RuntimeError('baseline_host_bytes_do_not_match_82ef6eb')
    out = args.out.resolve()
    if not out.is_relative_to(root): parser.error('output must stay inside the candidate worktree')
    out.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(root))
    from human_eye_plugin.blender_mcp_host import BlenderMCPHost, HostRemoteError
    from human_eye_plugin.runtime_identity import runtime_identity
    from human_eye_plugin.surface_proximity import measure_surface_proximity
    from human_eye_foveated_renderer import MeshEntity3D
    identity = runtime_identity()
    if identity['source_sha256'] != args.expected_source_sha256:
        raise RuntimeError('runtime_source_does_not_match_frozen_QA')

    class SocketMeter:
        def __init__(self, sock, counters): self.sock, self.counters = sock, counters
        def __getattr__(self, key): return getattr(self.sock, key)
        def __enter__(self): return self
        def __exit__(self, *exc): return self.sock.__exit__(*exc)
        def sendall(self, data):
            for counts in self.counters: counts['sent_bytes'] += len(data)
            return self.sock.sendall(data)
        def recv(self, size):
            value = self.sock.recv(size)
            for counts in self.counters: counts['received_bytes'] += len(value)
            return value

    class MeteredHost(BlenderMCPHost):
        def reset(self): self.counts = {'rpc_attempts': 0, 'sent_bytes': 0, 'received_bytes': 0}
        def _connect(self, deadline): return SocketMeter(super()._connect(deadline), (self.counts, self.total_counts))
        def _exchange(self, payload):
            self.counts['rpc_attempts'] += 1
            self.total_counts['rpc_attempts'] += 1
            return super()._exchange(payload)

    host = MeteredHost(root, port=args.port, timeout_s=60)
    baseline_host = MeteredHost(baseline_root, port=args.port, timeout_s=60)
    host.reset()
    host.total_counts = dict(host.counts)
    baseline_host.reset()
    baseline_host.total_counts = dict(baseline_host.counts)
    batch_deadline = turn_start + 900_000_000_000
    assets = Path(__file__).with_name('blender_assets.py').resolve()
    asset_source_sha = hashlib.sha256(assets.read_bytes()).hexdigest()
    prefix = 'M4_REAL_QA:'
    def asset_call(expression):
        # Reserve one minute for the one cleanup attempt; no retry/restart.
        remaining = (batch_deadline-time.perf_counter_ns())/1e9
        if expression != 'scope.cleanup()' and remaining <= 60:
            raise RuntimeError('batch_deadline_cleanup_reserve')
        host.timeout_s = min(60., max(.001, remaining if expression != 'scope.cleanup()' else remaining+60.))
        code = '\n'.join([
            'import hashlib, json, types',
            'from pathlib import Path',
            'blob = Path(' + repr(str(assets)) + ').read_bytes()',
            'assert hashlib.sha256(blob).hexdigest() == ' + repr(asset_source_sha),
            'scope = types.ModuleType("m4_asset_preparation")',
            'exec(compile(blob,' + repr(str(assets)) + ',"exec"),scope.__dict__)',
            'print(' + repr(prefix) + '+json.dumps(' + expression + ',allow_nan=False,separators=(",",":")))'])
        outer = host._exchange(json.dumps({'type': 'execute_code', 'params': {'code': code}}).encode())
        if outer.get('status') != 'success': raise RuntimeError('fixture_transport_failed:' + str(outer))
        text = outer['result']['result']
        if not text.startswith(prefix) or text.count('\n') != 1: raise RuntimeError('fixture_response_not_unique')
        return json.loads(text[len(prefix):])

    def nearest(scene, focal_id, deadline_ns):
        def check(_stage):
            if time.perf_counter_ns() >= deadline_ns: raise RuntimeError('whole_arm_deadline')
        check('begin')
        meshes = {m['object_id']: MeshEntity3D.from_dict(m) for m in scene['meshes']}
        records = {oid: measure_surface_proximity(meshes[focal_id], mesh, check)
                   for oid, mesh in meshes.items() if oid != focal_id}
        check('finish')
        known = {oid: r['distance_m'] for oid, r in records.items() if r['measurement_valid']}
        unresolved = sorted(set(records) - set(known))
        best = min(known.values()) if known else None
        return {'distances': known, 'unknown': unresolved, 'best': best,
                'nearest_ids': sorted(oid for oid, d in known.items() if d == best) if not unresolved else None,
                'records': records}

    def verify(full, packet, baseline, candidate):
        by_id = {m['object_id']: m for m in full['meshes']}
        chosen = {m['object_id']: m for m in packet['capture']['meshes']}
        rows = packet['coverage']
        assert packet['binding']['host_identity'] == full['host_identity']
        assert packet['binding']['unit'] == full['unit'] == 'm'
        assert packet['binding']['coordinate_frame'] == full['coordinate_frame'] == 'world'
        assert len(rows) == len(by_id) and {r['object_id'] for r in rows} == set(by_id)
        assert {r['object_id'] for r in rows if r['disposition'] == 'retained'} == set(chosen)
        for oid, mesh in chosen.items():
            assert mesh['vertices'] == by_id[oid]['vertices'] and mesh['faces'] == by_id[oid]['faces']
        for row in rows:
            mesh = by_id[row['object_id']]
            bounds, witness = row['bounds_world_m'], row['witness']
            if bounds is not None:
                assert all(bounds[0][k] <= v[k] <= bounds[1][k] for v in mesh['vertices'] for k in range(3))
            if witness is not None:
                indices = witness['triangle_vertex_indices']
                assert any(sorted(face) == sorted(indices) for face in mesh['faces'])
                assert witness['point_world_m'] == mesh['vertices'][indices[0]]
                assert witness['triangle_world_m'] == [mesh['vertices'][i] for i in indices]
                p = [list(map(F, mesh['vertices'][i])) for i in indices]
                u, v = [[p[j][k]-p[0][k] for k in range(3)] for j in (1, 2)]
                assert any(u[i]*v[j] != u[j]*v[i] for i, j in ((0, 1), (0, 2), (1, 2)))
            if row['disposition'] == 'excluded_strict_bound':
                assert row['lower_bound_m'] > packet['witness_upper_bound_m']
                assert row['object_id'] not in (baseline['nearest_ids'] or [])
                focal_vertices = by_id[packet['focal_id']]['vertices']
                gaps = [max(F(0), min(F(v[k]) for v in mesh['vertices'])-max(F(v[k]) for v in focal_vertices),
                            min(F(v[k]) for v in focal_vertices)-max(F(v[k]) for v in mesh['vertices'])) for k in range(3)]
                assert F(row['lower_bound_m']) <= max(gaps)
        if packet['upper_seed_id'] is not None:
            by_row = {r['object_id']: r for r in rows}
            a = by_row[packet['focal_id']]['witness']['point_world_m']
            b = by_row[packet['upper_seed_id']]['witness']['point_world_m']
            assert sum((F(x)-F(y))**2 for x, y in zip(a, b)) <= F(packet['witness_upper_bound_m'])**2
        if baseline['unknown']:
            # Unknown must remain explicit; this harness does not manufacture a
            # nearest answer from a partial solver result.
            assert candidate['unknown']
        else:
            assert candidate['nearest_ids'] == baseline['nearest_ids']
            assert candidate['best'] == baseline['best']

    cases = ('peripheral', 'all_overlap', 'equal_ties', 'zero', 'rotated_nonuniform',
             'large_offset_units', 'isolated_vertex', 'degenerate', 'unsupported_modifier')
    records, failure = [], None
    try:
        for case_index, case in enumerate(cases):
            record = {'case': case, 'arms': {}, 'status': 'running'}
            records.append(record)
            try:
                host.reset()
                setup_start = time.perf_counter_ns()
                record['asset'] = asset_call('scope.setup(' + repr(case) + ',' + repr(str(host.source)) + ','
                                            + repr(host._readonly_host_source_sha256) + ')')
                record['setup'] = {'elapsed_ns': time.perf_counter_ns()-setup_start, **host.counts}
                focal_id = record['asset']['focal_id']
                outputs = {}
                order = ('full', 'candidate') if case_index % 2 == 0 else ('candidate', 'full')
                for arm in order:
                    active_host = baseline_host if arm == 'full' else host
                    active_host.reset()
                    start = time.perf_counter_ns()
                    deadline = min(start+60_000_000_000, batch_deadline-60_000_000_000)
                    if deadline <= start: raise RuntimeError('batch_deadline_cleanup_reserve')
                    active_host.timeout_s = (deadline-start)/1e9
                    try:
                        with active_host.observation_transaction():
                            value = active_host.capture_scene() if arm == 'full' else active_host.capture_nearest_candidates(focal_id, deadline, 32*1024*1024)
                        scene = value if arm == 'full' else value['capture']
                        result = nearest(scene, focal_id, deadline)
                        metric = {'whole_arm_ns': time.perf_counter_ns()-start, **active_host.counts,
                                  'objects': len(scene['meshes']), 'vertices': sum(len(m['vertices']) for m in scene['meshes']),
                                  'faces': sum(len(m['faces']) for m in scene['meshes']),
                                  'result_document_bytes': len(json.dumps(value, ensure_ascii=True, separators=(',', ':')).encode()),
                                  'to_mesh_completed_from_successful_capture_path': len(scene['meshes']),
                                  'triangulations_completed_from_successful_capture_path': len(scene['meshes']),
                                  'native_C_calls_independently_profiled': False}
                        outputs[arm] = (value, result)
                        record['arms'][arm] = metric
                        (out/(case+'_'+arm+'.json')).write_bytes(json.dumps({'capture': value, 'M3': result}, indent=2).encode())
                    except HostRemoteError as exc:
                        if case != 'unsupported_modifier' or arm != 'candidate' or 'acquisition_static_triangle_source_required' not in str(exc): raise
                        record['arms'][arm] = {'expected_refusal': str(exc), **active_host.counts}
                        outputs[arm] = None
                if case != 'unsupported_modifier':
                    verify(outputs['full'][0], outputs['candidate'][0], outputs['full'][1], outputs['candidate'][1])
                record['status'] = 'passed'
            finally:
                host.reset()
                cleanup_start = time.perf_counter_ns()
                record['cleanup'] = asset_call('scope.cleanup()')
                record['cleanup_cost'] = {'elapsed_ns': time.perf_counter_ns()-cleanup_start, **host.counts}
    except BaseException as exc:
        failure = {'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()}
    finally:
        host.close()
        baseline_host.close()
        summary = {'source_sha256': identity['source_sha256'], 'asset_script_sha256': asset_source_sha,
                   'baseline_host_sha256': baseline_host_sha, 'baseline_host_path': str(baseline_host.source),
                   'cases': records, 'failure': failure, 'whole_turn_ns': time.perf_counter_ns()-turn_start,
                   'all_transport': {key: host.total_counts[key]+baseline_host.total_counts[key] for key in host.total_counts},
                   'maximum_registered_RPC_attempts': 36,
                   'batch_budget_s': 900, 'last_cleanup_maximum_extra_s': 60,
                   'model_consumers': 0, 'file_saves': 0, 'model_API_calls': 0}
        (out/'RESULTS.json').write_bytes(json.dumps(summary, indent=2).encode())
    if failure: raise SystemExit('Real QA failed; preserve RESULTS.json and all completed attempts')


if __name__ == '__main__': main()
