"""Independent frozen-geometry and current A/B raw reconstruction only."""
import ast
import hashlib
import json
import math
from fractions import Fraction as F
from pathlib import Path

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[1]
RUN=BASE/'run_01'
def load(path):return json.loads(Path(path).read_bytes())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def geometry_check(oracle,packet):
    full={m['object_id']:m for m in oracle['meshes']}
    kept={m['object_id']:m for m in packet['capture']['meshes']}
    rows={r['object_id']:r for r in packet['coverage']}
    assert len(rows)==len(packet['coverage'])==len(full) and set(rows)==set(full)
    assert set(kept)=={oid for oid,r in rows.items() if r['disposition']=='retained'}
    for oid,mesh in kept.items():
        assert mesh['vertices']==full[oid]['vertices'] and mesh['faces']==full[oid]['faces']
    focal=full[packet['focal_id']]
    for oid,r in rows.items():
        mesh=full[oid];box=r['bounds_world_m'];w=r['witness']
        if box is not None:
            assert all(F(box[0][k])<=F(p[k])<=F(box[1][k]) for p in mesh['vertices'] for k in range(3))
        if w is not None:
            ids=w['triangle_vertex_indices'];points=[mesh['vertices'][i] for i in ids]
            assert any(ids==face[j:]+face[:j] for face in mesh['faces'] for j in range(3))
            assert points==w['triangle_world_m'] and points[0]==w['point_world_m']
            e=[[F(points[j][k])-F(points[0][k]) for k in range(3)] for j in (1,2)]
            assert any(e[0][i]*e[1][j]!=e[0][j]*e[1][i] for i,j in ((0,1),(0,2),(1,2)))
        if r['disposition']=='excluded_strict_bound':
            assert r['lower_bound_m']>packet['witness_upper_bound_m']
            gap=max(F(0),*(min(F(p[k]) for p in mesh['vertices'])-max(F(p[k]) for p in focal['vertices']) for k in range(3)),
                    *(min(F(p[k]) for p in focal['vertices'])-max(F(p[k]) for p in mesh['vertices']) for k in range(3)))
            assert F(r['lower_bound_m'])<=gap
    if packet['upper_seed_id'] is not None:
        a=rows[packet['focal_id']]['witness']['point_world_m'];b=rows[packet['upper_seed_id']]['witness']['point_world_m']
        assert sum((F(x)-F(y))**2 for x,y in zip(a,b))<=F(packet['witness_upper_bound_m'])**2
    assert packet['M3_qualification_performed'] is False and packet['execution_authority'] is False
    return full,kept,rows


def infer_upper_calls(packet_a):
    """Operation-count inference from frozen source and original A point order.

    Mirrors only the count walk, not the independent Fraction math validator.
    No native counter was installed and no product result is generated here.
    """
    rows=packet_a['coverage'];focal=next(r for r in rows if r['object_id']==packet_a['focal_id'])['witness']
    upper=math.inf;calls=0
    def upper_l1(a,b):
        total=0.
        for x,y in zip(a,b):
            if x!=y:total=math.nextafter(total+math.nextafter(abs(x-y),math.inf),math.inf)
        return total
    for row in rows:
        if row['object_id']==packet_a['focal_id']:continue
        w=row['witness']
        if focal is not None and w is not None and upper!=0.:
            for a in focal['triangle_world_m']:
                for b in w['triangle_world_m']:
                    calls+=1;value=upper_l1(a,b)
                    if value<upper:upper=value
                    if upper==0.:break
                if upper==0.:break
    return {'A_upper_calls':len(rows)-1,'B_upper_calls':calls,'A_B_lower_calls_each':len(rows),
        'kind':'source_and_ledger_inference_not_instrumented','predicted_B_upper':upper if math.isfinite(upper) else None}


def main():
    result,plan,command=[load(RUN/name) for name in ('RESULTS.json','FROZEN_PLAN.json','COMMAND_RECEIPT.json')]
    assert command['exit_code']==0 and not command['product_source_drift'] and command['process_reaped']
    assert result['status']=='complete_observation_not_product_admission' and result['Blender_builder_processes']==0
    assert not result['cleanup_errors'] and result['primary_error'] is None and len(result['cases'])==11
    for row in plan['qa_sources']:assert sha(row['path'])==row['sha256']
    for row in plan['product_manifest']:assert sha(ROOT/row['path'])==row['sha256']
    oracle=Path(plan['oracle_run']);oldbase=oracle.parent
    assert sha(oldbase/'DELIVERY_MANIFEST.json')=='e2e1e55af178051a2020696c71252e1fda5dafb035bc62e64c2bc73434bb8516'
    oldseal={r['path']:r['sha256'] for r in load(oldbase/'DELIVERY_MANIFEST.json')['files']}
    assets=load(oracle/'assets/ASSETS.json')
    assert sha(oracle/'FROZEN_ASSETS.json')==plan['oracle_frozen_assets_sha256']==oldseal['run_01/FROZEN_ASSETS.json']
    rows=[];rpc=0;totals={};pids=[]
    for index,case in enumerate(result['cases']):
        name=case['case'];folder=RUN/('case_%02d_'%index+name)
        source_asset=assets['cases'][index]
        assert sha(source_asset['asset'])==source_asset['sha256']==oldseal['run_01/assets/'+name+'.blend']
        full_path=Path(plan['oracle_full_raw'][index]['path'])
        assert sha(full_path)==plan['oracle_full_raw'][index]['sha256']==oldseal[str(full_path.relative_to(oldbase)).replace('\\','/')]
        old=load(full_path)
        config,ready,closed=[load(folder/'owned'/f) for f in ('CONFIG.json','READY.json','WORKER_CLOSED.json')]
        assert sha(config['asset_copy'])==source_asset['sha256']==config['asset_sha256']
        assert ready['initial_fingerprint']==closed['initial_geometry_fingerprint']==closed['final_geometry_fingerprint']
        assert ready['pid']==closed['pid']==case['cleanup']['receipt']['pid']
        assert closed['poisoned'] is False and case['cleanup']['process_reaped'] and case['cleanup']['receipt']['exit_code']==0
        assert not case['cleanup']['error'] and not case['cleanup']['receipt']['error']
        assert case['cleanup']['receipt']['source_file_unchanged'] and case['cleanup']['receipt']['protected_files_unchanged']
        assert 0<config['deadline_ns']-config['started_ns']<=180_000_000_000
        pids.append(ready['pid'])
        events=[json.loads(s) for s in (folder/'owned/WORKER_EVENTS.jsonl').read_text().splitlines()]
        assert [e['sequence'] for e in events]==[1,2,3]
        assert all(e['status']=='completed' and e['terminal_geometry_and_file_checks_passed']
                   and e['script_error'] is None and e['render_events_after']==0 for e in events[:2])
        order=('A','B') if index%2==0 else ('B','A')
        data={'case':name,'classification':case['classification'],'order':list(order)}
        raws={arm:load(folder/(arm+'_RAW.json')) for arm in ('A','B')}
        for seq,arm in enumerate(order,1):
            code=(folder/'owned'/('call_'+str(seq))/'SCRIPT.py').read_text(encoding='utf-8-sig')
            assert hashlib.sha256(code.encode()).hexdigest()==events[seq-1]['script_sha256']
            constants={n.value for n in ast.walk(ast.parse(code)) if isinstance(n,ast.Constant) and isinstance(n.value,str)}
            assert '5.2.1 LTS' in constants
            host_sha='ba83c5455f0e2a9a3e67443f04f4519fa064eabd6af108a6b94d3537783baa22' if arm=='A' else '62a50124424afdbc22ee184576a49a7edeae5ef3c9aaf7368e60b9947904f0a6'
            assert host_sha in constants
            rec=case['arms'][arm];payload=raws[arm]['payload'];scene=payload['capture'] if payload else None
            data[arm]={'status':rec['status'],'error':rec['error'],'whole_ms':rec['whole_arm_before_receipt_ns']/1e6,
                'capture_ms':rec['phase_ns']['capture']/1e6,'M3_ms':rec['phase_ns'].get('M3',0)/1e6,
                'connector_ms':rec['phase_ns']['connector_source_read_and_bind']/1e6,**rec['transport'],
                'objects':len(scene['meshes']) if scene else None,'vertices':sum(len(m['vertices']) for m in scene['meshes']) if scene else None,
                'faces':sum(len(m['faces']) for m in scene['meshes']) if scene else None,
                'upper_m':payload['witness_upper_bound_m'] if payload else None,'M3_pairs':len(raws[arm]['M3']) if raws[arm]['M3'] else 0}
            rpc+=rec['transport']['rpc_attempts']
            for key,value in rec['transport'].items():totals[key]=totals.get(key,0)+value
        rpc+=case['cleanup']['transport']['rpc_attempts']
        for key,value in case['cleanup']['transport'].items():totals[key]=totals.get(key,0)+value
        data['startup_ms']=case['startup_ns']/1e6;data['cleanup_ms']=case['cleanup']['elapsed_ns']/1e6
        data['observed_B_vs_A_percent']=100*(data['B']['whole_ms']/data['A']['whole_ms']-1)
        data['observed_first_minus_second_ms']=data[order[0]]['whole_ms']-data[order[1]]['whole_ms']
        if name!='unsupported_modifier':
            a,b=raws['A']['payload'],raws['B']['payload']
            assert set(a)==set(b)
            assert a['binding']['host_identity']==b['binding']['host_identity']
            fa,ka,ra=geometry_check(old['payload'],a);fb,kb,rb=geometry_check(old['payload'],b)
            assert set(kb)<=set(ka)
            assert (b['witness_upper_bound_m'] if b['witness_upper_bound_m'] is not None else math.inf)<=(a['witness_upper_bound_m'] if a['witness_upper_bound_m'] is not None else math.inf)
            unknown_full={oid:r['reason'] for oid,r in old['M3'].items() if r['status']=='unknown'}
            data['unknown_full_geometry_oracle_only']=unknown_full
            for arm in ('A','B'):
                retained=raws[arm]['M3']
                unknown={oid:r['reason'] for oid,r in retained.items() if r['status']=='unknown'}
                data[arm]['missing_unknown']={oid:reason for oid,reason in unknown_full.items() if unknown.get(oid)!=reason}
                for oid,r in retained.items():
                    assert r['status']==old['M3'][oid]['status'] and r['reason']==old['M3'][oid]['reason'] and r['distance_m']==old['M3'][oid]['distance_m']
            inferred=infer_upper_calls(a)
            assert inferred['predicted_B_upper']==b['witness_upper_bound_m']
            data['comparisons_inferred']=inferred
            data['math_verified_both']=True;data['current_A_B_identity_equal']=True;data['old_epoch_compared']=False
        else:
            assert all(data[arm]['status']=='failed' and 'acquisition_static_triangle_source_required' in data[arm]['error']['message'] for arm in ('A','B'))
            data['comparisons_inferred']=None
        rows.append(data)
    assert rpc==33
    loose=rows[-1]
    assert (loose['A']['objects'],loose['A']['vertices'],loose['A']['faces'])==(3,9,3)
    assert (loose['B']['objects'],loose['B']['vertices'],loose['B']['faces'])==(2,6,2)
    summary={'scope':'one_fixed_A_B_observation_not_statistics','candidate_B_source_sha256':plan['product_sha256'],
        'candidate_A_source_sha256':plan['oracle_source_sha256'],'cases':rows,'case_count':11,'math_arm_checks':20,
        'RPC_including_close':rpc,'geometry_capture_attempts':22,'returned_captures':20,'expected_refusals':2,
        'unexpected_errors':0,'builder_processes':0,'Blender_PID_observations_all_reaped':pids,
        'transport':totals,'whole_real_command_ms':command['whole_command_ns']/1e6,
        'all_first_arms_observed_slower_than_second':all(r['observed_first_minus_second_ms']>0 for r in rows),
        'deterministic_loose_work_reduction_passed':True,
        'attributable_or_stable_whole_cost_gain_established':False,
        'decision':'explicit_B_candidate_work_reduction_only_stop_route_no_B2',
        'old_full_timing_in_new_scores':False,'old_epoch_compared':False}
    (RUN/'ANALYSIS.json').write_bytes((json.dumps(summary,indent=2)+'\n').encode())
    for r in rows:print(r['case'],round(r['A']['whole_ms'],3),round(r['B']['whole_ms'],3),r['A']['objects'],r['B']['objects'],r['comparisons_inferred'])
    print('whole_command_ms',summary['whole_real_command_ms'],'RPC',rpc,'first_arm_pattern',summary['all_first_arms_observed_slower_than_second'])


if __name__=='__main__':main()
