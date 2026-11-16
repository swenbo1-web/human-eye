"""Independent saved-artifact source, cost, budget and lifecycle audit.

This program reads the pinned checkout, Git objects and retained files only.
It never imports the product or launches Blender, MCP or a model.
"""
from collections import Counter
from fractions import Fraction
from pathlib import Path
import ast
import base64
import hashlib
import io
import json
import subprocess
import zipfile
import zlib

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe')
NSREL = 'verification/m4_global_local_qualification_001'
NS = ROOT / NSREL
RUN = Path('D:/he_m4_global_local_001')
OUT = Path(__file__).resolve().parent
FINAL = '99f939513111637b76a1d486622b4841cad9ccda'
PREEXEC = 'caa3d9a94ef5e8fe36a173892ce97c5042e80cb7'
PRODUCT = 'ccb608aa83de4b0e6671da89e0c8f387bd3f800e'
SOURCE = '7d2d4352f462c64a46e6fccf447c6f030c08b96e95517a3b2b6776ed50b69a6a'
ASSET = 'a2d55e9212a84d27489aa72a680092b4e91d94d9df27d29c5de40d8a4ca3d0c6'
CHECKS = 0


def check(value, label):
    global CHECKS
    CHECKS += 1
    if not value:
        raise AssertionError(label)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load(path):
    return json.loads(Path(path).read_bytes())


def rows(path):
    return [json.loads(line) for line in Path(path).read_bytes().splitlines() if line.strip()]


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, check=True).stdout


def blobs(specifications):
    raw = subprocess.run(['git', 'cat-file', '--batch'], cwd=ROOT, check=True,
                         input=('\n'.join(specifications) + '\n').encode(), capture_output=True).stdout
    result, offset = [], 0
    for specification in specifications:
        end = raw.index(b'\n', offset)
        header = raw[offset:end].split()
        check(len(header) == 3 and header[1] == b'blob', 'Git blob ' + specification)
        length = int(header[2])
        first = end + 1
        data = raw[first:first + length]
        check(len(data) == length and raw[first + length:first + length + 1] == b'\n', 'Git length')
        result.append(data)
        offset = first + length + 1
    check(offset == len(raw), 'Git batch exhausted')
    return result


def pin(record):
    raw = Path(record['path']).read_bytes()
    check(sha(raw) == record['sha256'], 'Pinned SHA ' + record['path'])
    if 'bytes' in record:
        check(len(raw) == record['bytes'], 'Pinned length ' + record['path'])
    return raw


check(git('rev-parse', 'HEAD').decode().strip() == FINAL, 'Fixed author HEAD')
check(git('status', '--porcelain') == b'', 'Author clean')
baseline = load(NS / 'BASELINE.json')
manifest = load(NS / 'CONTENT_MANIFEST.json')
members = manifest['files']
check(len(members) == manifest['member_count'] == 379, '379 sealed members')
paths = [NSREL + '/' + row['relative'] for row in members]
manifest_path = NSREL + '/CONTENT_MANIFEST.json'
changed = git('diff', '--name-only', baseline['baseline_git'], FINAL).decode().splitlines()
check(len(changed) == 380 and set(changed) == set(paths + [manifest_path]), '380 Git changed paths')
check(all(path.startswith(NSREL + '/') for path in changed), 'Only qualification namespace')
for row, raw in zip(members, blobs([FINAL + ':' + path for path in paths])):
    check((NS / row['relative']).read_bytes() == raw, 'Member Git exact ' + row['relative'])
    check(sha(raw) == row['sha256'] and len(raw) == row['bytes'], 'Member identity')
check((NS / 'CONTENT_MANIFEST.json').read_bytes() == blobs([FINAL + ':' + manifest_path])[0], 'Manifest Git exact')

archive = load(NS / 'RUNTIME_ARCHIVE.json')
check(len(archive['files']) == archive['file_count'] == 261, '261 raw originals')
archived_paths = set()
archive_bytes = 0
for row in archive['files']:
    original_path = RUN / row['relative']
    check(original_path.resolve().is_relative_to(RUN.resolve()), 'Runtime boundary')
    original = original_path.read_bytes()
    check(original == (NS / row['archive']).read_bytes(), 'Archive byte exact')
    check(len(original) == row['bytes'] and sha(original) == row['sha256'], 'Archive identity')
    archived_paths.add(original_path.resolve())
    archive_bytes += len(original)
check(archive_bytes == archive['bytes'] == 4256890, '4,256,890 raw bytes')
check(archived_paths == {path.resolve() for path in RUN.rglob('*') if path.is_file()}, 'All runtime files included')
check(archive['runtime_exclusions'] == [], 'No runtime exclusions')

freeze = load(NS / 'FROZEN.json')
check(len(freeze['files']) == 47, '47 frozen files')
for row, old in zip(freeze['files'], blobs([PREEXEC + ':' + NSREL + '/' + row['relative'] for row in freeze['files']])):
    raw = (NS / row['relative']).read_bytes()
    check(raw == old, 'Preexecution source exact ' + row['relative'])
    check(len(raw) == row['bytes'] and sha(raw) == row['sha256'], 'Frozen identity')
preexec = load(NS / 'PREEXEC_GIT.json')
check(preexec['git'] == PREEXEC and preexec['qualification_starts_before_commit'] == 0
      and preexec['qualification_rasters_before_commit'] == 0, 'Freeze before qualification')
check(preexec['fixture_preparation_processes_already_completed'] == 1, 'Asset preparation earlier')
check(freeze['actual_qualification_starts'] == freeze['actual_qualification_rasters'] == 0, 'Zero qualification at freeze')
check(git('diff', PRODUCT, FINAL, '--', 'human_eye_plugin', 'human_eye_module1_operators',
          'human_eye_foveated_renderer.py', 'human_eye_hook.py') == b'', 'Product unchanged')
for row in baseline['protected_direct_seals']:
    pin(row)
check(len(baseline['protected_direct_seals']) == 4, 'Four direct historical seals')
for row in baseline['copied_inputs'] + baseline['references']:
    check(pin(row['original']) == pin(row['copy']), 'Copied direct input exact')
dependencies = load(NS / 'SHARED_DEPENDENCY.json')
for path, expected in dependencies['files_sha256'].items():
    check(sha(Path(path).read_bytes()) == expected, 'Shared dependency exact ' + path)
check(dependencies['installation_or_download_performed'] is False, 'No dependency installation')

binding = load(NS / 'B_RUN_BINDING.json')
files = binding['source_manifest']
install = Path(binding['install_root'])
check(len(files) == 141 and binding['preparation_git'] == PRODUCT, 'Fixed 141 source product')
identity = dict(base_version=binding['base_version'], implementation_revision=binding['implementation_revision'], files=files)
check(sha(json.dumps(identity, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()) == binding['source_sha256'] == SOURCE,
      'Source aggregate recomputed')
wheel_path = ROOT / 'verification/m5_observe_measure_001/build_final/human_eye_spatial_plugin-9.7.2+m5.observe.measure.001.r1-py3-none-any.whl'
wheel = wheel_path.read_bytes()
check(sha(wheel) == binding['wheel_sha256'], 'Wheel identity')
with zipfile.ZipFile(io.BytesIO(wheel)) as package:
    for row, old in zip(files, blobs([PRODUCT + ':' + row['path'] for row in files])):
        installed = (install / row['path']).read_bytes()
        check(sha(installed) == row['sha256'], 'Installed source SHA')
        check(installed == old == package.read(row['path']), 'Git/install/wheel bytes same')

asset = load(NS / 'fixture/ASSET_BINDING.json')
check(sha(Path(asset['asset_path']).read_bytes()) == asset['asset_sha256'] == ASSET, 'Actual asset identity')
check(Path(asset['asset_path']).stat().st_size == asset['asset_bytes'], 'Actual asset size')
geometry = load(NS / 'fixture/GEOMETRY.json')
expected_geometry = {item['name']: item for item in geometry['objects']}
check(geometry['counts'] == dict(objects=9, triangles=56, vertices=54), 'Frozen geometry counts')
before = pin(asset['readback_before_save'])
after = pin(asset['readback_after_reload'])
check(before == after, 'Saved/reopened exact source geometry')
readback = json.loads(after)
for item in readback['objects']:
    expected = expected_geometry[item['name']]
    vertices = [[float(Fraction(value)) for value in point] for point in expected['vertices_world_m']]
    check(item['matrix_world'] == item['evaluated_matrix_world'] == expected['matrix_world'], 'Original/evaluated matrices')
    check(item['modifiers'] == [] and item['parent'] is None, 'Fixed independent mesh')
    for source_kind in ('native', 'evaluated'):
        source = item[source_kind]
        check(source['vertices_world'] == source['vertices_local'] == vertices, 'Original/evaluated source vertex rows')
        check(source['triangles'] == source['polygons'] == expected['triangles'], 'Original/evaluated triangle rows')
        check(source['triangle_polygon_indices'] == list(range(len(expected['triangles']))), 'Original polygon association')

preparation = load(RUN / 'fixture_preparation/RESULT.json')
spawn = load(RUN / 'fixture_preparation/SPAWN.json')
check(preparation['complete_ns'] == preparation['closed_ns'] - preparation['started_ns'] == 666632500, 'Preparation complete wall')
check(preparation['deadline_ns'] == spawn['original_deadline_ns'] == preparation['started_ns'] + 600_000_000_000, 'Preparation deadline unchanged')
check(preparation['status'] == 'completed' and preparation['errors'] == [] and preparation['exit_code'] == 0, 'Preparation successful')
check(preparation['process_reaped'] and preparation['Popen_handle_closed'] and preparation['stdout_closed'] and preparation['stderr_closed'], 'Preparation all handles closed')
check(preparation['retained_exit']['confirmed'] and preparation['retained_exit']['exited']
      and preparation['retained_exit']['handle_closed'] and preparation['retained_exit']['exit_code'] == 0, 'Preparation owned exit')
check(preparation['Blender_process_attempts'] == 1 and preparation['raster_attempts'] == preparation['model_consumers'] == preparation['paid_API_calls'] == 0,
      'One separate asset process, zero model/raster')
check(preparation['asset_sha256'] == ASSET and preparation['asset_binding_sha256'] == sha((NS / 'fixture/ASSET_BINDING.json').read_bytes()), 'Preparation asset and receipt bound')

sessions = []
embedded_count = 0
for label, frame_count in [('global', 6), ('local_open', 1), ('local_covered', 1)]:
    folder = RUN / 'sessions' / label
    result = load(folder / 'SLOT_RESULT.json')
    publication = load(folder / 'SLOT_PUBLICATION.json')
    close = load(folder / 'RUNTIME_CLOSE.json')
    start = load(folder / 'RUNTIME_START.json')
    config = load(folder / 'PRODUCT_CONFIG.json')
    clocks = result['clocks']
    check(result['status'] == publication['status'] == 'completed' and result['errors'] == [], 'Completed slot ' + label)
    check(result['model_consumers'] == result['paid_API_calls'] == 0, 'Zero model and paid calls')
    check(clocks['owned_deadline_ns'] == clocks['slot_started_ns'] + 600_000_000_000, 'Original 600s slot bound')
    check(start['owned_deadline_ns'] == start['consumer_deadline_ns'] == clocks['owned_deadline_ns'], 'Same runtime original deadline')
    check(clocks['public_deadline_ns'] == clocks['public_started_ns'] + 30_000_000_000, 'Original 30s public window')
    check(clocks['public_returned_ns'] <= clocks['public_deadline_ns'], 'Public returned in window')
    complete = publication['slot_result_published_ns'] - publication['slot_started_ns']
    check(complete == publication['complete_slot_ns'] and publication['slot_started_ns'] == clocks['slot_started_ns'], 'Complete slot wall recomputed')
    check(clocks['cleanup_closed_ns'] <= publication['slot_result_published_ns'] <= clocks['owned_deadline_ns'], 'Close and publication inside original bound')
    check(sha((folder / 'SLOT_RESULT.json').read_bytes()) == publication['result_sha256'], 'Published slot identity')
    check(config['request_budget_s'] == config['blender']['timeout_s'] == 30, 'Product/host 30s')
    check(config['expected_identity']['source_sha256'] == SOURCE, 'Configured source')
    initialized = load(folder / 'INITIALIZE.json')['result']['_meta']['human_eye']
    check(initialized['source_sha256'] == SOURCE and initialized['source_file_count'] == 141
          and initialized['source_kind'] == 'installed_distribution', 'Actual initialize identity')
    runtime = load(folder / 'mcp_io/RUNTIME.json')
    check(runtime['source_sha256'] == SOURCE and runtime['algorithm_monkeypatches'] == 0, 'Runtime source and original algorithm')
    check(sha(Path(runtime['entry']).read_bytes()) == runtime['entry_sha256'], 'Actual MCP harness entry bytes')

    requests = rows(folder / 'PUBLIC_REQUESTS.jsonl')
    check(len(requests) == result['public_requests_attempted'] == 1, 'Exactly one actual public observe')
    request = requests[0]
    tx = Path(request['actual_TX_path']).read_bytes()
    rx = Path(request['actual_RX_path']).read_bytes()
    check(sha(tx) == request['actual_TX_sha256'] and sha(rx) == request['actual_RX_sha256'], 'Original public wire hashes')
    check(json.loads(tx) == request['request'] and json.loads(rx) == request['response'], 'Original public JSON bodies')
    check(request['request']['params']['arguments'] == result['request_arguments'], 'Actual request arguments')
    check(request['request']['params']['name'] == 'human_eye_scene_observe' and result['request_arguments']['include_image'] is True
          and result['request_arguments']['response_detail'] == 'full', 'Original full actual-image entry')
    check(request['closed_ns'] - request['started_ns'] == request['complete_client_call_ns'], 'MCP client wall')
    check(clocks['public_started_ns'] <= request['started_ns'] <= request['closed_ns'] <= clocks['public_returned_ns'], 'Nested client window')
    check(request['producer_archive_index'] == request['internal_public_call_index'] == 1, 'Independent public/archive counters')
    check(result['product_is_error'] is False and request['response']['result']['isError'] is False, 'Actual success receipt')
    producer = load(request['producer_archive']['path'])
    check(sha(Path(request['producer_archive']['path']).read_bytes()) == request['producer_archive']['sha256'], 'Same returned producer identity')
    check(len(rows(folder / 'product_full/INDEX.jsonl')) == 1, 'One producer archive')
    check(producer['read_only'] is True and producer['execution_authority'] is False, 'Read-only facts')
    check(producer['binding']['runtime_source_sha256'] == SOURCE, 'Bound producer source')
    frames = producer['frames']
    audit = rows(folder / 'product_audit.jsonl')
    attempts = [event for event in audit if event.get('event') == 'active_observation_render_attempt']
    check(len(frames) == len(attempts) == producer['work']['raster_attempts'] == frame_count, 'Actual construction counts')
    check([event['view_name'] for event in attempts] == [frame['view_name'] for frame in frames], 'Actual view sequence')
    check(producer['work']['raster_completed'] == producer['work']['local_verified_images'] == frame_count, 'Constructed and verified counts')
    check(producer['work']['frame_reuses'] == 0 and producer['work']['result_cache_hit'] is False, 'Fresh qualification')
    check(sum(frame['PNG_bytes'] for frame in frames) == producer['work']['PNG_bytes'], 'PNG construction ledger')
    check(sum(frame['compressed_array_file_bytes'] for frame in frames) == producer['work']['NPZ_bytes'], 'NPZ construction ledger')
    for frame in frames:
        check(sha(Path(frame['image_path']).read_bytes()) == frame['image_sha256'], 'Actual frame PNG SHA')
        check(sha(Path(frame['arrays_path']).read_bytes()) == frame['arrays_sha256'], 'Actual frame NPZ SHA')

    for kind in ('MCP', 'NATIVE'):
        proof = load(folder / (kind + '_RUNTIME_PROOF.json'))
        check(proof['confirmed'] and proof['before_stdin'] and proof['error'] is None, 'Owned identity before input')
    mcp_close = close['MCP_stdio_close']
    check(mcp_close['confirmed'] and mcp_close['exit_code'] == 0 and mcp_close['forced_kill'] is False, 'MCP normal close')
    check(mcp_close['reader_stopped'] and all(mcp_close['pipes_closed'].values()) and mcp_close['process_handle_closed'] and mcp_close['errors'] == [], 'MCP pipes/readers/handle closed')
    held = close['MCP_retained_exit']
    check(held['confirmed'] and held['exited'] and held['exit_code'] == 0 and held['handle_closed'], 'MCP retained exit')
    held = result['cleanup']['native_retained_exit']
    check(held['confirmed'] and held['exited'] and held['exit_code'] == 0 and held['handle_closed'] and held['Popen_handle_closed'], 'Native retained exit')
    native = close['Blender_close']
    check(native['exit_code'] == 0 and native['process_reaped'] and native['error'] is None, 'Blender wait/reap')
    check(native['source_file_unchanged'] and native['protected_files_unchanged'], 'Protected asset state')
    state = load(folder / 'native/WORKER_CLOSED.json')
    check(state['initial_geometry_fingerprint'] == state['final_geometry_fingerprint'] and state['poisoned'] is False, 'Terminal geometry unchanged')
    check(native['original_deadline_ns'] == state['original_deadline_ns'] == clocks['owned_deadline_ns'], 'Native original deadline retained')
    check(close['errors'] == [] and close['runtime']['errors'] == [] and close['runtime']['closed'], 'Runtime closed without errors')
    check(sha((folder / 'native/input.blend').read_bytes()) == ASSET, 'Actual loaded asset copy exact')

    native_events = rows(folder / 'native/WORKER_EVENTS.jsonl')
    check([event['sequence'] for event in native_events] == [1, 2, 3], 'Raw read, product capture, close only')
    for sequence in (1, 2):
        script = (folder / f'native/call_{sequence}/SCRIPT.py').read_text(encoding='utf-8')
        transport = load(folder / f'native/WIRE/{sequence:03d}/REQUEST.bin')
        event = native_events[sequence - 1]
        check(transport['params']['code'] == script and event['script_sha256'] == sha(script.encode()), 'Actual executed string transport/worker exact')
        check(event['status'] == 'completed' and event['script_error'] is None, 'Actual script completion')
    extracted = []
    for node in ast.walk(ast.parse(script)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'b64decode' and node.args and isinstance(node.args[0], ast.Constant):
            raw = base64.b64decode(node.args[0].value)
            try:
                raw = zlib.decompress(raw)
            except zlib.error:
                pass
            extracted.append(raw)
    expected_sources = {(install / path).read_bytes() for path in ['human_eye_plugin/blender_host.py', 'human_eye_plugin/scene_residency.py']}
    check(len(extracted) == 2 and set(extracted) == expected_sources, 'Actual compiled host and residency source bytes')
    embedded_count += len(extracted)
    raw_scene = load(folder / 'raw_sources/live-source-001.json')
    check(raw_scene['source']['asset_sha256'] == ASSET, 'Actual additional raw-source asset')
    native_response = load(folder / 'native/WIRE/001/RESPONSE.bin')
    raw_text = native_response['result']['result'].split('CURRENT_RAW_SCENE:', 1)[1]
    actual_raw = json.loads(raw_text)
    check(raw_scene['objects'] == actual_raw['objects'], 'Retained source equals original native response')
    for item in raw_scene['objects']:
        expected = expected_geometry[item['name']]
        check(item['vertices'] == [[float(Fraction(value)) for value in point] for point in expected['vertices_world_m']], 'Raw current vertex rows exact')
        check(item['triangles'] == expected['triangles'], 'Raw current triangle rows exact')
    envelope = load(folder / 'native/WIRE/002/RESPONSE.bin')['result']['result']
    delta = json.loads(envelope.split('HUMAN_EYE_BLENDER_MCP:', 1)[1])['result']
    capture = delta['capture']
    resources = {(item['id'], item['revision']): item for item in delta['resources']}
    check(capture['capture_state'] == producer['binding']['capture_state'], 'Actual capture state producer same')
    check(capture['host_identity']['document_epoch'] == producer['binding']['document_epoch'], 'Actual document epoch producer same')
    check(len(capture['meshes']) == producer['work']['capture_object_count'], 'Actual retained object count')
    for index, mesh in enumerate(capture['meshes']):
        resource_ref = mesh['_scene_resource']
        resource = resources[(resource_ref['id'], resource_ref['revision'])]
        expected = expected_geometry[mesh['name']]
        check(resource['vertices_local'] == [[float(Fraction(value)) for value in point] for point in expected['vertices_world_m']], 'Actual product resource source rows')
        check(resource['faces'] == expected['triangles'], 'Actual product resource triangle rows')
        object_binding = producer['binding']['objects'][index]
        check(object_binding['object_index'] == index and object_binding['host_id'] == mesh['object_id']
              and object_binding['instance_id'] == capture['host_identity']['object_instances'][mesh['object_id']], 'Actual object/instance/order mapping')
    sessions.append(dict(label=label, complete_slot_ns=complete, complete_slot_ms=complete / 1e6,
                         public_root_ns=clocks['public_returned_ns'] - clocks['public_started_ns'],
                         MCP_client_ns=request['complete_client_call_ns'], service_total_ns=producer['stages']['service_total']['elapsed_ns'],
                         host_capture_ns=producer['stages']['host_capture']['elapsed_ns'],
                         raster_attempts=frame_count, PNG_bytes=producer['work']['PNG_bytes'],
                         NPZ_bytes=producer['work']['NPZ_bytes'], retained_array_payload_bytes=producer['work']['array_payload_bytes'],
                         capture_objects=producer['work']['capture_object_count'], capture_triangles=producer['work']['captured_triangle_count']))

counts = Counter()
for path in sorted((RUN / 'budget/claims').glob('*.json')):
    claim = load(path)
    settlement = load(RUN / 'budget/settlements' / path.name)
    check(settlement['token'] == claim['token'] and settlement['claim_sha256'] == sha(path.read_bytes()), 'Operation settlement original claim')
    check(settlement['settled_ns'] >= claim['claimed_ns'], 'Operation settlement ordered')
    check(claim['phase'] == 'qualification' and claim['reserved_upper_bound'] == 1, 'Qualification operation reservation')
    counts[claim['kind']] += 1
    if claim['kind'] == 'Blender_start':
        check(settlement['outcome'] == 'completed' and settlement['spawn_status'] == 'spawned', 'Confirmed actual start')
        check(settlement['pid'] == load(RUN / 'sessions' / claim['label'] / 'native/READY.json')['pid'], 'Claim and actual owned PID')
    elif claim['kind'] == 'raster_attempt':
        check(settlement['actual_attempts'] == settlement['confirmed_attempts_lower_bound'] == 1, 'One actual raster')
        check(settlement['released_proven_unconstructed_reservation'] == 0, 'Constructed raster kept charged')
    else:
        check(False, 'Unexpected operation kind')
check(counts == Counter(Blender_start=3, raster_attempt=8), 'Three owned and eight charged rasters')
check(len(list((RUN / 'budget/settlements').glob('*.json'))) == 11, 'All operation claims settled')
check(load(RUN / 'budget/LIMITS.json') == dict(Blender_start_attempts=3, all_rasters=18, consumer_tasks=0), 'Original budget ceiling')
check(embedded_count == 6, 'Six actual embedded source payloads')
check(len(list((RUN / 'sessions').iterdir())) == 3, 'Three qualification session directories')
check(not list(RUN.rglob('*CONSUMER*')), 'No consumer artifact')

failed_run = load(NS / 'RUNTIME_REVIEW_RUN.json')
check(failed_run['exit_code'] == 1 and failed_run['Blender_starts'] == failed_run['product_calls'] == failed_run['raster_attempts'] == 0,
      'Original saved-only runtime checker failure retained')
pin(failed_run['stderr'])
check(load(NS / 'RUNTIME_REVIEW_RUN_R1.json')['exit_code'] == 0, 'Derived runtime checker recovery retained')
for name in ['CHECKER_CORRECTION_01.json', 'CHECKER_CORRECTION_02.json']:
    correction = load(NS / 'checks' / name)
    check(correction['new_actual_operations'] == 0, 'Saved-only frame checker correction')
    pin(correction['corrected_source'])
decision = load(NS / 'DECISION.json')
check(decision['experiment_model_consumers'] == decision['experiment_paid_API_calls'] == 0, 'Decision zero model/paid')
check(decision['accepted_qualification'] is True, 'Author qualification scope')
wall_ns = decision['closed_ns'] - baseline['started_ns']
check(abs(wall_ns / 1e9 - decision['root_registration_to_decision_seconds']) < 1e-8, 'Registration-to-decision wall')
for name, expected in decision['report_pins'].items():
    check(sha((NS / name).read_bytes()) == expected, 'Final direct report pin ' + name)
for actual, reported in zip(sessions, decision['costs']):
    check(actual['label'] == reported['label'] and actual['complete_slot_ms'] == reported['complete_slot_ms'], 'Reported complete slot wall')
    check(actual['public_root_ns'] / 1e6 == reported['public_request_ms'], 'Reported root public window')

result = dict(status='passed_checked_scope', checks=CHECKS, fixed_git=FINAL, preexecution_git=PREEXEC,
              manifest_members=379, git_paths=380, frozen_inputs=47, runtime_originals=261, runtime_bytes=archive_bytes,
              source_files=141, source_sha256=SOURCE, actual_embedded_host_sources=embedded_count,
              asset_sha256=ASSET, sessions=sessions, asset_preparation_ns=preparation['complete_ns'],
              sum_separate_qualification_slot_ns=sum(item['complete_slot_ns'] for item in sessions),
              budget=dict(qualification_owned=3, preparation_Blender=1, actual_rasters=8, raster_limit=18,
                          pending_operations=0, models=0, paid_API=0),
              registration_to_decision_wall_ns=wall_ns, active_work_ns=None,
              model_benefit='unmeasured', performance_ranking='not_performed_qualification_scopes_differ',
              new_live_Blender=0, new_live_MCP=0, new_raster=0, new_model=0, new_paid_API=0)
OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'RESULT.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False))
