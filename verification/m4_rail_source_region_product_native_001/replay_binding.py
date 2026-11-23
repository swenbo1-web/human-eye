"""Derive the scoring ledger from archived offline public events and actual replay traffic."""

from pathlib import Path
from runpy import run_path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from replay import HERE, LABELS, PRE, PRIOR, ROOT, V, host, pin, read, require, save


BASE = run_path(str(V / 'm4_source_region_score_admission_001/score.py'))
CONTRACT = V / 'm1_source_region_facts_first_001/harness/reused/result_contract.py'
PUBLIC_READER = V / 'm4_source_region_score_admission_001/score.py'
BIND = run_path(str(CONTRACT))['bind_tool_result']
CLI_VERIFY = run_path(str(PRIOR / 'product_preflight.py'))['verify_cli_evidence']


def attachments(slot):
    """Return real thin attachment requests and replies in their receipt order."""
    by_id = {}
    for tx in sorted((slot / 'attachments').glob('bridge_*/*/TX.bin')):
        request = read(tx)
        if request['method'] != 'tools/call':
            continue
        receipt = read(tx.with_name('RECEIPT.json'))
        rx = tx.with_name('RX.bin')
        require(receipt['origin'] == 'owner' and receipt['owner_TCP_attempted'] is True
                and receipt['flush_completed_ns'] is not None and receipt['RPC_id'] == request['id']
                and request['id'] not in by_id, 'offline_thin_attachment_receipt_changed')
        by_id[request['id']] = (tx, rx, receipt['attempt'])
    return by_id


def binding(slot):
    consumer = slot / 'consumer'
    require(read(slot / 'OFFLINE_FIXTURE.json')['offline_fixture'] is True, 'offline_fixture_marker_required')
    events = {event['item']['id']:event['item'] for event in
              BASE['public_events'](consumer / 'events.jsonl')
              if event['type']=='item.completed' and event['item']['type']=='mcp_tool_call'}
    calls = BASE['ASSEMBLY'].QUALIFY.actual_calls(slot)
    mirror = attachments(slot)
    contracts = []
    for tx in sorted((slot / 'client_wire').glob('rpc_*/TX.bin')):
        request = read(tx)
        if request['method'] != 'tools/call':
            continue
        event = events.pop(request['id'])
        main = read(tx.with_name('RECEIPT.json'))
        rx = tx.with_name('RX.bin')
        a_tx,a_rx,attempt = mirror.pop(request['id'])
        call = calls[len(contracts)]
        response = read(rx)
        original_tx,original_rx = pin(tx),pin(rx)
        require(main['error'] is None and main['id'] == request['id']
                and main['TX_bytes'] == original_tx['bytes'] and main['RX_bytes'] == original_rx['bytes']
                and main['RX_sha256'] == original_rx['sha256']
                and tx.read_bytes() == a_tx.read_bytes() and rx.read_bytes() == a_rx.read_bytes(),
                'actual_offline_thin_original_wire_changed')
        require(request == call['request'] and response == call['reply']
                and attempt == call['attempt'] == len(contracts)+1
                and event['server'] == 'arm_engine' and event['tool'] == call['name']
                and event['arguments'] == request['params']['arguments'] and event['result'] == response['result'],
                'offline_public_event_differs_from_real_thin_and_owner')
        # The replay transcript records an actual MCP envelope; supply its
        # synthetic event status only to the shared body-and-envelope checker.
        status = 'failed' if response['result']['isError'] else 'completed'
        contract = BIND(response, {**event,'status':status})
        require(contract['matched'], 'shared_result_contract_rejected_offline_tool')
        contracts.append({**contract,'attempt':attempt,'tool':call['name'],
            'CLI_text_UTF8_bytes':sum(len(block['text'].encode('utf8')) for block in event['result']['content']
                                      if block['type']=='text'),
            'public_event_id':event['id'],'thin_TX':original_tx,'thin_RX':original_rx,
            'attachment_TX':pin(a_tx),'attachment_RX':pin(a_rx),'owner_TX':call['TX'],'owner_RX':call['RX']})
    require(not mirror and not events and len(contracts)==len(calls),'offline_tool_and_event_roster_changed')
    target = consumer / 'BUSINESS_SOURCE_BINDING.json'
    save(target,{'passed':True,'offline_fixture':True,'actual_models':0,'result_contracts':contracts,
                 'public_events':pin(consumer/'events.jsonl'),'raw_stdout_digest_only':pin(consumer/'stdout.raw.bin')})
    return pin(target), len(contracts)


def main():
    require(sys.flags.isolated and sys.dont_write_bytecode and host.sha(sys.executable)==host.PYTHON_SHA,
            'fixed_python_required')
    result = {label:binding(ROOT/'slots'/label) for label in LABELS}
    compact = {}
    for number,name in ((2,'M19'),(3,'M21')):
        path = ROOT/'slots/P1/product_calls'/f'call_{number:03d}'/'RESPONSE.json'
        raw = read(path)
        packet = raw['result']['content'][0]['text']
        verified = CLI_VERIFY(raw,True)
        require(verified['passed'] and len(verified['stages']) == 6
                and all(row['original_images_exact'] for row in verified['stages']),
                'fixed_offline_product_CLI_delivery_failed/' + name)
        compact[name] = {'body_UTF8_bytes':len(packet.encode('utf8')),'response':pin(path),'fixed_CLI':verified}
    save(PRE/'REPLAY_BINDING.json',{'passed':True,'offline_fixture':True,'actual_models':0,
         'by_slot':result,'product_fixed_cli':compact,
         'source_pins':[pin(p) for p in (HERE/'replay.py',Path(__file__),PUBLIC_READER,CONTRACT,
                                      PRIOR/'product_preflight.py')]})
    print(PRE/'REPLAY_BINDING.json',flush=True)


if __name__=='__main__':
    main()
