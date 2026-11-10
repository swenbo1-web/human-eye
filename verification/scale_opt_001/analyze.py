"""Post-run O/C cost ledger; no sampling, tuning, or model calls."""
from pathlib import Path
from collections import Counter
import csv,hashlib,json,math,statistics
HERE=Path(__file__).resolve().parent;DIAG=HERE.parent/'scale_diag_001'
def load(p):return json.loads(Path(p).read_bytes())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')
def stats(v):
    v=[x for x in v if x is not None]
    return None if not v else {'n':len(v),'all':v,'min':min(v),'median':statistics.median(v),'max':max(v)}
def payload(row):
    wire=row.get('result') or {};texts=[x['text'] for x in wire.get('result',{}).get('content',[]) if x.get('type')=='text']
    return json.loads(texts[0]) if len(texts)==1 else {'status':'invalid_wire'}
def facts(p,mode):
    if mode=='G':return {key:p.get(key) for key in ('status','sets','coverage','measurement_contracts')} | {'candidates':[
        {key:value for key,value in x.items() if key not in ('object_id','instance_id')} for x in p.get('candidates',[])]}
    return {key:p.get(key) for key in ('result_kind','status','distance_m','best_known_distance_m','unit','coverage','measurement_notes')} | {
        field:[{'name':o['name']} for o in p.get(field) or []] for field in ('nearest_objects','best_known_objects')}

def main():
    freeze=load(HERE/'FREEZE.json');plan=load(HERE/'measurements/PLAN.json');complete=load(HERE/'measurements/COMPLETE.json');runs=load(HERE/'measurements/RUNS.json')
    assert len(runs)==complete['physical_chains']==18 and complete['logical_recorded']==78 and not complete['stopped_reason']
    for path,want in freeze['files_sha256'].items():assert sha(path)==want,('freeze_changed',path)
    for path,want in freeze['same_fixtures_and_oracle'].items():assert sha(path)==want,('shared_input_changed',path)
    assert plan['chains']==freeze['order'] and plan['freeze_sha256']==sha(HERE/'FREEZE.json')
    oracle={s['id']:s for s in load(DIAG/'ORACLE.json')['snapshots']};logical=[];chains=[];physical=Counter();geometry={}
    for run in runs:
        root=HERE/'measurements'/(run['cell']+'_'+run['group']);chain=load(root/'CHAIN.json');chains.append({'run':run,'chain':chain})
        expect=range(7) if run['mode']=='T' else range(3);files=list(root.glob('MEASUREMENT_*.json'))
        got={load(p)['repeat_or_step']:p for p in files};assert len(got)==len(files) and set(got)==set(expect),'missing_duplicate_extra_row'
        for step in expect:
            raw=load(got[step]);assert raw['group']==run['group'] and raw['source_group']=='P' and raw['canonical']==freeze['versions'][run['group']]
            p=payload(raw);sid='T%d'%step if run['mode']=='T' else run['scene'];truth=oracle[sid];fixture=load(DIAG/'fixtures'/(sid+'.json'));mapping={o['logical_id']:o['name'] for o in fixture['objects']}
            binding=load(root/('STATE_%d.json'%step)) if run['mode']=='T' else load(root/'INITIAL.json')
            assert binding=={k:fixture[k] for k in ('unit_scale_m','objects')},'worldmesh_binding'
            if run['mode']=='G':
                truth=next(t for t in truth['pairs'] if t['candidate']=='peer');names=[mapping['peer']];c=p.get('candidates',[{}])[0]
                distance=(c.get('surface_proximity',{}).get('value') or {}).get('distance_m');valid=c.get('surface_proximity',{}).get('status')=='measured'
                actual_names=[c.get('name')];solid=c.get('closed_solid_relation',{});solid_ok=solid.get('status')=='measured' and solid.get('value')==truth.get('solid_relation') and truth['relation_qualified']
                reasons=[v.get('reason') for v in (c.get('surface_proximity',{}),solid) if v.get('reason')]
            else:
                truth=truth['global_nearest_unsigned'];assert truth['complete'];names=sorted(mapping[v] for v in truth['nearest_ids']);solid_ok=None
                valid=p.get('status')=='complete';distance=p.get('distance_m');actual_names=sorted(x['name'] for x in p.get('nearest_objects') or []);reasons=p.get('reason_codes',[])
            distance_ok=bool(valid and type(distance) in (int,float) and math.isfinite(distance) and
                max(abs(distance-truth['distance_lower_m']),abs(distance-truth['distance_upper_m']))<=freeze['accuracy_m'] and sorted(actual_names)==names)
            good=distance_ok and (solid_ok if run['mode']=='G' else True)
            outcome='error' if raw.get('exception') else 'complete_correct' if good else 'expired' if p.get('status')=='expired' else p.get('status','invalid')
            meter=raw['meter'];assert not meter['issues']
            work=Counter()
            for k in meter['details'].get('kernels',[]):
                if k['kind']=='surface_proximity':
                    for field,v in (k.get('work') or {}).items():
                        if type(v) is int:work[field]+=v
            q={'cell':run['cell'],'group':run['group'],'mode':run['mode'],'step':step,'snapshot':sid,'key':run['cell']+'_'+run['group']+'_'+str(step),
                'outcome':outcome,'complete_correct':good,'distance_correct':distance_ok,'solid_correct':solid_ok,'distance_m':distance,'names':actual_names,'reasons':reasons,
                'cold':step==0,'entry_ms':raw['entry_ns']/1e6,'setup_ms':raw['setup_ns_charged_to_cold']/1e6,
                'response_bytes':raw['response_bytes'],'ipc_counts':meter['counts'],'stages':meter['stages'],'kernel_work':dict(work),'capture_work':meter['details'].get('captures'),
                'cache_baseline':meter['baseline'],'cache_current':meter['current'],'rss_before':raw['rss_before'],'rss_after':raw['rss_after'],
                'raw_path':str(got[step].relative_to(HERE))}
            geometry[(run['cell'],run['group'],step)]=facts(p,run['mode']);logical.append(q);physical.update(meter['rpc_by_command'])
        events=[json.loads(x) for x in (root/'native/WORKER_EVENTS.jsonl').read_text().splitlines()]
        physical.update(worker_request_events=len(events),initial_readbacks=1,T_readbacks=len(list(root.glob('STATE_*_RECEIPT.json'))),
            coordinator_mutations=len(list(root.glob('MUTATION_*.json'))),close_attempts=1)
    assert len(logical)==78 and len({q['key'] for q in logical})==78
    comparisons=[]
    for cell in dict.fromkeys(q['cell'] for q in logical):
        for step in sorted({q['step'] for q in logical if q['cell']==cell}):
            a=next(q for q in logical if q['cell']==cell and q['group']=='O' and q['step']==step);b=next(q for q in logical if q['cell']==cell and q['group']=='C' and q['step']==step)
            comparable=a['outcome']==b['outcome'] and a['outcome'] in ('complete_correct','unknown')
            equal=geometry[(cell,'O',step)]==geometry[(cell,'C',step)] if comparable else None
            work_equal=a['kernel_work']==b['kernel_work'] if comparable else None
            if comparable:assert equal and work_equal,('geometric_or_work_drift',cell,step,equal,work_equal)
            assert not a['complete_correct'] or b['complete_correct'],('lost_success',cell,step)
            comparisons.append({'cell':cell,'step':step,'O':a['outcome'],'C':b['outcome'],'facts_equal':equal,'surface_work_equal':work_equal})
    quality={group:{'denominator':39,'complete_correct':sum(x['complete_correct'] for x in logical if x['group']==group),
          'outcomes':dict(Counter(x['outcome'] for x in logical if x['group']==group))} for group in ('O','C')}
    static=[]
    for cell in ('G_low','G_mid','G_high','D_low','D_mid','D_high'):
        for group in ('O','C'):
            rows=[q for q in logical if q['cell']==cell and q['group']==group]
            static.append({'cell':cell,'group':group,'correct':sum(q['complete_correct'] for q in rows),'cold_entry_ms':rows[0]['entry_ms'],
                 'setup_ms':rows[0]['setup_ms'],'warm_ms':stats([q['entry_ms'] for q in rows[1:]]),'outcomes':[q['outcome'] for q in rows]})
    T=[]
    for step in range(7):
        row={'step':step}
        for group in ('O','C'):
            selected=[q for q in logical if q['mode']=='T' and q['group']==group and q['step']==step]
            row[group]={'entry_ms':stats([q['entry_ms'] for q in selected]),'correct':sum(q['complete_correct'] for q in selected),
                'kernel_calls':[q['stages'].get('kernel.surface_proximity',{}).get('calls',0) for q in selected]}
        T.append(row)
    cost={group:stats([c['chain']['whole_chain_ns']/1e6 for c in chains if c['run']['mode']=='T' and c['run']['group']==group]) for group in ('O','C')}
    allcost={group:stats([c['chain']['driver_whole_chain_ns']/1e6 for c in chains if c['run']['mode']=='T' and c['run']['group']==group]) for group in ('O','C')}
    processcost={group:stats([c['run']['full_process_ns']/1e6 for c in chains if c['run']['mode']=='T' and c['run']['group']==group]) for group in ('O','C')}
    d={group:next(r['cold_entry_ms'] for r in static if r['cell']=='D_mid' and r['group']==group) for group in ('O','C')}
    targets={'D48_cold':{'O_ms':d['O'],'C_ms':d['C'],'reduction':1-d['C']/d['O'],'met':d['C']/d['O']<=.75},
        'T_chain_median':{'O_ms':cost['O']['median'],'C_ms':cost['C']['median'],'reduction':1-cost['C']['median']/cost['O']['median'],'met':cost['C']['median']/cost['O']['median']<=.75}}
    summary={'task':'SCALE-OPT-001','denominator':78,'quality':quality,'static':static,'T_steps':T,'T_chain_ms':cost,
       'T_driver_whole_ms':allcost,'T_full_process_ms':processcost,'targets':targets,'both_engineering_targets_met':all(v['met'] for v in targets.values()),
       'facts_and_work_comparisons':comparisons,'physical_counters':dict(physical),'no_lost_successes':True,
       'production_diff':'surface_proximity._bounded +4 lines only; no new traversal, cache, budget, method version or default configuration',
       'actual_leaf_definition':'product intersection_tests counts leaf evaluations; triangle_pairs includes traversal/pruning, not directly comparable to Native leaf count',
       'known_baseline_test_failures':load(HERE/'REGRESSIONS_BASELINE.json')['failure_ids'],'tokens':'N/A','fees':'N/A','coordinator_model_cost':'unmeasured',
       'admin_acceptance_pending':True,'no_p95_or_whole_complex_product_claim':True}
    dump(HERE/'LEDGER.json',{'logical':logical,'chains':chains,'physical_counters':dict(physical),'denominator':78});dump(HERE/'SUMMARY.json',summary)
    with (HERE/'LEDGER.csv').open('w',encoding='utf8',newline='') as f:
        columns=['key','cell','group','mode','step','cold','complete_correct','outcome','entry_ms','setup_ms','response_bytes','distance_m']
        writer=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');writer.writeheader();writer.writerows(logical)
    print(json.dumps({k:summary[k] for k in ('denominator','quality','targets','both_engineering_targets_met','T_chain_ms','physical_counters')},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
