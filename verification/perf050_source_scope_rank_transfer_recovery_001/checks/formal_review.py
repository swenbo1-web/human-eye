"""Score the two frozen formal answers against independent current source and image evidence."""

import json
import re
from hashlib import sha256
from pathlib import Path
from runpy import run_path
from shutil import copyfile
import sys


NS = Path(__file__).resolve().parents[1]
RUN = Path('D:/he_perf050_source_scope_rank_transfer_recovery_001')
V = NS.parent
LABELS = ('N1', 'P1')


def read(path):
    return json.loads(path.read_bytes())


def save(path, value):
    with path.open('xb') as file:
        file.write((json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode())


def require(value, reason):
    if not value:
        raise ValueError(reason)


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def witness(field):
    return [float(axis) for axis in field.replace('−','-').split(',')]


def transcript(answer):
    rows = []
    for line in answer.splitlines():
        if not line.startswith('|') or not re.search(r'Obj_0[58]',line):
            continue
        fields = [x.strip().replace('`','').replace('**','') for x in line.strip('|').split('|')]
        a, b = map(witness,re.findall(r'\(([^()]+)\)', ' '.join(fields[3:])))
        rows.append({'scope':'selected' if '选区' in fields[0] else 'whole',
            'reference':re.search(r'Obj_0[58]',fields[1]).group(), 'distance_m':float(fields[2]), 'witness_a':a,'witness_b':b})
    ranking = {}
    for scope, label in (('selected','选区'),('whole','整件')):
        line, = [s for s in answer.splitlines() if '按'+label in s and '更近' in s]
        ranking[scope] = re.search(r'Obj_0[58]',line).group()
    require('Obj_07' in answer and ('0–3' in answer or '0、1、2、3' in answer) and '求值' in answer,
            'final_selection_not_bound_to_current_evaluated_rows')
    return {'focus_object':'Obj_07','selected_source_triangle_ids':[0,1,2,3],'measurements':rows,'ranking':ranking}


def original_after_close(slot, oracle, meshes, reviewer, original):
    asset = slot/'native/input.blend'
    result = read(slot/'SLOT_RESULT.json')
    publication = read(slot/'SLOT_PUBLICATION.json')
    require(result['status'] == publication['status'] == 'completed' and result['model_consumers'] == 1
            and all(result[key]['passed'] for key in ('closure_verification','independent_before_after'))
            and digest(asset) == result['asset_sha256'] == oracle['ASSET_SHA']
            and publication['result_sha256'] == digest(slot/'SLOT_RESULT.json'), 'current_slot_or_close_not_bound')
    sources = [slot/'initial_capture/TERMINAL_SOURCE.json',slot/'TERMINAL_SOURCE.json']
    packets = [read(path) for path in sources]
    proofs = [oracle['verifies_geometry'](packet,meshes) for packet in packets]
    require(proofs[0] == proofs[1] and packets[0]['source']['pid'] == packets[1]['source']['pid']
            and all(Path(p['source']['asset_copy']) == asset for p in packets), 'current_geometry_instance_changed')
    text = original.decode()
    links = set(re.findall(r'\]\(<?([A-Za-z]:/[^)<>\n]+\.png)>?\)',text))
    require(len(links)==1, 'final_original_png_not_unique')
    link, = links
    resolved = Path(link).resolve(strict=True)
    frame, = [row for row in read(slot/'DEVICE_EVIDENCE.json')['frames'] if Path(row['PNG']).resolve(strict=True) == resolved]
    wire = sorted((slot/'owner').glob('tool_*/RESPONSE.json'))
    image = reviewer['review'](slot,frame['ref'],wire,link)
    require(image['explicit_final_path_resolves_to_same_original_PNG'] is True
            and any(item['declared_path_matches_original'] for item in image['bound_actual_image_deliveries'])
            and image['samples']['visible_source_triangle_indices'] == [0,1,2,3], 'missing_original_published_frame_or_samples')
    return proofs, image


def fixed_cli(extra):
    budget = run_path(str(V/'m4_cross_scale_live_qualification_001/checks/delivery.py'))['budget_helpers']
    helpers, policy = budget()
    sys.path.insert(0,str(V/'m5_global_observe_measure_qualification_001/checks'))
    omitted = run_path(str(V/'m5_global_observe_measure_qualification_001/checks/live_wire.py'))['omitted_paths']
    rows = []
    for index in (1,2):
        response = read(extra/'owner'/f'tool_{index:02d}'/'RESPONSE.json')['result']
        body = response['content'][0]['text']
        for seconds in ('0.0000','10.0000','100.0000'):
            items = helpers['model_items'](response,seconds)
            mcp = helpers['truncate_items'](items,policy['MCP_bytes'])
            history = helpers['truncate_items'](mcp,policy['history_approximate_tokens'],token_mode=True)
            for stage, retained in (('MCP',mcp),('history',history)):
                text = [item['text'] for item in retained if item['type']=='input_text'][1]
                missing = set(tuple(x) for x in omitted(body,text))
                rows.append({'attempt':index,'stage':stage,'head_bytes':len(items[0]['text'].encode()),
                    'actual_owner_body_bytes':len(body.encode()),'retained_body_bytes':len(text.encode()),
                    'retained_sha256':sha256(text.encode()).hexdigest(),
                    'root_region_ref_lost_leaves':sum(x[0]=='region_ref' for x in missing),
                    'lost_distance_or_point_leaves':[x for x in sorted(missing,key=repr)
                       if x[:4]==('task_result','facts','surface_proximity','value') and len(x)>4
                        and x[4] in ('distance_m','nearest_witness')],
                    'retained_image_ref_lost_leaves':sum(len(x)>2 and x[0]=='images' and x[-1]=='image_ref' for x in missing),
                    'native_PNG_count':sum(item['type']=='input_image' for item in retained)})
    return rows


def main():
    binding = read(V/'m1_joint_full_task_tail_scope_001/install/PRODUCT_RUN_BINDING.json')
    sys.path.insert(0,binding['dependency_root'])
    oracle = run_path(str(NS/'checks/truth.py'))
    reviewer = run_path(str(NS/'checks/image_evidence.py'))
    meshes, _ = oracle['frozen_meshes']()
    membership = run_path(str(oracle['MEMBERSHIP']))
    truth = read(NS/'checks/TRUTH.json')
    costs = read(NS/'consumer/COSTS.json')
    for folder in ('answers','evidence'):
        (NS/folder).mkdir(exist_ok=True)
    results = {}
    for label, cost in zip(LABELS,costs['slots'],strict=True):
        require(cost['label']==label and cost['cost_evidence_verified'] and len(cost['actual_requests'])==6
                and all(row['CLI_binding']=='content_and_envelope_match' for row in cost['actual_requests']), 'formal_public_wire_unconfirmed')
        slot = RUN/'slots'/label
        final_path = slot/'consumer/PUBLIC_FINAL.txt'
        original = final_path.read_bytes()
        events = [json.loads(line) for line in (slot/'consumer/stdout.raw.bin').read_bytes().splitlines() if line.strip()]
        messages = [row['item'] for row in events if row.get('type')=='item.completed'
                    and row.get('item',{}).get('type')=='agent_message']
        require(messages[-1]['text'].encode()==original, 'final_does_not_match_original_CLI_agent_event')
        answer = transcript(original.decode())
        scored = oracle['score_geometry'](answer,truth,meshes,membership)
        source, image = original_after_close(slot,oracle,meshes,reviewer,original)
        if label=='N1':
            visibility = image['independent_continuous_geometry']['status']=='projected_open_interiors_clear' and '结合几何检查' in original.decode()
        else:
            body = json.loads(read(slot/'owner/tool_02/RESPONSE.json')['result']['content'][0]['text'])
            visibility = (body['visibility']['complete_witness'] is None and '完整表面可见性仍为未知' in original.decode()
                and body['visibility']['visible_source_triangle_count']==4 and body['visibility']['unseen_source_triangle_count']==0
                and body['visibility']['selected_surface_pixels']==image['samples']['selected_surface_pixels'])
        copyfile(final_path,NS/'answers'/f'{label}.txt')
        copyfile(image['PNG'],NS/'evidence'/f'{label}-{image["view"]}.png')
        results[label] = {'score':int(scored['focus_and_selection_as_answered'])+scored['pair_passed']+scored['ranking_passed']+1+int(visibility),
           'max':9,'closed_source':source,'original_final_agent_message_item':messages[-1]['id'],
           'original_final_bytes':len(original),'original_final_sha256':digest(final_path),'geometry':scored,
           'visibility_claim_accepted':visibility,'final_image':image,'normalized_answer':answer}
    save(NS/'checks/QUALITY.json', {'passed':all(x['score']==9 for x in results.values()),'formal_complete':2,
         'verified':results,'human_click_observed':None,'provider_context_observed':None})
    save(NS/'checks/P1_FIXED_CLI_REPLAY.json',{'actual_CLI_events_content_match_owner':True,
        'policy_replay_is_offline_and_not_provider_inference':True,'profile':fixed_cli(RUN/'slots/P1')})
    print({key:row['score'] for key,row in results.items()})


if __name__ == '__main__':
    main()
