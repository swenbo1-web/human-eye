"""Derive content checks from completed original turns while preserving formal closure verdicts."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

import audit

read, require, file_pin = audit.read, audit.need, audit.pin


def reset_only(folder, frozen, topic):
    closed=read(folder/'closed.json')
    consumer=read(folder/'consumer/RESULT.json')
    transport=closed['transport']
    if consumer['passed_transport']:
        return False
    require(transport['error']['type']=='ConnectionResetError' and '10054' in transport['error']['message']
            and transport['closed'] and transport['transport_eof'] is False, 'not_the_observed_terminal_reset')
    require(consumer['raw_public_final_match'] and consumer['completion']['turn_status']=='turn.completed'
            and audit.checked_pin(consumer['native_closure'])==folder/'closed.json'
            and consumer['stdin_prompt']==frozen['fixture']['prompts'][topic]
            and consumer['consumer_exit']==closed['cli_exit']==closed['blender_exit']==0
            and closed['zero_geometry_preread'] and closed['same_before_after_capture'] and closed['error'] is None
            and closed['fixture_sha256_before']==closed['fixture_sha256_after']
                ==file_pin(folder/'input.blend')['sha256']==frozen['fixture']['blend']['sha256']
            and audit.checked_pin(closed['post_capture'])==folder/'post_capture.json'
            and consumer['cli_closed_ns']<=closed['closed_ns']<=closed['owned_deadline_ns'],
            'reset_with_unproven_final_or_native_closure')
    events=audit.public_cli(folder/'consumer/stdout.raw.bin')
    app_calls=[(r['item']['tool'],r['item']['arguments']) for r in events if r.get('type')=='item.completed'
               and r.get('item',{}).get('type')=='mcp_tool_call']
    catalog=audit.json_lines(folder/'wire/INDEX.jsonl')
    pairs=[]
    for row in catalog:
        if row['method']=='tools/call':
            req=audit.read(audit.checked_pin(row['tx']))
            response=audit.read(audit.checked_pin(row['rx']))
            require(req['id']==response['id'],'reset_misbound_last_request')
            pairs.append((req['params']['name'],req['params']['arguments']))
    # Explicit evidence that each tool response subsequently appeared in the actual completed CLI turn.
    # Several concurrent calls may complete in a different order.
    keyed=lambda row: json.dumps(row,sort_keys=True,ensure_ascii=False)
    require(sorted(map(keyed,pairs))==sorted(map(keyed,app_calls)) and len(catalog)==transport['requests'],
            'reset_has_a_tool_response_missing_from_public_turn')
    return True


def postflight(root, annotations):
    frozen,geometry,truth=audit.admission(root)
    answers=read(annotations)
    output={}
    for topic in audit.ORDER:
        folder=root/'slots'/f'NATURAL_{topic}'
        try:
            if not (folder/'consumer/RESULT.json').is_file():
                output[topic]={'status':'unrun'}
                continue
            receipt=read(folder/'consumer/RESULT.json')
            if receipt.get('completion',{}).get('turn_status')!='turn.completed':
                output[topic]={'status':'failed','reason':'missing_complete_public_turn','receipt':file_pin(folder/'consumer/RESULT.json')}
                continue
            derivation=reset_only(folder,frozen,topic)
            if derivation:
                def audited(condition,reason):
                    if reason!='natural_slot_not_normally_closed_and_bound':
                        require(condition,reason)
                audit.need=audited
            try:
                row=audit.natural_case(folder,frozen,geometry,truth,topic,answers.get(topic))
            finally:
                audit.need=require
            row.update(formal_transport_passed=receipt['passed_transport'],
                       after_reset_content_review=derivation,
                       formal_case_passed=bool(receipt['passed_transport'] and row.get('evidence_pass')))
            output[topic]=row
        except (KeyError,ValueError,TypeError,IndexError,OSError) as error:
            output[topic]={'status':'unverified','reason':str(error)}
    return output


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('root',type=lambda v:Path(v).resolve(strict=True))
    cli.add_argument('annotations',type=Path)
    cli.add_argument('output',type=Path)
    args=cli.parse_args()
    audit.save(args.output,postflight(args.root,args.annotations))

