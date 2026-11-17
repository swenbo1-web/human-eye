"""Audit original request outcomes, held-process closure and two-request costs."""

import base64
import hashlib
import json
from pathlib import Path
import statistics

HERE=Path(__file__).resolve().parent
RUNTIME=Path('D:/he_m4_m5_source_region_001')
CHECKS=[]
PINS={}


def check(name,value):
    CHECKS.append(dict(name=name,passed=bool(value)))


def raw(path):
    path=Path(path).resolve()
    data=path.read_bytes()
    row=dict(path=str(path),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
    previous=PINS.setdefault(str(path),row)
    check('stable/'+str(path),row==previous)
    return data


def read(path):
    return json.loads(raw(path))


def lines(path):
    return [json.loads(line) for line in raw(path).splitlines() if line.strip()]


def session(label):
    folder=RUNTIME/'sessions'/label
    result=read(folder/'SLOT_RESULT.json')
    publication=read(folder/'SLOT_PUBLICATION.json')
    close=read(folder/'RUNTIME_CLOSE.json')
    binding=read(result['run_binding_path'])
    check(label+'/completed',result['status']==publication['status']=='completed' and not result['errors'])
    check(label+'/published_result',hashlib.sha256(raw(folder/'SLOT_RESULT.json')).hexdigest()==publication['result_sha256'])
    check(label+'/original600',result['clocks']['owned_deadline_ns']==result['clocks']['slot_started_ns']+600_000_000_000
          ==close['runtime']['owned_deadline_ns'] and publication['complete_slot_ns']<600_000_000_000)
    for row in binding['source_manifest']:
        check(label+'/installed/'+row['path'],hashlib.sha256(raw(Path(binding['install_root'])/row['path'])).hexdigest()==row['sha256'])
    identity={key:binding[key] for key in ('base_version','implementation_revision')}
    digest=hashlib.sha256(json.dumps(dict(identity,files=binding['source_manifest']),sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
    check(label+'/143source',len(binding['source_manifest'])==143 and digest==binding['source_sha256'])
    status=close['Blender_status']
    state=status['closed']
    check(label+'/asset_and_geometry_intact',status['source_file_unchanged'] is True and status['protected_files_unchanged'] is True
          and state['initial_geometry_fingerprint']==state['final_geometry_fingerprint'] and not state['poisoned'])
    check(label+'/held_native_exit',result['cleanup']['native_retained_exit']['confirmed'] is True
          and result['cleanup']['native_retained_exit']['exit_code']==0 and result['cleanup']['native_retained_exit']['handle_closed'] is True
          and result['cleanup']['native_Popen_handle_closed'] is True and close['Blender_close']['process_reaped'] is True)
    check(label+'/held_mcp_exit',close['MCP_stdio_close']['confirmed'] is True and close['MCP_stdio_close']['reader_stopped'] is True
          and all(close['MCP_stdio_close']['pipes_closed'].values()) and close['MCP_retained_exit']['confirmed'] is True
          and close['MCP_retained_exit']['exit_code']==0 and not close['errors'])
    calls=lines(folder/'PUBLIC_REQUESTS.jsonl')
    entries=lines(folder/'product_full/INDEX.jsonl')
    expected_count=11 if label=='state' else 2
    check(label+'/request_denominator',len(calls)==len(result['requests'])==expected_count)
    check(label+'/separate_public_service_counts',len(entries)==expected_count-(2 if label=='state' else 0))
    cost=[]
    archive_indices=[]
    for index,(call,expected) in enumerate(zip(calls,result['requests'],strict=True),1):
        prefix=label+'/'+str(index)
        for name in ('request','response','actual_TX','actual_RX'):
            check(prefix+'/'+name,hashlib.sha256(raw(call[name+'_path'])).hexdigest()==call[name+'_sha256'])
        response=read(call['response_path'])
        error='error' in response or response.get('result',{}).get('isError') is True
        check(prefix+'/expected_outcome',error==expected['expected_error'])
        check(prefix+'/original30',0<=call['closed_ns']-call['started_ns']<30_000_000_000)
        if error:
            check(prefix+'/rejected_without_success_archive',call['producer_archive_index'] is None)
            cost.append(dict(call=index,label=expected['label'],expected_error=True,client_ms=(call['closed_ns']-call['started_ns'])/1e6,
                service_ms=None,raster_attempts=0,selected_images=0))
            continue
        entry=call['producer_archive']
        archive_indices.append(entry['index'])
        check(prefix+'/producer_window',call['started_ns']<=entry['started_ns']<=entry['producer_returned_ns']<=call['closed_ns'])
        original=read(entry['path'])
        check(prefix+'/producer_hash',hashlib.sha256(raw(entry['path'])).hexdigest()==entry['sha256'])
        public=json.loads(next(block['text'] for block in response['result']['content'] if block['type']=='text'))
        images=[block for block in response['result']['content'] if block['type']=='image']
        frames=original.get('frames',[])
        check(prefix+'/readonly',public['read_only'] is True and public['execution_authority'] is False)
        check(prefix+'/delivery_count',len(images)==len(frames))
        for block,frame in zip(images,frames,strict=True):
            check(prefix+'/nativePNG',hashlib.sha256(base64.b64decode(block['data'],validate=True)).hexdigest()==frame['image_sha256'])
            check(prefix+'/savedPNG',hashlib.sha256(raw(frame['image_path'])).hexdigest()==frame['image_sha256'])
            check(prefix+'/savedNPZ',hashlib.sha256(raw(frame['arrays_path'])).hexdigest()==frame['arrays_sha256'])
        work=original.get('work',{})
        cost.append(dict(call=index,label=expected['label'],expected_error=False,
            service_ms=(entry['producer_returned_ns']-entry['started_ns'])/1e6,
            client_ms=(call['closed_ns']-call['started_ns'])/1e6,raster_attempts=work.get('raster_attempts',0),
            selected_images=len(images),work=work,stages=original.get('stages',{})))
    check(label+'/producer_indices_ordered',archive_indices==[row['index'] for row in entries] and archive_indices==sorted(set(archive_indices)))
    events=lines(folder/'product_audit.jsonl')
    attempts=sum(row.get('event') in ('active_observation_render_attempt','source_region_render_attempt') for row in events)
    check(label+'/render_event_denominator',attempts==sum(row['raster_attempts'] for row in cost))
    return dict(label=label,version=result['version'],owned_ms=publication['complete_slot_ns']/1e6,requests=cost,
        business_service_ms=sum(row['service_ms'] or 0 for row in cost),business_client_ms=sum(row['client_ms'] for row in cost),
        raster_attempts=attempts)


def main():
    labels=['qualification_R0','pair1_R0','pair1_R1','pair2_R1','pair2_R0','pair3_R0','pair3_R1','state']
    records=[session(label) for label in labels]
    by_label={row['label']:row for row in records}
    starts=rasters=pending=0
    for path in sorted((RUNTIME/'budget/claims').glob('*.json')):
        claim=read(path)
        settlement=RUNTIME/'budget/settlements'/path.name
        done=read(settlement) if settlement.exists() else None
        if claim['kind']=='Blender_start':
            starts+=1
            check('owned_claim/'+path.name,done is not None and done.get('spawn_status')=='spawned')
        if claim['kind']=='raster_attempt':
            pending+=done is None
            rasters+=(done or {}).get('actual_attempts',0)
            check('raster_claim/'+path.name,done is not None and done['actual_attempts']==1)
    preparation=read(RUNTIME/'fixture_preparation/RESULT.json')
    check('one_asset_preparation',preparation['status']=='completed' and preparation['exit_code']==0
          and preparation['retained_exit']['confirmed'] is True and preparation['retained_exit']['handle_closed'] is True)
    check('full_budget',starts==8 and rasters==sum(row['raster_attempts'] for row in records)<=24 and pending==0)
    pairs=[]
    for index in (1,2,3):
        left,right=by_label['pair'+str(index)+'_R0'],by_label['pair'+str(index)+'_R1']
        pairs.append(dict(pair=index,initial_service_ms=left['business_service_ms'],candidate_service_ms=right['business_service_ms'],
            service_reduction=1-right['business_service_ms']/left['business_service_ms'],
            initial_client_ms=left['business_client_ms'],candidate_client_ms=right['business_client_ms'],
            initial_owned_ms=left['owned_ms'],candidate_owned_ms=right['owned_ms'],
            service_faster=right['business_service_ms']<left['business_service_ms']))
    performance=sum(row['service_faster'] for row in pairs)>=2 and statistics.median(row['service_reduction'] for row in pairs)>0
    result=dict(schema='source-region-runtime-cost-v1',passed=all(row['passed'] for row in CHECKS),checks=CHECKS,
        failed_checks=[row for row in CHECKS if not row['passed']],input_pins=list(PINS.values()),records=records,pairs=pairs,
        performance_timing_gate=performance,paired_service_reduction_median=statistics.median(row['service_reduction'] for row in pairs),
        complete_owned_reduction=1-statistics.median(row['candidate_owned_ms'] for row in pairs)/statistics.median(row['initial_owned_ms'] for row in pairs),
        budget=dict(owned=starts,asset_preparation=1,total_Blender=starts+1,rasters=rasters,pending=pending,model_consumers=0,paid_API_calls=0),
        qualification_scope='Initial R0 is retained as failed local-camera qualification. Corrected pair1_R0 is also the first accepted local-view qualification.',
        cost_scope='Sum of the two original same-producer service windows, separately summed client windows and complete owned lifecycle. Nested stages remain separate.',
        new_live_operations=0)
    with (HERE/'RUNTIME_REVIEW.json').open('x',encoding='utf8',newline='\n') as stream:
        json.dump(result,stream,sort_keys=True,ensure_ascii=False,indent=2)
        stream.write('\n')
    print(json.dumps(dict(passed=result['passed'],checks=len(CHECKS),failures=result['failed_checks'],performance=performance,budget=result['budget'])))


if __name__=='__main__':
    main()
