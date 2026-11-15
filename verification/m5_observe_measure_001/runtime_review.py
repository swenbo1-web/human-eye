"""Saved-only final source, process, budget and complete-window cross-check.

Run only after the root confirms all twelve owned sessions are closed. This
module imports no product or harness and starts no host, raster or model.
"""
from collections import Counter
import ast
import base64
import hashlib
import io
import json
from pathlib import Path
import re
import statistics
import struct
import subprocess
import time
import zipfile
import zlib

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUNTIME = Path('D:/he_m5_observe_measure_001')
QUALIFICATIONS = ['A_qual', 'B_initial_qual', 'B_qual']
ORDER = ['A1', 'B1', 'B2', 'A2', 'A3', 'B3', 'A_task_only', 'B_task_only']
LIMITS = dict(Blender_start_attempts=12, qualification_rasters=36, formal_rasters=36, all_rasters=72)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    with Path(path).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')


class Review:
    def __init__(self):
        self.pins = {}
        self.checks = []
        self.sources = {}
        self.slots = []

    def check(self, name, condition):
        self.checks.append(dict(name=name, passed=bool(condition)))

    def pin(self, path):
        path = Path(path).resolve()
        raw = path.read_bytes()
        entry = dict(path=str(path), sha256=digest(raw), bytes=len(raw))
        old = self.pins.setdefault(str(path), entry)
        self.check('immutable:' + str(path), entry == old)
        return entry

    def load(self, path):
        self.pin(path)
        return read(path)

    def lines(self, path):
        self.pin(path)
        return [json.loads(line) for line in Path(path).read_bytes().splitlines() if line.strip()]

    def source(self, path):
        path = Path(path).resolve()
        if str(path) in self.sources:
            return self.sources[str(path)]
        binding = self.load(path)
        manifest = binding['source_manifest']
        self.check('source141:' + str(path), len(manifest) == 141 and len({r['path'] for r in manifest}) == 141)
        identity = dict(base_version=binding['base_version'], implementation_revision=binding['implementation_revision'], files=manifest)
        encoded = json.dumps(identity, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()
        self.check('source_identity:' + str(path), digest(encoded) == binding['source_sha256'])
        install = Path(binding['install_root'])
        commit = binding['preparation_git']
        queries = ''.join(commit + ':' + row['path'] + '\n' for row in manifest).encode()
        process = subprocess.run(['git', 'cat-file', '--batch'], cwd=ROOT, input=queries,
                                 capture_output=True, check=True, timeout=60)
        output = io.BytesIO(process.stdout)
        git_rows = []
        for row in manifest:
            header = output.readline().decode().strip().split()
            if len(header) != 3 or header[1] != 'blob':
                raise ValueError('git_source_blob_missing:' + row['path'])
            blob = output.read(int(header[2]))
            if output.read(1) != b'\n':
                raise ValueError('git_batch_source_separator')
            installed = self.pin(install / row['path'])
            self.check('installed:' + binding['source_sha256'][:12] + ':' + row['path'], installed['sha256'] == row['sha256'])
            self.check('git_blob:' + commit[:12] + ':' + row['path'], digest(blob) == row['sha256'])
            git_rows.append(dict(path=row['path'], sha256=digest(blob), git_object=header[0], bytes=len(blob)))
        self.check('git_batch_consumed:' + commit[:12], output.read() == b'')
        wheel_directory = path.parent if path.name != 'A_RUN_BINDING.json' else HERE.parent / 'm4_target_acquisition_002/build_B'
        wheels = list(wheel_directory.glob('*.whl'))
        self.check('one_expected_wheel:' + str(path), len(wheels) == 1)
        if len(wheels) != 1:
            raise ValueError('version_wheel_ambiguous')
        wheel_pin = self.pin(wheels[0])
        self.check('wheel_digest:' + str(path), wheel_pin['sha256'] == binding['wheel_sha256'])
        with zipfile.ZipFile(wheels[0]) as wheel:
            for row in manifest:
                self.check('wheel_source:' + binding['source_sha256'][:12] + ':' + row['path'], digest(wheel.read(row['path'])) == row['sha256'])
        result = dict(binding_path=str(path), install_root=str(install), source_sha256=binding['source_sha256'],
            source_files=len(manifest), preparation_git=commit, wheel=wheel_pin, git_blobs=git_rows,
            source_scope='Each version checked against its own immutable installation, wheel and committed blobs. Current worktree may contain final B.')
        self.sources[str(path)] = result
        return result

    def wire(self, folder, binding):
        saved = self.load(folder / 'SAVED_WIRE.json')
        manifest = {row['path']: row['sha256'] for row in binding['source_manifest']}
        actual_payloads = []
        expected_steps = []
        for directory in sorted((folder / 'native/WIRE').glob('[0-9]*')):
            tx, rx = directory / 'REQUEST.bin', directory / 'RESPONSE.bin'
            a, b = self.pin(tx), self.pin(rx)
            request, response = read(tx), read(rx)
            sequence = int(directory.name)
            saved_row = next(row for row in saved['steps'] if row['sequence'] == sequence)
            self.check(folder.name + '/wire_bytes/' + directory.name,
                a['sha256'] == saved_row['request_sha256'] and b['sha256'] == saved_row['response_sha256']
                and a['bytes'] == saved_row['actual_TCP_TX_bytes'] and b['bytes'] == saved_row['actual_TCP_RX_bytes'])
            expected_steps.append(dict(sequence=sequence, type=request['type'], request_bytes=a['bytes'], response_bytes=b['bytes'],
                                       command=saved_row.get('command'), resources_forwarded=saved_row.get('resources_forwarded')))
            if request['type'] != 'execute_code':
                continue
            code = request['params']['code']
            self.check(folder.name + '/wire_script/' + directory.name,
                       digest(code.encode()) == saved_row['script_sha256'])
            for node in ast.walk(ast.parse(code)):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == 'compile' and len(node.args) >= 2):
                    continue
                expression = node.args[0]
                if not (isinstance(expression, ast.Call) and isinstance(expression.func, ast.Attribute)
                        and expression.func.attr == 'decompress'):
                    continue
                blob = zlib.decompress(base64.b64decode(ast.literal_eval(expression.args[0].args[0]), validate=True))
                loaded = Path(ast.literal_eval(node.args[1]))
                relative = loaded.relative_to(Path(binding['install_root'])).as_posix()
                self.check(folder.name + '/actual_TCP_loaded_source/' + relative,
                           digest(blob) == manifest[relative] == self.pin(loaded)['sha256'])
                actual_payloads.append(dict(path=relative, sha256=digest(blob), bytes=len(blob), wire_sequence=sequence))
            match = re.search(r'_request = _json.loads\((.+)\)\n', code)
            if match is not None:
                self.check(folder.name + '/actual_host_command/' + directory.name,
                           json.loads(ast.literal_eval(match.group(1))) == saved_row['command'])
        self.check(folder.name + '/actual_loaded_payload_list', actual_payloads == saved['loaded_source_payloads'])
        for row in saved['captures']:
            self.check(folder.name + '/original_decoded_capture/' + str(row['wire_sequence']),
                       self.pin(row['path'])['sha256'] == row['sha256'])
        index = self.load(folder / 'native/WIRE/INDEX.json')
        self.check(folder.name + '/all_wire_send_complete', len(index) == len(expected_steps)
                   and all(row['response_sendall_completed'] for row in index))
        return dict(steps=expected_steps, loaded_source_payloads=actual_payloads, captures=saved['captures'])

    def frame(self, folder, frame):
        image, arrays = Path(frame['image_path']).resolve(), Path(frame['arrays_path']).resolve()
        self.check(folder.name + '/frame_artifacts_inside_slot', image.is_relative_to(folder) and arrays.is_relative_to(folder))
        self.check(folder.name + '/frame_PNG_sha', self.pin(image)['sha256'] == frame['image_sha256'])
        self.check(folder.name + '/frame_NPZ_sha', self.pin(arrays)['sha256'] == frame['arrays_sha256'])
        with zipfile.ZipFile(arrays) as archive:
            for name, metadata in frame['arrays'].items():
                raw = archive.read(name + '.npy')
                self.check(folder.name + '/npy_magic/' + name, raw[:6] == b'\x93NUMPY')
                major = raw[6]
                header_size = 2 if major == 1 else 4
                length = struct.unpack('<H' if header_size == 2 else '<I', raw[8:8+header_size])[0]
                header = ast.literal_eval(raw[8+header_size:8+header_size+length].decode())
                payload = raw[8+header_size+length:]
                self.check(folder.name + '/npy_actual_array/' + name,
                    list(header['shape']) == metadata['shape'] and header['fortran_order'] is False
                    and len(payload) == metadata['nbytes'] and digest(payload) == metadata['sha256'])

    def slot(self, folder):
        folder = Path(folder).resolve()
        label = folder.name
        result = self.load(folder / 'RESULT.json')
        publication = self.load(folder / 'PUBLICATION.json')
        self.check(label + '/final_transport', publication['passed_transport_scope'] is True and result['errors'] == [])
        self.check(label + '/published_RESULT_bytes', publication['result_sha256'] == self.pin(folder / 'RESULT.json')['sha256'])
        self.check(label + '/full_clock_original600', publication['complete_session_ns'] == publication['result_published_ns']-result['started_ns']
            and result['original_owned_deadline_ns'] == result['started_ns']+600_000_000_000
            and publication['result_published_ns'] < result['original_owned_deadline_ns'])
        self.check(label + '/zero_model_paid', result['model_calls'] == result['paid_API_calls'] == 0)
        binding = self.load(result['binding_path'])
        expected_binding = (HERE/'A_RUN_BINDING.json' if label.startswith('A') else
            HERE/'build_initial/RUN_BINDING.json' if label=='B_initial_qual' else HERE/'build_final/RUN_BINDING.json')
        self.check(label + '/version_specific_binding_path', Path(result['binding_path']).resolve()==expected_binding.resolve())
        self.check(label + '/binding_sha', self.pin(result['binding_path'])['sha256'] == result['binding_sha256'])
        source = self.source(result['binding_path'])
        initialized = self.load(folder / 'INITIALIZE.json')['result']['_meta']['human_eye']
        self.check(label + '/actual_initialized_install_identity', initialized['source_kind'] == 'installed_distribution'
            and initialized['source_sha256'] == source['source_sha256'] == result['source_sha256'])
        native_spawn = self.load(folder / 'native/SPAWN.json')
        mcp_spawn = self.load(folder / 'stdio/SPAWN.json')
        mcp_start = self.load(folder / 'stdio/START.json')
        proof = self.load(folder / 'RUNTIME_PROOF.json')
        cleanup = result['cleanup']
        stdio = self.load(folder / 'stdio/CLOSE.json')
        native_closed = self.load(folder / 'native/WORKER_CLOSED.json')
        helper = HERE/'harness/state_owned_native.py' if label=='B_state' else HERE/'harness/reused/owned_native.py'
        self.check(label + '/actual_helper_source', self.pin(helper)['sha256']==native_spawn['helper_sha256'])
        self.check(label + '/MCP_process_identity', mcp_spawn['pid'] == mcp_start['pid'] == proof['runtime_pid']
            == proof['launcher_pid'] == stdio['pid'] and proof['confirmed'] is True)
        self.check(label + '/MCP_immediate_spawn_before_reader_ready', mcp_spawn['recorded_ns'] <= mcp_start['ready_ns'])
        self.check(label + '/MCP_held_exit_and_close', cleanup['MCP_retained']['confirmed'] is True
            and cleanup['MCP_retained']['exited'] is True and cleanup['MCP_retained']['exit_code'] == 0
            and cleanup['MCP_retained']['handle_closed'] is True)
        self.check(label + '/MCP_Popen_reader_pipes_closed', stdio['confirmed'] is True and stdio['exit_code'] == 0
            and stdio['reader_stopped'] is True and stdio['process_handle_closed'] is True
            and all(stdio['pipes_closed'].values()) and not stdio['errors'])
        self.check(label + '/native_owned_exit_reap', native_spawn['pid'] == native_closed['pid'] == cleanup['native']['pid']
            and cleanup['native']['exit_code'] == 0 and cleanup['native']['process_reaped'] is True
            and cleanup['native']['error'] is None)
        self.check(label + '/native_full_scene_restored', native_closed['poisoned'] is False
            and native_closed['final_geometry_fingerprint'] == native_closed['initial_geometry_fingerprint'])
        self.check(label + '/asset_original_copy_source_unchanged', cleanup['native']['source_file_unchanged'] is True
            and cleanup['native']['protected_files_unchanged'] is True
            and self.pin(folder / 'native/input.blend')['sha256'] == result['asset_sha256'])
        audit = self.lines(folder / 'audit.jsonl')
        self.check(label + '/every_original_audit_runtime_identity', all(
            row['pid'] == mcp_spawn['pid']
            and row['runtime_identity']['build_id'] == 'sha256:' + source['source_sha256']
            and row['identity_check']['compatible'] is True for row in audit))
        events = self.lines(folder / 'native/WORKER_EVENTS.jsonl')
        wire = self.wire(folder, binding)
        requests = []
        registered = self.load(HERE/'REQUESTS.json')
        if label=='B_state':
            state_registered = self.load(HERE/'STATE_REQUESTS.json')
            expected_requests=[]
            for stage in state_registered['order']:
                expected_requests.append(dict(state_registered['requests'][stage],id='m5_'+stage))
        else:
            key = 'task_only' if label.endswith('task_only') else 'A_main' if label.startswith('A') else 'B_main'
            expected_requests=registered[key]
        self.check(label + '/exact_registered_business_arguments',
                   [row['request'] for row in result['requests']]==expected_requests)
        producer_index = self.lines(folder / 'producer/INDEX.jsonl')
        for row in result['requests']:
            rid = row['id']
            receipt = row['receipt']
            original_receipt = self.load(folder / 'stdio' / ('rpc_' + str(receipt['index']).zfill(2)) / 'RECEIPT.json')
            self.check(label + '/original_client_receipt/' + rid, original_receipt == receipt)
            self.check(label + '/outer_original_call_clock/' + rid,
                row['complete_client_call_ns'] == row['completed_ns']-row['started_ns']
                and row['client_flush_to_received_ns'] == receipt['received_complete_ns']-receipt['stdin_flushed_ns']
                and row['client_internal_pre_receipt_ns'] == receipt['closed_ns']-receipt['started_ns'])
            server = row['server']
            self.check(label + '/server_own_clock/' + rid, server['request_to_reply_ns'] == server['reply_completed_ns']-server['request_received_ns'])
            self.check(label + '/four_independent_boundaries_inside_full_slot/' + rid,
                result['started_ns'] <= row['started_ns'] <= row['completed_ns'] <= publication['result_published_ns']
                and result['started_ns'] <= receipt['stdin_flushed_ns'] <= publication['result_published_ns']
                and result['started_ns'] <= receipt['received_complete_ns'] <= publication['result_published_ns']
                and result['started_ns'] <= server['request_received_ns'] <= server['reply_completed_ns'] <= publication['result_published_ns'])
            self.check(label + '/public_request30/' + rid, server['request_to_reply_ns'] <= 30_000_000_000)
            rpc = folder / 'stdio' / ('rpc_' + str(receipt['index']).zfill(2))
            self.check(label + '/original_stdio_RX_TX/' + rid,
                self.pin(rpc / 'RX.bin')['sha256'] == receipt['RX_sha256']
                and self.pin(rpc / 'RX.bin')['bytes'] == receipt['RX_bytes']
                and self.pin(rpc / 'TX.bin')['bytes'] == receipt['TX_bytes'])
            rx = (rpc/'RX.bin').read_bytes()
            self.check(label + '/actual_response_and_CRLF/' + rid,
                json.loads(rx) == row['response'] and json.loads((rpc/'TX.bin').read_bytes()) == row['request']
                and digest(rx.replace(b'\r\n',b'\n')) == server['RX_text_UTF8_LF_sha256'])
            archive = next(item for item in producer_index if item['index'] == row['producer_index'])
            self.check(label + '/same_producer_archive/' + rid, self.pin(archive['path'])['sha256'] == archive['sha256'])
            raw = self.load(archive['path'])
            context = self.load(archive['read_context'])
            for frame in raw.get('frames', []):
                self.frame(folder, frame)
            png_hashes = {frame['image_sha256'] for frame in raw.get('frames', [])}
            images = [block for block in row['response']['result']['content'] if block.get('type')=='image']
            self.check(label + '/actual_native_image_blocks/' + rid, len(images)==row['image_blocks']
                and all(digest(base64.b64decode(block['data'],validate=True)) in png_hashes for block in images))
            arrays = [mesh for selection in context['after']['selections'] for mesh in selection['mesh_arrays']]
            requests.append(dict(id=rid, complete_client_call_ns=row['complete_client_call_ns'],
                client_flush_to_received_ns=row['client_flush_to_received_ns'],
                client_internal_pre_receipt_ns=row['client_internal_pre_receipt_ns'],
                server_request_to_reply_ns=server['request_to_reply_ns'], original_stdio_RX_bytes=receipt['RX_bytes'],
                original_stdio_TX_bytes=receipt['TX_bytes'], server_LF_encoded_bytes=server['RX_text_UTF8_LF_bytes'],
                image_blocks=row['image_blocks'], producer_frames=len(raw.get('frames', [])),
                actual_work=raw.get('work'), stages=raw.get('stages'), normalized_retained_array_metadata=arrays,
                actual_allocation_count=None, actual_copy_count=None))
        control = None
        if label == 'B_state':
            control = self.load(folder / 'STATE_CONTROL.json')
            move = self.load(folder / 'native/M5_MATRIX_MOVE_RECEIPT.json')['response']['result']
            restore = self.load(folder / 'native/M5_MATRIX_RESTORE_RECEIPT.json')['response']['result']
            self.check(label + '/five_fixed_states_complete', control['transport_sequence_complete'] is True
                and len(control['completed_order']) == 5 and control['actual_fixture_matrix_setters'] == 2
                and control['product_setters'] == 0 and native_closed['m5_matrix_stage'] == 2)
            self.check(label + '/actual293_translation_and_restore', move['vertex_count'] == restore['vertex_count'] == 293
                and move['world_after'] == [[p[0]+.25,p[1],p[2]] for p in move['world_before']]
                and restore['world_after'] == move['world_before']
                and restore['matrix_after'] == move['matrix_before']
                and restore['after_fingerprint'] == move['before_fingerprint'])
        record = dict(label=label, phase=result['phase'], source_sha256=source['source_sha256'],
            binding_path=result['binding_path'], started_ns=result['started_ns'],
            complete_session_ns=publication['complete_session_ns'], business_windows=result['business_windows'],
            owned_lifecycle_ns=result['owned_lifecycle_ns'], setup_ns=result['setup_closed_ns']-result['started_ns'],
            requests=requests, actual_wire=wire, actual_worker_events=events, wrapper_work=result['wrapper_work'],
            cleanup=dict(MCP_Popen=stdio, MCP_retained=cleanup['MCP_retained'], Blender_Popen=cleanup['native'],
                Blender_individual_Win32_handle_close_receipt='unmeasured; owned Popen exit and wait/reap recorded',
                worker_close_event_status=events[-1]['status'],
                worker_close_event_scope='Generic unknown event retained independently of explicit closed RPC and held owned exit.'),
            state_control=control)
        self.slots.append(record)

    def budget(self):
        root = RUNTIME / 'budget'
        self.check('budget/frozen_limits', self.load(root / 'LIMITS.json') == LIMITS)
        claims = [self.load(path) for path in sorted((root / 'claims').glob('*.json'))]
        records = []
        counts = dict(starts=0, unknown_starts=0, qualification_actual=0, qualification_upper=0,
                      formal_actual=0, formal_upper=0, pending=0, failed_raster_settlements=0)
        starts_by_phase = Counter()
        for claim in claims:
            path = root / 'settlements' / (claim['token'] + '.json')
            settled = self.load(path) if path.exists() else None
            if settled is not None:
                self.check('budget/claim_hash/' + claim['token'], settled['claim_sha256']
                           == self.pin(root / 'claims' / (claim['token'] + '.json'))['sha256'])
            if claim['kind'] == 'Blender_start':
                counts['starts'] += 1
                starts_by_phase[claim['phase']] += 1
                counts['unknown_starts'] += settled is None or settled.get('spawn_status') == 'unknown'
            else:
                actual = None if settled is None else settled['actual_attempts']
                lower = 0 if settled is None else settled['confirmed_attempts_lower_bound']
                counts[claim['phase'] + '_actual'] += lower if actual is None else actual
                counts[claim['phase'] + '_upper'] += claim['reserved_upper_bound'] if actual is None else actual
                counts['pending'] += settled is None
                counts['failed_raster_settlements'] += bool(settled and settled['outcome'] == 'failed')
                if settled is not None:
                    evidence=settled['evidence']
                    audit_path=Path(evidence['audit_path'])
                    self.pin(audit_path)
                    original=audit_path.read_bytes()
                    tail=original[evidence['tail_start_bytes']:evidence['tail_start_bytes']+evidence['tail_bytes']]
                    self.check('budget/original_audit_byte_range/'+claim['token'],
                        len(tail)==evidence['tail_bytes'] and digest(tail)==evidence['tail_sha256'])
                    tail_rows=[json.loads(line) for line in tail.splitlines() if line.strip()]
                    render_events=[row for row in tail_rows if row.get('event')=='active_observation_render_attempt']
                    self.check('budget/per_request_actual_render_attempts/'+claim['token'],
                        render_events==evidence['render_attempt_events'] and actual==len(render_events))
            records.append(dict(claim=claim, settlement=settled))
        self.check('budget/twelve_owned_phase4plus8', counts['starts'] == 12 and starts_by_phase == {'qualification':4,'formal':8})
        self.check('budget/within_all_bounds', counts['qualification_upper'] <= 36
            and counts['formal_upper'] <= 36 and counts['qualification_upper']+counts['formal_upper'] <= 72)
        self.check('budget/no_unresolved_attempt', counts['unknown_starts'] == counts['pending'] == 0)
        actual_render_attempts = sum(len([line for line in self.lines(
            (RUNTIME/'control'/slot['label'] if slot['label']=='B_state' else RUNTIME/slot['phase']/slot['label'])/'audit.jsonl')
            if line['event']=='active_observation_render_attempt']) for slot in self.slots)
        self.check('budget/all_attempts_equal_original_audit_events', counts['qualification_actual']+counts['formal_actual'] == actual_render_attempts)
        return dict(limits=LIMITS, counts=counts, starts_by_phase=dict(starts_by_phase),
                    actual_render_attempt_events=actual_render_attempts, attempts_including_failures_unknown=records,
                    model_consumers=0, paid_API_calls=0,
                    scope='Reservation upper bounds and actual producer render-attempt events kept separate; failures count, unknown retains upper.')

    def history(self):
        baseline = self.load(HERE / 'BASELINE.json')
        self.check('asset/original_main_bytes_unchanged',
                   self.pin(baseline['asset']['path'])['sha256']==baseline['asset']['sha256'])
        manifest_count = members = 0
        for name, expected in baseline['protected_old_pins'].items():
            path = Path(name)
            self.check('history/protected_pin/' + name, self.pin(path)['sha256'] == expected)
            if path.name != 'CONTENT_MANIFEST.json':
                continue
            manifest_count += 1
            manifest = read(path)
            checkout = path.parents[2]
            for row in manifest['files']:
                member = checkout / row['path']
                actual = self.pin(member)
                self.check('history/member/' + str(member), actual['sha256'] == row['sha256'] and actual['bytes'] == row['bytes'])
                members += 1
        return dict(protected_pins=len(baseline['protected_old_pins']), manifests=manifest_count,
                    manifest_member_entries=members,
                    scope='Only registered old pins and their manifest-listed members. No recursive old-tree enumeration.')


def main():
    started = time.perf_counter_ns()
    review = Review()
    review.pin(__file__)
    gate = review.load(HERE / 'FORMAL_GATE.json')
    quality = review.load(HERE / 'QUALITY.json')
    quality_seal = review.load(HERE / 'QUALITY_SEAL.json')
    if (quality_seal.get('cost_unlocked') is not True or started <= quality_seal['sealed_ns']
            or quality_seal['quality_sha256'] != review.pin(HERE/'QUALITY.json')['sha256']):
        raise ValueError('root_quality_seal_required_before_paired_time_read')
    for label in QUALIFICATIONS:
        review.slot(RUNTIME / 'qualification' / label)
    review.slot(RUNTIME / 'control/B_state')
    for label in ORDER:
        review.slot(RUNTIME / 'formal' / label)
    formal = review.load(RUNTIME / 'formal/RUN_RESULT.json')
    review.check('formal/exact_once_eight_closed', formal['all_eight_transport_closed'] is True
        and [row['label'] for row in formal['records']] == ORDER and formal['dispatched'] == 8
        and formal['retries'] == formal['replacement_samples'] == 0 and formal['blocker'] is None)
    for row in gate['harness_pins']+gate['qualification_pins']:
        actual = review.pin(row['path'])
        review.check('formal/frozen_pin/' + row['path'], actual['sha256']==row['sha256'] and actual['bytes']==row['bytes'])
    budget = review.budget()
    history = review.history()
    correction = review.load(HERE/'STATE_LAUNCH_CORRECTION_01.json')
    review.check('preflight/isolated_import_failure_zero_actual',
        correction['Blender_starts_before']==correction['Blender_starts_after_failed_import']==3
        and correction['new_MCP_raster_model_paid_calls']==0 and correction['original_driver_changed'] is False
        and correction['initial_failure']=="ModuleNotFoundError: No module named run_case")
    slots = {row['label']:row for row in review.slots}
    pairs = []
    for i in (1,2,3):
        a,b = slots['A'+str(i)],slots['B'+str(i)]
        pairs.append(dict(pair=i, A_business_ns=a['business_windows'][0]['continuous_business_ns'],
            B_business_ns=b['business_windows'][0]['continuous_business_ns'],
            business_B_over_A=b['business_windows'][0]['continuous_business_ns']/a['business_windows'][0]['continuous_business_ns'],
            A_complete_session_ns=a['complete_session_ns'], B_complete_session_ns=b['complete_session_ns'],
            complete_session_B_over_A=b['complete_session_ns']/a['complete_session_ns']))
    ratio_business=statistics.median(row['business_B_over_A'] for row in pairs)
    ratio_complete=statistics.median(row['complete_session_B_over_A'] for row in pairs)
    faster=sum(row['business_B_over_A']<1 for row in pairs)
    report=dict(schema='m5-complete-runtime-review-v1', passed_checked_scope=all(row['passed'] for row in review.checks),
        qualification_only=False, started_ns=started, closed_ns=time.perf_counter_ns(),
        checks=review.checks, input_pins=list(review.pins.values()), source_versions=list(review.sources.values()),
        actual_slots=review.slots, actual_slot_count=len(review.slots), budget=budget, history=history,
        failed_preflight_retained=correction,
        author_association='Author implemented M5 engineering harness/passive archives and earlier saved qualification resource reports. This audit independently re-reads raw receipts and source/version material; no independent author claim.',
        diagnostic_edges_clarification=dict(B_initial_task_VFE_bytes=19748, retained_ReadContext_VF_bytes=13284,
            actual_vertex_bytes=7104, actual_face_bytes=6180, actual_edge_bytes=6464,
            edges=808, dtype_scope='vertices float64, faces/edges int32; retained context only lists V/F',
            actual_allocation_count=None, actual_copy_count=None),
        cost=dict(formal_main_pairs=pairs, median_business_B_over_A=ratio_business,
            median_complete_session_B_over_A=ratio_complete, B_faster_business_pairs=faster,
            registered_engineering_time_gate=ratio_business<=1.05 and ratio_complete<=1.05 and faster>=2,
            additional_10percent_benefit=ratio_business<=.9,
            task_only=dict(A=slots['A_task_only']['business_windows'],B=slots['B_task_only']['business_windows'],
                           scope='One diagnostic pair, no statistical benefit assertion'),
            model_calls=0, paid_API_calls=0, provider_billing_amount=None),
        quality_scope='Quality/source semantics accepted by separate saved review. This report verifies runtime provenance/counters/windows and does not substitute its own answers.',
        quality_report_schema=quality.get('schema'),
        clock_scope='Server and client transport preserve their own origin/completion samples within complete slot. No strict cross-process nesting added. Inclusive nested algorithm stages are not summed.',
        limitations=['Native fingerprint guard traversals remain source-derived with actual loop count unmeasured; their elapsed work remains inside clocks.',
            'Retained normalized array metadata and reported V/F/E payload bytes are representations. Allocation/copy counts, transient arrays and process memory attribution remain unmeasured.',
            'Worker generic close events may be unknown while explicit close response, matching final fingerprint and owned Popen exit/reap are recorded. These are distinct evidence.',
            'No model consumers or model quality comparison in M5. Task-only control is one pair. Engineering ratios apply to this fixed asset/task/installation only.'])
    write(HERE/'RUNTIME_REVIEW.json',report)
    write(HERE/'RUNTIME_COST_CROSSCHECK.json',dict(schema='m5-runtime-cost-crosscheck-v1',
        passed_checked_scope=report['passed_checked_scope'],qualification_only=False,
        author_association=report['author_association'],input_pins=report['input_pins'],cost=report['cost']))
    print(json.dumps(dict(passed=report['passed_checked_scope'], checks=len(review.checks),
        failed=sum(not row['passed'] for row in review.checks), owned=budget['counts']['starts'],
        raster_actual=budget['actual_render_attempt_events'], report_sha256=digest((HERE/'RUNTIME_REVIEW.json').read_bytes()))))


if __name__ == '__main__':
    main()
