"""Pinned verification controller, compiled in a normal Python -c main.

No product imports until the existing verified byte guard has been installed.
"""
import contextlib
import hashlib
import json
import math
from fractions import Fraction as F
from pathlib import Path
import subprocess
import sys
import time
import traceback
import types


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path, value): Path(path).write_bytes((json.dumps(value, indent=2, allow_nan=False)+'\n').encode())
def error_info(exc): return {'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()}
def counts(): return {'rpc_attempts': 0, 'send_attempted_bytes': 0, 'sendall_completed_bytes': 0, 'received_bytes': 0}


class MeterSocket:
    def __init__(self, sock, meter): self.sock, self.meter = sock, meter
    def __getattr__(self, key): return getattr(self.sock, key)
    def __enter__(self): return self
    def __exit__(self, *exc): return self.sock.__exit__(*exc)
    def sendall(self, data):
        self.meter['send_attempted_bytes'] += len(data)
        result = self.sock.sendall(data)
        self.meter['sendall_completed_bytes'] += len(data)
        return result
    def recv(self, size):
        data = self.sock.recv(size)
        self.meter['received_bytes'] += len(data)
        return data


def owned_address(owner, helper_sha):
    ready = owner.ready
    if (ready['host'] != '127.0.0.1' or type(ready['port']) is not int or ready['port'] <= 0
            or ready['pid'] != owner.process.pid or owner.process.poll() is not None
            or ready['deadline_ns'] != owner.config['deadline_ns'] or ready['helper_sha256'] != helper_sha):
        raise ValueError('owned_READY_binding')
    return ready['host'], ready['port']


def record_arm(host_factory, reader, solver, folder, arm):
    begun = time.perf_counter_ns()
    record = {'arm': arm, 'status': 'running', 'error': None, 'phase_ns': {}}
    payload = facts = None
    host = None
    try:
        phase = time.perf_counter_ns()
        try:
            host = host_factory()
            host.meter = counts()
        finally: record['phase_ns']['connector_source_read_and_bind'] = time.perf_counter_ns()-phase
        phase = time.perf_counter_ns()
        try: payload = reader(host)
        finally: record['phase_ns']['capture'] = time.perf_counter_ns()-phase
        phase = time.perf_counter_ns()
        try: facts = solver(payload)
        finally: record['phase_ns']['M3'] = time.perf_counter_ns()-phase
        record['status'] = 'returned'
    except BaseException as exc:
        record.update(status='failed', error=error_info(exc))
    finally:
        if host is not None: host.close()
        record['transport'] = dict(host.meter) if host is not None else counts()
        record['elapsed_before_serialization_ns'] = time.perf_counter_ns()-begun
        phase = time.perf_counter_ns()
        raw = (json.dumps({'payload': payload, 'M3': facts}, indent=2, allow_nan=False)+'\n').encode()
        record['phase_ns']['result_serialization'] = time.perf_counter_ns()-phase
        phase = time.perf_counter_ns()
        (folder/(arm+'_RAW.json')).write_bytes(raw)
        record['phase_ns']['raw_persistence'] = time.perf_counter_ns()-phase
        record['raw_bytes'] = len(raw)
        record['whole_arm_before_receipt_ns'] = time.perf_counter_ns()-begun
        save(folder/(arm+'_RECEIPT.json'), record)
    return record, payload, facts


def finish_owner(owner, native):
    begun = time.perf_counter_ns()
    metric = counts();metric['rpc_attempts'] = 1
    result = {'error': None, 'receipt': None}
    original = native.socket.create_connection
    def metered(*args, **kwargs): return MeterSocket(original(*args, **kwargs), metric)
    native.socket.create_connection = metered
    try: result['receipt'] = owner.close()
    except BaseException as exc: result['error'] = error_info(exc)
    finally:
        native.socket.create_connection = original
        result['elapsed_ns'] = time.perf_counter_ns()-begun
        result['transport'] = metric
        result['process_reaped'] = owner.process is not None and owner.process.poll() is not None
    return result


def compare_facts(full, retained, excluded):
    candidate = {oid: ({'status': 'not_evaluated_pruned', 'reason': 'strict_acquisition_bound'} if oid in excluded else retained[oid])
                 for oid in full}
    key = lambda row: (row['status'], row.get('reason'))
    full_unknown = {oid: row.get('reason') for oid, row in full.items() if row['status'] == 'unknown'}
    kept_unknown = {oid: row.get('reason') for oid, row in candidate.items() if row['status'] == 'unknown'}
    def best(rows):
        known = {oid: row['distance_m'] for oid, row in rows.items() if row['status'] == 'known'}
        value = min(known.values()) if known else None
        return {'value': value, 'ids': sorted(oid for oid, distance in known.items() if distance == value)}
    return {'candidate_all_IDs': candidate, 'full_all_IDs': full,
            'retained_status_and_reason_equal': all(key(full[oid]) == key(row) for oid, row in retained.items()),
            'retained_known_distances_equal': all(full[oid].get('distance_m') == row.get('distance_m')
                for oid,row in retained.items() if row['status'] == 'known'),
            'literal_full_M3_status_coverage_equal': all(key(full[oid]) == key(row) for oid, row in candidate.items()),
            'unknown_ID_reason_maps_equal': full_unknown == kept_unknown,
            'full_unknown': full_unknown, 'retained_unknown': kept_unknown,
            'missing_unknown_IDs': {oid: reason for oid, reason in full_unknown.items() if kept_unknown.get(oid) != reason},
            'known_minimum_and_ties_equal': best(full) == best(retained),
            'full_known_minimum': best(full), 'retained_known_minimum': best(retained),
            'full_scene_complete': False, 'scope': 'acquisition_only'}


def verify_math(full_scene, packet):
    full = {m['object_id']: m for m in full_scene['meshes']}
    kept = {m['object_id']: m for m in packet['capture']['meshes']}
    rows = packet['coverage'];by_row = {r['object_id']: r for r in rows}
    assert len(rows) == len(full) and set(by_row) == set(full)
    # Old full scene is geometry only. Its old process epoch must NOT be
    # compared with the current owned A/B session's identity.
    assert packet['binding']['unit'] == full_scene['unit'] == 'm'
    assert packet['binding']['coordinate_frame'] == full_scene['coordinate_frame'] == 'world'
    assert set(kept) == {r['object_id'] for r in rows if r['disposition'] == 'retained'}
    for oid, mesh in kept.items():
        assert mesh['vertices'] == full[oid]['vertices'] and mesh['faces'] == full[oid]['faces']
    focus_vertices = full[packet['focal_id']]['vertices']
    for row in rows:
        mesh = full[row['object_id']]
        bounds, witness = row['bounds_world_m'], row['witness']
        if bounds is not None:
            assert all(bounds[0][k] <= p[k] <= bounds[1][k] for p in mesh['vertices'] for k in range(3)), 'actual_mesh_outside_box'
        if witness is not None:
            ids = witness['triangle_vertex_indices']
            assert any(ids == f[i:]+f[:i] for f in mesh['faces'] for i in range(3)), 'witness_not_cyclic_actual_face'
            points = [mesh['vertices'][i] for i in ids]
            assert points == witness['triangle_world_m'] and points[0] == witness['point_world_m']
            e = [[F(points[j][k])-F(points[0][k]) for k in range(3)] for j in (1, 2)]
            assert any(e[0][i]*e[1][j] != e[0][j]*e[1][i] for i,j in ((0,1),(0,2),(1,2))), 'witness_degenerate'
        if row['disposition'] == 'excluded_strict_bound':
            assert row['lower_bound_m'] > packet['witness_upper_bound_m'], 'exclusion_not_strict'
            gap = max(F(0), *(min(F(p[k]) for p in mesh['vertices'])-max(F(p[k]) for p in focus_vertices) for k in range(3)),
                      *(min(F(p[k]) for p in focus_vertices)-max(F(p[k]) for p in mesh['vertices']) for k in range(3)))
            assert F(row['lower_bound_m']) <= gap, 'lower_not_conservative'
    seed = packet['upper_seed_id']
    if seed is not None:
        a = by_row[packet['focal_id']]['witness']['point_world_m']
        b = by_row[seed]['witness']['point_world_m']
        assert sum((F(x)-F(y))**2 for x,y in zip(a,b)) <= F(packet['witness_upper_bound_m'])**2
    return {'passed': True, 'full_objects': len(full), 'retained_objects': len(kept),
            'excluded_IDs': [r['object_id'] for r in rows if r['disposition'] == 'excluded_strict_bound']}


def main():
    plan_path = Path(sys.argv[1]).resolve();plan = json.loads(plan_path.read_bytes())
    root, out = Path(plan['root']), Path(plan['out'])
    start_ns, deadline = plan['start_ns'], plan['deadline_ns']
    summary = {'scope': 'acquisition_only', 'cases': [], 'primary_error': None, 'cleanup_errors': [], 'stages_ns': {}}
    owner = None
    def check():
        if time.perf_counter_ns() >= deadline: raise TimeoutError('original_batch_deadline')
    try:
        check();phase = time.perf_counter_ns()
        from human_eye_plugin.blender_mcp_host import BlenderMCPHost
        from human_eye_plugin.blender_host import BlenderSceneHost
        from human_eye_plugin.surface_proximity import measure_surface_proximity
        from human_eye_foveated_renderer import MeshEntity3D
        from human_eye_plugin.runtime_identity import runtime_identity
        identity = runtime_identity()
        assert identity['source_sha256'] == plan['product_sha256']
        assert VERIFIED_GUARD.verify_loaded()
        summary['product_identity'] = identity
        summary['stages_ns']['verified_imports'] = time.perf_counter_ns()-phase
        native_path = Path(plan['native_helper'])
        assert digest(native_path) == plan['native_helper_sha256']
        native = types.ModuleType('_m4_accepted_native');native.__file__ = str(native_path)
        sys.modules[native.__name__] = native
        exec(compile(native_path.read_bytes(),str(native_path),'exec',dont_inherit=True),native.__dict__)
        assert VERIFIED_GUARD.verify_loaded()
        if plan.get('entry_check_only'):
            summary['status'] = 'entry_verified_only_no_Blender'
            summary['native_helper_sha256'] = digest(native_path)
            return

        class MeteredHost(BlenderMCPHost):
            def _code(self,command,params,request_id):
                return "assert bpy.app.version_string == '5.2.1 LTS', 'frozen_Blender_version_changed'\n"+super()._code(command,params,request_id)
            def _connect(self, original_deadline): return MeterSocket(super()._connect(original_deadline), self.meter)
            def _exchange(self, payload):
                self.meter['rpc_attempts'] += 1
                return super()._exchange(payload)

        phase=time.perf_counter_ns()
        oracle=Path(plan['oracle_run'])
        assert digest(oracle/'FROZEN_ASSETS.json') == plan['oracle_frozen_assets_sha256']
        assets = json.loads((oracle/'assets/ASSETS.json').read_bytes())
        assert assets['blender_version']=='5.2.1 LTS'
        assert [r['case'] for r in assets['cases']] == plan['cases']
        for row in assets['cases']: assert digest(row['asset']) == row['sha256']
        for row in plan['oracle_full_raw']: assert digest(row['path'])==row['sha256']
        summary['assets_manifest_sha256'] = digest(oracle/'assets/ASSETS.json')
        save(out/'REUSED_FROZEN_ASSETS.json', {'manifest_sha256': summary['assets_manifest_sha256'], 'cases': assets['cases'],
            'geometry_oracle_only_no_old_times_or_epoch_reuse':True})
        summary['stages_ns']['old_asset_and_oracle_checks']=time.perf_counter_ns()-phase
        check()

        for index, asset in enumerate(assets['cases']):
            check()
            case = asset['case'];folder = out/('case_%02d_' % index+case);folder.mkdir()
            case_record = {'case': case, 'arms': {}, 'primary_error': None, 'cleanup': None}
            summary['cases'].append(case_record)
            owner = None
            try:
                phase = time.perf_counter_ns()
                owner_deadline = min(deadline, time.perf_counter_ns()+180_000_000_000)
                try:
                    owner = native.NativeSession.start(blender=plan['blender'],asset=asset['asset'],workspace=folder/'owned',
                        deadline_ns=owner_deadline,condition='N',expected_asset_sha256=asset['sha256'],max_calls=2)
                finally: case_record['startup_ns'] = time.perf_counter_ns()-phase
                address = owned_address(owner, plan['native_helper_sha256'])
                case_record['READY'] = owner.ready
                focal = BlenderSceneHost.object_id(types.SimpleNamespace(name=asset['focal_name'],name_full=asset['focal_name'],library=None))
                outputs = {}
                for arm in (('A','B') if index%2 == 0 else ('B','A')):
                    check()
                    arm_deadline = min(deadline, owner_deadline, time.perf_counter_ns()+60_000_000_000)
                    def host_factory():
                        return MeteredHost(plan['baseline_root'] if arm == 'A' else root,host=address[0],port=address[1],
                            timeout_s=max(.001,(arm_deadline-time.perf_counter_ns())/1e9))
                    def reader(host):
                        with host.observation_transaction():
                            return host.capture_nearest_candidates(focal,arm_deadline,8*1024*1024)
                    def solver(value):
                        scene = value['capture']
                        meshes = {m['object_id']: MeshEntity3D.from_dict(m) for m in scene['meshes']}
                        result = {}
                        def checkpoint(_):
                            check()
                            if time.perf_counter_ns() >= arm_deadline: raise TimeoutError('original_arm_deadline')
                        for oid, mesh in meshes.items():
                            if oid == focal: continue
                            measured = measure_surface_proximity(meshes[focal],mesh,checkpoint)
                            result[oid] = {'status': 'known' if measured['measurement_valid'] else 'unknown',
                                'reason': measured.get('reason'), 'distance_m': measured['distance_m'], 'measurement': measured}
                        checkpoint('publish');return result
                    record, payload, facts = record_arm(host_factory,reader,solver,folder,arm)
                    case_record['arms'][arm] = record
                    outputs[arm] = payload, facts
                    if record['error'] is not None:
                        expected = case == 'unsupported_modifier' and 'acquisition_static_triangle_source_required' in record['error']['message']
                        if not expected: raise RuntimeError('unexpected_arm_failure:'+record['error']['message'])
                        record['classification'] = 'expected_source_refusal'
                if case != 'unsupported_modifier':
                    old=json.loads(Path(plan['oracle_full_raw'][index]['path']).read_bytes())
                    packet_a,packet_b=outputs['A'][0],outputs['B'][0]
                    assert packet_a['binding']['host_identity']==packet_b['binding']['host_identity'],'current_A_B_source_binding_changed'
                    case_record['math']={arm:verify_math(old['payload'],outputs[arm][0]) for arm in ('A','B')}
                    case_record['comparison']={}
                    for arm in ('A','B'):
                        comparison=compare_facts(old['M3'],outputs[arm][1],case_record['math'][arm]['excluded_IDs'])
                        case_record['comparison'][arm]=comparison
                        assert comparison['retained_status_and_reason_equal'] and comparison['retained_known_distances_equal'],'retained_M3_state_changed'
                        if case=='far_second_degenerate':
                            far=BlenderSceneHost.object_id(types.SimpleNamespace(name='M4_Far_00',name_full='M4_Far_00',library=None))
                            assert comparison['missing_unknown_IDs'].get(far)=='surface_degenerate_triangle'
                        else:
                            assert comparison['unknown_ID_reason_maps_equal'] and comparison['known_minimum_and_ties_equal'],'known_or_unknown_fact_changed'
                    case_record['classification']='registered_contract_non_equivalence' if case=='far_second_degenerate' else 'unknown_geometry' if comparison['full_unknown'] else 'paired_known_geometry'
                    ua,ub=packet_a['witness_upper_bound_m'],packet_b['witness_upper_bound_m']
                    assert (ub if ub is not None else math.inf)<=(ua if ua is not None else math.inf),'B_upper_worse'
                    kept=lambda p:{m['object_id'] for m in p['capture']['meshes']}
                    assert kept(packet_b)<=kept(packet_a),'B_retained_set_expanded'
                    if case == 'loose_first_vertex':
                        case_record['classification'] = 'registered_loose_upper_diagnostic'
                        assert len(packet_a['capture']['meshes'])==3 and len(packet_b['capture']['meshes'])==2,'loose_case_no_actual_acquisition_reduction'
                        case_record['actual_global_upper_m'] = {'A':ua,'B':ub}
                else: case_record['classification'] = 'expected_source_refusal'
                assert VERIFIED_GUARD.verify_loaded()
            except BaseException as exc:
                case_record['primary_error'] = error_info(exc)
                raise
            finally:
                if owner is not None:
                    case_record['cleanup'] = finish_owner(owner,native)
                    closed_path = owner.workspace/'WORKER_CLOSED.json'
                    if closed_path.exists(): case_record['worker_closed'] = json.loads(closed_path.read_bytes())
                    save(folder/'CASE_RESULT.json',case_record)
                    cleanup = case_record['cleanup']
                    worker_closed = case_record.get('worker_closed', {})
                    if (not cleanup['process_reaped'] or cleanup['error'] or not cleanup['receipt']
                            or cleanup['receipt'].get('error') or not cleanup['receipt'].get('protected_files_unchanged')
                            or cleanup['receipt'].get('exit_code') != 0 or not worker_closed
                            or worker_closed.get('poisoned') is not False
                            or worker_closed.get('initial_geometry_fingerprint') != worker_closed.get('final_geometry_fingerprint')):
                        summary['cleanup_errors'].append({'case':case,'cleanup':cleanup})
                else: save(folder/'CASE_RESULT.json',case_record)
                owner = None
            if summary['cleanup_errors']: raise RuntimeError('owned_cleanup_failed')
        summary['status'] = 'complete_observation_not_product_admission'
    except BaseException as exc:
        summary['status'] = 'incomplete'
        summary['primary_error'] = error_info(exc)
    finally:
        summary['whole_driver_ns'] = time.perf_counter_ns()-start_ns
        summary['remaining_cases'] = plan['cases'][len(summary['cases']):]
        summary['Blender_builder_processes'] = 0
        summary['owned_sessions_attempted'] = len(summary['cases'])
        summary['model_consumers'] = summary['external_API_calls'] = summary['images'] = 0
        save(out/'RESULTS.json',summary)
    if summary['status'] == 'incomplete': raise SystemExit(1)


if __name__ == '__main__': main()
