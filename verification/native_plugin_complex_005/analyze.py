"""Read-only COMPLEX-005 protocol/raw-cost analysis; no semantic verdict.

No product, actor, CLI or model is imported/run. The output stays under private
and contains no answer text. Missing, failed and not-run slots remain in the
fixed 18-slot denominator. Run only after the root authorizes analysis of the
trial records; --self-test uses temporary synthetic records exclusively.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics
import tempfile
import tomllib


HERE = Path(__file__).resolve().parent
GROUPS = ('N', 'H', 'C')
TASKS = ('assembly', 'discovery')
READ_TOOL_NAMES = ('human_eye_scene_observe', 'human_eye_connection_status')
REUSED_V2_SHA256 = '674c0b1b7bbbcd5fdda5d994bdf52848cf5f005a6a4425fcac7e62b62fde09d0'
TOKENS = ('input_tokens', 'cached_input_tokens', 'cache_write_input_tokens',
          'output_tokens', 'total_tokens', 'reasoning_tokens', 'reasoning_output_tokens')
METRICS = ('prompt_to_final_ns', 'cli_wall_ns', 'total_task_wall_ns', 'setup_ns',
           'owner_finish_ns', 'actor_startup_ns', 'tool_attempts', 'native_attempts',
           'plugin_attempts', 'scene_observe_attempts', 'connection_status_attempts', 'all_plugin_read_attempts',
           'tool_errors', 'tool_time_ns', 'physical_worker_requests',
           'public_catalogue_rx_bytes', 'public_tool_rx_bytes', 'public_tool_text_bytes',
           'public_stdio_tx_bytes', 'public_stdio_rx_bytes', 'plugin_pipe_tx_bytes',
           'plugin_pipe_rx_bytes')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      allow_nan=False, separators=(',', ':')).encode('utf8')


def fingerprint(value):
    return digest(canonical(value))


def public_wire(value):
    """The frozen owner/attach compact UTF-8 serializer, including newline."""
    return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',', ':')).encode('utf8')+b'\n'


def summary(values, expected):
    known = [v for v in values if type(v) is int or type(v) is float and math.isfinite(v)]
    return dict(denominator=expected, reported=len(known), missing=expected-len(known),
        invalid_nonfinite=sum(type(v) is float and not math.isfinite(v) for v in values),
        median=statistics.median(known) if known else None,
        min=min(known) if known else None, max=max(known) if known else None,
        observed_sum=sum(known) if known else None)


def finite_output(value, path, replaced):
    """Keep a bad raw float from preventing publication of all 18 slots."""
    if type(value) is float and not math.isfinite(value):
        replaced.append(path)
        return None
    if isinstance(value, dict):
        return {key:finite_output(item,path+'.'+str(key),replaced) for key,item in value.items()}
    if isinstance(value, (list, tuple)):
        return [finite_output(item,path+'['+str(i)+']',replaced) for i,item in enumerate(value)]
    return value


class Evidence:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.inputs = {}

    def raw(self, path, issues, required=False):
        path = Path(path)
        if not path.is_file():
            if required:
                issues.append(dict(code='missing_evidence', path=str(path)))
            return None
        try:
            value = path.read_bytes()
        except OSError as exc:
            issues.append(dict(code='evidence_read_error', path=str(path), error=repr(exc)))
            return None
        self.inputs[str(path.resolve())] = digest(value)
        return value

    def json(self, path, issues, required=False):
        raw = self.raw(path, issues, required)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (ValueError, UnicodeError) as exc:
            issues.append(dict(code='invalid_json', path=str(path), error=repr(exc)))
            return None

    def jsonl(self, path, issues, required=False):
        raw = self.raw(path, issues, required)
        rows = []
        if raw is not None:
            for number, line in enumerate(raw.splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    rows.append(json.loads(line))
                except (ValueError, UnicodeError) as exc:
                    issues.append(dict(code='invalid_jsonl', path=str(path), line=number, error=repr(exc)))
        return rows


def check(checks, name, actual, issues):
    checks[name] = actual
    if actual is False:
        issues.append(dict(code='check_failed', check=name))


def replay_source_manifests(evidence, source, issues):
    """Re-hash frozen installed sources without importing or executing them."""
    result = {}
    for group, want in source.get('versions', {}).items():
        expected = want.get('identity', {})
        rows = expected.get('source_files')
        errors, actual_rows = [], []
        if not isinstance(rows, list) or not rows:
            result[group] = dict(passed=False, errors=['full_frozen_source_manifest_missing'])
            continue
        site = Path(want['installed_root']).resolve()
        if rows != want.get('runtime_sources'):
            errors.append('frozen_identity_and_runtime_source_manifests_differ')
        if len({row.get('path') for row in rows}) != len(rows):
            errors.append('duplicate_frozen_source_path')
        for row in rows:
            path = (site/row['path']).resolve()
            if not path.is_relative_to(site):
                errors.append('source_path_outside_install:'+row['path']); continue
            raw = evidence.raw(path, issues, True)
            actual_rows.append(dict(path=row['path'], sha256=digest(raw) if raw is not None else None))
            if raw is None or digest(raw) != row.get('sha256'):
                errors.append('installed_source_bytes_mismatch:'+row['path'])
        canonical_body = dict(base_version=expected.get('base_version'),
            implementation_revision=expected.get('implementation_revision'), files=rows)
        canonical_hash = digest(json.dumps(canonical_body,sort_keys=True,separators=(',',':'),
                                            ensure_ascii=True,allow_nan=False).encode('utf8'))
        if (canonical_hash != expected.get('source_sha256') or canonical_hash != want.get('source_sha256')
                or expected.get('build_id') != 'sha256:'+canonical_hash):
            errors.append('independent_frozen_canonical_hash_mismatch')
        result[group] = dict(passed=not errors, source_file_count=len(rows),
            independent_canonical_sha256=canonical_hash, actual_files_sha256=actual_rows,
            expected_manifest_origin='SOURCE_PREFLIGHT.json versions.'+group+'.identity.source_files', errors=errors)
        if errors: issues.append(dict(code='installed_source_replay_failed', group=group, errors=errors))
    return result


def source_binding(identity, config, group, source, replay=None):
    if group == 'N':
        return identity.get('runtime_identity') is None
    want = source.get('versions', {}).get(group)
    actual = identity.get('runtime_identity')
    if not want or not actual:
        return None
    expected = want.get('identity', {})
    members = expected.get('source_files')
    # initialize deliberately replaces the full source_files array with its
    # count. Its canonical hash is bound to the independently replayed manifest.
    member_binding = (actual.get('source_files') == members if 'source_files' in actual
                      else type(actual.get('source_file_count')) is int and
                      isinstance(members,list) and actual['source_file_count'] == len(members))
    core = tuple(key for key in expected if key != 'source_files')
    pin = actual.get('identity_check') or {}
    return (actual.get('source_kind') == 'installed_distribution' and member_binding
        and all(actual.get(key) == expected.get(key) for key in core)
        and replay is not None and replay.get('passed') is True
        and pin.get('compatible') is True and pin.get('pins_requested') is True and not pin.get('reasons')
        and (pin.get('expected') or {}).get('source_sha256') == want.get('source_sha256')
        and config.get('source_sha256') == want.get('source_sha256')
        and config.get('entry') == want.get('entry')
        and config.get('install_root') == want.get('installed_root'))


def normalized_mesh(raw):
    if not isinstance(raw, dict):
        return None
    rows = raw.get('objects')
    if not isinstance(rows, list):
        return None
    return dict(unit_scale_m=raw.get('unit_scale_m', 1.), objects=[
        dict(name=o.get('name'), vertices_local=o.get('vertices_local'),
             matrix_world=o.get('matrix_world'), faces=o.get('faces', o.get('triangles')))
        for o in rows])


def snapshot_receipt_matches(receipt, snapshot):
    if receipt is None or snapshot is None:
        return None
    try:
        response = receipt['response']
        return (response['status'] == 'success' and response['result']['executed'] is True
            and json.loads(response['result']['result']) == snapshot
            and receipt['source_file_unchanged'] is True
            and receipt['protected_files_unchanged'] is True)
    except (KeyError, TypeError, ValueError):
        return False


def parse_argv(argv):
    config, model, errors = {}, None, []
    if not isinstance(argv, list):
        return config, model, ['missing_argv']
    assignments = []
    for i, value in enumerate(argv):
        if value in ('-c', '--config'):
            if i+1 < len(argv): assignments.append(argv[i+1])
            else: errors.append('missing_config_value')
        if value in ('-m', '--model') and i+1 < len(argv): model = argv[i+1]
    try:
        config = tomllib.loads('\n'.join(assignments))
    except (ValueError, TypeError) as exc:
        errors.append('invalid_config_toml:'+str(exc))
    return config, model, errors


def usage_from_events(events, consumer):
    rows = [e.get('event', e).get('usage') for e in events
            if e.get('event', e).get('type') == 'turn.completed']
    rows = [row for row in rows if isinstance(row, dict)]
    numeric = [{key: row[key] for key in TOKENS if key in row} for row in rows]
    valid = all(type(v) is int and v >= 0 for row in numeric for v in row.values())
    agreement = (consumer.get('usage_rows') == numeric and
                 consumer.get('usage') == (numeric[-1] if numeric else None))
    totals = {key: sum(row[key] for row in numeric) for key in TOKENS
              if numeric and all(key in row for row in numeric)} if valid else {}
    return dict(public_turn_completed_count=len(rows), actual_usage_rows=rows,
        numeric_usage_rows=numeric, consumer_record_agrees=agreement,
        counters_valid=valid, observed_completed_turn_totals=totals,
        semantics='raw CLI turn counters; cached input is reported separately and never added to input; no inferred billing or provider request count',
        final_turn_usage=numeric[-1] if numeric else None,
        provider_request_count=None, fees=None, resolved_effort=None)


def response_status(value):
    statuses = []
    for block in (value or {}).get('result', {}).get('content', []):
        if block.get('type') == 'text':
            try:
                parsed = json.loads(block.get('text', ''))
            except (ValueError, TypeError):
                continue
            if isinstance(parsed, dict) and 'status' in parsed:
                statuses.append(parsed['status'])
    return statuses


def bridge_metrics(evidence, folder, group, read_schemas, issues):
    counts = Counter()
    records, catalogues, native_hashes, pids, exits, request_keys, response_keys = [], [], [], [], [], Counter(), Counter()
    model_exchanges = Counter()
    for bridge in sorted((folder / 'attachments').glob('bridge_*')):
        start = evidence.json(bridge/'STARTED.json', issues) or {}
        ended = evidence.json(bridge/'EXIT.json', issues)
        if start.get('pid') is not None: pids.append(start['pid'])
        tx_total = rx_total = 0
        for call in sorted(bridge.glob('[0-9]*')):
            tx = evidence.raw(call/'TX.bin', issues, True)
            rx = evidence.raw(call/'RX.bin', issues)
            if tx is None: continue
            tx_total += len(tx); rx_total += len(rx or b'')
            try:
                request = json.loads(tx)
                reply = json.loads(rx) if rx is not None else None
            except (ValueError, UnicodeError) as exc:
                issues.append(dict(code='public_bridge_invalid_frame', path=str(call), error=repr(exc)))
                counts['invalid_frames'] += 1
                continue
            method = request.get('method')
            counts['id_requests' if 'id' in request else 'notifications'] += 1
            kind = 'catalogue' if method == 'tools/list' else 'tool' if method == 'tools/call' else 'control'
            counts[kind+'_tx_bytes'] += len(tx); counts[kind+'_rx_bytes'] += len(rx or b'')
            counts[kind+'_requests'] += 1
            if 'id' in request and reply is None:
                counts['missing_response_frames'] += 1
            if reply is not None and reply.get('id') != request.get('id'):
                issues.append(dict(code='public_response_id_mismatch', path=str(call)))
                counts['response_id_mismatches'] += 1
            if kind == 'catalogue' and reply is not None:
                tools = reply.get('result', {}).get('tools', [])
                names = [t.get('name') for t in tools]
                expected = ['execute_blender_code'] + ([] if group == 'N' else list(READ_TOOL_NAMES))
                expected_reads = read_schemas if isinstance(read_schemas, list) else []
                read_shape = (not expected_reads if group == 'N' else
                    len(expected_reads) == 2 and {t.get('name') for t in expected_reads} == set(READ_TOOL_NAMES))
                valid = sorted(names) == sorted(expected) and len(names) == len(set(names)) and read_shape
                if not valid: issues.append(dict(code='unexpected_public_catalogue', names=names))
                for tool in tools:
                    if tool.get('name') == 'execute_blender_code': native_hashes.append(fingerprint(tool))
                    if tool.get('name') in READ_TOOL_NAMES and tool not in expected_reads:
                        valid = False
                        issues.append(dict(code='public_release_read_schema_changed', name=tool.get('name')))
                catalogues.append(dict(path=str(call), names=names, schema_sha256=fingerprint(tools), valid=valid))
            if kind == 'tool':
                arguments = request.get('params', {}).get('arguments')
                counts['arguments_compact_reencoded_bytes'] += len(json.dumps(arguments,
                    ensure_ascii=False,allow_nan=False,separators=(',', ':')).encode('utf8'))
                request_keys[fingerprint(request)] += 1
                if reply is not None:
                    response_keys[fingerprint(reply)] += 1
                    params = request.get('params', {})
                    result = reply.get('result') or {}
                    model_exchanges[fingerprint(dict(tool=params.get('name'),args=params.get('arguments'),
                        content=result.get('content'),structured_content=result.get('structuredContent')))] += 1
                    for block in reply.get('result', {}).get('content', []):
                        if block.get('type') == 'text': counts['tool_text_bytes'] += len(block.get('text', '').encode('utf8'))
                        elif block.get('type') == 'image':
                            counts['image_blocks'] += 1
                            counts['image_base64_characters'] += len(block.get('data', ''))
            records.append(dict(path=str(call), method=method, tx_bytes=len(tx), rx_bytes=None if rx is None else len(rx)))
        counts['stdio_tx_bytes'] += tx_total; counts['stdio_rx_bytes'] += rx_total
        if ended is None:
            issues.append(dict(code='missing_bridge_exit', path=str(bridge)))
        elif ended.get('complete_tx_bytes') != tx_total or ended.get('complete_rx_bytes') != rx_total:
            issues.append(dict(code='bridge_byte_total_mismatch', path=str(bridge)))
        if ended is not None:
            exits.append(dict(path=str(bridge), **ended))
            if ended.get('normal_exit') is not True:
                issues.append(dict(code='abnormal_bridge_exit', path=str(bridge)))
    return dict(counts=dict(counts), frames=records, catalogues=catalogues,
        exits=exits, model_tool_exchange_fingerprints=dict(model_exchanges),
        graceful_exit_receipts=len(exits), missing_graceful_exit_receipts=len(pids)-len(exits),
        graceful_client_exit_attested=bool(pids) and len(exits) == len(pids)
            and all(item.get('normal_exit') is True for item in exits),
        native_schema_sha256=sorted(set(native_hashes)), attachment_actual_pids=sorted(set(pids))), request_keys, response_keys


def owner_tools(evidence, owner, issues):
    document = evidence.json(owner/'TOOLS.json', issues)
    close = evidence.json(owner/'CLOSE.json', issues) or {}
    # A completed owner with zero attempts need not create TOOLS.json.
    if document is None and close.get('tool_attempts') == 0:
        document = dict(attempts=0, calls=0, wire_tool_bytes=0, tools=[])
    if document is None:
        return dict(attempts=None, rows=[], ledger_complete=None), Counter(), Counter()
    rows, requests, responses, transitions = document.get('tools', []), Counter(), Counter(), []
    actual, byte_bindings, code_sizes, text_bytes, script_bytes = [], [], [], 0, 0
    for call in sorted(owner.glob('tool_[0-9]*')):
        request = evidence.json(call/'REQUEST.json', issues, True)
        attempt = evidence.json(call/'ATTEMPT.json', issues, True)
        response = evidence.json(call/'RESPONSE.json', issues)
        if response is None: response = evidence.json(call/'ERROR_RESPONSE.json', issues)
        if request is not None:
            requests[fingerprint(request)] += 1
            code = request.get('params', {}).get('arguments', {}).get('code')
            if isinstance(code, str):
                code_size = len(code.encode('utf8')); script_bytes += code_size
                code_sizes.append(dict(attempt=attempt.get('attempt') if attempt else None, bytes=code_size))
        if response is not None:
            responses[fingerprint(response)] += 1
            text_bytes += sum(len(block.get('text', '').encode('utf8')) for block in
                response.get('result', {}).get('content', []) if block.get('type') == 'text')
        if attempt is not None:
            actual.append(attempt)
            if attempt not in rows: issues.append(dict(code='attempt_file_not_in_ledger', path=str(call)))
            expected_bytes = len(public_wire(response)) if response is not None else 0
            bound = attempt.get('response_bytes') == expected_bytes
            byte_bindings.append(dict(attempt=attempt.get('attempt'), recorded_bytes=attempt.get('response_bytes'),
                actual_response_compact_wire_bytes=expected_bytes, matched=bound))
            if not bound: issues.append(dict(code='owner_response_wire_byte_mismatch', path=str(call)))
        evidence.json(call/'NATIVE_RECEIPT.json', issues)
        if len(actual) > 1:
            prev, current = actual[-2:]
            transitions.append(dict(from_attempt=prev.get('attempt'), to_attempt=current.get('attempt'),
                from_tool=prev.get('name'), to_tool=current.get('name'), previous_is_error=prev.get('is_error'),
                previous_response_statuses=prev.get('response_statuses', [])))
        if response is not None and attempt is not None:
            attempt = dict(attempt, response_statuses=response_status(response))
            actual[-1] = attempt
    n = document.get('attempts', document.get('calls'))
    ledger_complete = (type(n) is int and n >= 0 and document.get('calls') == n
        and len(rows) == n and len(actual) == n
        and [r.get('attempt') for r in rows] == list(range(1, n+1))
        and all({k:v for k,v in item.items() if k != 'response_statuses'} == rows[i]
                for i,item in enumerate(actual)))
    # Compare request count as a multiset, including duplicate JSON-RPC IDs.
    ledger_complete = ledger_complete and sum(requests.values()) == n
    if not ledger_complete: issues.append(dict(code='owner_attempt_ledger_incomplete'))
    native = sum(r.get('name') == 'execute_blender_code' for r in rows)
    observe = sum(r.get('name') == 'human_eye_scene_observe' for r in rows)
    status = sum(r.get('name') == 'human_eye_connection_status' for r in rows)
    plugin = observe  # V2 compatibility: observation attempts, not successful solves.
    fallback = [t for t in transitions if t['from_tool'] == 'human_eye_scene_observe'
        and t['to_tool'] == 'execute_blender_code']
    return dict(attempts=n, calls=document.get('calls'), rows=actual,
        ledger_complete=ledger_complete, native_attempts=native, plugin_attempts=plugin,
        scene_observe_attempts=observe, connection_status_attempts=status,
        all_plugin_read_attempts=observe+status,
        attempts_by_tool=dict(Counter(r.get('name') for r in rows)),
        errors=sum(bool(r.get('is_error')) for r in rows),
        exceptions=sum(r.get('exception') is not None for r in rows),
        tool_time_ns=sum(r.get('elapsed_ns', 0) for r in rows),
        declared_response_wire_bytes=document.get('wire_tool_bytes'),
        sum_recorded_response_bytes=sum(r.get('response_bytes', 0) for r in rows),
        proposed_response_bytes_observed_sum=sum(r['produced_response_bytes'] for r in rows
            if type(r.get('produced_response_bytes')) is int),
        proposed_response_bytes_not_formed=sum(r.get('produced_response_bytes') is None for r in rows),
        response_wire_byte_bindings=byte_bindings,
        response_wire_bytes_verified=all(row['matched'] for row in byte_bindings) and len(byte_bindings) == n,
        owner_response_text_bytes=text_bytes, native_submitted_code_bytes=script_bytes,
        native_code_sizes=code_sizes,
        fallback_observed_adjacent_transitions=fallback,
        native_after_plugin_error_count=sum(bool(t['previous_is_error']) for t in fallback),
        native_after_plugin_unresolved_count=sum(any(status in ('partial','unknown','expired')
            for status in t['previous_response_statuses']) for t in fallback),
        fallback_intent_inferred=False), requests, responses


def peer_metrics(evidence, owner, issues):
    peer = owner/'plugin'
    start = evidence.json(peer/'START.json', issues) or {}
    closed = evidence.json(peer/'CLOSE.json', issues)
    rpc = evidence.json(peer/'RPC.json', issues)
    if rpc is None:
        return dict(present=peer.is_dir(), rpc_ledger_present=False, counts={}, requests=[],
            serve_launcher_pid=start.get('launcher_pid'), close_record=closed)
    counts, records, correlations = Counter(), [], []
    initialize_answer, catalogue_answer = None, None
    pending = []
    for folder in sorted(owner.glob('tool_[0-9]*')):
        request = evidence.json(folder/'REQUEST.json', issues) or {}
        attempt = evidence.json(folder/'ATTEMPT.json', issues) or {}
        if request.get('params', {}).get('name') in READ_TOOL_NAMES:
            start_ns, elapsed_ns = attempt.get('started_ns'), attempt.get('elapsed_ns')
            pending.append(dict(fingerprint=fingerprint(request), attempt=attempt.get('attempt'),
                started_ns=start_ns, ended_ns=start_ns+elapsed_ns
                    if type(start_ns) is int and type(elapsed_ns) is int else None))
    actual_rx_total = 0
    for call in sorted(peer.glob('[0-9]*')):
        tx = evidence.raw(call/'TX.bin', issues, True)
        rx = evidence.raw(call/'RX.bin', issues)
        receipt = evidence.json(call/'RECEIPT.json', issues, True) or {}
        if tx is None: continue
        actual_rx_total += len(rx or b'')
        try: request = json.loads(tx)
        except (ValueError, UnicodeError):
            issues.append(dict(code='invalid_internal_product_frame', path=str(call))); continue
        name = request.get('params', {}).get('name')
        scope = 'private_admin'
        if request.get('method') == 'tools/call' and name in READ_TOOL_NAMES:
            # Match complete messages as a multiset within their enclosing
            # owner interval. A reused JSON-RPC id cannot relabel startup status
            # as a consumer call, nor overwrite another recorded request.
            matches = [index for index,item in enumerate(pending)
                if item['fingerprint'] == fingerprint(request)
                and type(item['started_ns']) is int and type(item['ended_ns']) is int
                and type(receipt.get('started_ns')) is int
                and item['started_ns'] <= receipt['started_ns'] <= item['ended_ns']]
            if len(matches) == 1:
                matched = pending.pop(matches[0])
                scope = 'forwarded_query' if name == 'human_eye_scene_observe' else 'forwarded_status'
                correlations.append(dict(peer_request=len(records)+1, owner_attempt=matched['attempt'], tool=name,
                    request_sha256=fingerprint(request), scope=scope))
            elif not (name == 'human_eye_connection_status' and request.get('id') == 'private-status'
                      and request.get('params', {}).get('arguments') == {} and len(records) == 3):
                issues.append(dict(code='internal_product_read_not_bound_to_owner_attempt', path=str(call), name=name))
        if (receipt.get('method') != request.get('method') or receipt.get('request_id') != request.get('id')
                or receipt.get('attempted_send_bytes') != len(tx)
                or (receipt.get('send_confirmed') is True and receipt.get('sent_bytes') != len(tx))
                or (receipt.get('send_confirmed') is not True and receipt.get('sent_bytes') is not None)):
            issues.append(dict(code='internal_product_tx_receipt_binding_mismatch', path=str(call)))
        if rx is not None:
            try:
                answer = json.loads(rx)
                if request.get('method') == 'initialize': initialize_answer = answer
                if request.get('method') == 'tools/list': catalogue_answer = answer
                if 'id' not in request or answer.get('id') != request['id']:
                    issues.append(dict(code='internal_product_rx_id_mismatch', path=str(call)))
            except (ValueError, UnicodeError):
                issues.append(dict(code='invalid_internal_product_rx_json', path=str(call)))
        counts[scope+'_requests'] += 1
        counts[scope+'_attempted_tx_bytes'] += len(tx)
        counts[scope+'_confirmed_tx_bytes'] += receipt.get('sent_bytes') or 0
        counts[scope+'_rx_bytes'] += len(rx or b'')
        counts['errors'] += int(receipt.get('error') is not None)
        if receipt.get('received_bytes') != len(rx or b''):
            issues.append(dict(code='internal_product_rx_byte_mismatch', path=str(call)))
        records.append(dict(receipt, scope=scope))
    if rpc.get('requests') != [{k:v for k,v in row.items() if k != 'scope'} for row in records]:
        issues.append(dict(code='internal_product_rpc_ledger_mismatch'))
    confirmed_tx = sum(row.get('sent_bytes') or 0 for row in records)
    received = sum(row.get('received_bytes', 0) for row in records)
    if rpc.get('tx_bytes') != confirmed_tx or rpc.get('rx_bytes') != received:
        issues.append(dict(code='internal_product_byte_total_mismatch'))
    initialized = next((r for r in records if r.get('method') == 'initialize'), None)
    startup = (initialized['started_ns']+initialized['elapsed_ns']-start['started_ns']
               if initialized and type(start.get('started_ns')) is int else None)
    saved_initialize = evidence.json(owner/'PLUGIN_INITIALIZE.json', issues)
    saved_catalogue = evidence.json(owner/'PLUGIN_TOOLS.json', issues)
    return dict(present=True, rpc_ledger_present=True, counts=dict(counts), requests=records, close_record=closed,
        initialize_identity=(initialize_answer or {}).get('result', {}).get('_meta', {}).get('human_eye'),
        saved_initialize_equals_wire=saved_initialize == initialize_answer if initialize_answer is not None else None,
        actual_ordinary_tools=(catalogue_answer or {}).get('result', {}).get('tools'),
        saved_catalogue_equals_wire=saved_catalogue == catalogue_answer if catalogue_answer is not None else None,
        forwarded_read_correlations=correlations,
        serve_command=start.get('command'),
        tx_bytes=confirmed_tx if all(row.get('send_confirmed') is True for row in records) else None,
        confirmed_tx_bytes_lower_bound=confirmed_tx, rx_bytes=actual_rx_total,
        declared_tx_bytes=rpc.get('tx_bytes'), declared_rx_bytes=rpc.get('rx_bytes'), poisoned=rpc.get('poisoned'),
        send_bytes_exact=all(row.get('send_confirmed') is True for row in records),
        serve_launcher_pid=start.get('launcher_pid'), serve_post_popen_record_to_initialize_reply_ns=startup,
        private_catalogue_ns=sum(r['elapsed_ns'] for r in records if r.get('method') == 'tools/list'),
        startup_import_ns=None, import_separately_measured=False)


def worker_metrics(evidence, owner, closed, issues):
    event_path = owner/'native/WORKER_EVENTS.jsonl'
    events = evidence.jsonl(event_path, issues, True)
    log_complete = str(event_path.resolve()) in evidence.inputs and not any(
        issue.get('path') == str(event_path) and issue.get('code') in ('invalid_jsonl','evidence_read_error') for issue in issues)
    requests = [e for e in events if 'sequence' in e and 'started_ns' in e]
    executed = [e for e in requests if 'script_sha256' in e]
    unknown = [e for e in requests if 'script_sha256' not in e and e.get('status') == 'unknown'
               and not e.get('error_type') and not e.get('operation')]
    native_close = closed.get('native_close', {})
    attested = bool(log_complete and len(unknown) == 1 and requests and unknown[0] is requests[-1]
        and (native_close.get('response') or {}).get('status') == 'closed'
        and native_close.get('process_reaped') and native_close.get('exit_code') == 0
        and closed.get('worker_closed'))
    ready = evidence.json(owner/'native/READY.json', issues) or {}
    worker_closed = evidence.json(owner/'native/WORKER_CLOSED.json', issues)
    if worker_closed is not None and closed.get('worker_closed') != worker_closed:
        issues.append(dict(code='worker_closed_record_mismatch'))
    return dict(log_available_and_parse_complete=log_complete,
        physical_requests=len(requests) if log_complete else None, observed_physical_requests=len(requests),
        execute_requests_including_admin_and_plugin=len(executed) if log_complete else None,
        max_execute_sequence=max((e['sequence'] for e in executed), default=None),
        execute_statuses=dict(Counter(e.get('status') for e in executed)),
        execute_terminal_checks_passed=all(e.get('terminal_geometry_and_file_checks_passed') is True for e in executed) if log_complete and executed else None,
        administrative_snapshot_receipts=sum((owner/name).is_file() for name in ('INITIAL.json.receipt.json','FINAL.json.receipt.json')),
        legacy_unlabelled_close_candidates=unknown, close_attested_separately=attested,
        close_unknown_not_counted_as_failed_execute=attested,
        other_unlabelled_requests=[e for e in requests if 'script_sha256' not in e and not (attested and e is unknown[0])],
        response_send_unknown_events=[e for e in events if e.get('event') == 'response_send_unknown'],
        render_events=[e for e in events if str(e.get('event','')).startswith('render_')],
        native_worker_tcp_bytes=None, bytes_scope='native worker TCP bytes not exposed by these receipts',
        blender_actual_pid=ready.get('pid'), worker_closed=worker_closed)


def analyze_cell(evidence, slot, plan, source, run_row, expected, source_replays=None, cleanup=None):
    folder = evidence.root/'cells'/slot['cell']; owner = folder/'owner'
    issues, checks = [], {}
    consumer = evidence.json(folder/'CONSUMER.json', issues)
    row = dict(slot, run_status=(run_row or {}).get('status', 'not_run' if consumer is None else 'unlisted'),
        recorded=consumer is not None, protocol_completed=False, quality_status='unreviewed',
        issues=issues, checks=checks)
    if consumer is None:
        row['not_run_or_missing_reason'] = (run_row or {}).get('reason', (run_row or {}).get('error', 'no_consumer_record'))
        row['prepared_owner_evidence_present'] = owner.is_dir()
        # Setup can fail after creating a live owner but before CONSUMER.json.
        # Keep its closure/geometry evidence rather than treating it as no work.
        partial_close = evidence.json(owner/'CLOSE.json', issues) or {}
        partial_finish = evidence.json(folder/'OWNER_FINISH.json', issues) or {}
        partial_identity = evidence.json(owner/'IDENTITY.json', issues) or {}
        row.update(partial_owner_close=partial_close, partial_owner_finish=partial_finish,
            preparation_failure=evidence.json(folder/'PREPARE_FAILURE.json', issues),
            actor_error=evidence.json(folder/'ACTOR_ERROR.json', issues),
            owner_finish_ns=partial_finish.get('finish_elapsed_ns'),
            actor_startup_ns=partial_identity.get('startup_ns'))
        initial = evidence.json(owner/'INITIAL.json', issues)
        final = evidence.json(owner/'FINAL.json', issues)
        check(checks, 'initial_frozen_world_mesh_binding', normalized_mesh(initial) == expected
              if initial is not None and expected is not None else None, issues)
        check(checks, 'final_initial_mesh_equal', initial == final
              if initial is not None and final is not None else None, issues)
        if (owner/'native').is_dir():
            row['native_worker'] = worker_metrics(evidence, owner, partial_close, issues)
        if (owner/'plugin').is_dir():
            row['plugin_peer'] = peer_metrics(evidence, owner, issues)
        launch = evidence.json(folder/'ACTOR_LAUNCH.json', issues) or {}
        endpoint = evidence.json(folder/'ENDPOINT.json', issues) or {}
        row['pids'] = dict(actor_actual=partial_identity.get('actor_pid', partial_close.get('actor_pid', endpoint.get('actor_pid'))),
            actor_launcher=launch.get('launcher_pid', partial_finish.get('actor_launcher_pid')),
            serve_launcher=row.get('plugin_peer', {}).get('serve_launcher_pid'),
            blender_actual=row.get('native_worker', {}).get('blender_actual_pid'),
            final_process_scan='root CIM cleanup separate')
        return row
    check(checks, 'slot_binding', all(consumer.get(k) == slot[k] for k in ('cell','group','task','round')), issues)
    task = plan['tasks'][slot['task']]
    check(checks, 'model_input_hash_and_bytes', consumer.get('input_sha256') == task['model_input_sha256']
        and consumer.get('input_text_bytes') == task['model_input_bytes'], issues)
    config_argv, model, argv_errors = parse_argv(consumer.get('argv'))
    check(checks, 'model_and_requested_effort', model == plan['model'] == consumer.get('model')
        and config_argv.get('model') == plan['model'] and config_argv.get('model_reasoning_effort') == plan['requested_effort']
        and consumer.get('requested_effort') == plan['requested_effort'] and not argv_errors, issues)
    check(checks, 'public_consumer_isolation_flags', all(flag in consumer.get('argv', [])
        for flag in ('--ignore-user-config','--ignore-rules','--ephemeral','--strict-config','--json'))
        and config_argv.get('forced_login_method') == 'chatgpt'
        and config_argv.get('sandbox_mode') == 'read-only'
        and config_argv.get('web_search') == 'disabled', issues)
    check(checks, 'absolute_session_budget', type(consumer.get('started_ns')) is int
        and consumer.get('deadline_ns') == consumer['started_ns']+int(plan['max_session_seconds']*1e9), issues)
    identity = evidence.json(owner/'IDENTITY.json', issues, True) or {}
    actor_config = evidence.json(folder/'ACTOR_CONFIG.json', issues, True) or {}
    closed = evidence.json(owner/'CLOSE.json', issues, True) or {}
    finished = evidence.json(folder/'OWNER_FINISH.json', issues, True) or {}
    initial = evidence.json(owner/'INITIAL.json', issues, True)
    final = evidence.json(owner/'FINAL.json', issues, True)
    initial_receipt = evidence.json(owner/'INITIAL.json.receipt.json', issues, True)
    final_receipt = evidence.json(owner/'FINAL.json.receipt.json', issues, True)
    check(checks, 'actor_asset_and_slot_binding', actor_config.get('group') == slot['group']
        and actor_config.get('task') == slot['task'] and actor_config.get('asset_sha256') == task['asset_sha256']
        and identity.get('asset_sha256') == task['asset_sha256'], issues)
    check(checks, 'initial_frozen_world_mesh_binding', normalized_mesh(initial) == expected if initial is not None and expected is not None else None, issues)
    check(checks, 'final_initial_mesh_equal', initial == final if initial is not None and final is not None else None, issues)
    check(checks, 'initial_actual_worker_receipt_binding', snapshot_receipt_matches(initial_receipt, initial), issues)
    check(checks, 'final_actual_worker_receipt_binding', snapshot_receipt_matches(final_receipt, final), issues)
    check(checks, 'source_identity_binding', source_binding(identity, actor_config, slot['group'], source,
          (source_replays or {}).get(slot['group'])), issues)
    check(checks, 'owned_asset_source_unchanged', closed.get('asset_unchanged'), issues)
    check(checks, 'owner_lifecycle_confirmed', bool(finished.get('confirmed') and finished.get('actor_exit') == 0
        and closed.get('confirmed')), issues)
    events = evidence.jsonl(folder/'events.jsonl', issues, True)
    usage = usage_from_events(events, consumer)
    check(checks, 'usage_record_matches_public_turn_events', usage['consumer_record_agrees'], issues)
    check(checks, 'usage_counters_nonnegative_integers', usage['counters_valid'], issues)
    public = [event.get('event', event) for event in events]
    threads = [event.get('thread_id') for event in public if event.get('type') == 'thread.started']
    errors = [event for event in public if event.get('type') in ('error', 'turn.failed')]
    messages = [event['item'].get('text', '') for event in public
        if event.get('type') == 'item.completed' and event.get('item', {}).get('type') == 'agent_message']
    turn_count = sum(event.get('type') == 'turn.completed' for event in public)
    final_event_times = [event.get('perf_ns') for event in events if
        event.get('event',event).get('type') == 'item.completed' and
        event.get('event',event).get('item',{}).get('type') == 'agent_message']
    turn_event_times = [event.get('perf_ns') for event in events
                        if event.get('event',event).get('type') == 'turn.completed']
    check(checks, 'public_fresh_thread_binding', len(threads) == 1 and threads[0] == consumer.get('thread_id'), issues)
    check(checks, 'public_final_message_binding', bool(messages) and messages[-1] == consumer.get('final'), issues)
    check(checks, 'public_final_timestamp_binding', final_event_times[-1] == consumer.get('final_received_ns')
          if final_event_times else None, issues)
    check(checks, 'public_turn_timestamp_binding', turn_event_times[-1] == consumer.get('turn_completed_ns')
          if turn_event_times else None, issues)
    public_complete = bool(consumer.get('valid_completion') is True and len(threads) == 1
        and turn_count == 1 and messages and not errors and consumer.get('exit_code') == 0
        and consumer.get('process_reaped') and consumer.get('readers_stopped')
        and not consumer.get('deadline_timer_fired') and not consumer.get('errors')
        and not consumer.get('unexpected_tool_deviations'))
    tools, owner_requests, owner_responses = owner_tools(evidence, owner, issues)
    bridges, public_requests, public_responses = bridge_metrics(evidence, folder, slot['group'], actor_config.get('read_schemas'), issues)
    check(checks, 'owner_attempt_ledger_complete', tools['ledger_complete'], issues)
    check(checks, 'public_owner_tool_requests_match', public_requests == owner_requests, issues)
    check(checks, 'public_owner_tool_responses_match', public_responses == owner_responses, issues)
    check(checks, 'public_catalogue_observed', bool(bridges['catalogues']), issues)
    check(checks, 'public_expected_replies_present', bridges['counts'].get('missing_response_frames', 0) == 0, issues)
    check(checks, 'public_frames_parseable', bridges['counts'].get('invalid_frames', 0) == 0, issues)
    check(checks, 'public_request_response_ids_match', bridges['counts'].get('response_id_mismatches', 0) == 0, issues)
    cli_exchanges = Counter()
    for event in public:
        item = event.get('item', {})
        if event.get('type') == 'item.completed' and item.get('type') == 'mcp_tool_call':
            result = item.get('result') or {}
            cli_exchanges[fingerprint(dict(tool=item.get('tool'),args=item.get('arguments'),
                content=result.get('content'),structured_content=result.get('structured_content')))] += 1
    check(checks, 'public_cli_tool_outcomes_match_wire',
          dict(cli_exchanges) == bridges['model_tool_exchange_fingerprints'], issues)
    peer = peer_metrics(evidence, owner, issues)
    if slot['group'] != 'N':
        check(checks, 'actual_initialize_identity_matches_owner',
              peer.get('initialize_identity') == identity.get('runtime_identity')
              and peer.get('saved_initialize_equals_wire') is True, issues)
        want = source.get('versions', {}).get(slot['group'], {})
        command = peer.get('serve_command') or []
        product_config = evidence.json(owner/'product_config.json', issues, True) or {}
        check(checks, 'actual_controlled_serve_and_pin_binding', len(command) == 7
            and command[0] == want.get('dependency_python') and command[1:3] == ['-I','-B']
            and command[3] == want.get('entry') and command[4:6] == ['serve','--config']
            and Path(command[6]).resolve() == (owner/'product_config.json').resolve()
            and product_config.get('project_root') == want.get('installed_root')
            and (product_config.get('expected_identity') or {}).get('source_sha256') == want.get('source_sha256')
            and product_config.get('request_budget_s') == 30.
            and (product_config.get('blender') or {}).get('timeout_s') == 30., issues)
        schema_command = want.get('schema_command') or {}
        schema_path = Path(schema_command.get('stdout', evidence.root/(slot['group']+'_schemas.stdout.json')))
        schema_probe = evidence.json(schema_path, issues, True) or {}
        ordinary_tools = schema_probe.get('tools_list', {}).get('result', {}).get('tools')
        frozen_reads = [tool for tool in ordinary_tools if tool.get('name') in READ_TOOL_NAMES] if isinstance(ordinary_tools,list) else None
        check(checks, 'group_specific_public_read_schemas_bound',
            evidence.inputs.get(str(schema_path.resolve())) == schema_command.get('stdout_sha256')
            and frozen_reads is not None and len(frozen_reads) == 2
            and {tool.get('name') for tool in frozen_reads} == set(READ_TOOL_NAMES)
            and actor_config.get('read_schemas') == frozen_reads, issues)
        check(checks, 'actual_ordinary_catalogue_bound_to_this_release',
            isinstance(ordinary_tools,list) and peer.get('actual_ordinary_tools') == ordinary_tools
            and peer.get('saved_catalogue_equals_wire') is True, issues)
    else:
        checks['actual_initialize_identity_matches_owner'] = checks['actual_controlled_serve_and_pin_binding'] = True
        checks['group_specific_public_read_schemas_bound'] = actor_config.get('read_schemas', []) == []
        checks['actual_ordinary_catalogue_bound_to_this_release'] = True
    worker = worker_metrics(evidence, owner, closed, issues)
    check(checks, 'worker_event_log_available', worker['log_available_and_parse_complete'], issues)
    check(checks, 'worker_terminal_geometry_file_checks', worker['execute_terminal_checks_passed'], issues)
    wc = worker.get('worker_closed') or {}
    check(checks, 'worker_initial_final_fingerprints', wc.get('initial_geometry_fingerprint') == wc.get('final_geometry_fingerprint')
          if wc.get('initial_geometry_fingerprint') is not None else None, issues)
    native_close = closed.get('native_close') or {}
    check(checks, 'native_close_file_checks', native_close.get('source_file_unchanged') is True
          and native_close.get('protected_files_unchanged') is True if native_close else None, issues)
    check(checks, 'zero_public_images', bridges['counts'].get('image_blocks', 0) == 0 and not worker['render_events'], issues)
    check(checks, 'attempt_byte_ledger_sum', tools.get('declared_response_wire_bytes') == tools.get('sum_recorded_response_bytes')
          if tools['attempts'] is not None else None, issues)
    check(checks, 'owner_response_bytes_actual_binding', tools.get('response_wire_bytes_verified'), issues)
    check(checks, 'public_response_byte_total_binding', tools.get('declared_response_wire_bytes') == bridges['counts'].get('tool_rx_bytes', 0)
          if tools['attempts'] is not None else None, issues)
    check(checks, 'actor_close_attempt_count_binding', closed.get('tool_attempts') == tools['attempts']
          if tools['attempts'] is not None else None, issues)
    trace_events = evidence.jsonl(owner/'audit.jsonl', issues)
    trace_pids = sorted({event['trace']['pid'] for event in trace_events if isinstance(event.get('trace'), dict)
                         and type(event['trace'].get('pid')) is int})
    endpoint = evidence.json(folder/'ENDPOINT.json', issues) or {}
    launch = evidence.json(folder/'ACTOR_LAUNCH.json', issues) or {}
    actor_pids = [p for p in (identity.get('actor_pid'), closed.get('actor_pid'), endpoint.get('actor_pid')) if p is not None]
    check(checks, 'actor_actual_pid_consistent', len(set(actor_pids)) == 1 if actor_pids else None, issues)
    check(checks, 'actor_launcher_pid_consistent', launch.get('launcher_pid') == finished.get('actor_launcher_pid')
        if launch.get('launcher_pid') is not None and finished.get('actor_launcher_pid') is not None else None, issues)
    prompt_duration = (consumer['final_received_ns']-consumer['prompt_submitted_ns']
        if type(consumer.get('final_received_ns')) is int and type(consumer.get('prompt_submitted_ns')) is int else None)
    check(checks, 'prompt_to_final_timestamp_binding', prompt_duration == consumer.get('prompt_to_final_ns'), issues)
    public_completion_times = [event.get('perf_ns') for event in events
        if event.get('event',event).get('type') == 'turn.completed' or
        (event.get('event',event).get('type') == 'item.completed'
         and event.get('event',event).get('item',{}).get('type') == 'agent_message')]
    completion_within = (all(type(value) is int and consumer['started_ns'] <= value < consumer['deadline_ns']
        for value in public_completion_times) if public_completion_times else None)
    oversized = [item for item in tools.get('rows', []) if type(item.get('attempt')) is int
                 and item['attempt'] > plan['tool_attempts']]
    attempt_budget = (all(item.get('is_error') and 'common_tool_attempt_budget' in
        str((item.get('exception') or {}).get('message','')) for item in oversized)
        if tools['attempts'] is not None else None)
    code_overflow = [item for item in tools.get('native_code_sizes', []) if item['bytes'] > plan['code_bytes']]
    code_budget = all(any(row.get('attempt') == item['attempt'] and row.get('is_error')
        and 'code_bytes' in str((row.get('exception') or {}).get('message','')) for row in tools.get('rows', []))
        for item in code_overflow) if tools['attempts'] is not None else None
    pipe_bytes = bridges['counts'].get('tool_rx_bytes', 0)
    physical_guard = (worker['max_execute_sequence'] <= plan['physical_RPC_limit']
        if worker['max_execute_sequence'] is not None and worker['log_available_and_parse_complete'] else None)
    whole_cell = consumer.get('total_task_wall_ns')
    budget = dict(public_completion_before_450s_deadline=completion_within,
        whole_cell_within_570s=whole_cell <= plan['total_cell_seconds']*1e9 if type(whole_cell) is int else None,
        all_over_32_attempts_guard_rejected=attempt_budget, over_32_attempt_count=len(oversized),
        public_tool_delivery_within_1MiB=pipe_bytes <= plan['tool_response_bytes'],
        oversized_native_code_guard_rejected=code_budget, oversized_native_code_attempts=code_overflow,
        accepted_native_execute_sequence_within_128=physical_guard,
        worker_guard_semantics='execute sequence is bounded; close bypasses that guard; rejected physical attempts remain counted')
    check(checks, 'accepted_attempt_budget', attempt_budget, issues)
    check(checks, 'public_delivery_byte_budget', budget['public_tool_delivery_within_1MiB'], issues)
    check(checks, 'accepted_native_code_budget', code_budget, issues)
    check(checks, 'native_execute_guard_budget', physical_guard, issues)
    check(checks, 'completed_public_session_within_deadline', completion_within, issues)
    critical = ('slot_binding','actor_asset_and_slot_binding','model_input_hash_and_bytes','model_and_requested_effort',
        'public_consumer_isolation_flags','absolute_session_budget','initial_frozen_world_mesh_binding',
        'final_initial_mesh_equal','initial_actual_worker_receipt_binding','final_actual_worker_receipt_binding',
        'source_identity_binding','owned_asset_source_unchanged',
        'owner_lifecycle_confirmed','public_fresh_thread_binding','public_final_message_binding',
        'owner_attempt_ledger_complete','public_owner_tool_requests_match','public_owner_tool_responses_match',
        'public_catalogue_observed','public_expected_replies_present','zero_public_images',
        'worker_event_log_available','owner_response_bytes_actual_binding','public_response_byte_total_binding',
        'accepted_attempt_budget','public_delivery_byte_budget','accepted_native_code_budget',
        'native_execute_guard_budget','completed_public_session_within_deadline',
        'public_cli_tool_outcomes_match_wire','actual_initialize_identity_matches_owner',
        'actual_controlled_serve_and_pin_binding','group_specific_public_read_schemas_bound',
        'actual_ordinary_catalogue_bound_to_this_release')
    row.update(protocol_completed=public_complete,
        reported_cli_valid_completion=consumer.get('valid_completion'),
        protocol_audit_passed=public_complete and all(checks.get(name) is True for name in critical) and not issues,
        thread_id=consumer.get('thread_id'), public_turn_completed_count=turn_count,
        consumer_status=consumer.get('status'), consumer_errors=consumer.get('errors', []),
        unexpected_tools=consumer.get('unexpected_tool_deviations', []),
        deadline_timer_fired=consumer.get('deadline_timer_fired'), safe_to_continue_record=consumer.get('safe_to_continue'),
        prompt_to_final_ns=consumer.get('prompt_to_final_ns'), cli_wall_ns=consumer.get('wall_ns'),
        total_task_wall_ns=consumer.get('total_task_wall_ns'), setup_ns=consumer.get('pre_consumer_setup_ns'),
        owner_finish_ns=finished.get('finish_elapsed_ns'), actor_startup_ns=identity.get('startup_ns'),
        owner_close_ns=closed['ended_ns']-closed['started_ns'] if 'ended_ns' in closed and 'started_ns' in closed else None,
        tool_attempts=tools['attempts'], native_attempts=tools.get('native_attempts'), plugin_attempts=tools.get('plugin_attempts'),
        scene_observe_attempts=tools.get('scene_observe_attempts'),
        connection_status_attempts=tools.get('connection_status_attempts'),
        all_plugin_read_attempts=tools.get('all_plugin_read_attempts'),
        tool_errors=tools.get('errors'), tool_time_ns=tools.get('tool_time_ns'),
        physical_worker_requests=worker['physical_requests'],
        public_catalogue_rx_bytes=bridges['counts'].get('catalogue_rx_bytes', 0),
        public_tool_rx_bytes=bridges['counts'].get('tool_rx_bytes', 0),
        public_tool_text_bytes=bridges['counts'].get('tool_text_bytes', 0),
        public_stdio_tx_bytes=bridges['counts'].get('stdio_tx_bytes', 0),
        public_stdio_rx_bytes=bridges['counts'].get('stdio_rx_bytes', 0),
        plugin_pipe_tx_bytes=peer.get('tx_bytes'), plugin_pipe_rx_bytes=peer.get('rx_bytes'),
        public_bridge=bridges, owner_tools=tools, plugin_peer=peer, native_worker=worker, usage=usage,
        budget_accounting=budget,
        pids=dict(actor_actual=actor_pids[0] if len(set(actor_pids)) == 1 else None,
            actor_launcher=launch.get('launcher_pid'), consumer_popen=consumer.get('consumer_pid'),
            serve_launcher=peer.get('serve_launcher_pid'), serve_actual_from_trace=trace_pids,
            blender_actual=worker.get('blender_actual_pid'), attachment_actual=bridges['attachment_actual_pids'],
            consumer_actual_unless_separately_attested=None, final_process_scan='root CIM cleanup separate'),
        provider_retry_observations=consumer.get('provider_retry_observations', []),
        final_text_sha256=None if consumer.get('final') is None else digest(consumer['final'].encode('utf8')),
        final_text_bytes=consumer.get('output_text_bytes'), provider_request_count=None, fees=None, resolved_effort=None)
    # A missing thin-client EXIT is not a source mismatch or an unresolved
    # already-recorded request. Keep the strict graceful-receipt audit false,
    # and expose narrower independently attested outcomes/cleanup separately.
    missing_exit = [issue for issue in issues if issue.get('code') == 'missing_bridge_exit']
    row['limitations'] = [dict(code='client_graceful_shutdown_unattested', path=item['path'],
        scope='no EXIT.json; do not infer normal EOF or termination mechanism') for item in missing_exit]
    outcome_checks = ('public_fresh_thread_binding','public_final_message_binding',
        'public_final_timestamp_binding','public_turn_timestamp_binding',
        'usage_record_matches_public_turn_events','usage_counters_nonnegative_integers',
        'owner_attempt_ledger_complete','public_owner_tool_requests_match','public_owner_tool_responses_match',
        'public_catalogue_observed','public_expected_replies_present','public_frames_parseable',
        'public_request_response_ids_match','public_cli_tool_outcomes_match_wire',
        'owner_response_bytes_actual_binding','public_response_byte_total_binding','attempt_byte_ledger_sum')
    row['recorded_request_outcomes_audit_passed'] = public_complete and all(checks.get(name) is True for name in outcome_checks)
    cleanup = cleanup or {}
    absent = {item['pid'] for item in cleanup.get('pids', []) if item.get('present') is False}
    present = {item['pid'] for item in cleanup.get('pids', []) if item.get('present') is True}
    known = {value for value in row['pids'].values() if type(value) is int}
    known.update(trace_pids); known.update(bridges['attachment_actual_pids'])
    coverage = bool(known) and known <= absent
    row['cleanup_snapshot_binding'] = dict(known_recorded_pids=sorted(known),
        all_known_pids_absent=coverage, known_pids_missing_from_snapshot=sorted(known-absent-present),
        known_pids_present=sorted(known & present),
        owned_path_scan_empty=cleanup.get('owned_path_scan_empty'),
        scope=cleanup.get('scope'), fresh_process_enumeration_performed=False)
    backend_checks = ('actor_asset_and_slot_binding','initial_frozen_world_mesh_binding','final_initial_mesh_equal',
        'initial_actual_worker_receipt_binding','final_actual_worker_receipt_binding','source_identity_binding',
        'actual_initialize_identity_matches_owner','actual_controlled_serve_and_pin_binding',
        'group_specific_public_read_schemas_bound','actual_ordinary_catalogue_bound_to_this_release',
        'owned_asset_source_unchanged','owner_lifecycle_confirmed','worker_event_log_available',
        'worker_terminal_geometry_file_checks','worker_initial_final_fingerprints','native_close_file_checks',
        'actor_actual_pid_consistent','actor_launcher_pid_consistent')
    row['owned_backend_cleanup_audit_passed'] = bool(all(checks.get(name) is True for name in backend_checks)
        and worker['close_attested_separately'] and coverage and cleanup.get('owned_path_scan_empty') is True)
    row['client_shutdown'] = dict(graceful_exit_attested=bridges['graceful_client_exit_attested'],
        missing_graceful_exit_receipts=bridges['missing_graceful_exit_receipts'],
        recorded_attachment_pids_absent=bool(bridges['attachment_actual_pids']) and
            set(bridges['attachment_actual_pids']) <= absent,
        mechanism='unknown_without_EXIT_receipt' if missing_exit else 'see_actual_EXIT_receipts',
        backend_owned_by_client=False)
    row['source_binding_evidence'] = dict(
        method='compact initialize canonical/count + full frozen manifest + independent current installed-source byte replay + actual pinned serve/config',
        actual_initialize_uses_source_file_count='source_file_count' in (identity.get('runtime_identity') or {}),
        actual_initialize_source_file_count=(identity.get('runtime_identity') or {}).get('source_file_count'),
        installed_manifest_replay_passed=(source_replays or {}).get(slot['group'], {}).get('passed')
            if slot['group'] != 'N' else None,
        source_replay_scope='current source bytes and frozen controlled-entry evidence; no claim to observe every transient filesystem change')
    row['operational_evidence_audit_passed'] = bool(row['recorded_request_outcomes_audit_passed']
        and row['owned_backend_cleanup_audit_passed'] and
        all(issue.get('code') == 'missing_bridge_exit' for issue in issues))
    owner_started, owner_ended = closed.get('started_ns'), closed.get('ended_ns')
    row['owner_lifetime_ns'] = owner_ended-owner_started if type(owner_started) is int and type(owner_ended) is int else None
    # CLOSE.started_ns is Owner construction time, not entry to close().
    row['owner_close_ns'] = None
    row['timing_intervals'] = dict(
        prompt_to_final_ns=row['prompt_to_final_ns'], cell_setup_ns=row['setup_ns'],
        consumer_through_cleanup_ns=row['cli_wall_ns'], whole_cell_ns=row['total_task_wall_ns'],
        owner_finish_inclusive_ns=row['owner_finish_ns'], owner_lifetime_ns=row['owner_lifetime_ns'],
        initial_geometry_QA_rpc_ns=(initial_receipt or {}).get('elapsed_ns'),
        final_geometry_QA_rpc_ns=(final_receipt or {}).get('elapsed_ns'),
        native_close_rpc_and_reap_ns=native_close.get('elapsed_ns'),
        product_close_ns=None, product_import_only_ns=None, semantic_review_QA_ns=None,
        consumer_post_process_exit_cleanup_ns=consumer['cleanup_end_ns']-consumer['process_exit_ns']
            if type(consumer.get('cleanup_end_ns')) is int and type(consumer.get('process_exit_ns')) is int else None,
        actor_prepare_to_owner_started_ns=owner_started-launch['started_ns']
            if type(owner_started) is int and type(launch.get('started_ns')) is int else None,
        scope='inclusive intervals overlap; initial QA is in setup, final QA/native close in owner_finish; no sums of nested durations')
    row['byte_accounting'] = dict(
        public_catalogue_rx_bytes=row['public_catalogue_rx_bytes'],
        public_full_tool_request_tx_bytes=bridges['counts'].get('tool_tx_bytes', 0),
        arguments_compact_reencoded_bytes=bridges['counts'].get('arguments_compact_reencoded_bytes', 0),
        arguments_scope='compact UTF-8 re-encoding of decoded params.arguments; not a literal wire slice or token count',
        actual_public_cli_tool_rx_bytes=row['public_tool_rx_bytes'],
        actual_public_cli_tool_text_utf8_bytes=row['public_tool_text_bytes'],
        proposed_before_budget_response_bytes_observed=tools.get('proposed_response_bytes_observed_sum'),
        proposed_before_budget_not_formed_attempts=tools.get('proposed_response_bytes_not_formed'),
        owner_charged_response_wire_bytes=tools.get('declared_response_wire_bytes'),
        internal_peer_rx_bytes=row['plugin_pipe_rx_bytes'], internal_peer_tx_bytes=row['plugin_pipe_tx_bytes'],
        scope='public CLI bytes are attested at MCP ingress, not provider transport or token charges; catalogue, tool delivery and internal pipe stay separate')
    return row


def analyze(root):
    evidence = Evidence(root); global_issues = []
    reused_path = HERE.parent/'native_plugin_complex_004/analyze.py'
    reused_raw = evidence.raw(reused_path, global_issues, True)
    if reused_raw is not None and digest(reused_raw) != REUSED_V2_SHA256:
        global_issues.append(dict(code='reused_v2_source_pin_mismatch', path=str(reused_path)))
    adapter_raw = evidence.raw(Path(__file__), global_issues, True)
    plan = evidence.json(evidence.root/'PLAN.json', global_issues, True)
    if not isinstance(plan, dict): raise ValueError('PLAN.json required; no trial execution is performed')
    sequence = plan.get('sequence', [])
    expected_keys = {(task, group, r) for task in TASKS for group in GROUPS for r in (1,2,3)}
    actual_keys = [(s.get('task'),s.get('group'),s.get('round')) for s in sequence]
    if (plan.get('denominator') != 18 or len(sequence) != 18 or len({s.get('cell') for s in sequence}) != 18
            or len(set(actual_keys)) != 18 or set(actual_keys) != expected_keys):
        raise ValueError('exact_18_slot_N_H_C_two_task_three_round_plan_required')
    source = evidence.json(evidence.root/'SOURCE_PREFLIGHT.json', global_issues, True) or {}
    if source.get('passed') is not True: global_issues.append(dict(code='source_preflight_not_passed'))
    source_replays = replay_source_manifests(evidence, source, global_issues)
    cleanup = evidence.json(evidence.root/'CLEANUP.json', global_issues) or {}
    run = evidence.json(evidence.root/'RUN_RESULT.json', global_issues) or {}
    run_rows = run.get('cells', [])
    if run and run.get('denominator') != 18: global_issues.append(dict(code='run_result_denominator_changed'))
    if len({r.get('cell') for r in run_rows}) != len(run_rows): global_issues.append(dict(code='duplicate_run_result_slot'))
    if any(r.get('cell') not in {s['cell'] for s in sequence} for r in run_rows): global_issues.append(dict(code='extra_run_result_slot'))
    extra_cells = [str(path) for path in (evidence.root/'cells').glob('*')
                   if path.is_dir() and path.name not in {slot['cell'] for slot in sequence}]
    if extra_cells: global_issues.append(dict(code='extra_cell_directories', paths=extra_cells))
    expected_meshes = {}
    for task in TASKS:
        raw = evidence.json(Path(plan['tasks'][task]['initial']), global_issues, True)
        if task == 'assembly' and isinstance(raw, dict): raw = raw.get('initial')
        expected_meshes[task] = normalized_mesh(raw)
        rules = evidence.raw(Path(plan['session_rules']), global_issues, True)
        prompt = evidence.raw(Path(plan['tasks'][task]['prompt']), global_issues, True)
        if rules is not None and prompt is not None:
            actual = rules+b'\n'+prompt
            binding = digest(actual) == plan['tasks'][task]['model_input_sha256'] and len(actual) == plan['tasks'][task]['model_input_bytes']
            if not binding: global_issues.append(dict(code='frozen_session_rules_prompt_binding_mismatch', task=task))
    freeze = evidence.json(evidence.root/'FREEZE.json', global_issues, True) or {}
    changed = []
    for path, want in freeze.get('files_sha256', {}).items():
        raw = evidence.raw(path, global_issues, True)
        if raw is not None and digest(raw) != want: changed.append(path)
    if changed: global_issues.append(dict(code='frozen_source_or_input_changed', paths=changed))
    rows = []
    for slot in sequence:
        try:
            rows.append(analyze_cell(evidence, slot, plan, source,
                next((r for r in run_rows if r.get('cell') == slot['cell']), None), expected_meshes[slot['task']],
                source_replays, cleanup))
        except Exception as exc:
            # Malformed partial evidence must not erase a denominator slot or
            # prevent analysis of all later sessions. It is explicitly unknown.
            rows.append(dict(slot, run_status='analysis_error',
                recorded=(evidence.root/'cells'/slot['cell']/'CONSUMER.json').is_file(),
                protocol_completed=False, quality_status='unreviewed',
                issues=[dict(code='cell_analysis_error', error=repr(exc))], checks={}))
    thread_ids = [row['thread_id'] for row in rows if row.get('thread_id')]
    if len(thread_ids) != len(set(thread_ids)):
        global_issues.append(dict(code='thread_id_reused_across_fresh_slots'))
    groups = {}
    for task in TASKS:
        groups[task] = {}
        for group in GROUPS:
            selected = [r for r in rows if r['task'] == task and r['group'] == group]
            groups[task][group] = dict(denominator=3, recorded=sum(r['recorded'] for r in selected),
                protocol_completed=sum(r['protocol_completed'] for r in selected),
                statuses=dict(Counter(r['run_status'] for r in selected)),
                metrics={key:summary([r.get(key) for r in selected],3) for key in METRICS},
                protocol_audit_passed=sum(bool(r.get('protocol_audit_passed')) for r in selected),
                recorded_request_outcomes_audit_passed=sum(bool(r.get('recorded_request_outcomes_audit_passed')) for r in selected),
                owned_backend_cleanup_audit_passed=sum(bool(r.get('owned_backend_cleanup_audit_passed')) for r in selected),
                usage={key:summary([r.get('usage', {}).get('observed_completed_turn_totals', {}).get(key)
                                   for r in selected],3) for key in TOKENS})
    result = dict(schema='native-plugin-complex-005-raw-metrics-v1', cycle_id=plan['cycle_id'],
        denominator=18, recorded=sum(r['recorded'] for r in rows),
        protocol_completed=sum(r['protocol_completed'] for r in rows),
        protocol_audit_passed=sum(bool(r.get('protocol_audit_passed')) for r in rows),
        recorded_request_outcomes_audit_passed=sum(bool(r.get('recorded_request_outcomes_audit_passed')) for r in rows),
        owned_backend_cleanup_audit_passed=sum(bool(r.get('owned_backend_cleanup_audit_passed')) for r in rows),
        operational_evidence_audit_passed=sum(bool(r.get('operational_evidence_audit_passed')) for r in rows),
        missing_graceful_client_exit_receipts=sum(r.get('client_shutdown',{}).get('missing_graceful_exit_receipts',0) for r in rows),
        normal_client_exit_receipts=sum(r.get('public_bridge',{}).get('graceful_exit_receipts',0) for r in rows),
        plugin_source_identity_bound=sum(r['group'] != 'N' and r.get('checks',{}).get('source_identity_binding') is True for r in rows),
        source_manifests_replayed=source_replays,
        audit_definitions=dict(
            protocol_audit_passed='strict original audit including actual normal thin-client EXIT receipts; not relaxed after observing results',
            recorded_request_outcomes_audit_passed='all recorded id TX have valid matching RX; exact CLI tool outcome/owner ledger/response-byte bindings; completed public turn',
            owned_backend_cleanup_audit_passed='frozen mesh/worker receipts/source replay/actual pinned serve/owner close plus root cleanup snapshot covers known PIDs',
            operational_evidence_audit_passed='known outcomes and owned backend audit, with no issue other than explicitly missing graceful thin-client EXIT',
            limitation='missing EXIT never proves normal EOF, shutdown mechanism, or absence of every unrecorded transient process/message'),
        not_recorded=sum(not r['recorded'] for r in rows), rows=rows, groups=groups,
        quality_status='pending_root_blind_semantic_review; no semantic correctness or benefit verdict',
        semantic_quality=None, issues=global_issues, changed_frozen_files=changed,
        source_and_plan_audit_passed=not global_issues,
        all_slots_protocol_audit_passed=not global_issues and all(row.get('protocol_audit_passed') is True for row in rows),
        all_slots_operational_evidence_audit_passed=not global_issues and all(row.get('operational_evidence_audit_passed') is True for row in rows),
        byte_scopes='public stdio catalogue/tool/control TX+RX and internal product stdio pipe are separate; do not sum as model input; native-worker TCP unmeasured',
        timing_scopes='all wall-clock fields inclusive; actor startup includes native/product startup; import alone unmeasured; no p95 claim from n=3',
        input_receipt_scope='producer hash/count before stdin write; not a provider token receipt',
        provider_request_count=None, fees=None, resolved_effort=None,
        script_sha256=digest(Path(__file__).read_bytes()), inputs_sha256=evidence.inputs,
        reused_complex004_final_v2_sha256=REUSED_V2_SHA256,
        producer_sources_sha256={str(Path(__file__).resolve()):digest(adapter_raw) if adapter_raw is not None else None,
            str(reused_path.resolve()):digest(reused_raw) if reused_raw is not None else None},
        plugin_attempt_scopes='plugin_attempts/scene_observe_attempts count observation attempts, not successful solves; connection_status_attempts separate; all_plugin_read_attempts includes both',
        catalogue_scopes='public N has Native only; H/C have common Native plus their own unchanged scene/status; internal ordinary catalogues remain release-specific H4/C5',
        new_model_calls=0, new_Blender_runs=0, new_product_calls=0,
        final_process_scan='root CIM cleanup separate; no process enumeration performed here')
    replaced = []
    result = finite_output(result, '$', replaced)
    result['nonfinite_raw_field_paths_replaced_with_unknown'] = replaced
    if replaced:
        result['source_and_plan_audit_passed'] = result['all_slots_protocol_audit_passed'] = False
        result['all_slots_operational_evidence_audit_passed'] = False
        result['issues'].append(dict(code='nonfinite_raw_values_retained_in_original_evidence', paths=replaced))
    return result


def self_test():
    # Synthetic parser checks only; deliberately no production module import.
    assert summary([1,None,3],3)['missing'] == 1
    assert summary([float('nan'),1,None],3)['reported'] == 1
    replaced = []
    assert finite_output({'counter':float('inf')},'$',replaced) == {'counter':None} and replaced
    event = {'type':'turn.completed','usage':{'input_tokens':10,'cached_input_tokens':4,'output_tokens':2}}
    consumer = {'usage_rows':[event['usage']], 'usage':event['usage']}
    usage = usage_from_events([{'event':event}],consumer)
    assert usage['consumer_record_agrees'] and usage['observed_completed_turn_totals']['input_tokens'] == 10
    assert usage['provider_request_count'] is None
    cfg, model, errors = parse_argv(['codex','exec','-c','model="gpt-6.1-sol"', '-c','model_reasoning_effort="medium"','-m','gpt-6.1-sol','-'])
    assert model == cfg['model'] and cfg['model_reasoning_effort'] == 'medium' and not errors
    with tempfile.TemporaryDirectory(prefix='complex004-analysis-fakes-') as temporary:
        root = Path(temporary); issues = []; evidence = Evidence(root)
        def save(path, value):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value), encoding='utf8')
        source_site = root/'synthetic_site'; source_site.mkdir()
        (source_site/'sample.py').write_bytes(b'fixture source only\n')
        members = [dict(path='sample.py',sha256=digest((source_site/'sample.py').read_bytes()))]
        full_identity = dict(schema_version='1.0',base_version='fixture',implementation_revision='r1',
            build_id_basis='runtime_source_bytes_and_version_metadata',source_kind='installed_distribution',
            distribution_version='fixture.lab',source_hash_exclusions=[],protocol_version='2025-03-26',mode='live',
            source_files=members)
        body = dict(base_version='fixture',implementation_revision='r1',files=members)
        fixed_sha = digest(json.dumps(body,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
        full_identity.update(source_sha256=fixed_sha,build_id='sha256:'+fixed_sha)
        source = {'versions':{'H':dict(identity=full_identity,runtime_sources=members,
            installed_root=str(source_site),entry='fixture-entry',source_sha256=fixed_sha)}}
        replay = replay_source_manifests(evidence,source,issues)['H']
        compact = {key:value for key,value in full_identity.items() if key != 'source_files'}
        compact.update(source_file_count=1,identity_check=dict(compatible=True,pins_requested=True,reasons=[],
            expected={'source_sha256':fixed_sha}))
        config = dict(source_sha256=fixed_sha,entry='fixture-entry',install_root=str(source_site))
        assert source_binding({'runtime_identity':compact},config,'H',source,replay) is True
        wrong_count = dict(compact,source_file_count=2)
        assert source_binding({'runtime_identity':wrong_count},config,'H',source,replay) is False
        (source_site/'sample.py').write_bytes(b'changed fixture source\n')
        changed = replay_source_manifests(evidence,source,[])['H']
        assert changed['passed'] is False and source_binding({'runtime_identity':compact},config,'H',source,changed) is False
        owner = root/'owner'; owner.mkdir()
        (owner/'CLOSE.json').write_text(json.dumps({'tool_attempts':0}),encoding='utf8')
        tools, requests, responses = owner_tools(evidence,owner,issues)
        assert tools['attempts'] == 0 and tools['ledger_complete'] and not requests and not responses
        worker = owner/'native'; worker.mkdir()
        (worker/'WORKER_EVENTS.jsonl').write_text(json.dumps(dict(sequence=1,started_ns=1,status='unknown',elapsed_ns=3))+'\n',encoding='utf8')
        (worker/'WORKER_CLOSED.json').write_text(json.dumps({'pid':123}),encoding='utf8')
        close = {'native_close':{'response':{'status':'closed'},'process_reaped':True,'exit_code':0},'worker_closed':{'pid':123}}
        result = worker_metrics(evidence,owner,close,issues)
        assert result['close_attested_separately'] and result['execute_requests_including_admin_and_plugin'] == 0
        assert result['physical_requests'] == 1 and not result['other_unlabelled_requests']
        failed_close = worker_metrics(evidence,owner,{'native_close':{'response':None}},issues)
        assert not failed_close['close_attested_separately'] and len(failed_close['other_unlabelled_requests']) == 1
        attempts = []
        public = root/'cell/attachments/bridge_fake'
        save(public/'STARTED.json', {'pid':345})
        tool_names = ('human_eye_scene_observe','execute_blender_code')
        totals = Counter()
        for number, name in enumerate(tool_names,1):
            request = {'jsonrpc':'2.0','id':1,'method':'tools/call',
                       'params':{'name':name,'arguments':{}}}
            response = {'jsonrpc':'2.0','id':1,'result':{'content':[{'type':'text',
                'text':json.dumps({'status':'error' if number == 1 else 'success'})}], 'isError':number == 1}}
            tx = public_wire(request); rx = public_wire(response)
            call = public/str(number).zfill(3); call.mkdir()
            (call/'TX.bin').write_bytes(tx); (call/'RX.bin').write_bytes(rx)
            totals.update(tx=len(tx),rx=len(rx))
            attempt = dict(attempt=number,name=name,elapsed_ns=number,response_bytes=len(rx),
                           produced_response_bytes=len(rx),exception=None,is_error=number == 1)
            attempts.append(attempt)
            call = owner/('tool_%02d' % number)
            save(call/'REQUEST.json',request); save(call/'ATTEMPT.json',attempt)
            save(call/('ERROR_RESPONSE.json' if number == 1 else 'RESPONSE.json'),response)
        save(owner/'TOOLS.json',dict(attempts=2,calls=2,wire_tool_bytes=totals['rx'],tools=attempts))
        save(public/'EXIT.json',dict(normal_exit=True,complete_tx_bytes=totals['tx'],complete_rx_bytes=totals['rx']))
        tools, owner_req, owner_rx = owner_tools(evidence,owner,issues)
        bridge, public_req, public_rx = bridge_metrics(evidence,root/'cell','H',None,issues)
        assert tools['attempts'] == 2 and tools['errors'] == 1 and tools['ledger_complete']
        assert tools['native_after_plugin_error_count'] == 1
        assert owner_req == public_req and owner_rx == public_rx and sum(public_req.values()) == 2
        assert bridge['counts']['tool_rx_bytes'] == totals['rx']
        # Coordinated wrong byte totals must fail against the actual response.
        tampered = [dict(item) for item in attempts]; tampered[0]['response_bytes'] += 1
        save(owner/'tool_01/ATTEMPT.json',tampered[0])
        save(owner/'TOOLS.json',dict(attempts=2,calls=2,wire_tool_bytes=totals['rx']+1,tools=tampered))
        checked, _, _ = owner_tools(evidence,owner,issues)
        assert checked['ledger_complete'] and not checked['response_wire_bytes_verified']
        absent = root/'owner_missing'; (absent/'native').mkdir(parents=True)
        unknown = worker_metrics(evidence,absent,{},issues)
        assert unknown['physical_requests'] is None and unknown['log_available_and_parse_complete'] is False
        peer = owner/'plugin'; tx = public_wire({'jsonrpc':'2.0','id':'init','method':'initialize'})
        rx = public_wire({'jsonrpc':'2.0','id':'wrong','result':{}})
        rec = dict(request_id='init',method='initialize',started_ns=1,elapsed_ns=1,
            sent_bytes=len(tx),attempted_send_bytes=len(tx),send_confirmed=True,received_bytes=len(rx),error=None)
        save(peer/'START.json',{'started_ns':0,'launcher_pid':567})
        save(peer/'001/RECEIPT.json',rec); (peer/'001/TX.bin').write_bytes(tx); (peer/'001/RX.bin').write_bytes(rx)
        save(peer/'RPC.json',dict(requests=[rec],tx_bytes=len(tx),rx_bytes=len(rx),poisoned=False))
        peer_issues = []; peer_metrics(evidence,owner,peer_issues)
        assert any(issue['code'] == 'internal_product_rx_id_mismatch' for issue in peer_issues)
        # Fixed full denominator survives a completely unstarted run.
        rules = root/'SESSION_RULES.txt'; rules.write_bytes(b'rules')
        sequence = []
        for task in TASKS:
            for group in GROUPS:
                for round_ in (1,2,3):
                    sequence.append(dict(cell=str(len(sequence)+1).zfill(2),task=task,group=group,round=round_))
        fake_plan = dict(cycle_id='synthetic-only',denominator=18,sequence=sequence,tasks={},
                         session_rules=str(rules),model='gpt-6.1-sol',requested_effort='medium',max_session_seconds=450,
                         total_cell_seconds=570,tool_attempts=32,code_bytes=262144,
                         tool_response_bytes=1048576,physical_RPC_limit=128)
        for task in TASKS:
            prompt = root/(task+'.txt'); prompt.write_bytes(task.encode())
            initial = root/(task+'.json')
            mesh = {'unit_scale_m':1.,'objects':[]}
            save(initial, {'initial':mesh} if task == 'assembly' else mesh)
            raw = rules.read_bytes()+b'\n'+prompt.read_bytes()
            fake_plan['tasks'][task] = dict(prompt=str(prompt),initial=str(initial),
                model_input_sha256=digest(raw),model_input_bytes=len(raw),asset_sha256='a'*64)
        save(root/'PLAN.json',fake_plan); save(root/'SOURCE_PREFLIGHT.json',{'passed':True})
        save(root/'FREEZE.json',{'files_sha256':{}})
        full = analyze(root)
        assert full['denominator'] == full['not_recorded'] == len(full['rows']) == 18
        assert all(full['groups'][task][group]['denominator'] == 3
                   for task in TASKS for group in GROUPS)
        # One fully bound synthetic session alongside 17 unstarted slots:
        # completion is based on public events and receipts, never exit0 alone.
        slot = sequence[0]; cell = root/'cells'/slot['cell']; own = cell/'owner'
        task = fake_plan['tasks'][slot['task']]; mesh = {'unit_scale_m':1.,'objects':[]}
        wc = dict(pid=2000,initial_geometry_fingerprint='same',final_geometry_fingerprint='same')
        receipt = dict(response={'status':'success','result':{'executed':True,'result':json.dumps(mesh)}},
                       source_file_unchanged=True,protected_files_unchanged=True)
        for label in ('INITIAL','FINAL'):
            save(own/(label+'.json'),mesh); save(own/(label+'.json.receipt.json'),receipt)
        save(cell/'ACTOR_CONFIG.json',dict(group='N',task='assembly',asset_sha256='a'*64))
        save(own/'IDENTITY.json',dict(runtime_identity=None,actor_pid=1000,actor_parent_pid=1001,
                                     asset_sha256='a'*64,startup_ns=1))
        save(cell/'ACTOR_LAUNCH.json',{'launcher_pid':1001}); save(cell/'ENDPOINT.json',{'actor_pid':1000})
        save(cell/'OWNER_FINISH.json',dict(confirmed=True,actor_exit=0,actor_launcher_pid=1001,finish_elapsed_ns=1))
        save(own/'CLOSE.json',dict(confirmed=True,actor_pid=1000,tool_attempts=0,asset_unchanged=True,
            worker_closed=wc,native_close=dict(response={'status':'closed'},process_reaped=True,exit_code=0,
                source_file_unchanged=True,protected_files_unchanged=True)))
        save(own/'native/READY.json',{'pid':2000}); save(own/'native/WORKER_CLOSED.json',wc)
        (own/'native/WORKER_EVENTS.jsonl').write_text('\n'.join(json.dumps(row) for row in (
            dict(sequence=1,started_ns=1,status='completed',script_sha256='s',terminal_geometry_and_file_checks_passed=True),
            dict(sequence=2,started_ns=2,status='completed',script_sha256='s',terminal_geometry_and_file_checks_passed=True),
            dict(sequence=3,started_ns=3,status='unknown',elapsed_ns=1)))+'\n',encoding='utf8')
        bridge = cell/'attachments/bridge_one'; save(bridge/'STARTED.json',{'pid':1003})
        tx = json.dumps({'jsonrpc':'2.0','id':1,'method':'tools/list'}).encode()
        rx = json.dumps({'jsonrpc':'2.0','id':1,'result':{'tools':[{'name':'execute_blender_code'}]}}).encode()
        (bridge/'001').mkdir(); (bridge/'001/TX.bin').write_bytes(tx); (bridge/'001/RX.bin').write_bytes(rx)
        save(bridge/'EXIT.json',dict(normal_exit=True,complete_tx_bytes=len(tx),complete_rx_bytes=len(rx)))
        argv = ['codex','exec','--ignore-user-config','--ignore-rules','--ephemeral','--strict-config','--json']
        for key,value in dict(model='gpt-6.1-sol',model_reasoning_effort='medium',forced_login_method='chatgpt',
                              sandbox_mode='read-only',web_search='disabled').items():
            argv.extend(('-c',key+'='+json.dumps(value)))
        argv.extend(('-m','gpt-6.1-sol','-'))
        usage = dict(input_tokens=10,cached_input_tokens=4,output_tokens=2)
        final = 'synthetic answer'
        consumer = dict(slot,argv=argv,model='gpt-6.1-sol',requested_effort='medium',started_ns=100,
            deadline_ns=450000000100,input_sha256=task['model_input_sha256'],input_text_bytes=task['model_input_bytes'],
            prompt_submitted_ns=110,final_received_ns=121,turn_completed_ns=122,prompt_to_final_ns=11,usage_rows=[usage],usage=usage,
            valid_completion=True,thread_id='synthetic-thread',exit_code=0,process_reaped=True,readers_stopped=True,
            errors=[],unexpected_tool_deviations=[],final=final,output_text_bytes=len(final.encode()))
        save(cell/'CONSUMER.json',consumer)
        (cell/'events.jsonl').write_text('\n'.join(json.dumps({'perf_ns':120+i,'event':event}) for i,event in enumerate((
            {'type':'thread.started','thread_id':'synthetic-thread'},
            {'type':'item.completed','item':{'type':'agent_message','text':final}},
            {'type':'turn.completed','usage':usage})))+'\n',encoding='utf8')
        full = analyze(root)
        assert full['recorded'] == full['protocol_completed'] == full['protocol_audit_passed'] == 1, full['rows'][0]
        assert full['denominator'] == 18 and full['not_recorded'] == 17
        # Ordinary client termination may lack EXIT; never synthesize it or
        # turn that into a source mismatch. Known outcomes/backend are separate.
        (bridge/'EXIT.json').unlink()
        save(root/'CLEANUP.json',dict(pids=[dict(pid=p,present=False) for p in (1000,1001,1003,2000)],
            owned_path_scan_empty=True,scope='synthetic terminal PID snapshot'))
        no_exit = analyze(root); first = no_exit['rows'][0]
        assert first['protocol_audit_passed'] is False
        assert first['recorded_request_outcomes_audit_passed'] and first['owned_backend_cleanup_audit_passed'], first
        assert first['operational_evidence_audit_passed'] and not first['client_shutdown']['graceful_exit_attested']
        assert first['limitations'] and not (bridge/'EXIT.json').exists()
        bad_reply = json.loads(rx); bad_reply['id'] = 'wrong'
        (bridge/'001/RX.bin').write_bytes(public_wire(bad_reply))
        wrong_id = analyze(root)['rows'][0]
        assert wrong_id['recorded_request_outcomes_audit_passed'] is False
        consumer['exit_code'] = 0; consumer['valid_completion'] = True
        (cell/'events.jsonl').write_text(json.dumps({'event':{'type':'turn.failed'}})+'\n',encoding='utf8')
        failed = analyze(root)
        assert failed['recorded'] == 1 and failed['protocol_completed'] == 0 and failed['denominator'] == 18
    return dict(passed=True, scope='synthetic records only', new_model_calls=0, new_product_calls=0, new_Blender_runs=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=HERE)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--run', action='store_true', help='Postprocess finished trial only after coordinator authorization')
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test())); return
    if not args.run:
        print(json.dumps(dict(mode='interface_only_no_trial_read', requires='--run after coordinator confirms formal completion',
            default_output='private/ANALYSIS_PENDING_QUALITY.json'))); return
    run_path = args.root/'RUN_RESULT.json'
    run = json.loads(run_path.read_bytes()) if run_path.is_file() else {}
    if type(run.get('ended_ns')) is not int:
        raise ValueError('formal_run_completion_receipt_required_before_postprocessing')
    output = args.output or args.root/'private/ANALYSIS_PENDING_QUALITY.json'
    if output.exists(): raise FileExistsError('postprocess_output_exists_preserve_prior_result')
    result = analyze(args.root)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf8',newline='\n') as stream:
        stream.write(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(output=str(output), denominator=18, recorded=result['recorded'],
        protocol_completed=result['protocol_completed'], quality='unreviewed')))


if __name__ == '__main__':
    main()
