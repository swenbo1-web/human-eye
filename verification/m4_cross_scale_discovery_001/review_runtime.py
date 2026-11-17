"""Saved-only source, original deadlines, process closure, budget and paired costs."""

import argparse
import base64
import hashlib
import json
from pathlib import Path
import statistics

HERE=Path(__file__).resolve().parent
RUNTIME=Path('D:/he_m4_cross_scale_001')
CHECKS=[]
PINS={}


def check(name,value):
    CHECKS.append(dict(name=name,passed=bool(value)))


def raw(path):
    path=Path(path).resolve()
    data=path.read_bytes()
    item=dict(path=str(path),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
    previous=PINS.setdefault(str(path),item)
    check('stable_input/'+str(path),previous==item)
    return data


def read(path):
    return json.loads(raw(path))


def lines(path):
    return [json.loads(row) for row in raw(path).splitlines() if row.strip()]


def session(label):
    folder=RUNTIME/'sessions'/label
    result=read(folder/'SLOT_RESULT.json')
    publication=read(folder/'SLOT_PUBLICATION.json')
    binding=read(result['run_binding_path'])
    close=read(folder/'RUNTIME_CLOSE.json')
    check(label+'/published_completed',result['status']==publication['status']=='completed' and not result['errors'])
    check(label+'/result_identity',publication['result_sha256']==PINS[str((folder/'SLOT_RESULT.json').resolve())]['sha256'])
    check(label+'/original600',result['clocks']['owned_deadline_ns']==result['clocks']['slot_started_ns']+600_000_000_000
          ==close['runtime']['owned_deadline_ns'] and publication['complete_slot_ns']<600_000_000_000)
    for row in binding['source_manifest']:
        check(label+'/installed/'+row['path'],hashlib.sha256(raw(Path(binding['install_root'])/row['path'])).hexdigest()==row['sha256'])
    identity={key:binding[key] for key in ('base_version','implementation_revision')}
    digest=hashlib.sha256(json.dumps(dict(identity,files=binding['source_manifest']),sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
    check(label+'/142source_identity',len(binding['source_manifest'])==142 and digest==binding['source_sha256'])
    native=close['Blender_status']
    native_end=native['closed']
    check(label+'/no_source_edit',native['source_file_unchanged'] is True and native['protected_files_unchanged'] is True
          and native_end['initial_geometry_fingerprint']==native_end['final_geometry_fingerprint'] and not native_end['poisoned'])
    check(label+'/native_exit',result['cleanup']['native_retained_exit']['confirmed'] is True
          and result['cleanup']['native_retained_exit']['exit_code']==0
          and result['cleanup']['native_retained_exit']['handle_closed'] is True
          and result['cleanup']['native_Popen_handle_closed'] is True and close['Blender_close']['process_reaped'] is True)
    check(label+'/stdio_closed',close['MCP_stdio_close']['confirmed'] is True
          and close['MCP_stdio_close']['reader_stopped'] is True and all(close['MCP_stdio_close']['pipes_closed'].values())
          and close['MCP_retained_exit']['confirmed'] is True and close['MCP_retained_exit']['exit_code']==0 and not close['errors'])
    calls=lines(folder/'PUBLIC_REQUESTS.jsonl')
    entries=lines(folder/'product_full/INDEX.jsonl')
    check(label+'/complete_original_request_count',len(calls)==len(entries)==len(result['requests'])==(7 if label=='state' else 1))
    costs=[]
    for index,(call,entry) in enumerate(zip(calls,entries,strict=True),1):
        prefix=label+'/'+str(index)
        check(prefix+'/single_producer_window',call['producer_archive_index']==entry['index']==index
              and call['started_ns']<=entry['started_ns']<=entry['producer_returned_ns']<=call['closed_ns'])
        check(prefix+'/original30',0<=call['closed_ns']-call['started_ns']<30_000_000_000)
        for kind in ('request','response','actual_TX','actual_RX'):
            check(prefix+'/original_'+kind,hashlib.sha256(raw(call[kind+'_path'])).hexdigest()==call[kind+'_sha256'])
        original=read(entry['path'])
        check(prefix+'/producer_original_hash',PINS[str(Path(entry['path']).resolve())]['sha256']==entry['sha256'])
        response=read(folder/'product_calls'/('call_'+str(index).zfill(3))/'RESPONSE.json')
        public=json.loads(next(block['text'] for block in response['result']['content'] if block['type']=='text'))
        images=[block for block in response['result']['content'] if block['type']=='image']
        check(prefix+'/actual_public_success',response['result']['isError'] is False and public['read_only'] is True and public['execution_authority'] is False)
        check(prefix+'/selected_delivery_count',len(images)==len(original['frames'])==public['image_delivery']['mcp_content_constructed_image_count'])
        for block,frame in zip(images,original['frames'],strict=True):
            check(prefix+'/native_image_hash',hashlib.sha256(base64.b64decode(block['data'],validate=True)).hexdigest()==frame['image_sha256'])
        for frame in original.get('constructed_frames',original['frames']):
            check(prefix+'/PNG',hashlib.sha256(raw(frame['image_path'])).hexdigest()==frame['image_sha256'])
            check(prefix+'/NPZ',hashlib.sha256(raw(frame['arrays_path'])).hexdigest()==frame['arrays_sha256'])
        costs.append(dict(call=index,service_ms=(entry['producer_returned_ns']-entry['started_ns'])/1e6,
            service_stage_ms=original['stages']['service_total']['elapsed_ns']/1e6,
            client_ms=(call['closed_ns']-call['started_ns'])/1e6,
            raster_attempts=original['work']['raster_attempts'],frame_reuses=original['work']['frame_reuses'],
            source_parse_calls=original['work']['geometry_parse_calls'],capture_calls=original['work']['capture_calls'],
            selected_images=len(images),constructed_generation_images=len(original.get('constructed_frames',original['frames']))))
    audit=lines(folder/'product_audit.jsonl')
    attempts=[row for row in audit if row.get('event')=='active_observation_render_attempt']
    check(label+'/actual_attempt_event_count',sum(row['raster_attempts'] for row in costs)==len(attempts))
    return dict(label=label,version=result['version'],complete_owned_ms=publication['complete_slot_ns']/1e6,
        requests=costs,raster_attempts=len(attempts),errors=result['errors'])


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=HERE/'RUNTIME_REVIEW.json')
    args=parser.parse_args()
    order=['qualification_R0','pair1_R0','pair1_R1','pair2_R1','pair2_R0','pair3_R0','pair3_R1','state']
    sessions=[session(label) for label in order]
    records={row['label']:row for row in sessions}
    claims=lines_for_budget=[]
    raster=starts=pending=0
    for path in sorted((RUNTIME/'budget/claims').glob('*.json')):
        claim=read(path)
        settlement=RUNTIME/'budget/settlements'/path.name
        done=read(settlement) if settlement.exists() else None
        if claim['kind']=='Blender_start':
            starts+=1
            check('start_settled/'+path.name,done is not None and done.get('spawn_status')=='spawned')
        if claim['kind']=='raster_attempt':
            pending+=done is None
            raster+=(done or {}).get('actual_attempts',0)
            check('raster_settled/'+path.name,done is not None and done['actual_attempts']==1)
    check('8_owned_64_raster_budget',starts==8 and raster==sum(row['raster_attempts'] for row in sessions)<=64 and pending==0)
    pairs=[]
    for index in range(1,4):
        initial,optimized=records['pair'+str(index)+'_R0'],records['pair'+str(index)+'_R1']
        pairs.append(dict(pair=index,initial_service_ms=initial['requests'][0]['service_ms'],optimized_service_ms=optimized['requests'][0]['service_ms'],
            service_reduction=1-optimized['requests'][0]['service_ms']/initial['requests'][0]['service_ms'],
            initial_client_ms=initial['requests'][0]['client_ms'],optimized_client_ms=optimized['requests'][0]['client_ms'],
            initial_owned_ms=initial['complete_owned_ms'],optimized_owned_ms=optimized['complete_owned_ms'],
            owned_faster=optimized['complete_owned_ms']<initial['complete_owned_ms']))
    median_reduction=statistics.median(row['service_reduction'] for row in pairs)
    faster=sum(row['owned_faster'] for row in pairs)
    median_initial=statistics.median(row['initial_owned_ms'] for row in pairs)
    median_optimized=statistics.median(row['optimized_owned_ms'] for row in pairs)
    accepted=median_reduction>=.2 and faster>=2 and median_optimized<median_initial
    value=dict(schema='m4-cross-scale-runtime-review-v1',passed_checked_scope=all(row['passed'] for row in CHECKS),
        checks=CHECKS,failed_checks=[row for row in CHECKS if not row['passed']],input_pins=list(PINS.values()),sessions=sessions,
        budget=dict(owned_starts=starts,raster_attempts=raster,pending=pending,model_consumers=0,paid_API_calls=0),
        paired_costs=pairs,performance_gate_passed=accepted,service_paired_median_reduction=median_reduction,
        owned_faster_pairs=faster,initial_owned_median_ms=median_initial,optimized_owned_median_ms=median_optimized,
        time_scope='Original same-producer super.observe service window, exact client request window and full owned session are separately reported. Three timing pairs rank only after independent quality acceptance.',
        new_actual_operations=0)
    with args.output.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,sort_keys=True,ensure_ascii=False,indent=2)
        stream.write('\n')
    print(json.dumps(dict(passed=value['passed_checked_scope'],checks=len(CHECKS),failed=value['failed_checks'],performance_gate=accepted,budget=value['budget'])))


if __name__=='__main__':
    main()
