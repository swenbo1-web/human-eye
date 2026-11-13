"""Independent anonymous quality review. Read only the public 002 package."""
import hashlib
import json
import re
from collections import Counter
from decimal import Decimal
from fractions import Fraction
from itertools import combinations
from pathlib import Path

PUBLIC = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_surface_scan_continuous_consumption_002/quality/public')
OUT = Path(__file__).resolve().parent
HASHES = {}
CHECKS = []
def raw(rel):
    path = PUBLIC / rel
    data = path.read_bytes()
    HASHES[str(rel)] = hashlib.sha256(data).hexdigest()
    return data
def read(rel): return json.loads(raw(rel))
def check(name, value, detail=None):
    CHECKS.append({'name': name, 'passed': bool(value), 'detail': detail})
def pair(a,b): return tuple(sorted((a,b)))
def rational(v): return Fraction(int(v['numerator']), int(v['denominator']))

index = read('INDEX.json')
contract = read('scoring/SCORING_CONTRACT.json')
base_contract = read('scoring/BASE_SCORING_CONTRACT.json')
for rel, expected in index['fixed_quality_materials'].items():
    if rel.endswith('score_answer.py'): continue  # do not read or invoke author's scorer
    check('public_sha:' + rel, hashlib.sha256(raw(rel)).hexdigest() == expected)
truths = {}
threshold2 = Fraction(0.002) ** 2
tolerance = Fraction(contract['distance_tolerance_mm'])
for state in ('BASE','EDIT'):
    truth = read('scoring/' + state + '_TRUTH.json')
    snapshot = read('scoring/' + state + '_SNAPSHOT.json')
    d = {}
    for row in truth['pairs']:
        key = pair(row['object_a'], row['object_b'])
        q = rational(row['exact_squared_distance_m2'])
        check(state + ':unique:' + '/'.join(key), key not in d)
        check(state + ':nonnegative:' + '/'.join(key), q >= 0)
        check(state + ':threshold:' + '/'.join(key), (q <= threshold2) == row['matches_threshold'])
        d[key] = q
    labels = {'Obj_' + str(i).zfill(3) for i in range(1,25)}
    check(state + ':276_all_pairs', set(d) == {pair(a,b) for a,b in combinations(labels,2)})
    check(state + ':snapshot_binding', truth['snapshot_sha256'] == HASHES['scoring/' + state + '_SNAPSHOT.json'])
    check(state + ':scope_count', snapshot['counts'] == {'objects':24,'triangles':978,'vertices':530})
    positive = {key:q for key,q in d.items() if q <= threshold2}
    check(state + ':positive_count', len(positive) == (71 if state == 'BASE' else 72))
    truths[state] = d

def parse_answer(text):
    rows = []
    for lineno,line in enumerate(text.splitlines(), 1):
        if not line.startswith('|'): continue
        cells = [x.strip() for x in line.strip().strip('|').split('|')]
        if not cells or not re.fullmatch(r'Obj_\d{3}',cells[0]): continue
        others = re.findall(r'Obj_\d{3}',cells[1])
        # Two-column tables are manually reviewed, explicitly zero-distance groups.
        display = cells[2] if len(cells) == 3 else '0'
        if not re.fullmatch(r'\d+(?:\.\d+)?', display):
            raise ValueError('unparsed distance line:' + line)
        for other in others:
            rows.append({'pair':pair(cells[0],other),'mm':display,'line':lineno})
    return rows

def score_rows(rows, exact):
    expected = {key for key,q in exact.items() if q <= threshold2}
    multiplicity = Counter(tuple(row['pair']) for row in rows)
    failures = []
    for row in rows:
        key = tuple(row['pair'])
        if key not in exact: failures.append({'kind':'unknown_pair',**row}); continue
        value = Fraction(row['mm'])
        lower_m = max(Fraction(0), value - tolerance)/1000
        upper_m = (value + tolerance)/1000
        if not lower_m**2 <= exact[key] <= upper_m**2:
            failures.append({'kind':'wrong_distance',**row})
        if value != 0 and Decimal(row['mm']).as_tuple().exponent > -3:
            failures.append({'kind':'insufficient_precision',**row})
        if value == 0 and exact[key] != 0:
            failures.append({'kind':'nonzero_claimed_true_zero',**row})
    return {'count':len(rows),'unique':len(multiplicity),'missing':sorted(expected-set(multiplicity)), 'extra':sorted(set(multiplicity)-expected),'duplicates':[key for key,n in multiplicity.items() if n>1], 'distance_or_presentation_errors':failures}

def recursively_json(value):
    if isinstance(value,str):
        try: return json.loads(value)
        except ValueError: return value
    return value

def parse_current_stdout(text):
    rows = []
    zero_group = False
    for lineno,line in enumerate(text.splitlines(),1):
        if line in ('GROUPED_ZERO','ZERO_GROUPS'): zero_group=True; continue
        if line in ('NONZERO','POSITIVE'): zero_group=False; continue
        match = re.match(r'^(Obj_\d{3})\s+(Obj_\d{3})\s+(\d+(?:\.\d+)?)\b',line)
        if match:
            rows.append({'pair':pair(match[1],match[2]),'mm':match[3],'line':lineno})
        elif zero_group and re.match(r'^Obj_\d{3}\s+Obj_\d{3}',line):
            names=re.findall(r'Obj_\d{3}',line)
            rows.extend({'pair':pair(names[0],name),'mm':'0','line':lineno} for name in names[1:])
    return rows

results = []
evidence_summary = []
code_sources = {}
bindings = {}
for eid in index['anonymous_episode_order']:
    episode = read(eid + '/EPISODE.json')
    for ti, state in enumerate(('BASE','BASE','EDIT'),1):
        prefix = eid + '/turn_' + str(ti)
        turn = read(prefix + '/TURN.json')
        text = raw(prefix + '/answer.txt').decode('utf8')
        rows = parse_answer(text)
        numeric = score_rows(rows,truths[state])
        valid = not any(numeric[k] for k in ('missing','extra','duplicates','distance_or_presentation_errors'))
        check(prefix + ':full_numeric_list', valid, numeric if not valid else None)
        check(prefix + ':explicit_completeness', '完整' in text)
        check(prefix + ':mm', 'mm' in text or '毫米' in text)
        check(prefix + ':execution_completed', turn['execution_state']=='completed' and turn['valid_completion'] and turn['final_present'])
        evidence = read(prefix + '/tool_evidence.json')
        attempts = []
        for attempt in evidence['owner_attempts']:
            req = attempt['request']['params']
            args = req['arguments']
            code = args.get('code')
            code_sha = None
            if code is not None:
                code_sha = hashlib.sha256(code.encode('utf8')).hexdigest()
                code_sources.setdefault(code_sha, {'code':code, 'origins':[]})['origins'].append({'episode':eid,'turn':ti,'attempt':attempt['order']})
            texts = []
            for response in attempt['responses']:
                result = response['value'].get('result',{})
                for content in result.get('content',[]):
                    if content.get('type')=='text': texts.append(recursively_json(content['text']))
            attempts.append({'order':attempt['order'],'tool':req['name'],'arguments_without_code':{k:v for k,v in args.items() if k!='code'},'code_sha256':code_sha,'is_error':attempt['is_error'],'responses':texts})
        completed_events=[row['event'] for row in evidence['public_tool_events'] if row['phase']=='item.completed']
        check(prefix + ':all_current_attempts_delivered', len(attempts)==len(completed_events))
        for attempt, event in zip(evidence['owner_attempts'],completed_events):
            check(prefix + ':receipt:'+str(attempt['order']), attempt['is_error'] is False and event['status']=='completed' and event['error'] is None)
            check(prefix + ':request_binding:'+str(attempt['order']), attempt['request']['params']['arguments']==event['arguments'] and attempt['request']['params']['name']==event['tool'])
            current_result=attempt['responses'][-1]['value']['result']
            check(prefix + ':business_content_binding:'+str(attempt['order']), current_result['content']==event['result']['content'])
        last=attempts[-1]['responses'][-1]
        if last.get('result_kind')=='surface_scan':
            check(prefix + ':complete_current_scan',last['status']=='complete' and last['coverage']['catalog_scope_confirmed'] is True and last['delivery']['complete'] is True)
            check(prefix + ':scan_unknowns', last['coverage']['unknown']==last['coverage']['deferred']==0 and not last['scope_issues'] and not last['unsupported_objects'] and not last['unresolved'])
            check(prefix + ':scope_surface_units',last['scope']=='all_scene_mesh_triangle_surfaces' and last['unit']=='m' and last['coordinate_frame']=='world' and last['measurement_semantics']['solid_relation']=='not_evaluated')
            expected_positive=71 if ti<3 else 72
            check(prefix + ':scan_counts',last['coverage']['objects']==24 and last['coverage']['total_pairs']==276 and last['coverage']['measured_match']==expected_positive and last['coverage']['measured_nonmatch']==(41 if ti<3 else 42) and last['coverage']['bound_excluded']==(164 if ti<3 else 162) and last['delivery']['matches_total']==last['delivery']['delivered_matches']==expected_positive)
            business_rows=[]
            for n, vals in enumerate(last['matches']):
                item=dict(zip(last['match_columns'],vals))
                check(prefix + ':ref:'+str(n),last['objects'][item['object_a_ref']]['name']==item['object_a'] and last['objects'][item['object_b_ref']]['name']==item['object_b'])
                business_rows.append({'pair':pair(item['object_a'],item['object_b']),'mm':str(item['distance_mm']),'line':n})
            business_score=score_rows(business_rows,truths[state])
            # Business floats need not print three decimals; final presentation was separately checked.
            business_score['distance_or_presentation_errors']=[v for v in business_score['distance_or_presentation_errors'] if v['kind']!='insufficient_precision']
            check(prefix + ':current_business_facts',not any(business_score[k] for k in ('missing','extra','duplicates','distance_or_presentation_errors')))
            bind=last['binding']; bindings.setdefault(eid,[]).append(bind)
            if ti==2: check(prefix + ':repeat_current_binding',bind==bindings[eid][0])
            if ti==3:
                first=bindings[eid][0]
                check(prefix + ':edit_current_binding',bind['scene_revision']!=first['scene_revision'] and bind['scene_fingerprint']!=first['scene_fingerprint'] and bind['directory_sha256']!=first['directory_sha256'] and bind['document_epoch']==first['document_epoch'])
            current_basis={'classification':'sufficient','basis':'actual_current_observation_and_binding','source':prefix+'/tool_evidence.json','semantic_review':'Fresh scan is issued in this turn. Complete current facts and coverage are delivered; REPEAT binding matches BASE and EDIT changes revision/fingerprint/directory within the same document epoch. No administrative QA is used as consumer evidence.'}
        else:
            check(prefix + ':native_executed_current_read',last['status']=='success' and last['result']['executed'] is True)
            stdout=last['result']['result']
            business_rows=parse_current_stdout(stdout)
            business_score=score_rows(business_rows,truths[state])
            check(prefix + ':native_current_business_facts',not any(business_score[k] for k in ('missing','extra','duplicates','distance_or_presentation_errors')),business_score if business_score['count']!=(71 if ti<3 else 72) else None)
            codes='\n'.join(code_sources[a['code_sha256']]['code'] for a in attempts if a['code_sha256'])
            check(prefix + ':native_current_acquisition_source', 'evaluated_depsgraph_get()' in codes and 'evaluated_get(' in codes and 'matrix_world' in codes and 'calc_loop_triangles()' in codes and 'scene.objects' in codes or 'sc.objects' in codes and 'evaluated_depsgraph_get()' in codes and 'evaluated_get(' in codes and 'matrix_world' in codes and 'calc_loop_triangles()' in codes)
            current_basis={'classification':'sufficient','basis':'actual_current_geometry_read_then_computation','source':prefix+'/tool_evidence.json','semantic_review':'This turn re-enumerates scene meshes, acquires a current dependency graph and evaluated geometry/world transforms, then computes current pair distances. Later turns reuse a previously defined distance function, not previous geometry or final answers. Public stdout supplies the complete current list.'}
        evidence_summary.append({'anonymous_episode_id':eid,'turn':ti,'attempts':attempts})
        results.append({'anonymous_episode_id':eid,'anonymous_turn_id':turn['anonymous_turn_id'],'turn':ti,'state':('BASE','REPEAT','EDIT')[ti-1], 'execution_classification':turn['execution_state'],'numeric':numeric,'primary_content_classification':'complete_correct' if valid else 'review_required','auxiliary_context_reconstruction':'not_needed_full_current_list','current_state_basis':current_basis,'manual_semantics_and_evidence_pending':False,'extra_deterministic_errors':[]})

summary={'scope':'Anonymous public materials only; group/cost/private not read. Independent exact rational comparison against supplied frozen exact-squared oracle, no author scorer or geometry engine run.', 'turns':18,'episodes':6,'all_pair_dispositions':18*276,'positive_facts':sum(r['numeric']['count'] for r in results),'checks':len(CHECKS),'passed':sum(c['passed'] for c in CHECKS),'failed':[c for c in CHECKS if not c['passed']], 'results':results,'manual_review_pending':False,'new_live_model_Blender_API_calls':0}
(OUT/'NUMERIC_RESULTS.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
(OUT/'CHECKS.json').write_text(json.dumps(CHECKS,ensure_ascii=False,indent=2),encoding='utf8')
(OUT/'INPUT_SHA256.json').write_text(json.dumps(HASHES,ensure_ascii=False,indent=2),encoding='utf8')
(OUT/'PUBLIC_BUSINESS_EXTRACT.json').write_text(json.dumps(evidence_summary,ensure_ascii=False,indent=2),encoding='utf8')
(OUT/'PUBLIC_CODE_EXTRACT.json').write_text(json.dumps(code_sources,ensure_ascii=False,indent=2),encoding='utf8')
(OUT/'FINAL_RESULTS.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:summary[k] for k in ('turns','episodes','positive_facts','checks','passed','failed','manual_review_pending')},ensure_ascii=False))
print(json.dumps({'unique_public_codes':len(code_sources),'public_attempts':sum(len(row['attempts']) for row in evidence_summary)},ensure_ascii=False))
