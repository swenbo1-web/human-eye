"""Offline source, raw transport, work and lifecycle audit of the same five runs."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile


OUT = Path(__file__).resolve().parent
BATCH = OUT.parents[1]
ROOT = BATCH.parents[1]
RUN = BATCH / 'engineering/run_01'
INSTALL = BATCH / 'installation/run_01'
COMMIT = '452b44d2dcf231d6675bef54e568db0431a29261'
SOURCE = '4067c864c3db1ba586cd7179e6430db5acc4d71675b5295416d471632851a9f6'
WHEEL = 'f71c299926ebb38b1c09a2ca9b26a90416810b2407e3b955a43502ad86a55792'
EXPECTED = (
    ('base_default', None, 71, 112, 2),
    ('base_brief', 'brief', 71, 0, 3),
    ('base_full', 'full', 71, 0, 4),
    ('edit_default', None, 72, 10, 7),
    ('edit_full', 'full', 72, 0, 8),
)
CHECKS = []
SOURCES = {}


def check(condition, label):
    if not condition:
        raise AssertionError(label)
    CHECKS.append(label)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def raw(path):
    path = Path(path)
    data = path.read_bytes()
    name = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)
    SOURCES[name] = {'bytes': len(data), 'sha256': sha(data)}
    return data


def read(path):
    return json.loads(raw(path))


def lines(path):
    return [json.loads(line) for line in raw(path).splitlines() if line]


def git_blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def snapshot_fields(value):
    return {key: item for key, item in value.items() if key not in ('pid', 'blend_filepath')}


def main():
    ready = read(INSTALL / 'READY.json')
    fixed = read(INSTALL / 'FIXED_BUILD_INPUTS.json')
    receipt = read(INSTALL / 'receipt/ISOLATED_INSTALL.json')
    check(ready['commit'] == fixed['commit'] == receipt['fixed_commit'] == COMMIT, 'fixed committed candidate')
    check(ready['source_sha256'] == fixed['source_sha256'] == receipt['source_sha256'] == SOURCE, 'fixed runtime digest')
    check(ready['source_count'] == fixed['source_count'] == receipt['source_count'] == 138, '138 sources')
    check(ready['wheel_sha256'] == receipt['wheel_sha256'] == WHEEL, 'fixed wheel')
    check(ready['no_default_activation'] and not receipt['default_activation_changed']
          and not receipt['owned_reference_changed'], 'isolated installation receipt')
    tree_raw = subprocess.check_output(['git', 'ls-tree', '-rz', COMMIT], cwd=ROOT)
    tree = {entry.split(b'\t', 1)[1].decode(): entry.split(b'\t', 1)[0].split()[2].decode()
            for entry in tree_raw.split(b'\0') if entry}
    runtime = ast.parse(raw(ROOT / 'human_eye_plugin/runtime_identity.py'))
    constants = {node.targets[0].id: ast.literal_eval(node.value) for node in runtime.body
                 if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                 and node.targets[0].id in ('BASE_VERSION', 'IMPLEMENTATION_REVISION', '_ROOT_MODULES')}
    runtime_names = set(constants['_ROOT_MODULES']) | {
        name for name in tree if name.endswith('.py') and len(Path(name).parts) == 2
        and Path(name).parts[0] in ('human_eye_plugin', 'human_eye_module1_operators')}
    check({row['path'] for row in fixed['manifest']} == runtime_names, 'complete runtime manifest enumeration')
    wheel_paths = list((INSTALL / 'bundle').glob('*.whl'))
    check(len(wheel_paths) == 1 and sha(raw(wheel_paths[0])) == WHEEL, 'actual wheel bytes')
    source_root = INSTALL / ('source_' + COMMIT[:8])
    with zipfile.ZipFile(wheel_paths[0]) as wheel:
        for row in fixed['manifest']:
            relative = row['path']
            checkout = raw(ROOT / relative)
            check(git_blob(checkout) == tree[relative], 'commit source ' + relative)
            check(sha(checkout) == row['sha256'], 'manifest source ' + relative)
            check(raw(source_root / relative) == checkout, 'build source ' + relative)
            check(wheel.read(relative) == checkout, 'wheel source ' + relative)
            check(raw(Path(ready['install_root']) / relative) == checkout, 'installed source ' + relative)
    aggregate = {'base_version': constants['BASE_VERSION'],
                 'implementation_revision': constants['IMPLEMENTATION_REVISION'], 'files': fixed['manifest']}
    check(sha(json.dumps(aggregate, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()) == SOURCE,
          'independently recomputed source aggregate')
    check(sha(raw(Path(ready['entry']))) == ready['launcher_sha256'], 'entry bytes')
    check(sha(raw(Path(ready['release']) / 'admin/RUNTIME_BINDING.json')) == ready['binding_sha256'], 'runtime binding bytes')
    before = read(INSTALL / 'PROTECTED_BEFORE.json')
    after = read(INSTALL / 'PROTECTED_AFTER.json')
    check(after['all_unchanged'] and all(after['unchanged'].values()), 'recorded protected post-install hashes')
    for name, expected in before.items():
        path = Path(name)
        actual = sha(raw(path)) if path.is_file() else None
        check(actual == expected, 'protected current byte hash ' + name)

    binding = read(RUN / 'INPUT_BINDINGS.json')
    check(binding['ready'] == ready and binding['planned_business_rows'] == 5, 'run fixed ready and denominator')
    for name, expected in binding['files'].items():
        check(sha(raw(Path(name))) == expected, 'recorded input hash ' + name)
    runner_path = BATCH / 'engineering/run_candidate.py'
    runner_raw = raw(runner_path)
    check(sha(runner_raw) == binding['files'][str(runner_path.resolve())], 'controller source bound by pre-run recorded digest')
    runner_text = runner_raw.decode('utf8')
    check("check_deadline(deadline, 'before_final_verdict')" in runner_text
          and "'accepted_success': result['passed'] and complete_close_within_deadline" in runner_text,
          'historical deadline verdict path')
    config = read(RUN / 'config.json')
    session = read(RUN / 'native/SESSION.json')
    result = read(RUN / 'RESULTS.json')
    final = read(RUN / 'FINAL_TIMING.json')
    publication = read(RUN / 'TIMING_PUBLICATION.json')
    planned = read(RUN / 'PLANNED_ROWS.json')
    check([row['label'] for row in planned] == [row[0] for row in EXPECTED], 'fixed five slot order')
    check(result['execution_counts'] == {'attempted': 5, 'completed': 5, 'failed': 0, 'not_attempted': 0}, 'all original five retained')
    check(result['errors'] == [] and result['passed'] and result['source_files_unchanged'], 'recorded engineering checks')
    check(config['project_root'] == ready['install_root'] and config['expected_identity']['source_sha256'] == SOURCE,
          'configuration selects fixed installation')
    check(config['blender']['host'] == session['host'] == '127.0.0.1'
          and config['blender']['port'] == session['port'], 'configuration selects owned backend')
    check(not config['observe_on_prompt'] and config['request_budget_s'] == 30., 'ordinary fixed request budget')
    check(sha(raw(Path(session['asset']))) == sha(raw(Path(session['asset_copy']))) == session['asset_sha256']
          == binding['qualification']['asset_sha256'], 'original and private asset bytes')
    check(sha(raw(Path(session['blender']))) == session['blender_sha256'], 'recorded Blender executable')
    check(session['workspace'] == str((RUN / 'native').resolve()) and session['max_calls'] == 128, 'owned backend workspace and budget')
    check(sha(raw(Path(session['qa_pose_patch']['path']))) == session['qa_pose_patch']['sha256'], 'fixed registered pose patch')
    for state in ('base', 'edit'):
        snapshot = read(RUN / (state + '_ACTUAL_SNAPSHOT.json'))
        reference = read(ROOT / ('verification/m4_surface_scan_001/qualification/' + state.upper() + '_SNAPSHOT.json'))
        check(snapshot_fields(snapshot) == snapshot_fields(reference), state + ' complete qualified geometry')
        snapshot_receipt = read(RUN / (state + '_SNAPSHOT_RECEIPT.json'))
        check(json.loads(snapshot_receipt['response']['result']['result']) == snapshot, state + ' raw snapshot response')

    start = read(RUN / 'product/START.json')
    proof = read(RUN / 'RUNTIME_PROOF.json')
    initialize = read(RUN / 'INITIALIZE.json')
    identity = initialize['result']['_meta']['human_eye']
    check(identity['source_sha256'] == SOURCE and identity['source_file_count'] == 138
          and identity['source_kind'] == 'installed_distribution'
          and identity['distribution_version'] == ready['version'], 'actual initialize loaded identity')
    check(proof['confirmed'] and proof['launcher_pid'] == start['launcher_pid']
          and proof['runtime_pid'] != proof['launcher_pid'], 'actual runtime ancestry proof')
    check(start['command'] == [ready['dependency_python'], '-I', '-B', ready['entry'], 'serve', '--config', str(RUN / 'config.json')],
          'ordinary installed stdio command')
    tools = read(RUN / 'TOOLS.json')
    schema_tools = tools['result']['tools']
    check([item['name'] for item in schema_tools] == ['human_eye_scene_observe', 'human_eye_transform',
          'human_eye_connection_status', 'human_eye_clearance_segment', 'human_eye_arm_twist_observe'], 'ordinary full tool directory')
    observe = next(item for item in schema_tools if item['name'] == 'human_eye_scene_observe')
    detail = observe['inputSchema']['properties']['response_detail']
    check(detail['enum'] == ['full', 'brief'] and 'default' not in detail, 'conditional response detail schema')
    check('surface_scan defaults to brief' in detail['description'] and 'Other modes default to full' in detail['description'],
          'conditional default explanation')
    check('omitted response_detail or brief' in observe['description'] and 'Explicit full' in observe['description'],
          'ordinary observation display description')

    rpc = read(RUN / 'product/RPC.json')
    check(len(rpc['requests']) == 9 and not rpc['poisoned'], 'exact four metadata plus five business RPCs')
    check([row['method'] for row in rpc['requests'][:4]] == ['initialize', 'notifications/initialized', 'tools/list', 'ping'],
          'metadata-only prefix')
    raw_rpcs = []
    for index, record in enumerate(rpc['requests'], 1):
        folder = RUN / 'product' / str(index).zfill(3)
        tx = raw(folder / 'TX.bin')
        request = json.loads(tx)
        rx = raw(folder / 'RX.bin') if (folder / 'RX.bin').exists() else b''
        response = json.loads(rx) if rx else None
        check(read(folder / 'RECEIPT.json') == record, 'RPC receipt ' + str(index))
        check(record['method'] == request['method'] and record['request_id'] == request.get('id'), 'RPC request binding ' + str(index))
        check(record['sent_bytes'] == len(tx) and record['received_bytes'] == len(rx)
              and record['send_confirmed'] and record['error'] is None, 'RPC raw bytes ' + str(index))
        check(bool(rx) == ('id' in request), 'notification response scope ' + str(index))
        if response is not None:
            check(response['id'] == request['id'], 'response id ' + str(index))
        raw_rpcs.append((request, response, record))
    check(raw_rpcs[0][1] == initialize and raw_rpcs[2][1] == tools, 'raw initialize and directory bytes')
    check(rpc['tx_bytes'] == sum(row[2]['sent_bytes'] for row in raw_rpcs)
          and rpc['rx_bytes'] == sum(row[2]['received_bytes'] for row in raw_rpcs), 'complete stdio byte accounting')
    audit = lines(RUN / 'audit.jsonl')
    traces = [row for row in audit if row['event'] == 'request_trace']
    observations = [row for row in audit if row['event'] == 'observe']
    check(len(traces) == 6 and len(observations) == 5, 'startup and five actual observation traces')
    check({row['pid'] for row in traces} == {proof['runtime_pid']}, 'trace runtime pid binding')
    check(all(row['runtime_identity']['build_id'] == 'sha256:' + SOURCE for row in traces), 'trace loaded build identity')
    worker = lines(RUN / 'native/WORKER_EVENTS.jsonl')
    wire = read(RUN / 'native/WIRE/INDEX.json')
    check(len(wire) == len(worker) == 9, 'five captures plus four external QA/close RPCs')
    check(raw_rpcs[3][2]['started_ns'] + raw_rpcs[3][2]['elapsed_ns']
          <= proof['observed_ns'] <= proof['proved_ns'] <= worker[0]['started_ns'],
          'actual runtime proof after metadata and before first QA geometry')
    wire_data = {}
    for part in wire:
        sequence = part['sequence']
        folder = RUN / 'native/WIRE' / str(sequence).zfill(3)
        tx, rx = raw(folder / 'REQUEST.bin'), raw(folder / 'RESPONSE.bin')
        request, response = json.loads(tx), json.loads(rx)
        check(len(tx) == part['request_bytes'] and len(rx) == part['response_attempted_bytes']
              and part['response_sendall_completed'], 'host wire byte accounting ' + str(sequence))
        event = worker[sequence - 1]
        check(event['sequence'] == sequence, 'host worker sequence ' + str(sequence))
        if request['type'] == 'execute_code':
            code = request['params']['code']
            check(sha(code.encode('utf8')) == event['script_sha256'], 'host executed script hash ' + str(sequence))
            check(event['status'] == 'completed' and event['script_error'] is None, 'host script execution ' + str(sequence))
            check(event['changed_or_new_PNG_files'] == [] and event['terminal_geometry_and_file_checks_passed'],
                  'host readonly terminal scope ' + str(sequence))
        wire_data[sequence] = (request, response, event)
    business_rows = []
    for index, expected in enumerate(EXPECTED):
        label, detail, matches, kernels, sequence = expected
        row = result['business'][index]
        request, response, record = raw_rpcs[index + 4]
        check(row['state'] == label and row['response_detail'] == detail, 'business fixed slot ' + label)
        check(row['request'] == request == read(RUN / (label + '_REQUEST.json')), 'business raw request ' + label)
        args = request['params']['arguments']
        check(args['query'] == {'mode': 'surface_scan', 'threshold_m': .002}
              and args['include_image'] is False and args.get('response_detail') == detail,
              'ordinary scan query ' + label)
        check(('response_detail' in args) == (detail is not None), 'true default omission ' + label)
        check(row['response'] == response and row['stdio'] == record, 'business stdio response ' + label)
        check(not response['result']['isError'] and len(response['result']['content']) == 1
              and response['result']['content'][0]['type'] == 'text', 'text-only success ' + label)
        text = response['result']['content'][0]['text']
        value = json.loads(text)
        check(value == row['body'] and len(text.encode('utf8')) == row['business_text_utf8_bytes'], 'complete actual body bytes ' + label)
        check(len(value['matches']) == matches and value['delivery']['delivered_matches'] == value['delivery']['matches_total'] == matches,
              'actual match denominator ' + label)
        check(value['binding']['runtime_source_sha256'] == SOURCE, 'actual business source ' + label)
        if detail != 'full':
            check(value['display_encoding'] == 'surface-scan-task-table-v1' and len(text.encode('utf8')) <= 10240, 'compact byte gate ' + label)
        else:
            check('display_encoding' not in value and all('point_a_world' in part and 'point_b_world' in part for part in value['matches']),
                  'detailed witness structure ' + label)
        trace_id = value['trace_id']
        observation = next(item for item in observations if item['trace_id'] == trace_id)
        trace = next(item['trace'] for item in traces if item['trace_id'] == trace_id)
        check(observation['task_work'] == row['diagnostics'] and trace == row['trace'], 'business private audit binding ' + label)
        check(row['diagnostics']['kernel_calls'] == kernels and row['actual_host_RPC'] == 1,
              'actual kernel and capture count ' + label)
        host_request, host_response, event = wire_data[sequence]
        check(row['work_events'] == [event] and row['wire'] == [wire[sequence - 1]], 'business host wire binding ' + label)
        check(row['started_ns'] <= record['started_ns'] <= event['started_ns']
              <= record['started_ns'] + record['elapsed_ns'] <= row['ended_ns'] <= row['quality_check_end_ns'],
              'business ordered time chain ' + label)
        code = host_request['params']['code']
        check("getattr(_host, 'capture_surface_scan')" in code, 'one actual scan capture command ' + label)
        printed = host_response['result']['result']
        prefix = 'HUMAN_EYE_BLENDER_MCP:'
        check(printed.count(prefix) == 1, 'host response protocol marker ' + label)
        envelope = json.loads(printed.partition(prefix)[2].strip())
        capture = envelope['result']['capture']
        check(capture['work'] == row['diagnostics']['acquisition_work'], 'actual capture work binding ' + label)
        check(capture['threshold_m'] == .002
              and capture['result_kind'] == 'acquisition_only_not_surface_scan_result'
              and capture['scope'] == 'independent_static_triangle_meshes_current_evaluated_surfaces'
              and value['scope'] == 'all_scene_mesh_triangle_surfaces', 'host acquisition and outcome scopes ' + label)
        encode = [span for span in trace['spans'] if span['name'] == 'mcp.content_encode']
        projection = [span for span in trace['spans'] if span['name'] == 'mcp.surface_scan_compact_projection']
        check(len(encode) == 1 and len(projection) == int(detail != 'full'), 'actual display span count ' + label)
        if projection:
            check(encode[0]['start_offset_ns'] <= projection[0]['start_offset_ns']
                  and projection[0]['start_offset_ns'] + projection[0]['duration_ns']
                  <= encode[0]['start_offset_ns'] + encode[0]['duration_ns'], 'nested display span boundaries ' + label)
        business_rows.append({'slot': index + 1, 'label': label, 'matches': matches, 'kernel_calls': kernels,
            'host_capture_rpc': sequence, 'actual_host_captures': 1, 'body_utf8_bytes': len(text.encode('utf8')),
            'stdio_tx_bytes': record['sent_bytes'], 'stdio_rx_bytes': record['received_bytes'],
            'host_request_bytes': wire[sequence - 1]['request_bytes'], 'host_response_bytes': wire[sequence - 1]['response_attempted_bytes'],
            'host_capture_work': capture['work'], 'content_encode_ns': encode[0]['duration_ns'],
            'compact_projection_ns': projection[0]['duration_ns'] if projection else None})

    check(result['business'][0]['diagnostics']['measurement_cache_before']['measurement_entries'] == 0, 'initial engine cache empty')
    check(result['business'][0]['body']['binding'] == result['business'][1]['body']['binding'] == result['business'][2]['body']['binding'], 'BASE source binding equal')
    check(result['business'][3]['body']['binding'] == result['business'][4]['body']['binding']
          and result['business'][0]['body']['binding'] != result['business'][3]['body']['binding'], 'EDIT source binding updated')
    qa = [wire[sequence - 1] for sequence in (1, 5, 6, 9)]
    check(result['outside_business_RPC'] == qa, 'all external QA and close byte receipts')
    check(wire_data[1][0]['type'] == wire_data[6][0]['type'] == 'execute_code'
          and wire_data[1][0]['params']['code'] == wire_data[6][0]['params']['code'], 'two identical snapshot exporter calls')
    check(wire_data[5][0]['type'] == 'qa_advance' and wire_data[9][0]['type'] == 'close', 'one registered pose and close')
    check(wire_data[5][2]['target_name'] == 'Obj_008' and wire_data[5][2]['patch_sha256'] == session['qa_pose_patch']['sha256'], 'fixed pose target and hash')
    check(worker[-1]['status'] == 'unknown' and wire_data[9][1]['status'] == 'closed', 'close event script status unknown and actual close response')
    check(result['product_close']['confirmed'] and result['product_close']['process_reaped']
          and result['product_close']['reader_stopped'] and result['product_close']['exit_code'] == 0, 'owned product launcher closed')
    check(result['runtime_exit']['confirmed'] and result['runtime_exit']['handle_closed']
          and result['runtime_exit']['exit_code'] == 0, 'owned loaded runtime closed')
    check(result['native_close']['process_reaped'] and result['native_close']['exit_code'] == 0
          and result['native_close']['error'] is None and result['worker_closed']['qa_patch_applied'], 'owned Blender closed')
    check(not result['worker_closed']['poisoned'] and result['worker_closed']['final_geometry_fingerprint']
          == result['worker_closed']['accepted_geometry_fingerprint'], 'terminal registered geometry accepted')
    check(result['started_ns'] == final['started_ns']
          and result['deadline_ns'] == final['original_deadline_ns'] == session['deadline_ns']
          == result['started_ns'] + 590 * 10**9, 'same original 590-second deadline')
    check(result['product_close']['ended_ns'] <= result['runtime_exit']['observed_ns']
          <= worker[-1]['started_ns'] <= result['worker_closed']['closed_ns']
          <= result['business_and_owned_cleanup_end_ns'] <= final['business_receipts_closed_ns']
          <= publication['started_ns'] <= publication['closed_ns'], 'complete owned closure and receipt time chain')
    check(final['full_session_wall_ns'] == final['business_receipts_closed_ns'] - final['started_ns']
          and final['complete_business_write_close_within_original_deadline']
          == (final['business_receipts_closed_ns'] < final['original_deadline_ns']), 'complete deadline arithmetic')
    check(final['accepted_success'] == (result['passed'] and final['complete_business_write_close_within_original_deadline']) is True,
          'authoritative post-write-close accepted success')
    check(publication['publication_ns'] == publication['closed_ns'] - publication['started_ns'], 'separate timing publication')
    erratum = {
        'schema': 'runtime-proof-inherited-label-erratum-v1',
        'original_path': (RUN / 'RUNTIME_PROOF.json').relative_to(ROOT).as_posix(),
        'original_sha256': sha(raw(RUN / 'RUNTIME_PROOF.json')),
        'original_before_stdin': proof['before_stdin'],
        'before_stdin_field_is_valid_evidence': False,
        'correction_scope': 'metadata_complete_before_runtime_proof_before_first_QA_geometry',
        'original_file_modified': False,
        'actual_time_chain_ns': {
            'first_metadata_rpc_started': raw_rpcs[0][2]['started_ns'],
            'last_metadata_rpc_ended': raw_rpcs[3][2]['started_ns'] + raw_rpcs[3][2]['elapsed_ns'],
            'runtime_proof_observed': proof['observed_ns'],
            'runtime_proof_completed': proof['proved_ns'],
            'first_QA_geometry_request_started': worker[0]['started_ns'],
            'first_business_rpc_started': raw_rpcs[4][2]['started_ns'],
            'first_business_host_capture_started': worker[1]['started_ns'],
        },
        'identity_and_five_business_verdict': 'unchanged; the actual ancestry proof still precedes QA and business geometry',
    }
    erratum_path = OUT / 'RUNTIME_PROOF_ERRATUM.json'
    erratum_path.write_text(json.dumps(erratum, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    summary = {'schema': 'surface-scan-compact-five-originals-binding-review-v1', 'status': 'pass',
        'same_original_business_requests': 5, 'new_Blender_product_model_API_runs': 0, 'check_count': len(CHECKS),
        'commit': COMMIT, 'runtime_source_sha256': SOURCE, 'runtime_source_count': 138, 'wheel_sha256': WHEEL,
        'read_source_count': len(SOURCES), 'business': business_rows,
        'all_host_rpc': 9, 'business_host_rpc': 5, 'outside_business_rpc': 4,
        'outside_business': qa, 'outside_business_total_request_bytes': sum(row['request_bytes'] for row in qa),
        'outside_business_total_response_bytes': sum(row['response_attempted_bytes'] for row in qa),
        'stdio_metadata_calls': 4, 'stdio_business_calls': 5, 'stdio_tx_bytes': rpc['tx_bytes'], 'stdio_rx_bytes': rpc['rx_bytes'],
        'full_session_wall_ns': final['full_session_wall_ns'], 'accepted_success': final['accepted_success'],
        'runtime_proof_scope': 'after four metadata calls and before first QA snapshot or measured geometry',
        'retained_runtime_proof_label_issue': 'before_stdin=true is an inherited helper label inconsistent with actual metadata order; preserved unchanged, scope narrowed by raw monotonic timestamps',
        'runtime_proof_erratum_sha256': sha(erratum_path.read_bytes()),
        'loaded_runtime_pid': proof['runtime_pid'], 'owned_launcher_pid': proof['launcher_pid'],
        'owned_Blender_pid': session['pid'], 'source_files': SOURCES, 'checked_labels': CHECKS,
        'limitations': ['Current bytes and recorded loaded identity do not replay historical process memory.',
            'RUNTIME_PROOF.before_stdin=true is a retained inherited label; the verified scope is after metadata and before geometry.',
            'The product commit contains runtime sources; controller history is bound by its pre-run input digest and current matching bytes.',
            'Initial, edited and terminal checks have the recorded scope for reverted transient changes.',
            'Physical disk fsync, timing receipt publication own write and provider model consumption remain unmeasured.',
            'Close worker event keeps unknown script status, while its separate raw close response and owned reap are confirmed.',
            'This is a second audit of the same five original requests, with zero new live experiments.']}
    (OUT / 'BINDING_RESULT.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({key: value for key, value in summary.items()
                      if key not in ('source_files', 'checked_labels', 'business', 'outside_business')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
