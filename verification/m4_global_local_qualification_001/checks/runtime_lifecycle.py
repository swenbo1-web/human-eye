"""Audit this fixture preparation and three closed sessions using saved bytes."""

import ast
import base64
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import time
import zlib


NAMESPACE = Path(__file__).resolve().parent.parent
RUNTIME = Path('D:/he_m4_global_local_001')
LABELS = ('global', 'local_open', 'local_covered')
SOURCE = '7d2d4352f462c64a46e6fccf447c6f030c08b96e95517a3b2b6776ed50b69a6a'
CHECKS = []
PINS = {}


def check(name, value):
    CHECKS.append(dict(name=name, passed=bool(value)))


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    row = dict(path=str(path), sha256=digest(raw), bytes=len(raw))
    previous = PINS.setdefault(str(path), row)
    check('stable_input/' + str(path), previous == row)
    return row


def read(path):
    pin(path)
    return json.loads(Path(path).read_bytes())


def lines(path):
    pin(path)
    return [json.loads(row) for row in Path(path).read_bytes().splitlines() if row.strip()]


def check_pin(row):
    actual = pin(row['path'])
    check('declared_pin/' + row['path'], actual['sha256'] == row['sha256']
          and actual['bytes'] == row.get('bytes', actual['bytes']))


def geometry_rows(recipe):
    return {row['name']: dict(vertices=[[float(Fraction(value)) for value in point]
        for point in row['vertices_world_m']], triangles=row['triangles']) for row in recipe['objects']}


def fixture(recipe):
    binding = read(NAMESPACE / 'fixture/ASSET_BINDING.json')
    runtime_binding = read(RUNTIME / 'fixture/ASSET_BINDING.json')
    check('fixture/binding_original_copy', binding == runtime_binding)
    check('fixture/fixed_counts', recipe['counts'] == binding['counts']
          == dict(objects=9, vertices=54, triangles=56))
    for row in binding['input_pins'] + [binding[key] for key in
            ('geometry', 'builder', 'build_plan', 'readback_before_save', 'readback_after_reload')]:
        check_pin(row)
    check('fixture/current_asset_sha', pin(binding['asset_path'])['sha256'] == binding['asset_sha256'])
    before = read(binding['readback_before_save']['path'])
    after = read(binding['readback_after_reload']['path'])
    check('fixture/save_reload_exact', before == after)
    expected = geometry_rows(recipe)
    identity = [[int(i == j) for j in range(4)] for i in range(4)]
    for phase, data in (('before', before), ('after', after)):
        check('fixture/' + phase + '/scene', data['object_names'] == sorted(expected)
              and data['unit_system'] == 'METRIC' and data['scale_length'] == 1
              and data['frame'] == 1 and data['subframe'] == 0)
        for row in data['objects']:
            name = row['name']
            check('fixture/' + phase + '/' + name + '/identity',
                  row['matrix_world'] == row['evaluated_matrix_world'] == identity
                  and row['parent'] is None and row['modifiers'] == [])
            for mode in ('native', 'evaluated'):
                actual = row[mode]
                check('fixture/' + phase + '/' + name + '/' + mode,
                      actual['vertices_local'] == actual['vertices_world'] == expected[name]['vertices']
                      and actual['triangles'] == actual['polygons'] == expected[name]['triangles']
                      and actual['triangle_polygon_indices'] == list(range(len(expected[name]['triangles']))))
    preparation = read(RUNTIME / 'fixture_preparation/RESULT.json')
    check('fixture/one_separate_preparation_no_raster', preparation['Blender_process_attempts'] == 1
          and preparation['qualification_owned_starts'] == preparation['raster_attempts']
          == preparation['model_consumers'] == preparation['paid_API_calls'] == 0)
    check('fixture/preparation_held_close', preparation['status'] == 'completed'
          and preparation['errors'] == [] and preparation['exit_code'] == 0
          and preparation['process_reaped'] and preparation['Popen_handle_closed']
          and preparation['stdout_closed'] and preparation['stderr_closed']
          and preparation['retained_exit']['confirmed'] and preparation['retained_exit']['handle_closed']
          and preparation['retained_exit']['exit_code'] == 0)
    check('fixture/preparation_original600', preparation['deadline_ns'] == preparation['started_ns'] + 600_000_000_000
          and preparation['complete_ns'] == preparation['closed_ns'] - preparation['started_ns']
          and preparation['closed_ns'] < preparation['deadline_ns'])
    return dict(asset_sha256=binding['asset_sha256'], counts=binding['counts'],
                preparation=preparation, native_and_evaluated_exact=True)


def source():
    binding = read(NAMESPACE / 'B_RUN_BINDING.json')
    manifest = binding['source_manifest']
    for row in manifest:
        check('installed141/' + row['path'], pin(Path(binding['install_root']) / row['path'])['sha256'] == row['sha256'])
        check('worktree_product141/' + row['path'], pin(NAMESPACE.parents[1] / row['path'])['sha256'] == row['sha256'])
    identity = dict(base_version=binding['base_version'], implementation_revision=binding['implementation_revision'], files=manifest)
    actual = digest(json.dumps(identity, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode())
    check('source/fixed141_identity', len(manifest) == 141 and actual == binding['source_sha256'] == SOURCE)
    frozen = read(NAMESPACE / 'FROZEN.json')
    for row in frozen['files']:
        check('frozen/' + row['relative'], pin(NAMESPACE / row['relative'])['sha256'] == row['sha256'])
    return binding


def host_wire(folder, binding):
    index = read(folder / 'native/WIRE/INDEX.json')
    manifest = {row['path']: row['sha256'] for row in binding['source_manifest']}
    loaded, raw_scenes = [], []
    for row in index:
        root = folder / 'native/WIRE' / str(row['sequence']).zfill(3)
        request = read(root / 'REQUEST.bin')
        response = read(root / 'RESPONSE.bin')
        check(folder.name + '/wire_bytes/' + str(row['sequence']),
              (root / 'REQUEST.bin').stat().st_size == row['request_bytes']
              and (root / 'RESPONSE.bin').stat().st_size == row['response_attempted_bytes']
              and row['response_sendall_completed'] is True)
        check(folder.name + '/readonly_protocol/' + str(row['sequence']), request['type'] in ('execute_code', 'close'))
        stdout = response.get('result', {}).get('result', '')
        if isinstance(stdout, str):
            raw_scenes.extend(json.loads(line.split(':', 1)[1]) for line in stdout.splitlines()
                              if line.startswith('CURRENT_RAW_SCENE:'))
        if request['type'] != 'execute_code':
            continue
        for node in ast.walk(ast.parse(request['params']['code'])):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == 'compile' and len(node.args) >= 2):
                continue
            expression = node.args[0]
            if not (isinstance(expression, ast.Call) and isinstance(expression.func, ast.Attribute)
                    and expression.func.attr == 'decompress'):
                continue
            raw = zlib.decompress(base64.b64decode(ast.literal_eval(expression.args[0].args[0]), validate=True))
            path = Path(ast.literal_eval(node.args[1]))
            relative = path.relative_to(Path(binding['install_root'])).as_posix()
            check(folder.name + '/actual_loaded_source/' + relative,
                  digest(raw) == manifest[relative] == pin(path)['sha256'])
            loaded.append(dict(path=relative, sha256=digest(raw), wire_sequence=row['sequence']))
    check(folder.name + '/actual_blender_host_loaded', any(row['path'] == 'human_eye_plugin/blender_host.py' for row in loaded))
    return dict(index=index, loaded_source=loaded, raw_scenes=raw_scenes,
        request_bytes=sum(row['request_bytes'] for row in index),
        response_bytes=sum(row['response_attempted_bytes'] for row in index))


def session(label, binding, recipe, asset_sha):
    folder = RUNTIME / 'sessions' / label
    slot = read(folder / 'SLOT_RESULT.json')
    publication = read(folder / 'SLOT_PUBLICATION.json')
    close = read(folder / 'RUNTIME_CLOSE.json')
    runtime = close['runtime']
    clocks = slot['clocks']
    check(label + '/completed', slot['status'] == publication['status'] == 'completed'
          and slot['errors'] == close['errors'] == runtime['errors'] == [])
    check(label + '/absolute600', clocks['owned_deadline_ns'] == clocks['slot_started_ns'] + 600_000_000_000
          == runtime['owned_deadline_ns'] == runtime['consumer_deadline_ns'])
    check(label + '/published_result_and_clock', publication['result_sha256'] == pin(folder / 'SLOT_RESULT.json')['sha256']
          and publication['complete_slot_ns'] == publication['slot_result_published_ns'] - clocks['slot_started_ns']
          and publication['owned_budget_passed'] is True and publication['slot_result_published_ns'] < clocks['owned_deadline_ns'])
    config = read(folder / 'PRODUCT_CONFIG.json')
    check(label + '/public30', config['request_budget_s'] == config['blender']['timeout_s'] == 30
          and clocks['public_deadline_ns'] == min(clocks['owned_deadline_ns'], clocks['public_started_ns'] + 30_000_000_000)
          and clocks['public_returned_ns'] < clocks['public_deadline_ns'])
    initialized = read(folder / 'INITIALIZE.json')['result']['_meta']['human_eye']
    mcp_runtime = read(folder / 'mcp_io/RUNTIME.json')
    check(label + '/actual_source_identity', initialized['source_kind'] == 'installed_distribution'
          and initialized['source_sha256'] == runtime['product_source_sha256'] == mcp_runtime['source_sha256'] == SOURCE
          and mcp_runtime['algorithm_monkeypatches'] == 0)
    check(label + '/zero_model_paid_no_camera_override', slot['model_consumers'] == slot['paid_API_calls'] == 0
          and runtime['device']['external_camera_override'] is False)
    stdio = read(folder / 'mcp/CLOSE.json')
    check(label + '/stdio_reader_pipes_held_close', stdio['confirmed'] and stdio['exit_code'] == 0
          and stdio['reader_stopped'] and stdio['process_handle_closed'] and all(stdio['pipes_closed'].values())
          and stdio['errors'] == [])
    native = read(folder / 'native/WORKER_CLOSED.json')
    native_config = read(folder / 'native/CONFIG.json')
    check(label + '/blender_unsaved_geometry_unchanged', close['Blender_close']['exit_code'] == 0
          and close['Blender_close']['process_reaped'] and not native['poisoned']
          and native['initial_geometry_fingerprint'] == native['final_geometry_fingerprint']
          and close['Blender_status']['source_file_unchanged'] and close['Blender_status']['protected_files_unchanged']
          and pin(native_config['asset'])['sha256'] == pin(native_config['asset_copy'])['sha256'] == asset_sha)
    processes = {}
    for kind, proof_path, exit_row in (
            ('native', 'NATIVE_RUNTIME_PROOF.json', slot['cleanup']['native_retained_exit']),
            ('mcp', 'MCP_RUNTIME_PROOF.json', close['MCP_retained_exit'])):
        spawn = read(folder / kind / 'SPAWN.json')
        proof = read(folder / proof_path)
        check(label + '/held_process/' + kind, proof['confirmed'] and proof['runtime_pid'] == spawn['pid']
              and spawn['original_deadline_ns'] == clocks['owned_deadline_ns']
              and exit_row['confirmed'] and exit_row['exit_code'] == 0 and exit_row['exited'] and exit_row['handle_closed'])
        processes[kind] = dict(spawn=spawn, proof=proof, retained_exit=exit_row)
    check(label + '/native_Popen_handle_closed', slot['cleanup']['native_retained_exit']['Popen_handle_closed'] is True)
    wire = host_wire(folder, binding)
    expected = geometry_rows(recipe)
    saved = read(folder / 'SAVED_EVIDENCE.json')
    check(label + '/one_actual_raw_scene', len(wire['raw_scenes']) == len(saved['sources']) == 1)
    for source_row in saved['sources']:
        data = read(source_row['path'])
        check(label + '/raw_source_pin', pin(source_row['path'])['sha256'] == source_row['sha256'])
        geometry = {row['name']: dict(vertices=row['vertices'], triangles=row['triangles']) for row in data['objects']}
        actual_wire = wire['raw_scenes'][0]
        check(label + '/actual_raw_native_wire', actual_wire['objects'] == data['objects']
              and all(data['source'][key] == value for key, value in actual_wire['source'].items()))
        check(label + '/raw_whole_fixture_9_54_56', geometry == expected and data['source']['scale_length'] == 1
              and data['source']['asset_sha256'] == asset_sha and data['source']['pid'] == native_config['pid'])
    journal = lines(folder / 'PUBLIC_REQUESTS.jsonl')
    check(label + '/one_original_public_call', len(journal) == slot['public_requests_attempted'] == 1
          and journal == runtime['public_requests'])
    public = journal[0]
    request, response = read(public['request_path']), read(public['response_path'])
    check(label + '/registered_arguments', request['params']['arguments'] == read(NAMESPACE / 'REQUESTS.json')[label]
          and public['request'] == request and public['response'] == response
          and response.get('result', {}).get('isError') is False and 'error' not in response
          and 'post_reply_binding_error' not in public)
    check(label + '/actual_stdio_raw_json', read(public['actual_TX_path']) == request and read(public['actual_RX_path']) == response)
    for key in ('request', 'response', 'actual_TX', 'actual_RX'):
        check(label + '/public_pin/' + key, pin(public[key + '_path'])['sha256'] == public[key + '_sha256'])
    before_path, after_path = folder / 'product_calls/call_001/ARCHIVE_BEFORE.bin', folder / 'product_calls/call_001/ARCHIVE_AFTER.bin'
    pin(before_path)
    pin(after_path)
    index_path = folder / 'product_full/INDEX.jsonl'
    index = lines(index_path)
    check(label + '/one_actual_producer', len(index) == 1 and index[0]['index'] == public['producer_archive_index'] == 1
          and before_path.read_bytes() == b'' and after_path.read_bytes() == index_path.read_bytes()
          and public['started_ns'] <= index[0]['started_ns'] <= index[0]['producer_returned_ns'] <= public['closed_ns']
          and index[0]['new_observations_for_archive'] == 0)
    check(label + '/producer_result_sha', pin(index[0]['path'])['sha256'] == index[0]['sha256'])
    producer = read(index[0]['path'])
    read(index[0]['read_context'])
    server_rows = lines(folder / 'mcp_io/MCP_IO.jsonl')
    server = next(row for row in server_rows if row.get('response_id') == request['id'])
    receipt = read(folder / 'product_calls/call_001/RECEIPT.json')
    check(label + '/independent_clock_intervals', public['closed_ns'] >= public['started_ns']
          and receipt['received_complete_ns'] >= receipt['stdin_flushed_ns']
          and server['reply_completed_ns'] >= server['request_received_ns']
          and clocks['slot_started_ns'] <= server['request_received_ns'] < server['reply_completed_ns'] <= publication['slot_result_published_ns'])
    events = lines(folder / 'product_audit.jsonl')
    attempts = [row for row in events if row.get('event') == 'active_observation_render_attempt']
    worker = lines(folder / 'native/WORKER_EVENTS.jsonl')
    for frame in saved['frames']:
        check(label + '/frame_png_pin/' + frame['ref'], pin(frame['PNG'])['sha256'] == frame['PNG_sha256'])
        check(label + '/frame_npz_pin/' + frame['ref'], pin(frame['NPZ'])['sha256'] == frame['NPZ_sha256'])
    delivery = read(folder / 'delivered/DELIVERY.json')
    delivered = [base64.b64decode(block['data'], validate=True) for block in response['result']['content'] if block.get('type') == 'image']
    check(label + '/delivered_original_png_bytes', len(delivery['images']) == len(delivered)
          and all(pin(row['path'])['sha256'] == row['sha256'] == digest(raw)
                  and row['bytes'] == len(raw) for row, raw in zip(delivery['images'], delivered, strict=True)))
    return dict(label=label, status=slot['status'], processes=processes,
        complete_slot_ns=publication['complete_slot_ns'], public_client_call_ns=public['complete_client_call_ns'],
        public_flush_to_received_ns=public['client_flush_to_received_ns'],
        server_request_to_reply_ns=server['request_to_reply_ns'],
        request_raw_TX_bytes=pin(public['actual_TX_path'])['bytes'], reply_raw_RX_bytes=pin(public['actual_RX_path'])['bytes'],
        reply_server_UTF8_LF_bytes=server['RX_text_UTF8_LF_bytes'],
        actual_raster_attempt_events=len(attempts), actual_frame_count=len(saved['frames']),
        actual_public_image_count=len(delivered), host_wire=wire,
        worker_event_count=len(worker), generic_worker_close_response=close['Blender_close'].get('response'),
        work=producer.get('work'), stages=producer.get('stages'), wrapper_work=runtime['wrapper_work'])


def ledger(sessions):
    root = RUNTIME / 'budget'
    check('budget/limits', read(root / 'LIMITS.json') == dict(Blender_start_attempts=3, all_rasters=18, consumer_tasks=0))
    starts, raster, pending, unknown, consumers = [], 0, 0, 0, 0
    upper = 0
    for path in sorted((root / 'claims').glob('*.json')):
        claim = read(path)
        settlement_path = root / 'settlements' / (claim['token'] + '.json')
        settlement = read(settlement_path) if settlement_path.exists() else None
        check('budget/settled/' + claim['token'], settlement is not None)
        if settlement is not None:
            check('budget/claim_sha/' + claim['token'], settlement['claim_sha256'] == pin(path)['sha256'])
        if claim['kind'] == 'Blender_start':
            starts.append(dict(claim=claim, settlement=settlement))
            unknown += settlement is None or settlement.get('spawn_status') == 'unknown'
            check('budget/actual_spawn/' + claim['token'], settlement is not None and settlement.get('spawn_status') == 'spawned'
                  and settlement.get('pid') and settlement.get('outcome') == 'completed')
        elif claim['kind'] == 'consumer_task':
            consumers += 1
        elif claim['kind'] == 'raster_attempt':
            actual = None if settlement is None else settlement.get('actual_attempts')
            raster += actual if actual is not None else (settlement or {}).get('confirmed_attempts_lower_bound', 0)
            upper += claim['reserved_upper_bound'] if actual is None else actual
            pending += settlement is None
    actual_events = sum(row['actual_raster_attempt_events'] for row in sessions)
    check('budget/exact_three_owned_no_models', len(starts) == 3 and consumers == 0 and unknown == 0)
    check('budget/raster_actual_bounds', raster == actual_events and upper <= 18 and pending == 0)
    return dict(qualification_owned_starts=len(starts), preparation_processes=1,
        all_Blender_process_starts=len(starts)+1, owned_spawn_unknown=unknown,
        raster_attempts_actual=raster, raster_upper=upper, pending_raster_reservations=pending,
        consumers=consumers, paid_API_calls=0, starts=starts)


def main():
    started = time.perf_counter_ns()
    pin(__file__)
    recipe = read(NAMESPACE / 'fixture/GEOMETRY.json')
    fixture_result = fixture(recipe)
    binding = source()
    sessions = [session(label, binding, recipe, fixture_result['asset_sha256']) for label in LABELS]
    budget = ledger(sessions)
    result = dict(schema='m4-global-local-runtime-review-v1', qualification_only=True,
        passed_checked_scope=all(row['passed'] for row in CHECKS), checks=CHECKS,
        check_count=len(CHECKS), failed_checks=[row for row in CHECKS if not row['passed']],
        input_pins=list(PINS.values()), fixture=fixture_result, sessions=sessions, budget=budget,
        source_author_association='The reviewer authored the fixed fixture, constructor and this saved audit. Root authored and executed the qualification controller. Separate reviewers determine geometry and image qualification.',
        limits=['This audit checks saved lifecycle, source, bytes, budget and raw fixture readback. Geometry eligibility and image witness qualification are separate.',
                'The existing NativeSession guards traverse the full scene. Loop visits and allocation or copy counts were not instrumented.',
                'Server flush and client receipt use their own actual intervals. Cross-end completion timestamps are not required to nest.',
                'All slot times include readback, archival and cleanup through the saved result publication sample. They are qualification costs with zero model consumers.',
                'Actual raster attempts include failed construction. Reservations retain their upper bound until independently settled.'],
        started_ns=started, closed_ns=time.perf_counter_ns(), new_product_calls=0, new_Blender_starts=0, new_rasters=0)
    destination = NAMESPACE / 'RUNTIME_REVIEW.json'
    with destination.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps(dict(passed=result['passed_checked_scope'], checks=len(CHECKS),
                         failed=result['failed_checks'], sha256=hashlib.sha256(destination.read_bytes()).hexdigest())))


if __name__ == '__main__':
    main()
