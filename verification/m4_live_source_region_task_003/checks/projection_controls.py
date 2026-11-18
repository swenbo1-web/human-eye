"""Verify the CLI event projection against frozen 002 originals without live work."""

import argparse
import base64
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory


HERE = Path(__file__).resolve().parent
PRIOR = HERE.parents[1] / 'm4_live_source_region_task_002'
ORIGINALS = Path('D:/he_m4_live_source_region_task_002')
HALF = 524_288
sys.path.insert(0, str(HERE.parent))
import consumer_contract as contract


def compact(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')


def digest(raw):
    return sha256(raw).hexdigest()


def fingerprint(raw):
    return {'bytes': len(raw), 'sha256': digest(raw)}


def event_rows(raw):
    rows = [json.loads(line) for line in raw.splitlines()]
    return [{'type': row['event']['type'], 'item': row['event']['item'], 'perf_ns': row['perf_ns']}
            for row in rows if row['event'].get('item', {}).get('type') == 'mcp_tool_call']


def projected_item(item, text):
    candidate = deepcopy(item)
    candidate['result'] = {'content': [{'type': 'text', 'text': text}], 'structured_content': None}
    return candidate


def check_controls(originals):
    index_raw = (PRIOR / 'RUNTIME_INDEX.json').read_bytes()
    index = {row['path']: row for row in json.loads(index_raw)['files']}
    checked_files = {}

    def original(relative):
        raw = (originals / relative).read_bytes()
        actual = fingerprint(raw)
        if any(index[relative][key] != value for key, value in actual.items()):
            raise ValueError('002_original_fingerprint_mismatch/' + relative)
        checked_files[relative] = actual
        return raw

    def slot_inputs(slot):
        events = original(f'slots/{slot}/consumer/events.jsonl')
        stdout = original(f'slots/{slot}/consumer/stdout.raw.bin')
        rows = event_rows(events)
        completed = [row for row in rows if row['type'] == 'item.completed' and row['item']['server'] == 'arm_engine']
        raw_public = [line for line in stdout.splitlines(keepends=True) if b'"mcp_tool_call"' in line]
        for row in completed:
            corroboration = [line for line in raw_public if json.loads(line) == {'type': row['type'], 'item': row['item']}]
            if len(corroboration) != 1:
                raise ValueError('002_completed_event_not_unique_in_raw_stdout/' + slot)
            row['stdout_event'] = fingerprint(corroboration[0])
        return rows, completed

    def source(slot, attempt):
        return json.loads(original(f'slots/{slot}/owner/tool_{attempt:02d}/RESPONSE.json'))

    cases = []

    def case(name, passed, **details):
        cases.append({'case': name, 'passed': bool(passed), **details})

    def bind(name, response, item, expected, *, use_original=False):
        matcher = contract.M1.result_contract.bind_tool_result if use_original else contract.bind_tool_result
        outcome = matcher(response, item)
        case(name, outcome['matched'] is expected, binding=outcome)
        return outcome

    native_rows, native = slot_inputs('N1')
    _, plugin = slot_inputs('P1')
    full = source('N1', 1)
    item = native[0]['item']
    full_bytes = compact(full['result'])
    head, tail = full_bytes[:HALF].decode('utf-8'), full_bytes[-HALF:].decode('utf-8')
    removed = len(full_bytes.decode('utf-8')) - len(head) - len(tail)
    marker = f'…{removed} chars truncated…'
    public_text = item['result']['content'][0]['text']
    replay = head + marker + tail
    case('actual_large_result_replays_byte_for_byte', replay.encode('utf-8') == public_text.encode('utf-8'),
         compact_source_result=fingerprint(full_bytes), public_event_text=fingerprint(public_text.encode('utf-8')),
         public_stdout_event=native[0]['stdout_event'], retained_head_UTF8_bytes=len(head.encode('utf-8')),
         retained_tail_UTF8_bytes=len(tail.encode('utf-8')), removed_characters=removed)
    baseline = bind('actual_large_result_fails_original_exact_match', full, item, False, use_original=True)
    projection = bind('actual_large_result_matches_verified_projection', full, item, True)
    replay_receipt = projection.get('CLI_event_projection', {})
    replay_expected = {'source_compact_result_sha256': digest(full_bytes),
                       'CLI_projected_text_sha256': digest(public_text.encode('utf-8')),
                       'retained_prefix_UTF8_bytes': HALF, 'retained_suffix_UTF8_bytes': HALF,
                       'removed_characters': removed, 'model_supplied_content_scope': 'unmeasured'}
    case('large_result_requires_verified_projection', baseline['reason'] == 'content_mismatch'
         and projection['reason'] == 'verified_cli_text_projection'
         and all(replay_receipt.get(key) == value for key, value in replay_expected.items()))

    for attempt, kind in ((2, 'short_geometry'), (3, 'short_numeric'), (4, 'image_delivery')):
        response, observed = source('N1', attempt), native[attempt - 1]
        previous = contract.M1.result_contract.bind_tool_result(response, observed['item'])
        outcome = bind(f'actual_native_{kind}_matches_exactly', response, observed['item'], True)
        case(f'actual_native_{kind}_retains_original_contract', outcome == previous,
             public_stdout_event=observed['stdout_event'])
    plugin_first = source('P1', 1)
    plugin_item = plugin[0]['item']
    bind('actual_plugin_brief_and_image_match_exactly', plugin_first, plugin_item, True)
    for slot, response, observed in (('native', source('N1', 4), native[3]['item']), ('plugin', plugin_first, plugin_item)):
        changed = deepcopy(observed)
        image = next(block for block in changed['result']['content'] if block['type'] == 'image')
        png = bytearray(base64.b64decode(image['data'], validate=True))
        png[-1] ^= 1
        image['data'] = base64.b64encode(png).decode('ascii')
        bind(f'changed_{slot}_image_bytes_rejected', response, changed, False)
        bind(f'{slot}_image_result_cannot_use_text_projection', response, projected_item(observed, replay), False)

    for label, wrong in (('head', '!' + public_text[1:]), ('tail', public_text[:-1] + '!'),
                         ('count', head + f'…{removed + 1} chars truncated…' + tail),
                         ('retained_byte_count', head[:-1] + f'…{removed + 1} chars truncated…' + tail)):
        bind(f'altered_{label}_rejected', full, projected_item(item, wrong), False)
    extra_block = deepcopy(item)
    extra_block['result']['content'].append({'type': 'text', 'text': 'extra'})
    bind('unexpected_public_content_shape_rejected', full, extra_block, False)
    changed = dict(item, status='failed')
    bind('incorrect_status_rejected', full, changed, False)
    changed = dict(item, error={'message': 'unexpected'})
    bind('non_null_CLI_error_rejected', full, changed, False)
    short = source('N1', 2)
    ordinary_error = deepcopy(short)
    ordinary_error['result']['isError'] = True
    ordinary_error_item = dict(native[1]['item'], status='failed')
    matched_error = bind('exact_tool_error_retains_original_contract', ordinary_error, ordinary_error_item, True)
    case('exact_tool_error_remains_classified_as_error', matched_error['classification'] == 'tool_error')
    bind('error_disguised_as_success_rejected', ordinary_error, native[1]['item'], False)
    oversized_error = deepcopy(full)
    oversized_error['result']['isError'] = True
    error_bytes = compact(oversized_error['result'])
    error_result = error_bytes[:HALF].decode() + f'…{len(error_bytes) - 2 * HALF} chars truncated…' + error_bytes[-HALF:].decode()
    bind('unobserved_projected_error_structure_rejected', oversized_error,
         projected_item(dict(item, status='failed'), error_result), False)

    synthetic = deepcopy(full)
    text_block = synthetic['result']['content'][0]
    text_block['text'] = ''
    envelope = compact(synthetic['result'])
    before, after = envelope.split(b'"text":""')
    prefix_bytes = len(before + b'"text":"')
    suffix_bytes = len(b'"' + after)
    for edge, first_span in (('head', HALF - prefix_bytes - 1), ('tail', HALF)):
        trailing = HALF if edge == 'head' else HALF - suffix_bytes - 1
        text_block['text'] = 'x' * first_span + 'é' + 'z' * trailing
        encoded = compact(synthetic['result'])
        sides = (encoded[:HALF], encoded[-HALF:])
        selected = sides[0 if edge == 'head' else 1]
        try:
            selected.decode('utf-8')
        except UnicodeDecodeError:
            case(f'synthetic_UTF8_{edge}_bisects_code_point', True)
        else:
            case(f'synthetic_UTF8_{edge}_bisects_code_point', False)
        lossy_head, lossy_tail = [side.decode('utf-8', errors='replace') for side in sides]
        count = len(encoded.decode('utf-8')) - len(lossy_head) - len(lossy_tail)
        bind(f'lossy_UTF8_{edge}_projection_rejected', synthetic,
             projected_item(item, lossy_head + f'…{count} chars truncated…' + lossy_tail), False)

    for variant in ('original', 'stdio_response_id', 'owner_tcp_response', 'CLI_arguments', 'CLI_caller_id', 'CLI_stdout'):
        result = archive_case(originals, native_rows, original, variant)
        first = result['result_contracts'][0]
        if variant == 'original':
            archived_stdout = first.get('CLI_event_projection', {}).get('archived_CLI_stdout_line', {})
            passed = (not result['binding_errors'] and all(row['matched'] for row in result['result_contracts'])
                      and all(archived_stdout.get(key) == value for key, value in native[0]['stdout_event'].items()))
        else:
            gate = {'CLI_stdout': 'CLI_projection_event_original_mismatch',
                    'owner_tcp_response': 'CLI_projection_without_original_owner_TCP_binding'}.get(
                        variant, 'CLI_projection_without_original_RPC_binding')
            passed = not first['matched'] and gate in {error['reason'] for error in result['binding_errors']}
        case('original_N1_archive_' + variant, passed, binding_errors=result['binding_errors'], first_contract=first)

    decision_raw = (PRIOR / 'DECISION.json').read_bytes()
    prior = json.loads(decision_raw)
    native_outcome = next(row for row in prior['slots'] if row['slot'] == 'N1')
    slot_raw = original('slots/N1/SLOT_RESULT.json')
    case('original_formal_failure_preserved', json.loads(slot_raw)['status'] == native_outcome['published_runtime_status'] == 'failed')
    return {'schema': 'm4-live-source-region-task-003-offline-projection-controls-v1',
            'status': 'passed' if all(row['passed'] for row in cases) else 'failed',
            'activity': {'model_calls': 0, 'Blender_starts': 0, 'rasters': 0, 'CLI_launches': 0},
            'original_002': {'root': str(originals), 'runtime_index': fingerprint(index_raw),
                             'decision': fingerprint(decision_raw), 'formal_N1_status': native_outcome['published_runtime_status'],
                             'files_read_and_verified': checked_files},
            'cases': cases}


def archive_case(originals, native_rows, original, variant):
    from shutil import copyfile

    slot = originals / 'slots/N1'
    roots = (slot / 'owner', slot / 'consumer/attachments')
    sources = [p for root in roots for p in root.rglob('*') if p.is_file()]
    sources.extend(slot / 'consumer' / name for name in ('events.jsonl', 'stdout.raw.bin'))
    with TemporaryDirectory(prefix='m4-003-projection-') as temp:
        folder = Path(temp)
        for path in sources:
            relative = path.relative_to(slot)
            original((Path('slots/N1') / relative).as_posix())
            target = folder / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            copyfile(path, target)
        calls = [{'type': row['type'], 'perf_ns': row['perf_ns'], 'item': deepcopy(row['item'])}
                 for row in native_rows if row['type'] == 'item.completed']
        if variant == 'stdio_response_id':
            response_path, = (folder / 'consumer/attachments').glob('bridge_*/004/RX.bin')
            response = json.loads(response_path.read_bytes())
            response['id'] += 1
            response_path.write_bytes(compact(response))
        elif variant == 'owner_tcp_response':
            response_path = folder / 'owner/rpc_003/TCP_RX.bin'
            response = json.loads(response_path.read_bytes())
            response['result']['result']['content'][0]['text'] += '!'
            response_path.write_bytes(compact(response) + b'\n')
        elif variant == 'CLI_arguments':
            calls[0]['item']['arguments']['code'] += '\npass'
        elif variant == 'CLI_caller_id':
            calls[0]['item']['call_id'] = 'wrong-call-id'
        elif variant == 'CLI_stdout':
            stdout = folder / 'consumer/stdout.raw.bin'
            lines = stdout.read_bytes().splitlines(keepends=True)
            for index, line in enumerate(lines):
                if len(line) > 2 * HALF:
                    event = json.loads(line)
                    event['item']['id'] += '_changed'
                    lines[index] = compact(event) + b'\n'
            stdout.write_bytes(b''.join(lines))
        return contract.archive_turn(folder / 'consumer', {'audit_dir': str(folder / 'owner'), 'group': 'N'}, 1, calls)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--originals', type=Path, default=ORIGINALS)
    parser.add_argument('--output', type=Path, default=HERE / 'PROJECTION_CONTROLS.json')
    args = parser.parse_args()
    outcome = check_controls(args.originals.resolve())
    args.output.write_text(json.dumps(outcome, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
                           encoding='utf-8', newline='\n')
    for row in outcome['cases']:
        if not row['passed']:
            print('FAIL', row['case'])
    print(outcome['status'], sum(row['passed'] for row in outcome['cases']), 'of', len(outcome['cases']))
    return 0 if outcome['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
