"""Read-only public counts audit. Does not import or start any run component.

Use --slots 1 2 for completed-slot metadata only; --finalize requires the outer
controller result and all eight frozen terminal slots, then writes this audit.
Answer bodies are never interpreted or copied to the audit.
"""
import argparse
import base64
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct

OUT = Path(__file__).resolve().parent
RUN = OUT.parent
ACTUAL = RUN / 'actual_01'
PLAN = json.loads((RUN / 'PLAN.json').read_bytes())
NEUTRAL = Path(PLAN['neutral_run_root'])
sha = lambda raw: hashlib.sha256(raw).hexdigest()
compact = lambda value: json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf8')


def load(path, default=None):
    return json.loads(path.read_bytes()) if path.exists() else default


def file_meta(path):
    if not path.exists():
        return dict(path=str(path), exists=False)
    raw = path.read_bytes()
    return dict(path=str(path), exists=True, bytes=len(raw), sha256=sha(raw))


def decode_meta(path):
    if not path.exists():
        return None, None
    try:
        return json.loads(path.read_bytes()), None
    except (ValueError, UnicodeError) as error:
        return None, type(error).__name__


def image_meta(response):
    blocks = (response or {}).get('result', {}).get('content', [])
    result = []
    for block in blocks:
        if block.get('type') != 'image':
            continue
        raw = block.get('data', '').encode('ascii')
        row = dict(mimeType=block.get('mimeType'), base64_bytes=len(raw))
        try:
            decoded = base64.b64decode(raw, validate=True)
            row.update(decoded_bytes=len(decoded), sha256=sha(decoded))
            if decoded.startswith(b'\x89PNG\r\n\x1a\n') and len(decoded) >= 24:
                row['width'], row['height'] = struct.unpack('>II', decoded[16:24])
        except ValueError as error:
            row['decode_error'] = type(error).__name__
        result.append(row)
    return result


def public_text_bytes(response):
    if not isinstance(response, dict):
        return None
    result = response.get('result', {})
    count = len(compact(result['tools'])) if 'tools' in result else 0
    count += sum(len(block.get('text', '').encode('utf8'))
                 for block in result.get('content', []) if block.get('type') == 'text')
    if 'error' in response:
        count += len(compact(response['error']))
    return count


def rpc_row(slot, origin, folder):
    request, tx_error = decode_meta(folder / 'TX.bin')
    response, rx_error = decode_meta(folder / 'RX.bin')
    return dict(slot=slot, origin=origin, folder=str(folder),
        request_type=request.get('type') if isinstance(request, dict) else None,
        tx=file_meta(folder / 'TX.bin'), rx=file_meta(folder / 'RX.bin'),
        tx_decode_error=tx_error, rx_decode_error=rx_error,
        response_status=response.get('status') if isinstance(response, dict) else None,
        poisoned=response.get('poisoned') if isinstance(response, dict) else None,
        meter=load(folder / 'METER.json'))


def audit_slot(ordinal):
    folder = ACTUAL / f'{ordinal:02}'
    result = load(folder / 'RESULT.json')
    if result is None:
        return dict(ordinal=ordinal, folder_exists=folder.exists(), result_missing=True)
    assert result['status'] not in ('running', 'planned'), 'do not inspect a live slot'
    consumer = load(folder / 'CONSUMER.json', {})
    budget = load(folder / 'BUDGET.json', {})
    final = file_meta(folder / 'final.txt')
    if final['exists']:
        final['CRLF_count'] = (folder / 'final.txt').read_bytes().count(b'\r\n')
        final['body_inspected_for_quality'] = False
    final['logical_final_ledger_utf8_bytes'] = sum(e.get('bytes', 0) for e in budget.get('events', [])
        if e.get('kind') == 'public_text' and e.get('label') == 'final_text')
    events = []
    for event in consumer.get('public_events', []):
        item = event.get('item', {})
        if event.get('type') in ('item.started', 'item.completed'):
            content = (item.get('result') or {}).get('content', []) if isinstance(item.get('result'), dict) else []
            events.append(dict(event=event['type'], received_ns=event.get('received_ns'),
                id=item.get('id'), kind=item.get('type'), server=item.get('server'),
                tool=item.get('tool', item.get('name')), status=item.get('status'),
                error=item.get('error'), result_present=item.get('result') is not None,
                failed_tool_text=[block.get('text', '') for block in content if block.get('type') == 'text'] if item.get('status') == 'failed' else [],
                text_result_utf8_bytes=sum(len(block.get('text', '').encode('utf8')) for block in content if block.get('type') == 'text'),
                image_blocks=sum(block.get('type') == 'image' for block in content)))
    mcp = []
    for bridge in sorted(folder.glob('bridge_*')):
        for frame in sorted(p for p in bridge.iterdir() if p.is_dir() and p.name.isdigit()):
            request, tx_error = decode_meta(frame / 'TX.bin')
            generated, generated_error = decode_meta(frame / 'GENERATED_RESPONSE.bin')
            published, rx_error = decode_meta(frame / 'RX.bin')
            row = dict(slot=ordinal, bridge=bridge.name, frame=frame.name,
                method=request.get('method') if isinstance(request, dict) else None,
                request_id=request.get('id') if isinstance(request, dict) else None,
                tool=(request.get('params') or {}).get('name') if isinstance(request, dict) else None,
                tx=file_meta(frame / 'TX.bin'), generated_rx=file_meta(frame / 'GENERATED_RESPONSE.bin'),
                published_rx=file_meta(frame / 'RX.bin'), tx_decode_error=tx_error,
                generated_decode_error=generated_error, published_decode_error=rx_error,
                generated_public_text_utf8_bytes=public_text_bytes(generated),
                published_public_text_utf8_bytes=public_text_bytes(published),
                generated_image_blocks=image_meta(generated), published_image_blocks=image_meta(published),
                isError=(published or {}).get('result', {}).get('isError'),
                meter=load(frame / 'METER.json'))
            tools = (generated or {}).get('result', {}).get('tools')
            if tools is not None:
                row['full_server_catalogue_utf8_bytes'] = len(compact(tools))
                row['descriptors'] = [dict(name=tool.get('name'), utf8_bytes=len(compact(tool))) for tool in tools]
                row['model_effective_schema_bytes'] = None
            mcp.append(row)
    physical = [rpc_row(ordinal, 'native_execute_code', path)
                for path in sorted((folder / 'bridge_native').glob('native_*')) if path.is_dir()]
    physical += [rpc_row(ordinal, 'HE_owned_socket', path)
                 for path in sorted((folder / 'he_socket').glob('[0-9]*')) if path.is_dir()]
    if (folder / 'CLOSE_TX.bin').exists():
        request, tx_error = decode_meta(folder / 'CLOSE_TX.bin')
        response, rx_error = decode_meta(folder / 'CLOSE_RX.bin')
        physical.append(dict(slot=ordinal, origin='administrative_close',
            request_type=request.get('type') if isinstance(request, dict) else None,
            tx=file_meta(folder / 'CLOSE_TX.bin'), rx=file_meta(folder / 'CLOSE_RX.bin'),
            tx_decode_error=tx_error, rx_decode_error=rx_error,
            response_status=response.get('status') if isinstance(response, dict) else None,
            meter=load(folder / 'CLOSE_METER.json')))
    worker_folder = NEUTRAL / f'{ordinal:02}' / 'native'
    worker_events = []
    events_path = worker_folder / 'WORKER_EVENTS.jsonl'
    if events_path.exists():
        for line in events_path.read_bytes().splitlines():
            if not line:
                continue
            event = json.loads(line)
            kept = {key: event[key] for key in ('sequence', 'event', 'status', 'started_ns', 'elapsed_ns',
                'render_events_before', 'render_events_after', 'stdout_bytes', 'stderr_bytes',
                'terminal_geometry_and_file_checks_passed', 'changed_or_new_PNG_files') if key in event}
            kept['script_error_present'] = event.get('script_error') is not None
            worker_events.append(kept)
    he_audit = []
    if (folder / 'he_audit.jsonl').exists():
        for line in (folder / 'he_audit.jsonl').read_bytes().splitlines():
            if not line:
                continue
            event = json.loads(line)
            he_audit.append({key: event[key] for key in ('event', 'status', 'engine_invoked', 'time_unix') if key in event})
    png_files = []
    for path in sorted((NEUTRAL / f'{ordinal:02}').rglob('*.png')):
        row = file_meta(path)
        raw = path.read_bytes()
        if raw.startswith(b'\x89PNG\r\n\x1a\n') and len(raw) >= 24:
            row['width'], row['height'] = struct.unpack('>II', raw[16:24])
        png_files.append(row)
    images = []
    for path in sorted((folder / 'image_attempts').glob('*.json')):
        image = load(path)
        images.append(dict(path=str(path), origin=image.get('origin'), generated_blocks=image.get('generated_blocks'),
            encoded_data_bytes=image.get('encoded_data_bytes'), rows=image.get('rows'),
            reservation=image.get('reservation'), error=image.get('error'), elapsed_ns=image.get('elapsed_ns')))
    clocks = {key: result.get(key) for key in ('dispatch_ns', 'host_ready_ns', 'consumer_popen_ns',
        'first_public_tool_ns', 'final_received_ns', 'turn_completed_ns', 'process_exit_ns', 'cleanup_end_ns',
        'whole_cell_ns', 'answer_receive_latency_ns')}
    clocks.update(consumer_entry_ns=consumer.get('started_ns'), consumer_cleanup_end_ns=consumer.get('cleanup_end_ns'),
        consumer_finished_ns=consumer.get('finished_ns'), consumer_wall_ns=consumer.get('wall_ns'))
    return dict(ordinal=ordinal, task_id=result.get('task_id'), arm=result.get('arm'), status=result['status'],
        reason=result.get('reason'), denominator=result.get('denominator'), safe_to_continue=result.get('safe_to_continue'),
        cleanup_verified=result.get('cleanup_verified'), valid_completion=consumer.get('valid_completion'),
        consumer_complete=consumer.get('complete'), consumer_pid=consumer.get('consumer_pid'),
        consumer_exit_code=consumer.get('exit_code'), consumer_parent_reaped=consumer.get('process_reaped'),
        tree_reaped=consumer.get('tree_reaped'), registered_tree_cleanup=consumer.get('registered_tree_cleanup'),
        public_tool_actions_observed=consumer.get('tool_actions_observed', 0),
        deadline_timer_fired=consumer.get('deadline_timer_fired'), usage=consumer.get('usage'),
        provider_requests=consumer.get('provider_requests'), fees=consumer.get('fees'), backend=consumer.get('backend'),
        discarded_event_types=consumer.get('discarded_event_types'),
        stdout_bytes=consumer.get('stdout_bytes'), stderr_bytes=consumer.get('stderr_bytes'),
        stderr_diagnostics=consumer.get('stderr_diagnostics'),
        ledger={key: value for key, value in budget.items() if key != 'events'},
        ledger_public_text_events=[event for event in budget.get('events', []) if event.get('kind') == 'public_text'],
        ledger_action_events=[event for event in budget.get('events', []) if event.get('kind') == 'actions'],
        final_artifact=final, clocks=clocks, public_tool_events=events, MCP_rows=mcp, physical_RPC_rows=physical,
        native_session=result.get('native_session'), close=result.get('close'), closed_worker=result.get('closed_worker'),
        worker_event_metadata=worker_events, he_audit_metadata=he_audit,
        PNG_files=png_files, image_attempts=images, frozen_result=file_meta(folder / 'RESULT.json'))


def finalize():
    assert (OUT / 'RESULT.json').exists(), 'outer controller has not completed'
    assert not (OUT / 'COUNTS_AUDIT.json').exists(), 'do not overwrite an existing audit'
    outer = load(OUT / 'RESULT.json')
    assert outer.get('process_reaped') is True, 'outer owner has not reaped controller'
    frozen = load(ACTUAL / 'RESULTS.json')
    assert len(frozen['cells']) == 8 and all(row['status'] not in ('planned', 'running') for row in frozen['cells'])
    protected = {str(path): sha(path.read_bytes()) for path in ACTUAL.rglob('*') if path.is_file()}
    slots = []
    for row in frozen['cells']:
        ordinal = row['ordinal']
        slots.append(audit_slot(ordinal) if (ACTUAL / f'{ordinal:02}' / 'RESULT.json').exists()
            else {key: row.get(key) for key in ('ordinal', 'task_id', 'arm', 'status', 'reason', 'denominator', 'dispatch_ns')})
    mcp = [frame for slot in slots for frame in slot.get('MCP_rows', [])]
    rpc = [row for slot in slots for row in slot.get('physical_RPC_rows', [])]
    usages = [slot['usage'] for slot in slots if isinstance(slot.get('usage'), dict)]
    totals = {key: sum(usage.get(key, 0) for usage in usages)
              for key in ('input_tokens', 'cached_input_tokens', 'output_tokens')}
    findings = dict(cycle_id='CONSUMPTION-RUN-003', audited_utc=datetime.now(timezone.utc).isoformat(),
        scope='read-only public counts/wire/timing/usage; no truth, answer-body interpretation, scoring or new consumer/backend',
        scheduled_slots=8, slot_status_counts=dict(Counter(row['status'] for row in slots)), slots=slots,
        CLI_process_attempts=sum(slot.get('consumer_pid') is not None for slot in slots),
        answers_received=sum(slot.get('clocks', {}).get('final_received_ns') is not None for slot in slots),
        final_artifacts=sum(slot.get('final_artifact', {}).get('exists', False) for slot in slots),
        consumer_complete_count=sum(slot.get('consumer_complete') is True for slot in slots),
        valid_completion_count=sum(slot.get('valid_completion') is True for slot in slots),
        observed_public_tool_actions=sum(slot.get('public_tool_actions_observed', 0) for slot in slots),
        public_tool_started_by_name=dict(Counter(str(event['server']) + '.' + str(event['tool'])
            for slot in slots for event in slot.get('public_tool_events', []) if event['event'] == 'item.started')),
        public_tool_completed_by_status=dict(Counter(str(event['status'])
            for slot in slots for event in slot.get('public_tool_events', []) if event['event'] == 'item.completed')),
        admitted_server_actions=sum(slot.get('ledger', {}).get('actions', 0) for slot in slots),
        execute_RPC_ledger=sum(slot.get('ledger', {}).get('physical_rpc', 0) for slot in slots),
        actual_native_sessions=sum(slot.get('native_session') is not None for slot in slots),
        physical_RPC_by_origin=dict(Counter(row['origin'] for row in rpc)), physical_RPC_total=len(rpc),
        physical_RPC_request_types=dict(Counter(str(row['request_type']) for row in rpc)),
        physical_RPC_rows_with_TX_bytes=sum(row['tx'].get('bytes', 0) > 0 for row in rpc),
        physical_RPC_rows_with_RX_bytes=sum(row['rx'].get('bytes', 0) > 0 for row in rpc),
        physical_RPC_response_statuses=dict(Counter(str(row.get('response_status')) for row in rpc)),
        MCP_frame_count=len(mcp), MCP_methods=dict(Counter(frame['method'] for frame in mcp)),
        MCP_wire_TX_bytes=sum(frame['tx'].get('bytes', 0) for frame in mcp),
        MCP_generated_RX_bytes=sum(frame['generated_rx'].get('bytes', 0) for frame in mcp),
        MCP_published_RX_bytes=sum(frame['published_rx'].get('bytes', 0) for frame in mcp),
        physical_RPC_TX_bytes=sum(row['tx'].get('bytes', 0) for row in rpc),
        physical_RPC_RX_bytes=sum(row['rx'].get('bytes', 0) for row in rpc),
        generated_MCP_image_blocks=sum(len(frame['generated_image_blocks']) for frame in mcp),
        published_MCP_image_blocks=sum(len(frame['published_image_blocks']) for frame in mcp),
        ledger_generated_image_blocks=sum(slot.get('ledger', {}).get('generated_image_blocks', 0) for slot in slots),
        PNG_file_count=sum(len(slot.get('PNG_files', [])) for slot in slots),
        render_event_counts=dict(Counter(event.get('event') for slot in slots for event in slot.get('worker_event_metadata', [])
                                        if str(event.get('event', '')).startswith('render_'))),
        model_effective_schema_bytes=None, terminal_usage_once_per_fresh_context=totals,
        contexts_with_terminal_usage=len(usages), terminal_usage_scope='cached input is a subset of input; only each consumer terminal usage once',
        provider_requests=None, fees=None, actual_backend=None, backend_exposure='unexposed', quality_scores=None,
        outer_controller=outer, runner_wall_ns=frozen.get('run_wall_through_result_construction_ns'),
        clock_scope='same local perf-counter receive/wait observations; nested intervals must not be summed; received final is not certified correctness',
        frozen_result_modified=False, actual_consumer_or_scorer_launched_by_audit=0, actual_Blender_or_RPC_launched_by_audit=0,
        evidence_files=[file_meta(Path(path)) for path in protected])
    failed_messages = Counter()
    for slot in slots:
        for event in slot.get('public_tool_events', []):
            for text in event.get('failed_tool_text', []):
                try:message = json.loads(text).get('error')
                except (ValueError, AttributeError):message = text
                if isinstance(message, str):failed_messages[message] += 1
    findings['failed_tool_error_messages'] = dict(failed_messages)
    findings['full_server_catalogue_utf8_bytes_total'] = sum(frame.get('full_server_catalogue_utf8_bytes', 0) for frame in mcp)
    assert all(sha(Path(path).read_bytes()) == digest for path, digest in protected.items()), 'frozen evidence changed during audit'
    (OUT / 'COUNTS_AUDIT.json').write_text(json.dumps(findings, indent=2) + '\n', encoding='utf8', newline='\n')
    lines = ['# RUN003 counts audit', '',
        f"Eight frozen slots: {findings['slot_status_counts']}. Returned finals {findings['answers_received']}; saved final artifacts {findings['final_artifacts']}; frozen valid completions {findings['valid_completion_count']}. No quality score assigned.", '',
        '| Slot | Task | Arm | Status | Public tools | Native/HE/close RPC | Input/cached/output tokens | Final receive seconds |',
        '|---|---|---|---|---:|---|---|---:|']
    for slot in slots:
        counts = Counter(row['origin'] for row in slot.get('physical_RPC_rows', []))
        usage = slot.get('usage') or {}
        latency = slot.get('clocks', {}).get('answer_receive_latency_ns')
        lines.append(f"| {slot['ordinal']} | {slot.get('task_id')} | {slot.get('arm')} | {slot['status']} | {slot.get('public_tool_actions_observed', 0)} | {counts['native_execute_code']}/{counts['HE_owned_socket']}/{counts['administrative_close']} | {usage.get('input_tokens')}/{usage.get('cached_input_tokens')}/{usage.get('output_tokens')} | {None if latency is None else latency / 1e9} |")
    lines += ['',
        f"Public tools observed {findings['observed_public_tool_actions']}; admitted server actions {findings['admitted_server_actions']}. MCP frames {findings['MCP_frame_count']} with methods {findings['MCP_methods']}. MCP TX {findings['MCP_wire_TX_bytes']} / generated RX {findings['MCP_generated_RX_bytes']} / published RX {findings['MCP_published_RX_bytes']} bytes.", '',
        f"Physical RPCs {findings['physical_RPC_total']}: {findings['physical_RPC_by_origin']}. Administrative closes are separate from the execute ledger. HE socket RPC count measures owned physical requests, not the number of HE logical observe calls. Full returned catalogues and each descriptor are measured per tools/list frame in JSON; effective model-delivered schema bytes remain null.", '',
        f"Terminal usage counted once across {len(usages)} contexts: input {totals['input_tokens']}, cached subset {totals['cached_input_tokens']}, output {totals['output_tokens']}. Provider requests and fees remain null; actual backend is unexposed.", '',
        f"MCP images generated/published {findings['generated_MCP_image_blocks']}/{findings['published_MCP_image_blocks']}; ledger generated {findings['ledger_generated_image_blocks']}; private PNG files {findings['PNG_file_count']}; worker render events {findings['render_event_counts']}.", '',
        f"Outer controller wall {outer['wall_ns'] / 1e9}s. Runner wall {None if findings['runner_wall_ns'] is None else findings['runner_wall_ns'] / 1e9}s. Per-cell and consumer clocks retain their own boundaries and are not added. Final receive latency does not establish task correctness or engine benefit.", '',
        f"Tool completion states: {findings['public_tool_completed_by_status']}. The failed HE tool error messages, preserved verbatim as ordinary tool results, are {findings['failed_tool_error_messages']}. These tool errors do not rewrite the eight frozen slot states.", '',
        f"Returned catalogue UTF-8 bytes across all twelve tools/list frames total {findings['full_server_catalogue_utf8_bytes_total']}. Each native catalogue is 563 bytes (descriptor 561). Each HE catalogue contains four tools and is 17,808 bytes; its human_eye_scene_observe descriptor is 8,767 bytes. Host/model filtering remains unexposed.", '',
        'The audit parsed only public event metadata, numeric usage, tool/protocol envelopes, byte lengths and worker audit metadata. Final text was hashed and counted as bytes only. Disk CRLF bytes and logical final-text ledger bytes are recorded separately. Frozen results, cleanup flags, prior runs and source files were not modified. No private global log, truth, model, CLI consumer, Blender, service, socket or RPC was used by this audit.']
    (OUT / 'COUNTS_AUDIT.md').write_text('\n'.join(lines) + '\n', encoding='utf8', newline='\n')
    print(json.dumps({key: findings[key] for key in ('slot_status_counts', 'answers_received', 'valid_completion_count',
        'observed_public_tool_actions', 'physical_RPC_by_origin', 'physical_RPC_total', 'terminal_usage_once_per_fresh_context')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--slots', type=int, nargs='*')
    parser.add_argument('--finalize', action='store_true')
    args = parser.parse_args()
    if args.finalize:
        finalize()
    else:
        assert args.slots and all(1 <= ordinal <= 8 for ordinal in args.slots)
        for ordinal in args.slots:
            row = audit_slot(ordinal)
            print(json.dumps({key: row.get(key) for key in ('ordinal', 'task_id', 'arm', 'status', 'public_tool_actions_observed', 'usage', 'ledger', 'clocks')}))
