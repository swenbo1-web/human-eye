"""Grade a closed source-region answer using its admitted asset domain."""

import argparse
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import re
from runpy import run_path
import sys
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
V = HERE.parent
OUTPUT_ROOT = Path('D:/he_m4_source_region_score_admission_001')
ASSEMBLY = SimpleNamespace(**run_path(str(V/'m4_assembly_cross_asset_product_native_001/score.py')))
YANYITE = ASSEMBLY.OPPOSITE
DOMAINS = {'assembly':ASSEMBLY,'yanyite':YANYITE}
OLD = ASSEMBLY.OLD
load, pin, require, write = ASSEMBLY.load, ASSEMBLY.pin, ASSEMBLY.require, ASSEMBLY.write


def load_public_tool_header():
    directory = V/'m4_assembly_evidence_consumption_001'
    previous = sys.modules.pop('bridge', None)
    original = sys.path[:]
    try:
        sys.path.insert(0,str(directory))
        return run_path(str(directory/'consumer_contract.py'))['public_tool_event_header']
    finally:
        sys.path[:] = original
        sys.modules.pop('bridge',None)
        if previous is not None:
            sys.modules['bridge'] = previous


PUBLIC_TOOL_HEADER = load_public_tool_header()
TIMED_HEADER = rb'^\s*\{\s*"perf_ns"\s*:\s*[0-9]+\s*,\s*"event"\s*:\s*'
MESSAGE_HEADER = re.compile(
    TIMED_HEADER + rb'\{\s*"type"\s*:\s*"item\.completed"\s*,\s*"item"\s*:\s*\{\s*'
    rb'"id"\s*:\s*"(?:[^"\\\x00-\x1f]|\\.)*"\s*,\s*"type"\s*:\s*"agent_message"\s*[,}]')
TURN_HEADER = re.compile(TIMED_HEADER + rb'\{\s*"type"\s*:\s*"(turn\.(?:completed|failed))"\s*[,}]')
USAGE_FIELDS = ('input_tokens','cached_input_tokens','output_tokens')


def public_events(path):
    """Parse approved timed envelopes. A failure header is retained without its body."""
    with Path(path).open('rb') as stream:
        for line in stream:
            head = line[:4096]
            tool = PUBLIC_TOOL_HEADER(head,timed=True)
            if (tool and tool.group(1) == b'item.completed') or MESSAGE_HEADER.match(head):
                event = json.loads(line)['event']
                item_type = 'mcp_tool_call' if tool else 'agent_message'
                require(event['type'] == 'item.completed' and event['item']['type'] == item_type,
                        'public_event_header_and_body_disagree')
                yield event
                continue
            turn = TURN_HEADER.match(head)
            if turn is not None:
                if turn.group(1) == b'turn.failed':
                    yield {'type':'turn.failed'}
                else:
                    event = json.loads(line)['event']
                    require(event['type'] == 'turn.completed','public_event_header_and_body_disagree')
                    usage = event.get('usage') or {}
                    yield {'type':'turn.completed','usage':{
                        key:usage[key] for key in USAGE_FIELDS if type(usage.get(key)) is int and usage[key]>=0}}


def verify_public_final(slot,result):
    """Bind the published final, raw public tools, and original stdout hash."""
    answer = slot/'consumer/PUBLIC_FINAL.txt'
    archived = pin(answer)
    require(result['answer']==archived,'published_final_file_changed')
    consumer = slot/'consumer'
    raw = (consumer/'stdout.raw.bin').resolve(strict=True)
    completed, calls = [], []
    turn_completed,turn_failed = False,False
    for event in public_events(consumer/'events.jsonl'):
        if event['type'] == 'item.completed':
            item = event['item']
            if item['type'] == 'agent_message':
                completed.append(item)
            elif item.get('result') and not item.get('error'):
                calls.append(item)
        elif event['type'] == 'turn.completed':
            turn_completed = True
        elif event['type'] == 'turn.failed':
            turn_failed = True
    require(completed and turn_completed and not turn_failed and
            answer.read_text(encoding='utf8').rstrip('\n') == completed[-1]['text'].rstrip('\n'),
            'public_final_not_the_completed_original_CLI_answer')
    with raw.open('rb') as stream:
        digest = sha256()
        count = 0
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            digest.update(chunk)
            count += len(chunk)
    return archived,completed[-1],calls,{'path':str(raw),'bytes':count,'sha256':digest.hexdigest()}


def load_producer(path):
    """Adapt the already validated producer receipt path for the legacy reader."""
    return load(Path(path))


_assembly_frame_source = OLD.with_replacements(ASSEMBLY.frame_source_binding,load=load_producer)
_assembly_frames = OLD.with_replacements(ASSEMBLY.qualify_frames,frame_source_binding=_assembly_frame_source)


def strict_json(path):
    def unique_keys(pairs):
        result = {}
        for k,v in pairs:
            require(k not in result,'duplicate_claim_JSON_key/'+k)
            result[k] = v
        return result

    def invalid_number(_):
        raise ValueError('nonfinite_claim_JSON_number')

    def finite_float(raw):
        number = float(raw)
        require(isfinite(number),'nonfinite_claim_JSON_number')
        return number

    return json.loads(Path(path).read_bytes(),object_pairs_hook=unique_keys,
                      parse_constant=invalid_number,parse_float=finite_float)


def read_claims(claim_path,domain,slot,answer):
    table = strict_json(claim_path)
    require(type(table) is dict and table.get('answer_sha256')==answer['sha256']
            and table.get('slot')==slot.name,'literal_claims_unbound_to_original_answer')
    claims = table.get('claims')
    require(type(claims) is dict,'invalid_required_claim_manifest')
    expected = set(domain.REQUIRED)
    unexpected = claims.keys()-expected
    missing = expected-claims.keys()
    require(not unexpected,'unexpected_claim_items/'+','.join(sorted(unexpected)))
    require(not missing,'missing_required_claim_items/'+','.join(sorted(missing)))
    require(all(type(row) is dict for row in claims.values()),'invalid_mandatory_claim_type')
    return claims


def check_claim(domain,item,row,answer,geometry,frames,claims):
    region,_,criterion = item.partition('.')
    # Only these asset-specific branches use an alternate coordinate domain.
    if criterion in ('distance','nearest_pair','threshold'):
        return domain.check_claim(item,row,answer,geometry,frames,claims)
    quote = row['quote']
    require(isinstance(quote,str) and quote.strip() and quote in answer,'claim_quote_absent_from_actual_final')
    if item == 'nearer':
        require(row['value']==geometry['nearer'],'incorrect_nearer_region')
    elif criterion == 'counts':
        current = geometry['regions'][region]
        counts = row['triangles'],row['vertices']
        require(counts==(current['triangle_count'],current['vertex_count']) and
                all(re.search(r'(?<!\d)'+str(value)+r'(?!\d)',quote) for value in counts),
                'source_counts_not_current_or_literal')
    elif criterion == 'direction':
        require(ASSEMBLY.QUALIFY.near_point(row['world_unit_direction'],geometry['regions'][region]['direction_world'],
                                           OLD.POSITION_TOL),'world_direction_reversed_or_invalid')
    elif criterion == 'image':
        return OLD.find_image(row,frames[region],answer)
    elif criterion == 'pixel':
        image = claims.get(region+'.image')
        require(isinstance(image,dict),'pixel_claim_without_current_image')
        OLD.check_pixel(row,OLD.find_image(image,frames[region],answer))
    elif criterion == 'scope':
        require(row['observable_scope']=='actual_samples_in_one_frame' and
                row['implies_complete_visibility'] is False and row['implies_all_unsampled_are_occluded'] is False,
                'curve_single_view_visibility_overstatement')
    else:
        raise ValueError('unexpected_claim_criterion')
    return None


def score_slot(asset,slot,claim_path):
    domain = DOMAINS[asset]
    slot = Path(slot).resolve(strict=True)
    require(slot.name in domain.PRODUCT_SOURCES,'unexpected_formal_slot')
    result_path = slot/'SLOT_RESULT.json'
    result,publication = load(result_path), load(slot/'SLOT_PUBLICATION.json')
    require(slot.name==result['label']==publication['label'] and publication['result_sha256']==pin(result_path)['sha256'],
            'slot_result_unbound')
    require(result['status']==publication['status']=='completed' and result.get('consumer',{}).get('valid_completion'),
            'slot_has_no_closed_final')
    historical,known = domain.historical_truth()
    geometry,terminal,device = domain.verify_closed_source(slot,historical,known)
    answer,final,cli_calls,stdout = verify_public_final(slot,result)
    claims = read_claims(claim_path,domain,slot,answer)
    frame_verifier = _assembly_frames if domain is ASSEMBLY else domain.qualify_frames
    if any((slot/'owner').glob('tool_*')):
        calls = ASSEMBLY.QUALIFY.actual_calls(slot)
        frames,unusable = frame_verifier(slot,terminal,device,geometry,cli_calls,calls)
        product = domain.verify_product_measurements(slot,calls,geometry,terminal)
    else:
        require(not device['frames'] and not cli_calls,'frame_or_CLI_tool_traffic_has_no_owner_call')
        calls,frames,unusable,product = [],dict.fromkeys(domain.BOXES,()),[],{}
    criteria,chosen = {},{}
    for item in domain.REQUIRED:
        row = claims[item]
        try:
            frame = check_claim(domain,item,row,final['text'],geometry,frames,claims)
            if frame is not None:
                chosen[item] = frame
            criteria[item] = {'status':'pass','quote':row['quote']}
        except (OSError,ValueError,KeyError,TypeError,IndexError) as error:
            criteria[item] = {'status':'failure','quote':row.get('quote'),'reason':str(error)}
    if len(chosen)==2 and len({frame['ref'] for frame in chosen.values()})!=2:
        for item in chosen:
            criteria[item].update(status='failure',reason='same_frame_reused_for_two_local_originals')
    passed = sum(row['status']=='pass' for row in criteria.values())
    adoption = domain.score_slot.__globals__['score_exposure'](slot,calls,product,geometry,frames,chosen,claims,criteria)
    return {'asset':asset,'slot':slot.name,'actual_status':publication['status'],'final_available':True,
            'answer':answer,'CLI_stdout':stdout,'actual_final_item':final['id'],'same_slot_geometry':geometry,
            'usable_frames':frames,'unusable_frames':unusable,'passed_items':passed,'total_items':len(domain.REQUIRED),
            'quality_complete':passed==len(domain.REQUIRED),'claim_transcription':pin(claim_path),
            'failure_records':result.get('errors',[]),'criteria':criteria,'chosen_images':chosen,'adoption':adoption}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset',choices=tuple(DOMAINS),required=True)
    for field in ('slot','claims','output'):
        parser.add_argument('--'+field,type=Path,required=True)
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode,'fixed_isolated_interpreter_required')
    output = args.output.resolve()
    require(output.is_relative_to(OUTPUT_ROOT.resolve()) and output!=OUTPUT_ROOT.resolve(),
            'score_output_must_stay_in_new_evidence_directory')
    try:
        verdict = score_slot(args.asset,args.slot,args.claims)
    except (OSError,ValueError,KeyError,TypeError,IndexError,AttributeError) as error:
        verdict = {'asset':args.asset,'slot':args.slot.name,'quality_complete':False,'passed_items':0,
                   'total_items':len(DOMAINS[args.asset].REQUIRED),'error':str(error),'adoption':None}
    write(output,verdict)
    print({key:verdict[key] for key in ('asset','slot','quality_complete','passed_items','total_items','error') if key in verdict})
    return 0 if verdict['quality_complete'] else 1


if __name__=='__main__':
    raise SystemExit(main())
