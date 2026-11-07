"""Independent raw reconstruction; no production or QA-driver imports/runs."""
import ast
import csv
import hashlib
import json
import math
from fractions import Fraction as F
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN = Path(__file__).with_name('run_01')
def load(path): return json.loads(Path(path).read_bytes())
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    result, plan = load(RUN/'RESULTS.json'), load(RUN/'FROZEN_PLAN.json')
    command = load(RUN/'COMMAND_RECEIPT.json')
    assert result['status'] == 'complete_observation_not_product_admission'
    assert command['exit_code'] == 0 and command['process_reaped'] and not command['product_source_drift']
    assert result['primary_error'] is None and result['cleanup_errors'] == []
    assert len(result['cases']) == len(plan['cases']) == 11
    for row in plan['qa_sources']: assert sha(row['path']) == row['sha256']
    for row in plan['product_manifest']: assert sha(ROOT/row['path']) == row['sha256']
    assert sha(plan['native_helper']) == plan['native_helper_sha256']
    assets = load(RUN/'assets/ASSETS.json')
    assert sha(RUN/'assets/ASSETS.json') == result['assets_manifest_sha256']
    assert [x['case'] for x in assets['cases']] == plan['cases']
    rows, raw_rpc, byte_totals, pids = [], 0, {}, [result['builder']['pid']]
    math_cases = 0
    for index, case in enumerate(result['cases']):
        name = case['case'];folder = RUN/('case_%02d_'%index+name)
        original = assets['cases'][index]
        assert sha(original['asset']) == original['sha256']
        config, ready, closed = [load(folder/'owned'/f) for f in ('CONFIG.json','READY.json','WORKER_CLOSED.json')]
        assert config['asset_sha256'] == sha(config['asset_copy']) == original['sha256']
        assert ready['pid'] == closed['pid'] == case['cleanup']['receipt']['pid']
        pids.append(ready['pid'])
        assert ready['initial_fingerprint'] == closed['initial_geometry_fingerprint'] == closed['final_geometry_fingerprint']
        assert closed['poisoned'] is False and case['cleanup']['process_reaped']
        assert case['cleanup']['receipt']['exit_code'] == 0 and case['cleanup']['error'] is None
        assert case['cleanup']['receipt']['protected_files_unchanged'] and case['cleanup']['receipt']['source_file_unchanged']
        assert 0 < config['deadline_ns']-config['started_ns'] <= 180_000_000_000
        events = [json.loads(line) for line in (folder/'owned/WORKER_EVENTS.jsonl').read_text().splitlines()]
        assert [x['sequence'] for x in events] == [1,2,3]
        assert all(x['status'] == 'completed' and x['terminal_geometry_and_file_checks_passed']
                   and x['script_error'] is None and x['render_events_after'] == 0 for x in events[:2])
        # The unchanged helper leaves the close event at its initial "unknown"
        # label. Close response + WORKER_CLOSED + owner.wait establish outcome.
        assert case['cleanup']['receipt']['response']['status'] == 'closed'
        order = ('full','candidate') if index%2 == 0 else ('candidate','full')
        for sequence, arm in enumerate(order,1):
            script = folder/'owned'/('call_'+str(sequence))/'SCRIPT.py'
            raw = script.read_bytes()
            # The unchanged Windows helper writes SCRIPT.py via write_text,
            # while its event hashes the original LF request string it executes.
            # Verify that executed text separately from stored file bytes.
            text = script.read_text(encoding='utf-8-sig')
            assert hashlib.sha256(text.encode('utf8')).hexdigest() == events[sequence-1]['script_sha256']
            tree = ast.parse(text)
            constants = {n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and isinstance(n.value,str)}
            expected_host = ('5d2605d9cac66b0755bb5c68af37d852f49285f109448c7dd9220d4d3494a307'
                             if arm == 'full' else 'ba83c5455f0e2a9a3e67443f04f4519fa064eabd6af108a6b94d3537783baa22')
            assert expected_host in constants
        full, candidate = [load(folder/(arm+'_RAW.json')) for arm in ('full','candidate')]
        data = {'case':name,'classification':case['classification']}
        for arm, raw in (('full',full),('candidate',candidate)):
            rec = case['arms'][arm]
            for key,value in rec['transport'].items(): byte_totals[key] = byte_totals.get(key,0)+value
            raw_rpc += rec['transport']['rpc_attempts']
            payload = raw['payload']
            scene = payload if arm == 'full' else payload['capture'] if payload is not None else None
            data[arm] = {'status':rec['status'],'error':rec['error'],
                'whole_ms':rec['whole_arm_before_receipt_ns']/1e6,'capture_ms':rec['phase_ns'].get('capture',0)/1e6,
                'M3_ms':rec['phase_ns'].get('M3',0)/1e6, 'connector_ms':rec['phase_ns']['connector_source_read_and_bind']/1e6,
                **rec['transport'], 'objects':len(scene['meshes']) if scene else None,
                'vertices':sum(len(m['vertices']) for m in scene['meshes']) if scene else None,
                'faces':sum(len(m['faces']) for m in scene['meshes']) if scene else None}
        raw_rpc += case['cleanup']['transport']['rpc_attempts']
        for key,value in case['cleanup']['transport'].items(): byte_totals[key] = byte_totals.get(key,0)+value
        data['startup_ms'] = case['startup_ns']/1e6
        data['cleanup_ms'] = case['cleanup']['elapsed_ns']/1e6
        if name != 'unsupported_modifier':
            scene, packet = full['payload'], candidate['payload']
            meshes = {x['object_id']:x for x in scene['meshes']}
            selected = {x['object_id']:x for x in packet['capture']['meshes']}
            coverage = {x['object_id']:x for x in packet['coverage']}
            assert len(coverage) == len(packet['coverage']) == len(meshes) and set(meshes) == set(coverage)
            assert packet['binding']['host_identity'] == scene['host_identity']
            for oid,mesh in selected.items():
                assert mesh['vertices'] == meshes[oid]['vertices'] and mesh['faces'] == meshes[oid]['faces']
            focal = meshes[packet['focal_id']]
            for oid,row in coverage.items():
                mesh = meshes[oid];bounds=row['bounds_world_m'];w=row['witness']
                if bounds is not None:
                    assert all(F(bounds[0][k]) <= F(p[k]) <= F(bounds[1][k]) for p in mesh['vertices'] for k in range(3))
                if w is not None:
                    ids=w['triangle_vertex_indices'];points=[mesh['vertices'][i] for i in ids]
                    assert any(set(face) == set(ids) for face in mesh['faces'])
                    assert points == w['triangle_world_m'] and points[0] == w['point_world_m']
                    e=[[F(points[j][k])-F(points[0][k]) for k in range(3)] for j in (1,2)]
                    assert any(e[0][i]*e[1][j] != e[0][j]*e[1][i] for i,j in ((0,1),(0,2),(1,2)))
                if row['disposition'] == 'excluded_strict_bound':
                    assert row['lower_bound_m'] > packet['witness_upper_bound_m']
                    gap=max(F(0),*(min(F(p[k]) for p in mesh['vertices'])-max(F(p[k]) for p in focal['vertices']) for k in range(3)),
                            *(min(F(p[k]) for p in focal['vertices'])-max(F(p[k]) for p in mesh['vertices']) for k in range(3)))
                    assert F(row['lower_bound_m']) <= gap
            if packet['upper_seed_id']:
                a=coverage[packet['focal_id']]['witness']['point_world_m'];b=coverage[packet['upper_seed_id']]['witness']['point_world_m']
                assert sum((F(x)-F(y))**2 for x,y in zip(a,b)) <= F(packet['witness_upper_bound_m'])**2
            unknown_full={oid:r['reason'] for oid,r in full['M3'].items() if r['status']=='unknown'}
            unknown_kept={oid:r['reason'] for oid,r in candidate['M3'].items() if r['status']=='unknown'}
            missing={oid:r for oid,r in unknown_full.items() if unknown_kept.get(oid)!=r}
            assert missing == case['comparison']['missing_unknown_IDs']
            data.update(math_verified=True,unknown_full=unknown_full,unknown_retained=unknown_kept,missing_unknown=missing,
                retained_distances_equal=case['comparison']['retained_known_distances_equal'],
                known_minimum_and_ties_equal=case['comparison']['known_minimum_and_ties_equal'],
                literal_M3_status_coverage_equal=case['comparison']['literal_full_M3_status_coverage_equal'],
                upper_m=packet['witness_upper_bound_m'],M3_full_pairs=len(full['M3']),M3_retained_pairs=len(candidate['M3']))
            if name=='loose_first_vertex':
                focus=coverage[packet['focal_id']]['witness']['triangle_world_m']
                exact_bounds=[sum(abs(F(a[k])-F(b[k])) for k in range(3)) for oid,row in coverage.items()
                    if oid!=packet['focal_id'] and row['witness'] is not None for a in focus for b in row['witness']['triangle_world_m']]
                data['nine_existing_point_pairs_exact_upper_m']=float(min(exact_bounds))
                data['potential_only_no_optimization_or_rerun']=True
            math_cases += 1
        else:
            assert data['candidate']['status']=='failed' and 'acquisition_static_triangle_source_required' in data['candidate']['error']['message']
            data['math_verified']=None
        data['pair_observed_whole_delta_percent']=100*(data['candidate']['whole_ms']/data['full']['whole_ms']-1)
        rows.append(data)
    assert len(set(pids)) == 12 and raw_rpc == 33
    summary = {'scope':'one_fixed_paired_observation_not_statistics','source_sha256':plan['product_sha256'],
        'case_count':11,'math_checked_cases':math_cases,'geometry_RPC_attempts':22,'total_RPC_including_close':raw_rpc,
        'capture_returned':21,'expected_source_refusals':1,'unexpected_errors':0,'Blender_PIDs_reaped':pids,
        'assets_all_unchanged':True,'product_all131_unchanged':True,'QA_runtime_files_unchanged':True,
        'builder_ms':result['builder']['elapsed_ns']/1e6,'whole_real_command_ms':command['whole_command_ns']/1e6,
        'transport':byte_totals,'cases':rows,
        'script_hash_note':'Worker SCRIPT.py uses Windows CRLF via write_text; event binds original executed LF string. All22 normalized text SHA match their execution events; stored bytes are also sealed in delivery manifest.',
        'close_audit_note':'Original helper close event label unknown; independently confirmed closed response, unchanged WORKER_CLOSED and Popen reap for all11.'}
    (RUN/'ANALYSIS.json').write_bytes((json.dumps(summary,indent=2)+'\n').encode())
    for row in rows:
        print(row['case'],round(row['full']['whole_ms'],3),round(row['candidate']['whole_ms'],3),
              round(row['pair_observed_whole_delta_percent'],2),row['full']['objects'],row['candidate']['objects'])
    print('RPC',raw_rpc,'math',math_cases,'real_command_ms',summary['whole_real_command_ms'])


if __name__=='__main__':main()
