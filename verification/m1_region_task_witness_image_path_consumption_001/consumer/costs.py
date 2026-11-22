"""Record actual path opportunities, requests, original answers and complete task costs."""

import json
from pathlib import Path
from runpy import run_path
import sys


NS=Path(__file__).resolve().parents[1]
V=NS.parent
sys.path[:0]=[str(NS/'harness'),str(NS/'qualification')]
from common import EXTERNAL, FORMAL_LABELS, read, save, sha
from diagnostic import CONDITIONS, SCHEMA, rows


def first_packet(account):
    for call in account.get('actual_requests',[]):
        arguments=call.get('arguments') or {}
        query=arguments.get('query') or {}
        if (call['tool']!='human_eye_scene_observe' or not isinstance(query,dict) or query.get('mode')!='active_observation'
                or query.get('region_task')!=CONDITIONS or arguments.get('include_image',True) is not True
                or call['wire_content']['error'] or not call['product'] or not call['stdio_RX']):
            continue
        reply=read(call['stdio_RX']['path'])['result']
        body=json.loads(reply['content'][0]['text'])
        if body.get('schema')!=SCHEMA:
            continue
        frames,scopes=rows(body['frames']),rows(body['scopes'])
        found=[]
        for witness in rows(body['witnesses']):
            frame=frames[witness['frame_index']]
            if frame['native_content_block_index'] is not None:
                found.append(frame['image_ref'])
        paths={}
        if 'witness_image_paths' in body:
            for address in rows(body['witness_image_paths']):
                frame=frames[address['frame_index']]
                paths[frame['image_ref']]={'path':address['local_image_path'],'image_sha256':frame['image_sha256'],
                        'scope_id':scopes[frame['scope_index']]['scope_id'],'frame_identity':frame['frame_identity']}
        return {'attempt':call['attempt'],'requested_detail':arguments.get('response_detail','omitted'),
                'witness_refs':found,'paths':paths,'wire_text_bytes':call['wire_content']['text_bytes'],
                'wire_PNG_bytes':sum(image['bytes'] for image in call['wire_content']['PNG']),
                'unmodified_arguments':call['product']['arguments']==arguments,
                'cli_text_bytes':call['CLI_delivered_text_bytes'],'cli_images':call['CLI_delivered_images']}
    return None


def matching_reads(account,packet):
    if not packet:
        return []
    result=[]
    for call in account.get('actual_requests',[]):
        if call['tool']!='read_images':
            continue
        refs=call['arguments'].get('refs',[])
        relevant=sorted(set(refs)&set(packet['witness_refs']))
        if not relevant:
            continue
        result.append({'attempt':call['attempt'],'matching_refs':relevant,'all_refs':refs,
                       'error':call['wire_content']['error'],'PNG_bytes':sum(item['bytes'] for item in call['wire_content']['PNG']),
                       'text_bytes':call['wire_content']['text_bytes'],'original_RPC_ms':call['dispatch_to_CLI_result_ms']})
    return result


def collect():
    frozen=read(NS/'FROZEN.json')
    token=sha(NS/'FROZEN.json')
    helper=run_path(str(V/'perf050_readonly_product_pilot_001/consumer/costs.py'))['summarize']
    accounts=[]
    for label in FORMAL_LABELS:
        row=helper(EXTERNAL/'slots'/label,token)
        packet=first_packet(row)
        answer=(EXTERNAL/'slots'/label/'consumer/PUBLIC_FINAL.txt')
        answer_text=answer.read_bytes().decode('utf8') if answer.is_file() else ''
        row['first_matching_packet']=packet
        row['matching_witness_read_images']=matching_reads(row,packet)
        row['first_packet_paths_present_verbatim_in_original_answer']=[
            ref for ref,value in (packet or {}).get('paths',{}).items() if value['path'] in answer_text]
        if row['status']=='completed' and row['initial_prompt_sha256']!=frozen['prompt_sha256']:
            row['cost_evidence_verified']=False
            row['cost_review_errors'].append('shared_prompt_changed')
        accounts.append(row)
    evidence=NS/'evidence'
    evidence.mkdir(exist_ok=True)
    output=evidence/'COSTS.json'
    save(output,{'freeze_sha256':token,'slots':accounts,
                 'actual_consumers':sum(row['model_consumers_launched'] for row in accounts),
                 'provider_internal_timing':None,'cash_billing':None,
                 'scope':'derived path occurrences are not quality, provenance or attribution judgments'})
    print('Saved',output,sha(output),flush=True)


if __name__=='__main__':
    collect()
