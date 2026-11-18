"""Reconcile the closed assembly slots using their original tool and timing records."""

import hashlib
import json
from pathlib import Path
import sys
import time

NS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(NS / 'harness'))
from common import ASSET, ASSET_SHA256, EXTERNAL, read, save, sha


def content_metrics(blocks):
    return {'text_UTF8_bytes': sum(len(r['text'].encode('utf8')) for r in blocks if r['type'] == 'text'),
            'images': sum(r['type'] == 'image' for r in blocks)}


def seconds(start, end):
    return (end - start) / 1e9 if type(start) is int and type(end) is int else None


def audit_slot(label, frozen, sealed):
    folder = EXTERNAL / 'slots' / label
    result = read(folder / 'SLOT_RESULT.json')
    pub = read(folder / 'SLOT_PUBLICATION.json')
    assert pub['result_sha256'] == sha(folder / 'SLOT_RESULT.json') == sealed['slot_result_sha256']
    assert result['freeze_sha256'] == frozen
    began, end = result['started_ns'], pub['published_ns']
    consumer_dir = folder / 'consumer'
    if not (consumer_dir / 'CONSUMER.json').is_file():
        return {'slot': label, 'status': result['status'], 'errors': result['errors'], 'model_record': 'missing',
                'started_ns': began, 'published_ns': end, 'full_window_s': seconds(began, end),
                'within_owned_deadline': end < result['owned_deadline_ns']}
    consumer = read(consumer_dir / 'CONSUMER.json')
    owner = read(folder / 'owner/TOOLS.json')
    closure = read(folder / 'RUNTIME_CLOSE.json')
    binding = read(consumer_dir / 'BUSINESS_SOURCE_BINDING.json')
    receipts = {row['attempt']: row for row in binding['result_contracts']}
    turns = []
    stdio = {}
    for tx_path in (consumer_dir / 'attachments').glob('bridge_*/*/TX.bin'):
        wire = read(tx_path)
        if wire.get('method') == 'tools/call':
            receipt = read(tx_path.with_name('RECEIPT.json'))
            ordinal = receipt['attempt']
            assert ordinal not in stdio
            stdio[ordinal] = (tx_path, tx_path.with_name('RX.bin'))
    usages = []
    with (consumer_dir / 'stdout.raw.bin').open('rb') as stream:
        for line in stream:
            # The pinned CLI emits compact JSONL with the top-level type first.
            if line.startswith(b'{"type":"turn.completed",'):
                usages.append(json.loads(line)['usage'])
    assert usages == consumer['raw_usage_events']
    assert sealed['sha256'] is None or sha(consumer_dir / 'PUBLIC_FINAL.txt') == sealed['sha256']
    for row in owner['tools']:
        ordinal = row['attempt']
        directory = folder / 'owner' / f'tool_{ordinal:02d}'
        original = read(directory / 'REQUEST.json')
        reply_path = directory / 'RESPONSE.json'
        reply = read(reply_path)
        assert original['jsonrpc'] == reply['jsonrpc'] == '2.0' and original['id'] == reply['id']
        blocks = reply['result']['content']
        contract = receipts.get(ordinal, {})
        tx_path, rx_path = stdio[ordinal]
        assert read(tx_path) == original and read(rx_path) == reply
        assert (sha(tx_path), sha(rx_path)) == (contract['TX_sha256'], contract['RX_sha256'])
        assert not content_metrics(blocks)['images']
        turns.append({'attempt': ordinal, 'tool': original['params']['name'], 'RPC_id': original['id'],
            'request_sha256': sha(directory / 'REQUEST.json'), 'response_sha256': sha(reply_path),
            'request_arguments_sha256': hashlib.sha256(json.dumps(original['params']['arguments'],
                ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
            'tool_error': reply['result']['isError'], **content_metrics(blocks),
            'owner_started_ns': row.get('started_ns'), 'owner_closed_ns': row.get('closed_ns'),
            'CLI_received_ns': contract.get('CLI_received_ns'), 'match': contract.get('reason'),
            'CLI_event_text_UTF8_bytes': contract.get('CLI_text_UTF8_bytes')})
    frame_receipts = [row for row in (result.get('budget') or {}).get('records', [])
                      if row['claim']['label'] == label and row['claim']['kind'] == 'raster_attempt']
    assert not frame_receipts and consumer['public_image_count'] == 0
    reported = consumer['tool_accounting']
    assert len(turns) == len(stdio) == owner['attempts'] == binding['stdio_attempts']
    final = consumer.get('final_received_ns')
    terminal = result.get('terminal_source')
    closed = closure.get('Blender_status', {}).get('closed') or {}
    native = closure.get('Blender_close', {})
    return {'slot': label, 'status': result['status'], 'errors': result['errors'], 'started_ns': began, 'published_ns': end,
        'within_owned_deadline': end < result['owned_deadline_ns'],
        'within_task_deadline': result['consumer_returned_ns'] < result['task_deadline_ns'],
        'full_window_s': seconds(began, end), 'startup_to_answer_s': seconds(began, final),
        'startup_to_ready_s': seconds(began, result.get('ready_ns')),
        'prompt_to_first_successful_tool_evidence_s': seconds(consumer.get('prompt_submitted_ns'), binding.get('first_CLI_nonempty_successful_evidence_ns')),
        'first_successful_tool_evidence_to_answer_s': seconds(binding.get('first_CLI_nonempty_successful_evidence_ns'), final),
        'last_tool_to_answer_s': seconds(binding.get('last_CLI_tool_result_ns'), final),
        'answer_to_publish_s': seconds(final, end), 'tool_accounting': reported,
        'within_tools_limit': max(owner['attempts'] + reported['completed_empty_discoveries'], reported['completed_CLI_tool_calls']) <= 12,
        'attempts': turns, 'binding_errors': binding['binding_errors'], 'usage': usages,
        'owner_text_UTF8_bytes': sum(row['text_UTF8_bytes'] for row in turns),
        'CLI_event_text_UTF8_bytes': sum(row['CLI_event_text_UTF8_bytes'] or 0 for row in turns),
        'images_and_rasters': 0, 'terminal_source': terminal,
        'Blender_cleanup': {'exit_code': native.get('exit_code'), 'scene_unchanged': closed.get('scene_unchanged'),
                            'copy_and_original_unchanged': native.get('protected_files_unchanged'),
                            'retained_handle_exit': closure.get('Blender_exit')},
        'public_MCP_cleanup': closure.get('public_MCP_close'), 'CLI_exit_code': consumer.get('exit_code'),
        'CLI_thread_id': consumer.get('thread_id'), 'thin_retained_exit': consumer.get('runtime_exit'),
        'thin_graceful_exit_receipt_count': len(list((consumer_dir / 'attachments').rglob('EXIT.json')))}


def main():
    began = time.perf_counter_ns()
    frozen = sha(NS / 'FROZEN.json')
    seal = read(NS / 'ANSWERS_SEALED.json')
    quality_path = NS / 'scoring/QUALITY.json'
    assert quality_path.is_file()
    slots = [audit_slot(row['slot'], frozen, row) for row in seal['answers']]
    native, plugin = slots
    assert native['published_ns'] <= plugin['started_ns'] and sha(ASSET) == ASSET_SHA256
    save(NS / 'checks/RUNTIME_REVIEW.json', {'started_ns': began, 'closed_ns': time.perf_counter_ns(),
        'launch_order': ['N1', 'P1'], 'frozen_sha256': frozen, 'quality_sha256': sha(quality_path), 'slots': slots,
        'unmeasured': ['provider actual input', 'cash fees', 'provider request count', 'image tokens', 'reason for undocumented thin MCP shutdown'],
        'scope': 'Original public tool, wire, usage, timing and closure receipts. Analysis event bodies were not decoded.'})


if __name__ == '__main__':
    main()
