"""Post-run ledger; frozen oracle intervals determine quality, never elapsed time."""
from pathlib import Path
from collections import Counter,defaultdict
import csv,hashlib,json,math,statistics,sys

HERE=Path(__file__).resolve().parent
def load(p):return json.loads(Path(p).read_bytes())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,v):Path(p).write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8',newline='\n')
def ms(v):return None if v is None else v/1e6
def summarize(values):
    v=[x for x in values if x is not None]
    return None if not v else {'n':len(v),'all':v,'min':min(v),'median':statistics.median(v),'max':max(v)}
def payload(row):
    raw=row.get('result') or {}
    if row['group']=='N':return raw
    texts=[c['text'] for c in raw.get('result',{}).get('content',[]) if c.get('type')=='text']
    if len(texts)!=1:return {'status':'invalid_wire','raw':raw}
    return json.loads(texts[0])
def stage(row,key):return row.get('meter',{}).get('stages',{}).get(key,{}).get('duration_ns')

def main():
    freeze=load(HERE/'FREEZE.json');assert load(HERE/'measurements/COMPLETE.json')['logical_expected']==78
    hashes={name:sha(HERE/name)==value for name,value in freeze['files'].items()};assert all(hashes.values()),'frozen_file_changed'
    oracle={x['id']:x for x in load(HERE/'ORACLE.json')['snapshots']};runs=load(HERE/'measurements/RUNS.json')
    assert len(runs)==18 and len({(r['cell'],r['group']) for r in runs})==18
    logical=[];chains=[];sourcechecks=[];physical=Counter();hostpids=[];actorpids=[]
    for run in runs:
        folder=HERE/'measurements'/(run['cell']+'_'+run['group']);chain=load(folder/'CHAIN.json');chains.append(dict(run,**{'chain':chain}))
        actorpids.append(run['actor_pid']);hostpids.append(chain['pid'])
        initial=load(folder/'INITIAL.json');expected=load(HERE/'fixtures'/(run['scene']+'.json'))
        initial_ok=initial=={k:expected[k] for k in ('unit_scale_m','objects')};assert initial_ok,'initial_binding'
        sourcechecks.append({'chain':folder.name,'initial_mesh_exact':initial_ok,'file_unchanged':chain['file_unchanged']})
        files=sorted(folder.glob('MEASUREMENT_*.json'));expected_steps=range(7) if run['mode']=='T' else range(3)
        got={load(p)['repeat_or_step']:p for p in files};assert len(got)==len(files) and set(got)<=set(expected_steps),'duplicate_or_extra_measurement'
        for step in expected_steps:
            sid='T%d'%step if run['mode']=='T' else run['scene'];o=oracle[sid]
            raw_fixture=load(HERE/'fixtures'/(sid+'.json'));mapping={v['logical_id']:v['name'] for v in raw_fixture['objects']}
            if run['mode']=='G':
                truth=next(p for p in o['pairs'] if p['candidate']=='peer');truth_names=[mapping['peer']]
            else:
                truth=o['global_nearest_unsigned'];assert truth['complete'];truth_names=sorted(mapping[k] for k in truth['nearest_ids'])
            key=run['cell']+'_'+run['group']+'_'+str(step)
            q={'key':key,'cell':run['cell'],'group':run['group'],'mode':run['mode'],'step':step,'snapshot':sid,
               'cold':step==0,'expected_names':truth_names,'oracle_lower_m':truth['distance_lower_m'],'oracle_upper_m':truth['distance_upper_m'],
               'source_binding':initial_ok,'observed':step in got,'distance_correct':False,'solid_correct':None,'complete_correct':False}
            if step not in got:
                assert run['cell']=='G_high' and run['group']=='N' and step in (1,2),'unexpected_missing_measurement'
                q.update(outcome='not_attempted_session_poisoned',entry_ms=None,cold_setup_ms=None)
                logical.append(q);continue
            row=load(got[step]);assert row['group']==run['group'] and row['scene']==run['scene'] and row['mode']==run['mode']
            if run['mode']=='T':
                actual=load(folder/('STATE_%d.json'%step));q['source_binding']=actual=={k:raw_fixture[k] for k in ('unit_scale_m','objects')};assert q['source_binding'],'T_state_binding'
            p=payload(row);q.update(status=p.get('status'),entry_ms=ms(row['entry_ns']),cold_setup_ms=ms(row['setup_ns_charged_to_cold']),response_bytes=row['response_bytes'],
                   raw_path=str(got[step].relative_to(HERE)),rss_before=row.get('rss_before'),rss_after=row.get('rss_after'))
            if run['group']=='N':
                distance=p.get('distance_m');names=p.get('nearest_names');solid=p.get('solid') or {};solid_value=solid.get('relation')
                valid=p.get('status')=='complete';reason=(row.get('exception') or {}).get('type');work=p.get('work')
                q.update(native_work=work,native_stages=p.get('stages'),cache_array_bytes=p.get('cache_array_bytes'),ipc=row['meter'])
            else:
                if run['mode']=='G':
                    candidates=p.get('candidates',[]);candidate=candidates[0] if len(candidates)==1 else {}
                    d=candidate.get('surface_proximity',{});distance=(d.get('value') or {}).get('distance_m');valid=d.get('status')=='measured';names=[candidate.get('name')]
                    solid=candidate.get('closed_solid_relation',{});solid_value=solid.get('value');reason=';'.join(v for v in (d.get('reason'),solid.get('reason')) if v)
                else:
                    distance=p.get('distance_m');valid=p.get('status')=='complete';names=sorted(v.get('name') for v in p.get('nearest_objects') or []);solid={};solid_value=None
                    reason=p.get('code') or p.get('error');q['coverage']=p.get('coverage')
                meter=row['meter'];assert not meter.get('issues'),('meter_issue',key,meter.get('issues'))
                kernel_work=Counter()
                for kernel in meter.get('details',{}).get('kernels',[]):
                    if kernel['kind']=='surface_proximity':
                        for k,v in (kernel.get('work') or {}).items():
                            if type(v) is int:kernel_work[k]+=v
                q.update(product_stages=meter['stages'],product_counts=meter['counts'],kernel_work=dict(kernel_work),
                  kernel_work_scope='completed kernel calls only; interrupted current kernel unmeasured' if p.get('status')=='expired' else 'all returned kernel calls',
                  kernel_results=meter.get('details',{}).get('kernels',[]),capture_work=meter.get('details',{}).get('captures'),
                  admission=meter.get('details',{}).get('admission'),cache_baseline=meter.get('baseline'),cache_current=meter.get('current'),
                  ipc={'socket_send_bytes':meter['counts'].get('socket_send_bytes',0),'socket_recv_bytes':meter['counts'].get('socket_recv_bytes',0)},
                  rpc_by_command=meter.get('rpc_by_command'))
                physical.update(meter.get('rpc_by_command',{}))
            q.update(distance_m=distance,nearest_names=names,solid_value=solid_value,reason=reason)
            q['distance_correct']=bool(valid and type(distance) in (int,float) and math.isfinite(distance)
                 and max(abs(distance-truth['distance_lower_m']),abs(distance-truth['distance_upper_m']))<=freeze['accuracy_m']
                 and sorted(names or [])==truth_names)
            if run['group']=='P' and valid:
                binding=p.get('context',{}) if run['mode']=='G' else p.get('binding',{})
                assert binding.get('runtime_source_sha256')==freeze['source_canonical'],'result_runtime_binding'
                if run['mode']!='G':
                    coverage=p['coverage'];assert coverage['targets_excluding_focal']==len(raw_fixture['objects'])-1
                    assert coverage['distance_valid']+coverage['strictly_excluded']==coverage['targets_excluding_focal'] and coverage['unresolved']==0,'global_coverage'
            if run['mode']=='G':q['solid_correct']=bool(truth['relation_qualified'] and solid.get('status')=='measured' and solid_value==truth['solid_relation'])
            q['complete_correct']=q['distance_correct'] and (q['solid_correct'] if run['mode']=='G' else True) and q['source_binding']
            if row.get('exception'):q['outcome']='timeout' if 'Timeout' in row['exception']['type'] else 'error'
            elif p.get('status')=='expired':q['outcome']='expired'
            elif q['complete_correct']:q['outcome']='complete_correct'
            elif p.get('status') in ('unknown','partial'):q['outcome']=p['status']
            else:q['outcome']='wrong_or_incomplete'
            logical.append(q)
        events=folder/'native/WORKER_EVENTS.jsonl'
        events=[json.loads(x) for x in events.read_text().splitlines()] if events.exists() else []
        physical.update({'worker_request_events':len([x for x in events if 'sequence' in x]),
                         'coordinator_mutations':len(list(folder.glob('MUTATION_*.json'))),
                         'initial_readbacks':1,'T_readbacks':len(list(folder.glob('STATE_*_RECEIPT.json'))),
                         'native_logical_sent':len(files) if run['group']=='N' else 0,'close_attempts':1})
    assert len(logical)==78 and len({q['key'] for q in logical})==78
    dump(HERE/'LEDGER.json',{'schema':'scale-diag-001-ledger-v1','logical_denominator':78,'observed_rows':sum(q['observed'] for q in logical),
         'frozen_hashes_verified':hashes,'logical':logical,'chains':chains,'sourcechecks':sourcechecks,'physical_counters':dict(physical),
         'pids':{'actors':actorpids,'hosts':hostpids},'tokens':'N/A','fees':'N/A','oracle_midpoint_halfwidth_ignored':True})
    with (HERE/'LEDGER.csv').open('w',encoding='utf8',newline='') as f:
        cols=['key','cell','group','mode','step','cold','observed','outcome','complete_correct','distance_correct','solid_correct','entry_ms','cold_setup_ms','distance_m','solid_value','response_bytes','reason']
        writer=csv.DictWriter(f,fieldnames=cols,extrasaction='ignore');writer.writeheader();writer.writerows(logical)
    stats={}
    for group in ('N','P'):
        rows=[q for q in logical if q['group']==group]
        stats[group]={'denominator':39,'complete_correct':sum(q['complete_correct'] for q in rows),'distance_correct':sum(q['distance_correct'] for q in rows),'outcomes':dict(Counter(q['outcome'] for q in rows))}
    table=[]
    for cell in ('G_low','G_mid','G_high','D_low','D_mid','D_high'):
        for group in ('N','P'):
            rows=[q for q in logical if q['cell']==cell and q['group']==group]
            table.append({'cell':cell,'group':group,'correct':'%d/3'%sum(q['complete_correct'] for q in rows),
                          'cold_entry_ms':rows[0]['entry_ms'],'cold_setup_ms':rows[0]['cold_setup_ms'],'warm_ms':summarize([q['entry_ms'] for q in rows[1:]]),
                          'outcomes':[q['outcome'] for q in rows]})
    T=[]
    for group in ('N','P'):
        for step in range(7):
            rows=[q for q in logical if q['mode']=='T' and q['group']==group and q['step']==step]
            T.append({'group':group,'step':step,'correct':sum(q['complete_correct'] for q in rows),'entry_ms':summarize([q['entry_ms'] for q in rows]),
                      'kernel_calls':[q.get('product_stages',{}).get('kernel.surface_proximity',{}).get('calls',0) if group=='P' else (q.get('native_work') or {}).get('pair_calls') for q in rows],
                      'response_bytes':[q['response_bytes'] for q in rows]})
    fractions=[]
    for q in logical:
        if q['group']=='P' and q['observed'] and q['outcome']=='complete_correct' and (q['mode']=='D' or q['mode']=='T'):
            kernel=q['product_stages'].get('geometry.nearest_pair_loop',{}).get('duration_ns',0)
            if kernel:fractions.append({'key':q['key'],'nearest_loop_fraction':kernel/(q['entry_ms']*1e6),'nearest_loop_ms':ms(kernel)})
    summary={'quality':stats,'static':table,'T_steps':T,'T_full_chain_ms':{group:summarize([ms(c['chain']['whole_chain_ns']) for c in chains if c['mode']=='T' and c['group']==group]) for group in ('N','P')},
             'nearest_loop_fraction_completed_noncache':fractions,'planned':78,'observed':sum(q['observed'] for q in logical),
             'main_bottleneck':'M3 per-pair exact distance traversal and preflight full-combination cap; not host connection or directory capture',
             'one_next_candidate':'SCALE-OPT-001: conservative best-first triangle hierarchy for distance, exact leaf predicates retained, actual visited-work budget; retain independent face/bytes/deadline limits and solid unknowns until separately qualified',
             'production_sources_changed':False,'no_performance_acceptance_claim':True}
    dump(HERE/'SUMMARY.json',summary)
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
