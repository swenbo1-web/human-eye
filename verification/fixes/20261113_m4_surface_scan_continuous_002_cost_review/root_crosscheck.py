"""Root recomputation from original FINAL_TIMING and CLI terminal usage."""
from pathlib import Path
from fractions import Fraction
from statistics import median
import hashlib
import json

ROOT=Path(__file__).parent
SOURCE=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification')
BATCH=SOURCE/'m4_surface_scan_continuous_consumption_002'
COST=SOURCE/'m4_surface_scan_continuous_consumption_002_cost'
inputs={}
def read(p):
    body=p.read_bytes();inputs[str(p)]=hashlib.sha256(body).hexdigest()
    return json.loads(body)
def rational(x):
    return {'numerator':x.numerator,'denominator':x.denominator,'value':float(x)}

ledger=read(COST/'LEDGER.json')
assert inputs[str(COST/'LEDGER.json')]=='7ddc121ab742baae53837784dc13f49e5af93f67cbb2949e524722b15d2b9838'
run=read(BATCH/'RUN_RESULT.json')
sealpath=Path('D:/hefe/verification/fixes/20261113_m4_surface_scan_continuous_002_quality_review/QUALITY_SEAL.json')
seal=read(sealpath)
assert inputs[str(sealpath)]==ledger['quality_seal_sha256']=='ccea554353a6f0607263124d2170ef3b2094a07e222c86276f522184b7f5316c'
assert seal['quality']['primary_complete_correct']==seal['quality']['current_state_basis_sufficient']==18
episodes=[]
for rec in run['records']:
    timing=read(Path(rec['folder'])/'FINAL_TIMING.json')
    duration=timing['business_receipts_closed_ns']-timing['started_ns']
    assert duration==timing['full_episode_wall_ns']
    turns=[]
    for turn in rec['coordinator']['turns']:
        folder=Path(turn['folder']);t=read(folder/'FINAL_TIMING.json')
        body=(folder/'events.jsonl').read_bytes();inputs[str(folder/'events.jsonl')]=hashlib.sha256(body).hexdigest()
        events=[json.loads(line)['event'] for line in body.splitlines()]
        terminals=[e for e in events if e.get('type')=='turn.completed']
        assert len(terminals)==1
        u=terminals[0]['usage']
        assert all(type(u[k]) is int and u[k]>=0 for k in ('input_tokens','cached_input_tokens','output_tokens'))
        assert u['cached_input_tokens']<=u['input_tokens']
        elapsed=t['consumer_record_closed_ns']-t['started_ns']
        assert elapsed==t['full_turn_wall_ns']
        turns.append({'label':turn['turn_label'],'time_ns':elapsed,'input':u['input_tokens'],
                      'cached_input':u['cached_input_tokens'],'output':u['output_tokens'],
                      'reported_total':u['input_tokens']+u['output_tokens'],
                      'noncached_input_plus_output':u['input_tokens']-u['cached_input_tokens']+u['output_tokens']})
    assert [t['label'] for t in turns]==['BASE','REPEAT','EDIT']
    episodes.append({'cell':rec['cell'],'group':rec['group'],'pair':rec['pair'],'full_time_ns':duration,'turns':turns})
assert len(episodes)==6 and {e['cell'] for e in episodes}=={'N1','N2','N3','C1','C2','C3'}
views={}
for name,idx in [('FULL',(0,1,2)),('BASE',(0,)),('REPEAT_EDIT',(1,2))]:
    rows=[]
    for pair in (1,2,3):
        row={'pair':pair}
        for group in ('N','C'):
            e=next(e for e in episodes if e['group']==group and e['pair']==pair)
            row[group+'_time_ns']=e['full_time_ns'] if name=='FULL' else sum(e['turns'][i]['time_ns'] for i in idx)
            row[group+'_input_plus_output']=sum(e['turns'][i]['reported_total'] for i in idx)
            row[group+'_noncached_input_plus_output']=sum(e['turns'][i]['noncached_input_plus_output'] for i in idx)
        row['time_ratio']=Fraction(row['C_time_ns'],row['N_time_ns'])
        row['token_ratio']=Fraction(row['C_input_plus_output'],row['N_input_plus_output'])
        old=next(x for x in ledger['views'][name]['pairs'] if x['pair']==pair)
        assert all(old[k]==row[k] for k in ('N_time_ns','C_time_ns','N_input_plus_output','C_input_plus_output'))
        assert row['time_ratio']==Fraction(old['time_C_over_N']['numerator'],old['time_C_over_N']['denominator'])
        rows.append(row)
    med=median(x['time_ratio'] for x in rows)
    original=ledger['views'][name]['median_pair_time_C_over_N']
    assert med==Fraction(original['numerator'],original['denominator'])
    totals={g+'_'+k:sum(x[g+'_'+k] for x in rows) for g in ('N','C') for k in ('time_ns','input_plus_output','noncached_input_plus_output')}
    token_ratio=Fraction(totals['C_input_plus_output'],totals['N_input_plus_output'])
    noncache_ratio=Fraction(totals['C_noncached_input_plus_output'],totals['N_noncached_input_plus_output'])
    views[name]={'pairs':[{k:rational(v) if isinstance(v,Fraction) else v for k,v in row.items()} for row in rows],
                 'totals':totals,'median_pair_time_ratio':rational(med),'reported_token_total_ratio':rational(token_ratio),
                 'noncached_input_plus_output_ratio':rational(noncache_ratio)}
gates={'quality':True,'time':views['FULL']['median_pair_time_ratio']['value']<=.70,
       'token':views['FULL']['totals']['C_input_plus_output']<=views['FULL']['totals']['N_input_plus_output']}
assert all(gates.values()) and all(ledger['gates'][k]==v for k,v in gates.items())
result={'source_delivery':'a798caf982e2d7eefe0bf52b739b9bef88526be4','cost_delivery':'21f08a9826adf5ef44a305e3d6d1898f0dac5e80',
        'episodes':episodes,'views':views,'gates':gates,'source_sha256':inputs,
        'scope':'Original timing arithmetic and one actual CLI terminal usage per invocation. Scope already independently proved; no new session lookup or live run. Noncached diagnostic is not a price calculation or replacement gate.'}
(ROOT/'ROOT_CROSSCHECK.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps({'gates':gates,'views':{n:{k:v for k,v in view.items() if k!='pairs'} for n,view in views.items()}},ensure_ascii=False))
