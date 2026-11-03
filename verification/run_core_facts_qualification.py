"""Independent grading of recorded complete-core product calls.

Consumes an acquisition manifest, not arbitrary trusted packets. This verifies
finite QA observations; it is not a new production source-admission entry.
"""
import argparse,hashlib,json,math,sys
from pathlib import Path
from verification.model_trial.b3e_native import prepare_native,METRICS
from verification.deformation_context_oracle import (payload,verify_context,check_row as _check_row,
    verify_region,expected_memberships,digest)
from verification.deformation_anchor_oracle import PIN_KEYS
from verification.deformation_region_oracle import all_facts
from verification.core_facts_fixtures import analytic_expectation,verify_fixture_inputs

if not __debug__:raise RuntimeError('qualification requires enabled assertions')
REGISTRATION_SHA256={
    'legacy_registration':'1062e4939093158b13d4469e71af0ca61e7c6e5a9782f8a9d6901b5d65ce09ea',
    'heldout_registration':'32cb69ade69f622fb1c8c234d8b6f72af7984c291ef2eae827cb271ae18ea077',
}


def load(p):
    def pairs(items):
        value={}
        for key,child in items:
            if key in value:raise ValueError('duplicate QA JSON key')
            value[key]=child
        return value
    return json.loads(Path(p).read_bytes(),object_pairs_hook=pairs,
        parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite QA JSON')))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def same_facts(actual,expected):
    assert type(actual) is dict and type(expected) is dict
    assert set(actual)==set(expected),'fact field mismatch'
    assert type(actual['core_triangle_count']) is int and actual['core_triangle_count']>=0
    assert type(actual['core_states']) is dict and set(actual['core_states'])=={'measured','collapsed','unknown'}
    assert all(type(v) is int and v>=0 for v in actual['core_states'].values())
    assert sum(actual['core_states'].values())==actual['core_triangle_count']
    assert type(actual['core_unknown_reasons']) is dict and all(type(v) is int and v>0 for v in actual['core_unknown_reasons'].values())
    assert sum(actual['core_unknown_reasons'].values())==actual['core_states']['unknown']
    assert type(actual['core_extrema']) is dict and set(actual['core_extrema'])==set(METRICS)
    for key in ('core_status','core_triangle_count','core_states','core_unknown_reasons'):assert actual[key]==expected[key],(key,actual,expected)
    for k in METRICS:
        a=actual['core_extrema'][k];b=expected['core_extrema'][k]
        assert a is None and b is None or type(a) in (int,float) and type(b) in (int,float) and math.isfinite(a) and math.isfinite(b) and math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-9),(k,a,b)


def check_row(row,truth):
    assert type(row) is dict and type(row['triangle']) is int
    assert type(row['vertices']) is list and len(row['vertices'])==3 and all(type(v) is int for v in row['vertices'])
    if truth['state']!='unknown':
        values=row['principal_stretches']
        assert type(values) is list and len(values)==2 and all(type(v) in (int,float) and math.isfinite(v) for v in values)
        assert type(row['area_ratio']) in (int,float) and math.isfinite(row['area_ratio'])
    _check_row(row,truth)


def verify_region_strict(report,packet,region):
    checked=verify_region(report,packet,region)
    query=report['region_query'];rows=query['triangles']
    assert type(rows) is list and len(rows)==min(4,len(checked['matched_triangle_indices']))
    row_ids=[row['triangle'] for row in rows]
    assert len(set(row_ids))==len(row_ids) and set(row_ids)<=set(checked['matched_triangle_indices'])
    for row in rows:check_row(row,checked['facts'][row['triangle']])
    return checked


def validate_manifest(manifest):
    assert manifest['schema']=='complete-core-acquisition-manifest-v1'
    assert type(manifest['blocks']) is int and manifest['blocks']==3
    assert type(manifest['cases']) is list and len(manifest['cases'])==16
    expected={};registrations={}
    for key,hash_value in REGISTRATION_SHA256.items():
        assert sha(manifest[key])==hash_value,('changed frozen registration',key)
        registrations[key]=load(manifest[key])
    for case in registrations['legacy_registration']['cases']:
        assert case['name'] not in expected
        expected[case['name']]=(False,case)
    for case in registrations['heldout_registration']['cases']:
        assert case['case'] not in expected
        expected[case['case']]=(True,case)
    assert len(expected)==16 and {c['case'] for c in manifest['cases']}==set(expected)
    assert len({c['case'] for c in manifest['cases']})==len(manifest['cases'])
    runtime=manifest['runtime_source_sha256']
    assert type(runtime) is str and len(runtime)==64 and all(v in '0123456789abcdef' for v in runtime)
    assert Path(manifest['entry']).is_absolute() and Path(manifest['python']).is_absolute()
    assert sha(manifest['entry'])==manifest['entry_sha256']
    folders=set()
    for case in manifest['cases']:
        assert type(case['heldout']) is bool and case['heldout'] is expected[case['case']][0]
        assert all(Path(case[k]).is_absolute() for k in ('catalog','policy','profile','selection'))
        calls=case['calls'];assert type(calls) is list and len(calls)==6
        slots=set()
        for call in calls:
            assert call['mode'] in ('core','context') and type(call['block']) is int and 0<=call['block']<3
            slot=(call['mode'],call['block']);assert slot not in slots;slots.add(slot)
            folder=Path(call['folder']);assert folder.is_absolute()
            normalized=str(folder.resolve()).casefold();assert normalized not in folders;folders.add(normalized)
        assert slots=={(mode,block) for mode in ('core','context') for block in range(3)}
    return registrations,expected


def validate_command(receipt,call,manifest,policy_path):
    command=receipt['command'];assert type(command) is list and len(command)==14
    entry=Path(manifest['entry']);profile=Path(receipt['operator_profile'])
    assert command[:4]==[manifest['python'],'-I','-B',manifest['entry']]
    assert sha(entry)==receipt['entry_sha256']==manifest['entry_sha256']
    assert command[4]=='--operator-profile' and Path(command[5]).resolve()==profile.resolve()
    assert command[6]=='--output' and Path(command[7]).resolve()==Path(call['folder']).resolve()/'readback'
    assert command[8]==('--core-query' if call['mode']=='core' else '--context-query')
    selection_path=Path(command[9]);assert selection_path.is_absolute()
    assert command[10]=='--context-policy' and Path(command[11]).resolve()==Path(policy_path).resolve()
    assert command[12]=='--context-policy-sha256' and command[13]==sha(policy_path)==receipt['context_policy_sha256']
    assert sha(profile)==receipt['operator_profile_sha256'] and sha(selection_path)==receipt['selection_sha256']
    return profile,load(selection_path)


def check_policy_domain(case,policy,registrations,expected,manifest):
    heldout,record=expected[case['case']]
    if heldout:
        fixed=registrations['heldout_registration']['fixed_policy']
        wanted=dict(required_core_half_extents_m=fixed['core_half'],primary_half_extents_m=fixed['primary_half'],
            candidate_half_extents_m=fixed['candidates'],max_surplus_members=fixed['max_surplus_members'],
            min_saved_bytes=fixed['min_saved_bytes'],planning_budget_ms=fixed['planning_budget_ms'])
    elif record['authored']:
        wanted=dict(required_core_half_extents_m=record['core'],primary_half_extents_m=record['primary'],
            candidate_half_extents_m=record['candidates'],max_surplus_members=record['max_surplus_members'],
            min_saved_bytes=256,planning_budget_ms=250)
    else:
        # Reuse the already sealed actual operator INPUT, whose domain differs
        # from the old nominal registration for these two external static frames.
        previous=Path(manifest['legacy_registration']).parent/'actual_context_queries_r1'/case['case']/'POLICY.json'
        old=load(previous)
        wanted={k:old[k] for k in ('required_core_half_extents_m','primary_half_extents_m',
            'candidate_half_extents_m','max_surplus_members','min_saved_bytes','planning_budget_ms')}
    if not heldout:
        previous=Path(manifest['legacy_registration']).parent/'actual_context_queries_r1'/case['case']/'POLICY.json'
        assert policy['source_ref']==load(previous)['source_ref'],'registered legacy asset/frame/roles changed'
    for key,value in wanted.items():assert policy[key]==value,('policy domain changed',case['case'],key)


def exterior_challenge(packet,analytic):
    """A heldout's intended difficulty must actually exist in captured data."""
    core=analytic['members'];total=len(packet['inputs']['mesh']['triangles'])
    exterior=[i for i in range(total) if i not in set(core)]
    rows=all_facts(packet,exterior);measured=[r for r in rows.values() if r['state']!='unknown']
    unknown={str(i):r['reason'] for i,r in rows.items() if r['state']=='unknown'}
    maximum=max((r['principal_stretches'][0] for r in measured),default=None)
    area=max((r['area_ratio'] for r in measured),default=None)
    facts=analytic['facts']['core_extrema']
    realized=maximum is not None and area is not None and maximum>facts['max_principal_stretch'] and area>facts['max_area_ratio']
    return dict(status='realized' if realized else 'not_realized',passed=realized,
        exterior_triangle_indices=exterior,unknown_reasons=unknown,max_measured_principal_stretch=maximum,
        max_measured_area_ratio=area,reason='independent_measured_exterior_extrema_exceed_core' if realized else
        'exterior_unknown_or_no_larger_measurable_extrema',oracle='independent_full_snapshot_QR_SVD_not_production_metrics')


def verify_call(call,*,runtime_source_sha256,catalog,policy_path,manifest,case):
    folder=Path(call['folder']);receipt=load(folder/'EXECUTION.json');readback=folder/'readback'
    assert receipt['actual_subprocess'] is True and type(receipt['exit_code']) is int and receipt['exit_code']==0
    assert type(receipt['complete_tool_wall_ns']) is int and receipt['complete_tool_wall_ns']>0
    report=load(readback/'REPORT.json');packet=load(readback/'SNAPSHOTS.json')['second'];publication=load(readback/'PUBLICATION.json')
    out=(folder/'STDOUT.txt').read_bytes();assert out==payload(report) and out.isascii()
    assert publication['payload_bytes']==len(out) and publication['payload_sha256']==sha(folder/'STDOUT.txt')==receipt['stdout_sha256']
    profile_path,selection=validate_command(receipt,call,manifest,policy_path)
    assert profile_path.resolve()==Path(case['profile']).resolve()
    assert Path(receipt['command'][9]).resolve()==Path(case['selection']).resolve()
    profile=load(profile_path);policy=load(policy_path)
    assert profile['runtime_source_sha256']==packet['identity']['runtime_source_sha256']==runtime_source_sha256
    assert profile['scene_sha256']==sha(profile['scene_file'])==packet['identity']['scene_sha256']
    assert profile['blender_sha256']==sha(profile['blender_executable'])==packet['identity']['binary_sha256']
    assert profile['mesh_name']==packet['inputs']['mesh']['name'] and profile['rig_name']==packet['inputs']['rig']['name']
    assert profile['expected_frame']==packet['inputs']['frame'] and profile['unit_scale_m']==packet['inputs']['unit_scale_m']
    assert sha(profile_path)==packet['identity']['profile_sha256']
    assert catalog['operator_pins']=={key:packet['identity'][key] for key in PIN_KEYS}
    assert selection==dict(schema='surface-deformation-context-selection-v1',source_ref=catalog['source_ref'],
        catalog_sha256=catalog['catalog_sha256'],anchor_id=policy['anchor_id'],policy_sha256=sha(policy_path))
    assert report['source_sha256']==packet['source_sha256'] and report['execution_authority'] is False
    assert type(report['geometry_setters']) is int and report['geometry_setters']==0 and report['original_file_saved'] is False
    assert Path(publication['report_file']).resolve()==(readback/'REPORT.json').resolve()
    assert Path(publication['snapshot_file']).resolve()==(readback/'SNAPSHOTS.json').resolve()
    assert type(publication['elapsed_ns']) is int and 0<publication['elapsed_ns']<30_000_000_000
    native,truth=prepare_native(packet,catalog,policy)
    if call['mode']=='context':
        audit=load(readback/'CONTEXT_AUDIT.json')
        expected=expected_memberships(packet,catalog,policy)
        primary=audit['primary_report'];assert primary['source_sha256']==packet['source_sha256']
        verify_region_strict(primary,packet,expected['primary_region'])
        assert [r['triangle'] for r in audit['core_rows']]==expected['core_members']
        for row in audit['core_rows']:check_row(row,expected['core_facts'][row['triangle']])
        for record in audit['candidate_records']:
            if 'report' in record:
                verify_region_strict(record['report'],packet,expected['candidate_regions'][record['candidate_index']])
        verified=verify_context(report,audit,packet,catalog,policy,primary)
        assert verified['core_members']==truth['core_triangle_indices']
        return dict(report=report,packet=packet,audit=audit,native=native,truth=truth)
    assert call['mode']=='core' and report['schema']=='surface-deformation-core-facts-v1'
    audit=load(readback/'CORE_AUDIT.json');same_facts(report['facts'],truth['facts'])
    assert report['core_ref']['region']==truth['core_region'] and report['source_ref']==truth['source_ref']
    assert report['core_ref']['policy_sha256']==sha(policy_path) and report['core_ref']['catalog_sha256']==catalog['catalog_sha256']
    assert report['operator_pins']==catalog['operator_pins'] and audit['core_triangle_indices']==truth['core_triangle_indices']
    assert audit['core_rows_sha256']==digest(audit['core_rows'])
    assert audit['actor_B2_rows_passes']==1 and audit['geometry_cache_preparations']==audit['region_scans']==1
    assert audit['pure_projection_B2_rows_passes']==audit['pure_projection_geometry_cache_preparations']==audit['pure_projection_region_scans']==audit['candidates_evaluated']==0
    assert audit['published_publication_bytes']==len(out) and audit['published_publication_sha256']==sha(folder/'STDOUT.txt')
    assert [r['triangle'] for r in audit['core_rows']]==truth['core_triangle_indices']
    for row in audit['core_rows']:check_row(row,truth['core_facts'][row['triangle']])
    for metric in METRICS:
        witness=report['core_witnesses'][metric];value=truth['facts']['core_extrema'][metric]
        if value is None:assert witness is None
        else:
            assert type(witness) is int and witness in truth['core_triangle_indices'] and truth['core_facts'][witness]['state']!='unknown'
            row=truth['core_facts'][witness];v=row['principal_stretches'][0 if metric=='max_principal_stretch' else 1] if 'stretch' in metric else row['area_ratio']
            assert math.isclose(v,value,rel_tol=1e-9,abs_tol=1e-9)
            values={r['triangle']:(r['principal_stretches'][0 if metric=='max_principal_stretch' else 1] if 'stretch' in metric else r['area_ratio'])
                for r in audit['core_rows'] if r['state']!='unknown'}
            best=(max if metric.startswith('max') else min)(values.values())
            assert witness==min(i for i,v in values.items() if v==best),'exact production tie must use lowest ID'
    c=report['completeness'];assert c['membership_complete'] is True and c['core_facts_complete'] is True and c['metric_witnesses_complete'] is True and c['unknown_reasons_omitted']==0
    assert c['member_ids_omitted']==c['per_face_rows_omitted']==len(truth['core_triangle_indices'])
    assert report['scope']['peripheral_shrinking'] is False and report['scope']['damage']=='not_inferred'
    return dict(report=report,packet=packet,audit=audit,native=native,truth=truth)


def qualify(manifest):
    registrations,expected=validate_manifest(manifest)
    results=[]
    for case in manifest['cases']:
        catalog=load(case['catalog']);checks=[]
        check_policy_domain(case,load(case['policy']),registrations,expected,manifest)
        analytic=analytic_expectation(registrations['heldout_registration'],case['case']) if case['heldout'] else None
        if analytic is not None:
            if case.get('analytic_facts') is not None:same_facts(case['analytic_facts'],analytic['facts'])
            if case.get('analytic_members') is not None:assert case['analytic_members']==analytic['members']
        for call in case['calls']:
            checked=verify_call(call,runtime_source_sha256=manifest['runtime_source_sha256'],catalog=catalog,policy_path=case['policy'],manifest=manifest,case=case)
            if analytic is not None:
                verify_fixture_inputs(checked['packet'],registrations['heldout_registration'],case['case'])
                same_facts(checked['truth']['facts'],analytic['facts'])
                if call['mode']=='core':same_facts(checked['report']['facts'],analytic['facts'])
                assert checked['truth']['core_triangle_indices']==analytic['members']
            row=dict(mode=call['mode'],block=call['block'],folder=call['folder'],all_passed=True,source_sha256=checked['packet']['source_sha256'])
            if case['case']=='outer_dominates_mixed18':row['exterior_challenge']=exterior_challenge(checked['packet'],analytic)
            checks.append(row)
        results.append(dict(case=case['case'],heldout=case['heldout'],checks=checks))
    challenges=[check['exterior_challenge'] for case in results for check in case['checks'] if 'exterior_challenge' in check]
    return dict(schema='complete-core-recorded-qualification-v1',all_passed=True,core_facts_gate_passed=True,cases=results,
        all_registered_exterior_challenges_realized=all(c['passed'] for c in challenges),
        unverified_challenge_not_advantage_evidence=True,
        scope='Finite recorded product entry and independent SAT/NumPy metrics; six heldouts also analytic. Not universal source admission or model benefit.')


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args(argv)
    result=qualify(load(args.manifest))
    with args.output.open('x',encoding='utf8') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(dict(all_passed=result['all_passed'],cases=len(result['cases']))));return 0


if __name__=='__main__':raise SystemExit(main())
