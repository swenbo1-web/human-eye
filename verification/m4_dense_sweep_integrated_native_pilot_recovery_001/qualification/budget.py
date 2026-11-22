"""Reconcile original qualification raster work with owned claims and actual wire bytes."""

import base64
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re


QUALIFIERS = ('QN', 'QP')
EXPECTED = {'QN': (2, 6), 'QP': (3, 4)}
LIMITS = {'Blender_start_attempts': 4, 'all_rasters': 48, 'consumer_tasks': 2,
          'rasters_by_slot': dict.fromkeys(('QN', 'QP', 'N1', 'P1'), 12), 'tools_per_slot': 12}
RENDER_EVENTS = {'active_observation_render_attempt', 'source_region_render_attempt'}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(data):
    return sha256(data).hexdigest()


class Original:
    def __init__(self, root, read_bytes):
        self.root = Path(root).resolve(strict=True)
        self.read_bytes = read_bytes
        self.pins = {}

    def bytes(self, path):
        path = Path(path).resolve(strict=True)
        require(path.is_relative_to(self.root), 'original_budget_artifact_outside_owner_root')
        raw = self.read_bytes(path)
        self.pins[path] = {'path': str(path), 'sha256': digest(raw), 'bytes': len(raw)}
        return raw

    def read(self, path):
        return json.loads(self.bytes(path))

    def lines(self, path):
        return [json.loads(row) for row in self.bytes(path).splitlines() if row]


def raw_rpc(source, root, receipt, request, response):
    require(type(receipt['index']) is int and receipt['index'] > 0 and receipt['error'] is None,
            'original_raster_rpc_receipt_not_successful')
    folder = root / f'rpc_{receipt["index"]:02d}'
    tx, rx = (source.bytes(folder / item) for item in ('TX.bin', 'RX.bin'))
    require(source.read(folder / 'RECEIPT.json') == receipt and len(tx) == receipt['TX_bytes']
            and len(rx) == receipt['RX_bytes'] and digest(rx) == receipt['RX_sha256']
            and json.loads(tx) == request and json.loads(rx) == response, 'original_raster_rpc_bytes_detached')
    return tx, rx


def original_public(source, slot, diagnostic):
    number = diagnostic['index']
    folder = slot / 'client' / f'call_{number:02d}'
    raw_tx, raw_rx = (source.bytes(folder / f'{name}.json') for name in ('REQUEST', 'RESPONSE'))
    request, response = json.loads(raw_tx), json.loads(raw_rx)
    receipt = source.read(folder / 'RECEIPT.json')
    require(diagnostic['request_sha256'] == digest(raw_tx) and diagnostic['response_sha256'] == digest(raw_rx)
            and request['id'] == response['id'] == f'qualification-{number}'
            and diagnostic['name'] == request['params']['name'] and response['result']['isError'] is False,
            'original_raster_public_call_detached')
    _, rx = raw_rpc(source, slot / 'client/transport', receipt, request, response)
    owner = slot / 'owner' / f'tool_{number:02d}'
    require(source.read(owner / 'REQUEST.json') == request and source.read(owner / 'RESPONSE.json') == response
            and source.read(owner / 'RECEIPT.json')['RPC_id'] == request['id'], 'original_raster_owner_call_detached')
    return request, response, digest(rx)


def raster_clock(stage, claim, settlement, deadline, *, reserve_before_construction):
    begin, end = stage['started_ns'], stage['closed_ns']
    require(all(type(value) is int for value in (begin, end, stage['elapsed_ns']))
            and end - begin == stage['elapsed_ns'] > 0
            and claim['claimed_ns'] <= begin < end <= deadline, 'original_raster_clock_outside_admission')
    if reserve_before_construction:
        require(settlement['settled_ns'] <= begin, 'product_raster_started_before_admission')
    else:
        require(end <= settlement['settled_ns'], 'native_raster_settled_before_return')


def prove_native(source, slot, result, records):
    device = source.read(slot / 'DEVICE_EVIDENCE.json')
    events = [row for row in device['events'] if row['event'] == 'native_raster_attempt']
    frames = device['frames']
    require(device['label'] == slot.name and device['group'] == 'N'
            and [event['ordinal'] for event in events] == [1, 2]
            and all(row['origin'] == 'common_native' for row in frames)
            and len(frames) == len(events) == len(records) == 2
            and len({row['ref'] for row in frames}) == 2, 'native_raster_ordinal_or_owner_roster_invalid')
    proof = []
    for event, frame, record, call in zip(events, frames, records, result['diagnostic_calls'][3:5], strict=True):
        claim, settlement = record['claim'], record['settlement']
        evidence = settlement['evidence']
        require(settlement['outcome'] == event['status'] == 'raster_returned'
                and set(evidence) == {'runtime', 'ordinal', 'origin', 'view', 'started_ns', 'closed_ns', 'elapsed_ns'}
                and all(event[key] == value for key, value in evidence.items())
                and Path(event['runtime']).resolve() == slot, 'native_raster_charge_owner_or_event_detached')
        stage = frame['stages']['actual_raster']
        raster_clock(stage, claim, settlement, result['task_deadline_ns'], reserve_before_construction=False)
        require(all(event[key] == stage[key] for key in ('started_ns', 'closed_ns', 'elapsed_ns'))
                and call['started_ns'] <= claim['claimed_ns'] < settlement['settled_ns'] <= call['returned_ns'],
                'native_raster_frame_or_call_clock_detached')
        request, response, rx_sha = original_public(source, slot, call)
        contents = response['result']['content']
        exposed = json.loads(contents[0]['text'])['frame']
        png = Path(frame['PNG']).resolve(strict=True)
        require(png.is_relative_to(slot / 'native_frames') and png.parent.name == f'{event["ordinal"]:03d}'
                and frame['view_name'] == request['params']['arguments']['direction']
                and all(exposed[key] == frame[key] for key in ('ref', 'frame_identity', 'scope_id', 'view_name')),
                'native_raster_frame_changed_in_public_reply')
        raw = source.bytes(png)
        delivered = [base64.b64decode(row['data'], validate=True) for row in contents if row['type'] == 'image']
        require(delivered == [raw] and len(raw) == frame['PNG_bytes'] and digest(raw) == frame['PNG_sha256'],
                'native_raster_reread_png_wire_detached')
        proof.append({'ordinal': event['ordinal'], 'claim_token': claim['token'], 'frame_ref': frame['ref'],
                      'public_reply_sha256': rx_sha, 'png_sha256': digest(raw)})
    return proof


def product_call(source, slot, result, diagnostic, meter, entry):
    index = entry['index']
    folder = slot / 'product_calls' / f'call_{index:03d}'
    request, response, receipt = (source.read(folder / name) for name in ('REQUEST.json', 'RESPONSE.json', 'RECEIPT.json'))
    tx, rx = raw_rpc(source, slot / 'mcp', receipt, request, response)
    rx_lf = rx.replace(b'\r\n', b'\n')
    public_request, public_response, _ = original_public(source, slot, diagnostic)
    require((receipt['index'], request['id'], response['id'], meter['response_id'])
            == (meter['sequence'], meter['id'], meter['id'], meter['id'])
            and diagnostic['started_ns'] <= receipt['started_ns'] <= meter['request_received_ns']
            <= entry['started_ns'] <= entry['producer_returned_ns'] <= entry['saved_ns']
            <= meter['reply_completed_ns'] <= receipt['received_complete_ns'] <= diagnostic['returned_ns']
            <= result['task_deadline_ns'] and public_request['params'] == request['params']
            and public_response['result'] == response['result'] and digest(tx) == meter['TX_sha256']
            and len(tx) == meter['TX_bytes'] and digest(rx_lf) == meter['RX_text_UTF8_LF_sha256']
            and len(rx_lf) == meter['RX_text_UTF8_LF_bytes'], 'product_raster_attempt_rpc_or_producer_clock_detached')
    producer_path = slot / 'product_full' / f'call_{index:03d}/SERVICE_RESULT.json'
    raw = source.bytes(producer_path)
    require(Path(entry['path']).resolve() == producer_path and entry['sha256'] == digest(raw)
            and entry['new_observations_for_archive'] == 0, 'product_raster_producer_original_bytes_detached')
    before, after = (source.bytes(folder / name) for name in ('ARCHIVE_BEFORE.bin', 'ARCHIVE_AFTER.bin'))
    require(after.startswith(before) and [json.loads(row) for row in after[len(before):].splitlines()] == [entry],
            'product_raster_producer_archive_delta_detached')
    return json.loads(raw)


def prove_product(source, slot, result, close, records):
    audit_path = slot / 'product_audit.jsonl'
    audit = source.bytes(audit_path)
    attempts, rows = [], []
    offset = 0
    for raw in audit.splitlines(keepends=True):
        row = json.loads(raw)
        if row['event'] in RENDER_EVENTS:
            attempts.append((offset, len(raw), digest(raw), row))
        rows.append(row)
        offset += len(raw)
    meters = [row for row in source.lines(slot / 'mcp_io/MCP_IO.jsonl') if row['method'] == 'tools/call']
    entries = source.lines(slot / 'product_full/INDEX.jsonl')
    require([row['raster_actual'] for row in meters] == [3, 0] and [row['index'] for row in entries] == [1, 2],
            'product_raster_attempt_meter_or_producer_roster_invalid')
    discovery, measurement = (product_call(source, slot, result, diagnostic, meter, entry)
                              for diagnostic, meter, entry in zip(result['diagnostic_calls'][1::2],
                                                                  meters, entries, strict=True))
    frames = discovery['constructed_frames']
    require(len(frames) == len(records) == len(attempts) == 3
            and len({row['frame_identity'] for row in frames}) == len({row['scope_id'] for row in frames}) == 3
            and discovery['work']['raster_attempts'] == discovery['work']['raster_completed'] == 3
            and not measurement.get('constructed_frames') and measurement['work']['raster_attempts'] == 0
            and measurement['work']['raster_completed'] == 0, 'product_raster_producer_attempt_roster_invalid')
    trace, = [row for row in rows if row['event'] == 'request_trace'
              and row['trace']['annotations'].get('mcp_request_id') == meters[0]['id']]
    binding_digest = attempts[0][3]['binding_digest']
    require(type(binding_digest) is str and re.fullmatch(r'[0-9a-f]{64}', binding_digest),
            'product_raster_request_binding_digest_invalid')
    proof = []
    for ordinal, (record, indexed, frame) in enumerate(zip(records, attempts, frames, strict=True), 1):
        claim, settlement = record['claim'], record['settlement']
        evidence = settlement['evidence']
        start, count, hashed, event = indexed
        require(Path(evidence['audit_path']).resolve() == audit_path
                and (evidence['tail_start_bytes'], evidence['tail_bytes'], evidence['tail_sha256']) == (start, count, hashed)
                and evidence['event'] == event['event'] == 'active_observation_render_attempt'
                and settlement['outcome'] == 'producer_attempt_admitted', 'product_raster_audit_slice_wrong_or_repeated')
        require(event['attempt'] == ordinal and event['view_name'] == frame['view_name']
                and event['session_id'] == discovery['session_id']
                and event['binding_digest'] == binding_digest
                and event['runtime_identity']['build_id'] == 'sha256:' + result['product_source_sha256']
                and event['pid'] == trace['pid'] == close['public_MCP_close']['pid']
                and all(event[key] == trace[key] == discovery['request_trace'][key] for key in ('request_id', 'trace_id'))
                and meters[0]['audit_start_bytes'] <= start < start + count <= meters[1]['audit_start_bytes']
                and entries[0]['started_ns'] <= claim['claimed_ns'], 'product_raster_producer_attempt_or_request_detached')
        raster_clock(frame['stages']['actual_raster'], claim, settlement, entries[0]['producer_returned_ns'],
                     reserve_before_construction=True)
        proof.append({'ordinal': ordinal, 'claim_token': claim['token'], 'scope_id': frame['scope_id'],
                      'frame_identity': frame['frame_identity'], 'audit_offset': start, 'audit_sha256': hashed,
                      'producer_request_id': event['request_id'], 'wire_request_id': meters[0]['id']})
    return proof


def original_close(source, slot, result, publication):
    close = source.read(slot / 'RUNTIME_CLOSE.json')
    end, native = close['Blender_exit'], close['Blender_close']
    require(result['closure_verification']['passed'] is True and result['owner_close']['confirmed'] is True
            and result['independent_before_after']['passed'] is True and publication['owned_budget_passed'] is True
            and result['status'] == publication['status'] == 'completed' and not close['errors']
            and publication['started_ns'] == result['started_ns']
            and publication['published_ns'] - publication['started_ns'] == publication['complete_slot_ns']
            and native['process_reaped'] is True and end['confirmed'] is True
            and end['exited'] is True and end['handle_closed'] is True
            and native['exit_code'] == end['exit_code'] == 0
            and result['cleanup_started_ns'] <= end['observed_ns'] <= close['closed_ns']
            <= result['closed_ns'] <= publication['published_ns'] < result['owned_deadline_ns']
            and result['task_deadline_ns'] - result['started_ns'] == 450_000_000_000
            and result['owned_deadline_ns'] - result['started_ns'] == 600_000_000_000
            and native['original_deadline_ns'] == result['owned_deadline_ns'],
            'original_close_or_published_timing_invalid')
    if slot.name == 'QP':
        held = source.read(slot / 'mcp/HELD_CLOSE.json')
        exit_receipt = close['public_MCP_exit']
        eof_path, exit_path = (slot / 'mcp_io' / name for name in ('EOF.json', 'WORKER_EXIT.json'))
        eof, worker_exit = (source.bytes(path) for path in (eof_path, exit_path))
        eof_record, worker_record = (json.loads(raw) for raw in (eof, worker_exit))
        require(held == close['public_MCP_close'] and held['confirmed'] and held['production_eof_and_exit_verified']
                and held['stdout_eof_seen'] and held['process_handle_closed'] and exit_receipt['handle_closed']
                and exit_receipt['confirmed'] is True and exit_receipt['exited'] is True
                and held['exit_code'] == exit_receipt['exit_code'] == 0
                and held['closed_ns'] <= exit_receipt['observed_ns'] <= close['closed_ns']
                and Path(held['worker_eof']['path']).resolve() == eof_path
                and Path(held['worker_exit']['path']).resolve() == exit_path
                and digest(eof) == held['worker_eof']['sha256'] and digest(worker_exit) == held['worker_exit']['sha256']
                and eof_record['pid'] == worker_record['pid'] == held['pid']
                and eof_record['source_sha256'] == worker_record['source_sha256'] == result['product_source_sha256']
                and eof_record['input_eof_observed'] is True and eof_record['observe_calls'] == 2
                and worker_record['production_returned'] is True and worker_record['production_return_code'] == 0
                and eof_record['input_eof_ns'] <= eof_record['closed_ns'] <= worker_record['closed_ns']
                <= held['stdout_eof_observed_ns'] <= held['closed_ns'],
                'original_production_mcp_close_eof_or_exit_invalid')
    else:
        require(close.get('public_MCP_close') is None, 'native_arm_unexpected_product_worker')
    return close


def original_records(source, ledger, results, closures):
    records, settled = {}, set()
    for path in sorted((ledger / 'claims').glob('*.json')):
        raw = source.bytes(path)
        claim = json.loads(raw)
        token, label, kind = claim['token'], claim['label'], claim['kind']
        require(type(token) is str and re.fullmatch(r'[0-9a-f]{32}', token) and token == path.stem and token not in records,
                'original_claim_token_duplicate_or_detached')
        require(label in QUALIFIERS and claim['phase'] == 'qualification'
                and kind in ('Blender_start', 'business_tool', 'raster_attempt'),
                'original_claim_cross_slot_phase_or_formal_escape')
        result = results[label]
        earliest, latest = ((result['started_ns'], result['ready_ns']) if kind == 'Blender_start'
                            else (result['ready_ns'], result['cleanup_started_ns']))
        require(type(claim['reserved_upper_bound']) is int and claim['reserved_upper_bound'] == 1
                and type(claim['claimed_ns']) is int
                and earliest <= claim['claimed_ns'] < min(latest, result['task_deadline_ns']),
                'original_claim_over_limit_or_outside_slot')
        settlement_path = ledger / 'settlements' / path.name
        settlement = None
        if kind != 'business_tool':
            settlement = source.read(settlement_path)
            settled.add(settlement_path.name)
            require(settlement['token'] == token and settlement['claim_sha256'] == digest(raw)
                    and type(settlement['settled_ns']) is int
                    and claim['claimed_ns'] <= settlement['settled_ns'] < result['closed_ns'],
                    'original_settlement_token_digest_or_clock_invalid')
            if kind == 'raster_attempt':
                require(settlement['settled_ns'] < result['task_deadline_ns']
                        and type(settlement['actual_attempts']) is int and settlement['actual_attempts'] == 1
                        and type(settlement['confirmed_attempts_lower_bound']) is int
                        and settlement['confirmed_attempts_lower_bound'] == 1
                        and type(settlement['released_proven_unconstructed_reservation']) is int
                        and settlement['released_proven_unconstructed_reservation'] == 0,
                        'original_raster_reservation_unsettled_over_cap_or_unconfirmed')
            else:
                require(settlement['outcome'] == 'completed' and settlement['spawn_status'] == 'spawned'
                        and settlement['pid'] == closures[label]['Blender_close']['pid'],
                        'original_blender_reservation_unconfirmed_or_cross_slot')
        records[token] = {'claim': claim, 'settlement': settlement}
    require({path.name for path in (ledger / 'settlements').glob('*.json')} == settled,
            'original_settlement_roster_extra_or_unbound')
    return records


def verify(old_root, *, read_bytes=Path.read_bytes):
    """Derive original slot charges and independently verify historical cumulative counts."""
    source = Original(old_root, read_bytes)
    ledger = source.root / 'budget'
    require(source.read(ledger / 'LIMITS.json') == LIMITS, 'original_budget_limit_contract_changed')
    results, closures = {}, {}
    for label in QUALIFIERS:
        slot = source.root / 'slots' / label
        raw = source.bytes(slot / 'SLOT_RESULT.json')
        result = results[label] = json.loads(raw)
        publication = source.read(slot / 'SLOT_PUBLICATION.json')
        require(result['label'] == publication['label'] == label and result['phase'] == 'qualification'
                and publication['result_sha256'] == digest(raw)
                and result['model_consumers'] == result['paid_API_calls'] == 0,
                'original_qualification_publication_binding_changed')
        closures[label] = original_close(source, slot, result, publication)
    records = original_records(source, ledger, results, closures)
    by_slot, summary, cumulative = {}, {}, 0
    for index, label in enumerate(QUALIFIERS, 1):
        result = results[label]
        slot = source.root / 'slots' / label
        owned = sorted((row for row in records.values() if row['claim']['label'] == label),
                       key=lambda row: row['claim']['claimed_ns'])
        counts = Counter(row['claim']['kind'] for row in owned)
        rasters_expected, calls_expected = EXPECTED[label]
        require(counts == {'Blender_start': 1, 'business_tool': calls_expected, 'raster_attempt': rasters_expected}
                and counts['raster_attempt'] <= LIMITS['rasters_by_slot'][label]
                and counts['business_tool'] <= LIMITS['tools_per_slot'], 'original_slot_claim_roster_or_budget_changed')
        business = [row['claim']['claimed_ns'] for row in owned if row['claim']['kind'] == 'business_tool']
        require(all(row['started_ns'] <= stamp <= row['returned_ns'] <= result['task_deadline_ns']
                    for row, stamp in zip(result['diagnostic_calls'], business, strict=True)),
                'original_business_admissions_detached')
        rasters = [row for row in owned if row['claim']['kind'] == 'raster_attempt']
        proof = (prove_native(source, slot, result, rasters) if label == 'QN'
                 else prove_product(source, slot, result, closures[label], rasters))
        local_actual = sum(row['settlement']['actual_attempts'] for row in rasters)
        cumulative += local_actual
        summary[label] = {'business_admissions': len(business), 'raster_actual': local_actual,
                          'raster_upper': counts['raster_attempt']}
        snapshot = result['budget']
        expected = [records[token] for token in sorted(records) if records[token]['claim']['label'] in summary]
        require(snapshot['records'] == expected and snapshot['limits'] == LIMITS
                and snapshot['slots'] == summary and snapshot['slots'][label]['raster_actual'] == local_actual,
                'original_slot_budget_snapshot_and_raw_settlements_disagree')
        require(snapshot['counts'] == {
            'Blender_spawned_confirmed': index, 'Blender_spawned_unknown': 0, 'Blender_start_attempts': index,
            'business_admissions': sum(row['business_admissions'] for row in summary.values()),
            'consumer_admissions': 0, 'formal_raster_actual': 0, 'formal_raster_upper': 0,
            'pending_raster_reservations': 0, 'all_raster_actual': cumulative, 'all_raster_upper': cumulative,
            'qualification_raster_actual': cumulative, 'qualification_raster_upper': cumulative,
        } and cumulative <= LIMITS['all_rasters'], 'original_cumulative_budget_or_pending_count_disagrees')
        by_slot[label] = {**summary[label], 'cumulative_raster_actual': cumulative, 'evidence': proof}
    return {'passed': True, 'by_slot': by_slot,
            'historical_total': {'blender': 2, 'rasters': cumulative, 'business': 10, 'models': 0},
            'source_pins': [source.pins[path] for path in sorted(source.pins)]}
