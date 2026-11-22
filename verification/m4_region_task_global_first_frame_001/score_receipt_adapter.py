"""Apply the frozen score to the already closed, original wire receipts."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
from runpy import run_path


NS = Path(__file__).resolve().parent
SCORE = run_path(str(NS/'score.py'))
OLD_WIRE = SCORE['OLD']['wire']
FROZEN_PROOF = SCORE['brief_proof']
VERIFY = SCORE['VERIFY']
require, pin = SCORE['require'], SCORE['pin']


def wire(root, request):
    # Stock client receipts omit TX_sha256. The new summary separately binds it
    # to the actual TX bytes, while the frozen scorer binds both worker digests.
    summary_wire = request['wire']
    standard = {key:value for key,value in summary_wire.items() if key != 'TX_sha256'}
    data = OLD_WIRE(root,{**request,'wire':standard})
    require(summary_wire['TX_sha256']==data[-1]['TX']['sha256'],'actual_enriched_summary_TX_changed')
    return data


def brief_proof(reply, body, producer, root, main, raw, negative_path):
    if not main or len(producer['constructed_frames']) != 2 or negative_path is None:
        return FROZEN_PROOF(reply,body,producer,root,main,raw,negative_path)
    proof = FROZEN_PROOF(reply,body,producer,root,main,raw,None)
    records = VERIFY['records']
    published, = [row for row in proof['public_witnesses'] if row['object_name']=='Component_582']
    other, = [row for row in proof['public_witnesses'] if row['object_name']=='Component_736']
    require(published['frame_index']==0 and other['frame_index']==1
            and published['pixel_row_index']==other['pixel_row_index'],'unexpected_reindexed_actual_witnesses')
    known = {frame['image_ref']:pin(frame['image_path']) for frame in producer['frames']}
    wrapped = {**producer,'frames':producer['constructed_frames']}
    controls = []
    for change_pixel_index in (False,True):
        value = deepcopy(body)
        table = value['witnesses']
        wanted = [row['region_index'] for row in records(table)].index(published['region_index'])
        current = table['rows'][wanted]
        current[table['columns'].index('frame_index')] = 1
        if change_pixel_index:
            current[table['columns'].index('pixel_row_index')] = other['pixel_row_index']+1
        changed = deepcopy(reply)
        changed['result']['content'][0]['text'] = json.dumps(value,ensure_ascii=False,separators=(',',':'))
        expected = VERIFY['WITNESS_BINDING_ERROR'] if change_pixel_index else 'v2_witness_state_or_pixel_row'
        try:
            VERIFY['verify_public_witnesses'](changed,wrapped,slot=root,authoritative_paths=known,require_paths=True)
        except ValueError as exc:
            require(str(exc)==expected,'wrong_frame_not_rejected_for_its_expected_binding')
        else:
            raise ValueError('wrong_frame_was_accepted')
        target = negative_path.with_stem(negative_path.stem+('_DISTINCT_PIXEL_ROW' if change_pixel_index else ''))
        with target.open('x',encoding='utf8',newline='\n') as stream:
            json.dump(changed,stream,ensure_ascii=False,separators=(',',':'))
        controls.append({**pin(target),'reason':expected})
    proof['reindex_negatives'] = controls
    return proof


def main(runtime, exact, output):
    failure_path = runtime/'REPLAY_SCORE.json'
    failure = SCORE['read'](failure_path)
    require(failure['passed'] is False and failure['error'].startswith('held_wire_receipt_changed/'),
            'original_frozen_score_rejection_missing')
    SCORE['OLD']['wire'] = wire
    FROZEN_PROOF.__globals__['brief_proof'] = brief_proof
    result = SCORE['main'](runtime,exact,output)
    result['offline_receipt_adapter'] = {
        'original_FROZEN_scorer':pin(NS/'score.py'),
        'original_rejected_score':pin(failure_path),
        'original_failure':failure['error'],
        'retouched_product_or_rerun_slots':0,
    }
    return result


if __name__=='__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--runtime',type=Path,required=True)
    ap.add_argument('--exact',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    a = ap.parse_args()
    try:
        report = main(a.runtime.resolve(strict=True),a.exact,a.output)
    except (OSError,ValueError,KeyError,IndexError) as error:
        report = {'passed':False,'quality_passed':False,'error':str(error),'error_type':type(error).__name__}
    with a.output.open('x',encoding='utf8',newline='\n') as out:
        json.dump(report,out,ensure_ascii=False,indent=2,allow_nan=False)
        out.write('\n')
    print(json.dumps({key:val for key,val in report.items() if key not in ('arms','pairs')}),flush=True)
    raise SystemExit(0 if report['passed'] else 1)
