"""Recompute the fixed engineering gates from original formal receipts."""

from fractions import Fraction
import hashlib
import json
from pathlib import Path
import statistics
import time


HERE = Path(__file__).resolve().parent
RUNTIME = Path('D:/he_m4_target_002')


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value, label):
    if not value:
        raise AssertionError(label)


def main():
    prereg = read(HERE / 'PREREGISTRATION.json')
    formal = read(RUNTIME / 'formal/RESULT.json')
    quality_path = HERE / 'FORMAL_QUALITY.json'
    quality = read(quality_path)
    quality_passed = quality.get('passed_checked_scope', quality.get('passed')) is True
    schedule = prereg['formal_schedule']
    require(len(schedule) == 12 and len({row['label'] for row in schedule}) == 12, 'twelve unique slots')
    result_labels = [row['label'] for row in formal['results']]
    require(len(result_labels) == len(set(result_labels))
            and set(result_labels) <= {row['label'] for row in schedule}, 'unique bound result rows')
    require(formal['retries'] == 0 and formal['replacement_samples'] == 0, 'one formal execution')
    records = []
    pins = []
    unavailable = []
    for slot in schedule:
        folder = RUNTIME / 'formal' / slot['label']
        if not (folder / 'RESULT.json').is_file():
            unavailable.append(dict(**slot, reason='missing_or_not_dispatched'))
            continue
        result = read(folder / 'RESULT.json')
        if not result['passed'] or result['errors']:
            unavailable.append(dict(**slot, reason='failed_operational_slot', errors=result['errors']))
            pins.append(dict(path=str(folder / 'RESULT.json'), sha256=sha(folder / 'RESULT.json')))
            continue
        events = [json.loads(row) for row in (folder / 'io_audit/MCP_IO.jsonl').read_bytes().splitlines() if row.strip()]
        server_rows = [row for row in events if row.get('id') == 'target_observation']
        client_rows = [(path, read(path)) for path in (folder / 'stdio').glob('rpc_*/RECEIPT.json')]
        clients = [(path, row) for path, row in client_rows if row.get('id') == 'target_observation']
        requests = [row for row in result['requests'] if row.get('id') == 'target_observation']
        require(len(server_rows) == len(clients) == len(requests) == 1, 'one main request per slot')
        server = server_rows[0]
        client_path, client = clients[0]
        request = requests[0]
        response_path = client_path.parent / 'RX.bin'
        raw = response_path.read_bytes()
        require(len(raw) == client['RX_bytes'] and hashlib.sha256(raw).hexdigest() == client['RX_sha256'], 'original wire bytes')
        decoded = json.loads(raw)
        text = [row['text'] for row in decoded['result']['content'] if row['type'] == 'text']
        require(len(text) == 1, 'one public text')
        public = json.loads(text[0])
        server_ns = server['reply_completed_ns'] - server['request_received_ns']
        transport_ns = client['received_complete_ns'] - client['stdin_flushed_ns']
        complete_call_ns = request['client_call_completed_ns'] - request['client_call_started_ns']
        require(server_ns == server['request_to_reply_ns'] == request['server_request_to_reply_ns'], 'server interval')
        require(transport_ns == request['client_flush_to_received_ns'], 'transport interval')
        require(complete_call_ns == request['client_outer_including_recording_ns'], 'outer complete call interval')
        work = public['work']['target_acquisition']
        records.append(dict(**slot, server_ns=server_ns, client_transport_ns=transport_ns,
             complete_client_call_ns=complete_call_ns, complete_session_ns=result['complete_session_ns'],
             postrun_validation_ns=result['postrun_validation_ns'], raw_MCP_reply_bytes=len(raw),
             public_text_UTF8_bytes=len(text[0].encode('utf-8')),
             image_blocks=sum(row['type'] == 'image' for row in decoded['result']['content']),
             acquisition=work, host_wire_index=result['host_wire_index']))
        for path in (folder / 'RESULT.json', folder / 'io_audit/MCP_IO.jsonl', client_path, response_path):
            pins.append(dict(path=str(path), sha256=sha(path)))
    gates = {}
    for asset in ('main', 'target_only'):
        rows = {(row['variant'], row['pair']): row for row in records if row['input'] == asset}
        if len(rows) != 6:
            gates[asset] = dict(timing_gate_passed=False, status='not_evaluable_failed_or_missing_slots')
            continue
        paired = []
        for index in (1, 2, 3):
            a, b = rows['A', index], rows['B', index]
            business = Fraction(b['server_ns'], a['server_ns'])
            session = Fraction(b['complete_session_ns'], a['complete_session_ns'])
            paired.append(dict(pair=index, server_ratio_exact=str(business), server_ratio=float(business),
                               session_ratio_exact=str(session), session_ratio=float(session)))
        business_median = statistics.median(Fraction(row['server_ratio_exact']) for row in paired)
        session_median = statistics.median(Fraction(row['session_ratio_exact']) for row in paired)
        faster = sum(Fraction(row['server_ratio_exact']) < 1 for row in paired)
        gate_passed = business_median <= (Fraction(9, 10) if asset == 'main' else Fraction(21, 20))
        if asset == 'main':
            gate_passed = gate_passed and faster >= 2 and session_median <= 1
        gates[asset] = dict(pairs=paired, business_ratio_median=float(business_median),
             business_ratio_median_exact=str(business_median), session_ratio_median=float(session_median),
             session_ratio_median_exact=str(session_median), B_faster_pairs=faster,
             timing_gate_passed=bool(gate_passed))
    evidence = ('A_QUALIFICATION_R1.json', 'B_QUALIFICATION.json', 'LEGACY_REGRESSION.json',
                'CACHE_REVIEW.json', 'FORMAL_QUALITY.json', 'B_INSTALLED_PURE.json')
    evidence_status = {}
    for name in evidence:
        result = read(HERE / name)
        evidence_status[name] = result.get('passed_checked_scope', result.get('passed')) is True
        pins.append(dict(path=str(HERE / name), sha256=sha(HERE / name)))
    accepted = (quality_passed and all(evidence_status.values()) and not unavailable
                and all(row['timing_gate_passed'] for row in gates.values()))
    decision = dict(schema='m4-target-acquisition-002-engineering-decision-v1',
         disposition='qualified_engineering_gain_ready_for_review' if accepted else 'not_admitted_ready_for_review',
         passed_frozen_gates=accepted, quality_passed=quality_passed, gates=gates, records=records,
         evidence_status=evidence_status, failed_or_unavailable_slots=unavailable,
         formal_slots=12, formal_repetitions=1, retries=0, replacement_samples=0,
         preregistration_sha256=sha(HERE / 'PREREGISTRATION.json'),
         clarification_sha256=sha(HERE / 'MEASUREMENT_CLARIFICATION.json'),
         computed_from='Original per-slot server IO, client receipts and outer request timestamps',
         scope='Three fixed engineering pairs per input. Population tails, model quality, tokens and fees unmeasured.',
         experimental_models=0, paid_experiment_APIs=0, input_pins=pins,
         decision_source_sha256=sha(__file__), closed_ns=time.perf_counter_ns())
    with (HERE / 'DECISION.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(decision, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps(dict(disposition=decision['disposition'], gates=gates)))


if __name__ == '__main__':
    main()
