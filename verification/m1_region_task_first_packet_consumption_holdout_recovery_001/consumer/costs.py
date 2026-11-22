"""Reconcile natural first-packet exposure and complete costs from actual consumer events."""

import json
from pathlib import Path
from runpy import run_path
import sys


NS = Path(__file__).resolve().parents[1]
V = NS.parent
sys.path.insert(0,str(NS/'harness'))
from common import EXTERNAL, FORMAL_LABELS, read, save, sha


BRIEF = 'active-observation-region-task-brief-v2'


def exposures(costs):
    matches = []
    for step in costs.get('actual_requests',[]):
        request = step['product']
        arguments = step['arguments']
        query = arguments.get('query') if isinstance(arguments,dict) else None
        if (step['tool'] != 'human_eye_scene_observe' or not request or not isinstance(query,dict)
                or query.get('mode') != 'active_observation' or 'region_task' not in query):
            continue
        raw = read(Path(step['stdio_RX']['path'])) if step['stdio_RX'] else {}
        result = raw.get('result') or {}
        texts = [block['text'] for block in result.get('content',[]) if block['type']=='text']
        if not texts or result.get('isError') is not False:
            matches.append({'attempt':step['attempt'],'requested':arguments.get('response_detail','omitted'),'success':False})
            continue
        packet = json.loads(texts[0])
        observed = packet.get('schema') == BRIEF or 'region_task' in packet.get('facts',{})
        matches.append({'attempt':step['attempt'],'requested':arguments.get('response_detail','omitted'),
                        'success':observed,'actual_shape':'evidence' if packet.get('schema') == BRIEF else 'standard_full',
                        'explicit_full_projected':arguments.get('response_detail')=='full' and packet.get('schema')==BRIEF,
                        'text_bytes':step['wire_content']['text_bytes'],'pngs':step['wire_content']['PNG'],
                        'CLI_delivered_text_bytes':step['CLI_delivered_text_bytes'],
                        'CLI_delivered_images':step['CLI_delivered_images'],'response_sha256':step['stdio_RX']['sha256'],
                        'unmodified_arguments':request['arguments']==arguments,'query':query})
    return matches


def collect():
    expected = read(NS/'FROZEN.json')
    token = sha(NS/'FROZEN.json')
    helper = run_path(str(V/'perf050_readonly_product_pilot_001/consumer/costs.py'))['summarize']
    rows = []
    for label in FORMAL_LABELS:
        row = helper(EXTERNAL/'slots'/label,token)
        row['matching_observation_requests'] = exposures(row)
        row['first_successful_matching'] = next((obs for obs in row['matching_observation_requests'] if obs['success']),None)
        if row['status'] == 'completed' and row['initial_prompt_sha256'] != expected['prompt_sha256']:
            row['cost_review_errors'].append('actual_prompt_changed')
            row['cost_evidence_verified'] = False
        rows.append(row)
    a,b = [row['first_successful_matching'] for row in rows]
    observed = bool(a and b and a['actual_shape']=='standard_full' and b['actual_shape']=='evidence'
                    and a['unmodified_arguments'] and b['unmodified_arguments']
                    and all(row['status']=='completed' and row['cost_evidence_verified'] for row in rows)
                    and rows[0]['thread_id'] and rows[1]['thread_id'] and rows[0]['thread_id']!=rows[1]['thread_id'])
    evidence = NS/'evidence'
    evidence.mkdir(exist_ok=True)
    output = evidence/'COSTS.json'
    save(output,{'freeze_sha256':token,'slots':rows,'observed_endpoint_delivery_difference':observed,
                 'explicit_B_full_projection_exposure':bool(observed and b['explicit_full_projected']),
                 'actual_consumers':sum(row['model_consumers_launched'] for row in rows),
                 'provider_timing':None,'provider_cash_billing':None})
    print('Saved',output.name,sha(output),flush=True)


if __name__=='__main__':
    collect()
