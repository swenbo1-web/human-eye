"""Measure the two closed slots from public CLI, actual stdio and native TCP receipts."""

import json
from hashlib import file_digest
from pathlib import Path
import re
from runpy import run_path

HERE = Path(__file__).resolve().parent
RUN = Path('D:/he_m1_m2_source_region_scoped_measurement_consumption_001')
ALLOWED_USAGE = ('input_tokens', 'cached_input_tokens', 'output_tokens')
TURN = re.compile(rb'^\s*\{\s*"perf_ns"\s*:\s*(\d+)\s*,\s*"event"\s*:\s*\{\s*"type"\s*:\s*"turn\.completed"\s*[,}]')
PREFIX = 'HUMAN_EYE_BLENDER_MCP:'
WIRE = HERE.parent / 'm2_source_region_cold_selective_transport_recovery_001/verify.py'


def read(path):
    return json.loads(path.read_bytes()) if path.is_file() else {}


def lines(path):
    return [json.loads(line) for line in path.read_bytes().splitlines() if line.strip()] if path.is_file() else []


def pin(path):
    with path.open('rb') as stream:
        return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': file_digest(stream,'sha256').hexdigest()}


def elapsed(start, end):
    if type(start) is int and type(end) is int:
        if start > end:
            raise ValueError('recorded_cost_window_inverted')
        return end - start
    return None


def usage(folder, consumer):
    def project(event):
        return {k: event[k] for k in ALLOWED_USAGE if type(event.get(k)) is int and event[k] >= 0}
    path = folder / 'events.jsonl'
    timed = []
    if path.is_file():
        with path.open('rb') as stream:
            for line in stream:
                match = TURN.match(line[:4096])
                if match:
                    event = json.loads(line)['event']
                    assert event['type'] == 'turn.completed'
                    timed.append({'perf_ns':int(match[1]), 'usage':project(event.get('usage') or {})})
    expected = [project(row) for row in consumer.get('raw_usage_events', [])]
    assert [row['usage'] for row in timed] == expected
    raw = folder / 'stdout.raw.bin'
    receipt = pin(raw) if raw.is_file() else None
    if receipt and consumer.get('stdout_raw_sha256'):
        assert receipt['sha256'] == consumer['stdout_raw_sha256']
    value = timed[0]['usage'] if len(timed) == 1 else {}
    totals = None
    if len(value) == len(ALLOWED_USAGE):
        consumed, cached, output = (value[k] for k in ALLOWED_USAGE)
        assert cached <= consumed
        totals = {'input': consumed, 'cached_input': cached, 'output': output,
                  'input_plus_output':consumed+output, 'input_minus_cache_plus_output':consumed-cached+output}
    return {'public_completed_turns':timed,'totals':totals,'raw_stdout_digest_only':receipt}


def query_mode(arguments):
    query = arguments.get('query')
    return query.get('mode') if type(query) is dict else None


def bridge(slot):
    archive = read(slot/'consumer/BUSINESS_SOURCE_BINDING.json')
    by_attempt = {row['attempt']:row for row in archive.get('result_contracts',[])}
    actual = read(slot/'owner/BRIDGE_RESULT.json')
    results = []
    for tx in sorted((slot/'consumer/attachments').glob('bridge_*/*/TX.bin')):
        raw = read(tx)
        if raw.get('method') != 'tools/call':
            continue
        parent = tx.parent
        receipt = read(parent/'RECEIPT.json')
        idx = receipt.get('attempt')
        if idx is None:
            # Catalogue/empty skill discovery or a request rejected at the front.
            continue
        matched = by_attempt.get(idx, {})
        tx_stats = pin(tx)
        rx_stats = pin(parent/'RX.bin') if (parent/'RX.bin').is_file() else None
        if matched:
            assert tx_stats['sha256'] == matched['TX_sha256']
            if rx_stats and matched.get('RX_sha256'):
                assert rx_stats['sha256'] == matched['RX_sha256']
        args = raw['params'].get('arguments',{})
        results.append({
            'attempt':idx,'name':raw['params'].get('name'),'arguments':args,'query_mode':query_mode(args),
            'is_error':(read(parent/'RX.bin').get('result') or {}).get('isError'),
            'source_text_bytes':matched.get('source_text_UTF8_bytes'),
            'CLI_text_bytes':matched.get('CLI_text_UTF8_bytes'),
            'CLI_match':matched.get('matched'),'CLI_received_ns':matched.get('CLI_received_ns'),
            'received_ns':receipt.get('received_ns'),'owner_TCP_attempted':receipt.get('owner_TCP_attempted'),
            'frontend_roundtrip_ns':elapsed(receipt.get('received_ns'),receipt.get('flush_completed_ns')),
            'TX':tx_stats,'RX':rx_stats,
        })
    assert len({row['attempt'] for row in results}) == len(results)
    return {'calls':results,'bridge_accounting_errors':archive.get('binding_errors'),
            'transport_errors':actual.get('transport_errors'),'protocol_errors':actual.get('protocol_errors'),
            'owner_calls':actual.get('calls',[])}


def product_mcp(slot):
    calls=[]
    meter = {row['id']:row for row in lines(slot/'mcp_io/MCP_IO.jsonl') if row.get('method')=='tools/call'}
    for row in lines(slot/'PUBLIC_REQUESTS.jsonl'):
        receipt=row['receipt']
        req=row['request']
        ident=req['id']
        rx=row['response']
        assert row['id']==ident==rx['id'] and receipt['id']==ident
        args=req['params'].get('arguments',{})
        value=rx.get('result') or {}
        contents=value.get('content',[])
        producer_info=row.get('producer_archive')
        producer = read(Path(producer_info['path'])) if producer_info and producer_info.get('path') else {}
        calls.append({'id': ident,'starts_ns':row['started_ns'],'client_returned_ns':row.get('client_returned_ns'),
                      'tool':req['params']['name'],'query_mode':query_mode(args),
                      'is_error':value.get('isError',False) or 'error' in rx,
                      'body_bytes':sum(len(item['text'].encode('utf8')) for item in contents if item.get('type')=='text'),
                      'native_image_blocks':sum(item.get('type')=='image' for item in contents),
                      'TX_bytes':receipt.get('TX_bytes'),'RX_bytes':receipt.get('RX_bytes'),
                      'TX_sha256':receipt.get('TX_sha256'),'RX_sha256':receipt.get('RX_sha256'),
                      'roundtrip_ns':receipt.get('elapsed_ns'),'meter':meter.get(ident),
                      'producer':producer_info,'producer_stages':producer.get('stages'),'producer_work':producer.get('work')})
    return calls


def native_tcp(slot):
    root=slot/'native/WIRE'
    index=read(root/'INDEX.json')
    if not index: return []
    fixed_script=run_path(str(WIRE))['fixed_script']
    client={row['host_request_id']:row for row in
            read(slot/'mcp_io/REAL_HOST_STAGES.json').get('requests',[]) if row.get('host_request_id')}
    native={row['sequence']:row for row in lines(slot/'native/WORKER_EVENTS.jsonl')}
    rows=[]
    for item in index:
        n=item['sequence']
        packet=root/f'{n:03}'
        tx,rx=packet/'REQUEST.bin',packet/'RESPONSE.bin'
        request, reply=read(tx),read(rx)
        tx_pin,rx_pin=pin(tx),pin(rx)
        assert tx_pin['bytes']==item['request_bytes'] and rx_pin['bytes']==item['response_attempted_bytes']
        method=request.get('type')
        payload=(reply.get('result') or {}).get('result')
        record={'native_sequence':n,'outer_command':method,'TX':tx_pin,'RX':rx_pin,
                'duplex_bytes':tx_pin['bytes']+rx_pin['bytes'],
                'sendall_completed':item['response_sendall_completed'],'native_worker_event':native.get(n)}
        if isinstance(payload,str) and payload.startswith(PREFIX):
            fixed,allocation=fixed_script(request['params']['code'])
            embedded=json.loads(payload[len(PREFIX):])
            assert fixed['id']==embedded['id']
            capture=embedded.get('result') or {}
            record.update({'production_command':fixed['command'],'request_id':fixed['id'],
                           'bootstrap_and_request':allocation,'embedded_schema':capture.get('schema'),
                           'host_read_meter':client.get(fixed['id'])})
            if capture.get('schema') == 'human-eye-scene-delta-v1':
                record['full_delta_mesh_resources_sent']=len(capture['resources'])
            if capture.get('schema') == 'human-eye-private-source-region-residency-v1':
                record['selective_work']=capture['work']
        rows.append(record)
    return rows


def summarize(label):
    slot=RUN/'slots'/label
    if not slot.exists():return {'label':label,'status':'unrun'}
    result=read(slot/'SLOT_RESULT.json')
    public=read(slot/'SLOT_PUBLICATION.json')
    consumer=read(slot/'consumer/CONSUMER.json')
    if public and result:
        assert public['result_sha256']==pin(slot/'SLOT_RESULT.json')['sha256']
    db=bridge(slot)
    attempts=db['calls']
    arrived=[row['CLI_received_ns'] for row in attempts if type(row.get('CLI_received_ns')) is int]
    prompt,final=consumer.get('prompt_submitted_ns'),consumer.get('final_received_ns')
    sockets=native_tcp(slot)
    mcp=product_mcp(slot)
    for call in mcp:
        start, end = call['starts_ns'], call['client_returned_ns']
        call['nested_host_requests'] = [
            {'sequence': row['native_sequence'], 'request_id': row['request_id']}
            for row in sockets if row.get('host_read_meter') and type(start) is int and type(end) is int
            and start <= row['host_read_meter']['stages']['host_request']['started_ns']
            <= row['host_read_meter']['stages']['host_request']['closed_ns'] <= end
        ]
    tool_gaps = [following['received_ns'] - current['CLI_received_ns']
                 for current, following in zip(attempts,attempts[1:])
                 if type(current['CLI_received_ns']) is int and type(following['received_ns']) is int]
    return {'label':label,'status':public.get('status','unconfirmed'),'freeze':result.get('freeze_sha256'),
            'reported_models':result.get('model_consumers'),'public_final_available':(slot/'consumer/PUBLIC_FINAL.txt').is_file(),
            'closure_verified':(result.get('closure_verification') or {}).get('passed'),
            'source_verified':(result.get('independent_before_after') or {}).get('passed'),
            'prompt_sha256':consumer.get('input_sha256'),'consumer_completed':consumer.get('valid_completion'),
            'configuration':read(slot/'consumer/ACTUAL_CONFIGURATION.json'),
            'public_usage':usage(slot/'consumer',consumer),'budget':result.get('budget'),
            'bridge':db,'product_mcp':mcp,'native_TCP':sockets,
            'totals':{'bridge_TX':sum(x['TX']['bytes'] for x in attempts),
                      'bridge_RX':sum(x['RX']['bytes'] for x in attempts if x['RX']),
                      'product_TX':sum(x['TX_bytes'] or 0 for x in mcp),
                      'product_RX':sum(x['RX_bytes'] or 0 for x in mcp),
                      'product_body':sum(x['body_bytes'] for x in mcp),
                      'actual_host_duplex':sum(x['duplex_bytes'] for x in sockets),
                      'production_TCP_duplex':sum(x['duplex_bytes'] for x in sockets if 'production_command' in x)},
            'clock_ns':{
                'whole_slot':elapsed(result.get('started_ns'),public.get('published_ns')),
                'start_to_ready':elapsed(result.get('started_ns'),result.get('ready_ns')),
                'ready_to_prompt':elapsed(result.get('ready_ns'),prompt),
                'prompt_to_first_attempt':elapsed(prompt,attempts[0]['received_ns'] if attempts else None),
                'prompt_to_final':elapsed(prompt,final),
                'last_bound_tool_to_final':elapsed(max(arrived) if arrived else None,final),
                'final_to_published':elapsed(final,public.get('published_ns')),
                'cleanup_to_published':elapsed(result.get('cleanup_started_ns'),public.get('published_ns')),
                'between_tool_gaps':tool_gaps,
                'frontend_roundtrip_sum':sum(row['frontend_roundtrip_ns'] or 0 for row in attempts),
                'product_roundtrip_sum':sum(row['roundtrip_ns'] or 0 for row in mcp),
            }}


def main():
    arms={label:summarize(label) for label in ('A1','B1')}
    prompt_sha=pin(HERE/'inputs/PROMPT.txt')['sha256']
    matching=all(arm['prompt_sha256']==prompt_sha for arm in arms.values() if arm.get('reported_models'))
    result={'arms':arms,'observed_original_same_prompt':matching,'prompt_sha256':prompt_sha,
            'scope':'actual public CLI and protocol intervals; provider hidden timing and billing unobserved'}
    assert matching
    path=RUN/'COSTS.json'
    with path.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(result,stream,indent=2,ensure_ascii=False,allow_nan=False)
        stream.write('\n')
    print(pin(path))


if __name__ == '__main__':
    main()
