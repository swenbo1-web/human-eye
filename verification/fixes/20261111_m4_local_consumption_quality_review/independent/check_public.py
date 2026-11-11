"""Independent public-only evidence checks; never imports product or evaluates recorded code."""
from pathlib import Path
import ast
import hashlib
import json
import math
import re

B = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_local_relation_consumption_001')
P = B / 'quality_handoff/handoff_01/public'
OUT = Path(__file__).parent
checks = []

def check(name, condition):
    checks.append({'name': name, 'passed': bool(condition)})
    assert condition, name

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def texts(attempt):
    result = []
    for response in attempt['responses']:
        for c in response['value']['result']['content']:
            if c.get('type') == 'text':
                result.append(json.loads(c['text']))
    return result

def bounds_from_output(s):
    first = s.splitlines()[0]
    if first.startswith('{'):
        return {n: {'lo': v['lo'], 'hi': v['hi'], 'center': v['center']} for n,v in json.loads(first).items()}
    if first.startswith('['):
        return {v['name']: {'lo': v['min'], 'hi': v['max'], 'center': v['center']} for v in json.loads(first)}
    found = {}
    for line in s.splitlines():
        m = re.match(r'(N\d+).*?(?:bounds|min) (\[[^\]]+\]) (?:max )?(\[[^\]]+\]) center (\[[^\]]+\])', line)
        if m:
            found[m[1]] = dict(zip(['lo','hi','center'], map(ast.literal_eval, m.groups()[1:])))
    return found

def geometry_from_output(s):
    result = {}
    current = None
    for line in s.splitlines():
        line = line.strip()
        if re.fullmatch('N[0-9]+', line):
            current = line
        match = re.match(r'(N\d+) (?:world_vertices|world vertices|vertices) (\[.*)', line)
        if match:
            current = match[1]
            coords = ast.literal_eval(match[2])
            if len(coords[0]) == 2 and isinstance(coords[0][0], int):
                coords = [x[1] for x in coords]
            result.setdefault(current, {})['vertices'] = coords
        elif line.startswith('verts ') and current:
            result.setdefault(current, {})['vertices'] = [x[1] for x in ast.literal_eval(line[6:])]
        elif line.startswith('faces ') and current:
            result.setdefault(current, {})['faces'] = ast.literal_eval(line[6:])
        match = re.match(r'(N\d+) world vertex coordinate levels (\[.*)', line)
        if match:
            result.setdefault(match[1], {})['levels'] = ast.literal_eval(match[2])
    return result

index = json.loads((P/'INDEX.json').read_bytes())
truth = json.loads((B/'scoring/TRUTH.json').read_bytes())
contract = json.loads((B/'scoring/SCORING_CONTRACT.json').read_bytes())
check('fixed_nine_slots', len(index['answers']) == index['fixed_slots'] == 9)
check('public_task_hash', sha(P/'tasks/T1.txt') == index['tasks'][0]['input_sha256'])
check('public_image_hash', sha(P/'tasks/INITIAL.png') == index['tasks'][0]['initial_image_sha256'])
rows = []
for item in index['answers']:
    aid = item['anonymous_id']
    d = P / aid
    check(aid+':answer_sha', sha(d/'answer.txt') == item['answer_original_sha256'])
    check(aid+':present_completed', item['answer_state']=='present' and item['execution_record_state']=='completed')
    e = json.loads((d/'tool_evidence.json').read_bytes())
    sc = json.loads((d/'source_consistency.json').read_bytes())
    done = [x['event'] for x in e['public_tool_events'] if x['phase']=='item.completed']
    check(aid+':all_owner_responses_have_consumer_completed_matches', len(done)==len(e['owner_attempts']) and all(
        a['request']['params']['name']==v['tool'] and a['request']['params']['arguments']==v['arguments'] and
        a['responses'][0]['value']['result']['content']==v['result']['content'] and not a['is_error'] and v['status']=='completed' and v['error'] is None
        for a,v in zip(e['owner_attempts'],done)))
    check(aid+':source_asset', sc['ACTOR_CONFIG']['asset_sha256']==truth['source_scene_sha256']==sc['owner_IDENTITY']['asset_sha256'])
    check(aid+':public_source_consistency', sc['INITIAL_original_file_sha256']==sc['FINAL_original_file_sha256'] and sc['CLOSE']['asset_unchanged'] and sc['CLOSE']['geometry_unchanged'] and sc['CLOSE']['errors']==[])
    native = []
    observations = []
    for a in e['owner_attempts']:
        for value in texts(a):
            if a['request']['params']['name']=='execute_blender_code':
                native.append(value['result']['result'])
            else:
                observations.append(value)
    bounds = bounds_from_output(native[0])
    check(aid+':all28_bounds_observed', len(bounds)==28)
    height = (bounds['N12']['center'][2]+bounds['N24']['center'][2])/2
    rear = bounds['N10']['hi'][1]
    pipe = [(bounds['N04']['center'][i]+bounds['N19']['center'][i])/2 for i in range(2)]
    predicates = {}
    for n in ['N15','N16','N18','N25']:
        c = bounds[n]['center']
        predicates[n] = [c[2]<height, c[1]>rear, math.dist(c[:2],pipe)<=.7]
    check(aid+':target_predicates_match_independent_truth', predicates=={c['object_id']:c['three_conditions'] for c in truth['candidate_evaluations']})
    geom = {}
    for s in native:
        geom.update(geometry_from_output(s))
    frame = geom['N16']
    levels = frame.get('levels') or [sorted(set(v[k] for v in frame['vertices'])) for k in range(3)]
    check(aid+':observed_frame_levels_support_localization', all(len(a)==len(b) and max(abs(x-y) for x,y in zip(a,b)) < 1e-6 for a,b in zip(levels, [[.11,.135,.225,.25],[.08,.12],[.3,.325,.395,.42]])))
    observed_relations = []
    if observations:
        check(aid+':one_pair_query_correct_target', len(observations)==1 and observations[0]['target']['name']=='N16')
        for c,t in zip(observations[0]['candidates'],truth['relations']):
            rel=c['closed_solid_relation']
            dist=c['surface_proximity']['value']['distance_m']
            klass='solid_overlap' if rel['value']=='penetrating' else 'within_contact_tolerance' if dist<=.00025 else 'separated'
            check(aid+':'+c['name']+':relation_matches_truth', c['name']==t['neighbor_id'] and klass==t['classification'] and rel['status']=='measured')
            check(aid+':'+c['name']+':distance_matches_truth', abs(dist*1000-t['minimum_distance_mm'])<1e-9)
            observed_relations.append({'id':c['name'],'classification':klass,'distance_m':dist,'local_evidence_present':'local_evidence' in rel})
    else:
        check(aid+':all_four_native_mesh_topologies_observed', all(n in geom and 'faces' in geom[n] for n in ['N16','N13','N08','N28']))
        check(aid+':frame_material_boundary_observed', len(frame['vertices'])==16 and len(frame['faces'])==16 and [5,6,14,13] in [list(f) for f in frame['faces']])
        vertices={n:geom[n]['vertices'] for n in ['N16','N13','N08','N28']}
        f=vertices['N16'];s=vertices['N13'];l=vertices['N08'];r=vertices['N28']
        witness=[.245,.1,.36]
        check(aid+':strict_common_interior_arithmetic', f[5][0]<witness[0]<max(v[0] for v in f) and min(v[1] for v in f)<witness[1]<max(v[1] for v in f) and min(v[2] for v in f)<witness[2]<max(v[2] for v in f) and all(min(v[k] for v in s)<witness[k]<max(v[k] for v in s) for k in range(3)))
        gap=min(v[0] for v in f)-max(v[0] for v in l)
        check(aid+':locator_positive_gap_with_attained_yz', 0<gap<.00025 and all(max(min(v[k] for v in f),min(v[k] for v in l))<witness[k]<min(max(v[k] for v in f),max(v[k] for v in l)) for k in [1,2]))
        clearances=[min(v[0] for v in r)-f[4][0],f[5][0]-max(v[0] for v in r),min(v[2] for v in r)-f[4][2],f[6][2]-max(v[2] for v in r)]
        check(aid+':rod_entire_prismatic_section_inside_opening', min(clearances)>.00025 and min(v[1] for v in r)<min(v[1] for v in f)<max(v[1] for v in f)<max(v[1] for v in r))
        observed_relations=[{'id':'N13','classification':'solid_overlap','strict_common_interior_point':witness},{'id':'N08','classification':'within_contact_tolerance','distance_m':gap},{'id':'N28','classification':'separated','distance_m':min(clearances)}]
    rows.append({'anonymous_id':aid,'target_predicates_from_public_geometry':predicates,'height_threshold_m':height,'front_beam_rear_y_m':rear,'pipe_mid_xy_m':pipe,'target_radius_m':math.dist(bounds['N16']['center'][:2],pipe),'frame_coordinate_levels':levels,'relation_observations_checked_against_truth':observed_relations,'answer_sha256':sha(d/'answer.txt'),'evidence_sha256':sha(d/'tool_evidence.json'),'source_sha256':sha(d/'source_consistency.json')})

result={'scope':'Independent public-only arithmetic/provenance checks plus separately recorded semantic judgment; no product, Blender, model, private grouping or cost reads. No recorded code executed.','input_commit':'06d1b4b4cadd880884a0a3c0927a3095ea761f30','index_sha256':sha(P/'INDEX.json'),'scoring_contract_sha256':sha(B/'scoring/SCORING_CONTRACT.json'),'truth_sha256':sha(B/'scoring/TRUTH.json'),'checks':checks,'check_count':len(checks),'all_passed':all(c['passed'] for c in checks),'rows':rows}
(OUT/'PUBLIC_CHECKS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'check_count':len(checks),'all_passed':True,'rows':len(rows)}))
