"""Frozen A1c functional contract, never a model or production permission."""
import copy,hashlib,json,math
from pathlib import Path
from verification.engineering_task_contract import choose_region,he_regions,digest

ROOT=Path(__file__).resolve().parents[1]
BUILD='955895672b5a04308bad314665c564a766589b54b079e9f9d0a5591d24a67bf0'
CONTRACT='anchored_boundary_observation_v1'
ASSETS={
 'closed_torus':'189f4e73563a329312d1e0575796f2ad63c1b7f6b77bb839fb0966056872bbc7',
 'opened_torus':'fc53e7e79e387f3fa0b64fb204065104a674c660794f578b239f0cd2dd6e417f',
 'nonplanar_clear':'2624942ef11d6dcc2b3e293caec8473dd9186d0f30661b46748ee3551234e28a',
 'center_blocked':'558d5e60994d02ffad6e2a1f2b71d3c9470eb3b048b271a273bd614913ecb05a',
 'feature_blocked':'c2ead66626d98fcf010ca7084da4e7195911917eb628047195221c55db56e1bb',
 'dense1808':'2f4f1c4594e4e2eb828b1e5aa872a301fa6cb1e80b0620d5c14da0e324219250',
 'local128':'3082a59649e33220fe7320664fe1a6bd782a89def62e4bc579d52ec2a8d36941',
 'wire_and_isolated':'c78f529691f7e37ea07f398959c80ac00a0accdb2fa23df1e5cceaf8863c8891'}
CATEGORIES=['boundary_edges','loose_edges','isolated_vertices']
HELPERS=('engineering_task_contract.py','engineering_native_service.py','engineering_stdio.py','engineering_owned_server.py',
 'native_engineering_baseline.py','run_native_engineering_preflight.py','engineering_qualification.py','engineering_evidence.py','run_engineering_qualification.py',
 'engineering_baseline_cases.py','structure_task_representatives.py','nonplanar_patch_fixtures.py','nonplanar_dense_fixtures.py')
POLICY=dict(schema='m2-a1c-registration-v1',engine_build=BUILD,task_contract=CONTRACT,assets=ASSETS,
 phases={'native_reference':dict(arm='native',rounds=3,tasks=3),'functional_qualification':dict(arm='he',rounds=1,tasks=1)},
 limits=dict(queries=6,images=2,png_bytes=16777216,text_bytes=524288,refs=16,duration_s=180,registrations=16),
 first_limit_ms=3390,warm_limit_ms=2000,source_members_per_selected_region=64,
 io='one_host_outer_reply_per_RPC_and_one_client_PNG_per_received_image',
 quality='counts_all_boundary_positions_selected_complete_members_and_registered_pixel_floors',
 old_global_members_gate_unchanged=True,full_guarantee_equivalence=False,HE_cost_trials_permitted=False,model_trials_permitted=False)


def need(condition,reason):
    if not condition:raise ValueError(reason)


def registration():return copy.deepcopy(POLICY)


def admit(spec):
    """Trusted harness spec; no natural-language/tool argument can select a phase."""
    path=Path(spec['qualification_registration']);raw=path.read_bytes()
    need(len(raw)<=65536 and hashlib.sha256(raw).hexdigest()==spec['qualification_sha256'],'qualification_registration_digest')
    value=json.loads(raw);need(digest(value)==digest(POLICY),'qualification_contract_changed')
    phase=spec['purpose'];need(phase in POLICY['phases'],'qualification_purpose')
    need(spec['arm']==POLICY['phases'][phase]['arm'],'qualification_arm')
    need(spec.get('case_id') in ASSETS and spec.get('asset_task_sha256')==ASSETS[spec['case_id']],'qualification_asset')
    helpers=spec['helpers'];need(type(helpers) is dict and len(helpers)==len(HELPERS)
        and {Path(p).name for p in helpers}==set(HELPERS),'qualification_helpers')
    for name,expected in helpers.items():
        p=Path(name);need(p.resolve()==p and p.parent==ROOT/'verification','qualification_helper_root')
        need(hashlib.sha256(p.read_bytes()).hexdigest()==expected,'qualification_helper_changed')
    return value


def integer(v):return type(v) is int and v>=0


def canonical(group,category):
    need(type(group) is list and bool(group),'qualification_members')
    if category=='isolated_vertices':
        need(all(integer(v) for v in group),'qualification_member_index');members=group
    else:
        need(all(type(e) is list and len(e)==2 and all(integer(v) for v in e) and e[0]!=e[1] for e in group),'qualification_member_edge')
        members=[tuple(sorted(e)) for e in group]
    need(len(set(members))==len(members),'qualification_duplicate_member')
    return sorted(members)


def normalize(value,arm):
    """Only public fields. No asset, oracle, source-index hint or private file."""
    need(arm in ('native','he'),'qualification_arm')
    if arm=='native':
        facts=value['native']['facts'];regions=copy.deepcopy(value['regions'])
        need(set(facts)==set(CATEGORIES) and len(regions)==len(facts['boundary_edges']),'qualification_native_categories')
        for region,members in zip(regions,facts['boundary_edges']):
            region.update(members=members,member_count=len(members),patch_ref=region['ref'],selection_only=False)
        totals={c:len(facts[c]) for c in CATEGORIES};complete=value['region_coverage']['complete'] is True
        coverage=copy.deepcopy(value['region_coverage']);known={c:True for c in CATEGORIES}
    else:
        d=value['diagnostic'];need(d['protocol']=='raw-mesh-structure-v3','qualification_HE_protocol')
        checks=d['report']['checks'];need(set(checks)==set(CATEGORIES),'qualification_HE_categories')
        facts={c:checks[c]['regions'] for c in CATEGORIES};totals={c:checks[c]['total'] for c in CATEGORIES}
        complete=all(checks[c]['state']=='complete' for c in CATEGORIES)
        regions,coverage=he_regions(value);patches={}
        for c in CATEGORIES:
            rows=[p for p in d['patches'] if p['category']==c]
            need(len(rows)==len(facts[c]),'qualification_patch_distribution')
            for p,members in zip(rows,facts[c]):patches[(c,p['cluster_ordinal'])]=members
        refs={r['patch_ref']:(r['category'],r['cluster_ordinal']) for r in value['patch_refs']}
        summaries={r['summary_id']:r for r in d['region_summary']['entries']}
        for region in regions:
            if region['selection_only']:
                region.update(members=None,member_count=summaries[region['ref']]['member_count'])
            else:
                members=patches[refs[region['patch_ref']]];region.update(members=members,member_count=len(members))
        known={c:d['region_summary']['coverage'][c]['member_lists_complete'] for c in CATEGORIES}
    need(all(type(facts[c]) is list for c in CATEGORIES),'qualification_facts')
    for c in CATEGORIES:
        for group in facts[c]:canonical(group,c)
    for r in regions:
        need(integer(r['member_count']) and r['member_count']>0,'qualification_member_count')
        if not r['selection_only']:need(len(r['members'])==r['member_count'],'qualification_member_count')
    return dict(totals=totals,scan_complete=complete,facts=facts,regions=regions,region_coverage=coverage,
        member_lists_complete=known,published_members={c:sum(len(g) for g in facts[c]) for c in CATEGORIES})


def select(normalized,anchor):
    choice=choose_region(normalized['regions'],anchor,**normalized['region_coverage'])
    if choice['status']=='selected':
        region=choice['region']
        if region['selection_only'] or region['member_count']>64 or not region['patch_ref']:
            return dict(status='not_localizable',reason='selected_members_not_fully_delivered_within_64',region=region)
    return choice


def quality(case,norm,selection,pixels,image_count):
    """Post-hoc oracle only; cannot return a ref or feed geometry to select()."""
    expected=case['expected'];totals={c:len(expected[c]) for c in CATEGORIES}
    need(norm['scan_complete'] and norm['totals']==totals,'qualification_scan_or_totals')
    legacy=all(norm['member_lists_complete'].values())
    for c in CATEGORIES:
        actual=[canonical(g,c) for g in norm['facts'][c]];wanted=[canonical(g,c) for g in expected[c]]
        need(all(g in wanted for g in actual) and len(actual)==len({repr(g) for g in actual}),'qualification_wrong_public_members')
        legacy&=sorted(actual)==sorted(wanted)
    # Baked world coordinates are stored by factory Blender as binary32.
    import struct
    target=next(o for o in case['objects'] if o['object_id']==case['task']['object_id'])
    points=[[struct.unpack('<f',struct.pack('<f',x))[0] for x in p] for p in target['world_vertices']]
    bounds=[]
    for group in expected['boundary_edges']:
        vertices={v for e in group for v in e}
        bounds.append([[min(points[v][k] for v in vertices) for k in range(3)],[max(points[v][k] for v in vertices) for k in range(3)]])
    need(sorted(r['bounds'] for r in norm['regions'])==sorted(bounds),'qualification_public_positions')
    if bounds:
        need(selection['status']=='selected','qualification_selection_unavailable')
        r=selection['region'];need(canonical(r['members'],'boundary_edges') in [canonical(g,'boundary_edges') for g in expected['boundary_edges']],
            'qualification_selected_members')
        group=next(g for g,b in zip(expected['boundary_edges'],bounds) if b==r['bounds'])
        need(canonical(group,'boundary_edges')==canonical(r['members'],'boundary_edges'),'qualification_selected_position_members')
    else:need(selection['status']=='empty','qualification_false_boundary')
    if case['id'] in ('nonplanar_clear','center_blocked','dense1808'):
        floor=10 if case['id']=='center_blocked' else 12
        need(image_count==2 and pixels and pixels['status']=='scored' and pixels['readable_pairs']>=floor,'qualification_pixel_floor')
    if pixels and pixels['status']=='scored':need(pixels['false_visible']==0,'qualification_false_visibility')
    if case['id']=='feature_blocked':need(image_count<=1 and (pixels is None or pixels['readable_pairs']==0),'qualification_occluded_detail')
    return dict(common_contract_checks_passed=True,old_all_members_passed=bool(legacy),
        useful_local=bool(image_count==2 and pixels and pixels.get('readable_pairs',0)),
        local_gap_preserved=case['id'] in ('opened_torus','local128'),member_lists_complete=norm['member_lists_complete'])


def eligibility(native_rows,he_rows,processes):
    expected_n={(c,r,t) for c in ASSETS for r in range(3) for t in range(3)}
    expected_h={(c,0,0) for c in ASSETS}
    def keys(rows):return [(r['case'],r['round'],r['task']) for r in rows]
    nk=keys(native_rows);hk=keys(he_rows)
    matrix=(len(nk)==len(expected_n) and set(nk)==expected_n and len(hk)==len(expected_h) and set(hk)==expected_h)
    quality_ok=matrix and all(r.get('quality',{}).get('common_contract_checks_passed') is True and r.get('lifecycle_passed') is True for r in native_rows+he_rows)
    timings_ok=matrix and all(type(r.get('complete_task_ms')) in (int,float) and math.isfinite(r['complete_task_ms'])
        and 0<=r['complete_task_ms']<=(3390 if r['task']==0 else 2000) for r in native_rows)
    pkeys=[(p.get('arm'),p.get('case'),p.get('round')) for p in processes]
    pexpected={('native',c,r) for c in ASSETS for r in range(3)}|{('he',c,0) for c in ASSETS}
    processes_ok=(len(pkeys)==len(pexpected) and set(pkeys)==pexpected and all(type(p.get('host_exit')) is int and type(p.get('mcp_exit')) is int
        and p['host_exit']==0 and p['mcp_exit']==0
        and p.get('source_unchanged') is True and p.get('display_restored') is True for p in processes))
    ready=matrix and quality_ok and timings_ok and processes_ok
    return dict(matrix_complete=matrix,common_contract_checks_passed=quality_ok,native_cost_reference_passed=timings_ok,
        process_and_state_passed=processes_ok,A2_may_be_registered=ready,A2_started=False,
        strict_full_guarantee_speed_claim_permitted=False,old_global_members_gate_passed=False,
        old_release_cost_gate_passed=False,model_trials_permitted=False,
        reason='limited_observer_comparison_ready_with_explicit_assurance_differences' if ready else 'qualification_incomplete_or_failed')
