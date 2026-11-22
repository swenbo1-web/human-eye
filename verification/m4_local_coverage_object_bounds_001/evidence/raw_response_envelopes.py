"""Derive clock partitions from the already closed worker and stock-client lines."""
from hashlib import sha256
import json
from pathlib import Path
import sys


def receipt(path, raw=None):
    raw = path.read_bytes() if raw is None else raw
    return {'path':str(path.resolve()),'bytes':len(raw),'sha256':sha256(raw).hexdigest()}


def read(path):
    return json.loads(path.read_bytes())


def require(valid, name):
    if not valid:
        raise ValueError(name)


def arm(root, label, score):
    location = root/'arms'/label
    snapshot = location/'SUMMARY.json'
    stock = location/'mcp_io/MCP_IO.jsonl'
    summary = read(snapshot)
    require(receipt(snapshot)==score['arms'][label]['formal_summary'],'summary_not_scored/'+label)
    trace = [json.loads(line) for line in stock.read_bytes().splitlines()]
    worker_calls = [row for row in trace if row['method']=='tools/call']
    require(len(worker_calls)==len(summary['requests'])==3,'request_count_mismatch/'+label)
    measurements = {}
    for phase,row,worker in zip(('cold','warm','noimage'),summary['requests'],worker_calls,strict=True):
        client = row['wire']
        wire = location/'mcp'/f"rpc_{client['index']:02}"
        rx,tx = wire/'RX.bin',wire/'TX.bin'
        raw,incoming = rx.read_bytes(),tx.read_bytes()
        utf8lf = raw.replace(b'\r\n',b'\n')
        require(client==read(wire/'RECEIPT.json')
                and client['index']==worker['sequence']
                and client['id']==worker['id']==worker['response_id']==json.loads(raw)['id']==json.loads(incoming)['id']
                and (client['RX_bytes'],client['RX_sha256'])==(len(raw),sha256(raw).hexdigest())
                and (worker['RX_text_UTF8_LF_bytes'],worker['RX_text_UTF8_LF_sha256'])==(len(utf8lf),sha256(utf8lf).hexdigest())
                and worker['TX_bytes']==client['TX_bytes']==len(incoming)
                and worker['TX_sha256']==sha256(incoming).hexdigest()
                and worker['raster_actual']==row['raster_attempts'],'same_transaction_wire_binding_failed/'+label+'/'+phase)
        service = row['stages']['service_total']
        start,after_write = client['started_ns'],client['stdin_flushed_ns']
        received,flush = worker['request_received_ns'],worker['reply_completed_ns']
        got,decoded,closed = (client[k] for k in ('received_complete_ns','consumer_json_decoded_ns','closed_ns'))
        enter,exit = service['started_ns'],service['closed_ns']
        require(start<=after_write and received<=enter<=exit<=flush and got<=decoded<=closed
                and worker['request_to_reply_ns']==flush-received
                and service['elapsed_ns']==exit-enter
                and client['elapsed_ns']==closed-start,'raw_clock_interval_inconsistent/'+label+'/'+phase)
        by_stage = {'client_request_write_and_flush':after_write-start,
                    'client_flush_to_worker_received_signed':received-after_write,
                    'worker_before_service':enter-received,'product_service':exit-enter,
                    'worker_service_end_to_stdout_flush':flush-exit,
                    'worker_stdout_flush_to_client_read_signed':got-flush,
                    'client_JSON_decode':decoded-got,'client_tail':closed-decoded}
        require(sum(by_stage.values())==client['elapsed_ns'],'clock_partition_did_not_close/'+label+'/'+phase)
        measurements[phase] = {'request_id':client['id'],'partition_ns':by_stage,
            'worker_envelope_ns':worker['request_to_reply_ns'],'client_RPC_ns':client['elapsed_ns'],
            'wire_TX':receipt(tx,incoming),'wire_RX':receipt(rx,raw)}
    return {'worker_trace':receipt(stock),'summary':receipt(snapshot),'transactions':measurements}


def main(root, output):
    scorer = root/'REPLAY_SCORE.json'
    score = read(scorer)
    require(score['passed'] and score['quality_passed'],'original_score_did_not_pass')
    raw = {label:arm(root,label,score) for label in ('N1','P1','N2','P2','N3','P3','HN','HP')}
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump({'passed':True,'matched_actual_transactions':24,
                   'scope':'actual held worker + stock client online timestamps, reading archived transactions only',
                   'service_end_to_flush_includes':'result archive, public projection/encoding, and output write/flush; separate JSON-serialization clock unavailable',
                   'signed_intervals':'in-process flush/reader boundaries may overlap across processes; magnitudes do not measure provider inference',
                   'reproduction':['D:/he_anchor_001/venv/Scripts/python.exe','-IB','-X','utf8',str(Path(__file__).resolve()),
                                   str(root),str(output)],
                   'input_score':receipt(scorer),'analysis_source':receipt(Path(__file__)),
                   'arms':raw},stream,indent=2,sort_keys=True)
        stream.write('\n')
    for label,record in raw.items():
        stage = record['transactions']['cold']
        timing = stage['partition_ns']
        fields = [stage['client_RPC_ns'],stage['worker_envelope_ns'],timing['product_service'],
                  timing['worker_service_end_to_stdout_flush'],timing['client_JSON_decode']]
        print(label, ' '.join(f'{ns/1_000_000:.3f}' for ns in fields))


if __name__=='__main__':
    main(Path(sys.argv[1]),Path(sys.argv[2]))
