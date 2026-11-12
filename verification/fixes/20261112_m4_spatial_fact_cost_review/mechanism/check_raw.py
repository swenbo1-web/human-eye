"""Root saved-data audit of consumption; no product/consumer code execution."""
from pathlib import Path
import hashlib
import json

B = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_spatial_fact_consumption_001')
O = Path(__file__).resolve().parent
Q = Path('D:/hefe/verification/fixes/20261112_m4_spatial_fact_consumption_review')
inputs = {}
def raw(p):
    b = p.read_bytes()
    inputs[str(p)] = {'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()}
    return b
def read(p): return json.loads(raw(p).decode('utf-8-sig'))
def lines(p): return [json.loads(s) for s in raw(p).decode('utf-8-sig').splitlines() if s]
def find_key(v, key):
    if isinstance(v, dict):
        for k, x in v.items():
            if k == key: yield x
            else: yield from find_key(x, key)
    elif isinstance(v, list):
        for x in v: yield from find_key(x, key)

assert hashlib.sha256(raw(Q/'QUALITY_SEAL.json')).hexdigest() == 'fa467d121359d8ffff45693887de2598f1d34a811bf031849215042ef0e44852'
scores = {s['anonymous_id']: s for s in read(Q/'root_quality/SCORES.json')['scores']}
mapping = read(B/'runtime/handoff_01/private/control/private/ANON_MAP.json')['rows']
assert len(mapping) == 6 and len({m['cell'] for m in mapping}) == 6
cells = []
all_closed = []
for m in mapping:
    c = B/'cells'/m['cell']; owner = c/'owner'
    anon = B/'runtime/handoff_01/public'/m['anonymous_id']
    assert raw(c/'PUBLIC_FINAL.txt') == raw(anon/'answer.txt')
    assert scores[m['anonymous_id']]['status'] == 'complete_correct'
    public = read(anon/'tool_evidence.json')['owner_attempts']
    worker = lines(owner/'native/WORKER_EVENTS.jsonl')
    audit = lines(owner/'audit.jsonl') if (owner/'audit.jsonl').exists() else []
    steps = []; assigned = set()
    folders = sorted(owner.glob('tool_*'))
    assert len(folders) == len(public)
    for folder, pe in zip(folders, public):
        req, res, a = (read(folder/f) for f in ('REQUEST.json','RESPONSE.json','ATTEMPT.json'))
        # Public packet intentionally omits administrative JSON-RPC ids/_meta.
        assert pe['request'] == {'method':req['method'], 'params':{
            'name':req['params']['name'], 'arguments':req['params']['arguments']}}
        assert res['result'] == next(x['value']['result'] for x in pe['responses'] if x['kind']=='RESPONSE.json')
        assert req['params']['name'] == a['name']
        start, end = a['started_ns'], a['started_ns']+a['elapsed_ns']
        host = [e for e in worker if 'script_sha256' in e and start <= e['started_ns'] <= end]
        assigned.update(e['sequence'] for e in host)
        assert len(host) == (0 if a['is_error'] else 1)
        st = {'order': a['attempt'], 'tool': a['name'], 'start_ns': start, 'end_ns': end,
              'handler_ns': a['elapsed_ns'], 'response_bytes': a['response_bytes'],
              'error': a['is_error'], 'host_executions': len(host), 'request_file': str(folder/'REQUEST.json')}
        if a['name']=='human_eye_scene_observe':
            args = req['params']['arguments']; facts = args['query']['requested_facts']
            assert args['include_image'] is False
            assert args['query']['target']['name']=='Target'
            assert {x['name'] for x in args['query']['candidates']} == {'Peer_000','Competing_001','Near_003'}
            assert {'spatial_relation','surface_proximity'} <= set(facts)
            body = json.loads(res['result']['content'][0]['text'])
            st['requested_facts'] = facts
            if not a['is_error']:
                assert body['schema_version']=='task-query-set-v2'
                assert len(body['pairs'])==3
                assert body['summary']['nearest_separated_complete'] is True
                observed = [e for e in audit if e.get('event')=='observe' and e.get('trace_id')==body['trace_id']]
                assert len(observed)==1
                closed = list(find_key(observed[0]['task_work'],'closed_solid_work'))
                assert len(closed)==3
                all_closed.extend(closed)
                st['closed_work_units'] = sum(x['work_units'] for x in closed)
                st['closed_value_bytes'] = 0
                for p in body['pairs']:
                    f = p['facts']
                    assert f['spatial_relation']['status']=='measured' and f['spatial_relation']['value']=='separated'
                    assert f['surface_proximity']['status']=='measured'
                    assert f['closed_solid_relation']['status']=='unknown' and f['closed_solid_relation']['reason']=='closed_solid_work_budget'
                    st['closed_value_bytes'] += len(json.dumps(f['closed_solid_relation'],ensure_ascii=False,separators=(',',':')).encode())
            else:
                assert body['executed'] is False
                assert 'nearest_witness' in facts
        else:
            assert a['name']=='execute_blender_code'
            st['code_utf8_bytes']=len(req['params']['arguments']['code'].encode())
        steps.append(st)
    qa=[e for e in worker if 'script_sha256' in e and e['sequence'] not in assigned]
    assert len(qa)==2 and qa[0]['script_sha256']==qa[1]['script_sha256']
    for prior, after in zip(steps, steps[1:]): assert prior['end_ns'] <= after['start_ns']
    native=sum(s['tool']=='execute_blender_code' for s in steps)
    success=sum(s['tool']=='human_eye_scene_observe' and not s['error'] for s in steps)
    if m['group']=='P': assert native==0 and success==1
    else: assert success==0
    cells.append({**m, 'quality':'complete_correct', 'steps':steps, 'qa_executions':len(qa),
                  'native_calls':native, 'successful_spatial_queries':success,
                  'natural_adoption':m['group']=='P' and success==1 and native==0})

totals={g:{'attempts':sum(len(c['steps']) for c in cells if c['group']==g),
           'handler_ns':sum(s['handler_ns'] for c in cells if c['group']==g for s in c['steps']),
           'response_bytes':sum(s['response_bytes'] for c in cells if c['group']==g for s in c['steps']),
           'errors':sum(s['error'] for c in cells if c['group']==g for s in c['steps'])} for g in ('N','P')}
assert totals['N']['attempts']==8 and totals['P']['attempts']==4 and totals['P']['errors']==1
assert sum(c['natural_adoption'] for c in cells)==3
assert len(all_closed)==9 and sum(x['work_units'] for x in all_closed)==2359296
p1=next(c for c in cells if c['cell']=='spc02')['steps']
result={'schema':'root-raw-consumption-review-v1','evidence_commit':'5cdf62f311f94890ca569d06c1a858f1578225e4',
        'quality_sealed_first':True,'cells':cells,'totals':totals,
        'extra_closed_count':len(all_closed),'extra_closed_work_units':sum(x['work_units'] for x in all_closed),
        'extra_closed_component_bytes':sum(s.get('closed_value_bytes',0) for c in cells for s in c['steps']),
        'invalid_request_to_correction_unattributed_ns':p1[1]['start_ns']-p1[0]['end_ns'],
        'natural_adoption':{'passed':3,'required':2,'denominator':3},
        'causal_savings_from_removing_extra_queries':None,
        'source_files':inputs}
(O/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('cells','source_files')},ensure_ascii=False))
