"""Independent saved identity, raw costs and stopped-slot reconstruction."""
import collections
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(r'C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe')
NS = ROOT / 'verification/m5_task_consumption_001'
RUN = Path(r'D:/he_m5_task_consume_001')
OUT = Path(__file__).resolve().parent
FINAL = 'baf8799d9e1cb411d39da58c28171b00ac76f12f'
BASE = '14c8c6b8206dcaecc373bc9aa895cda1d622eee3'
FREEZE = '99c5ba3ebcd62cbb94174a06e0a419912257bc91'
count = 0


def check(value, name):
    global count
    count += 1
    if not value:
        raise AssertionError(name)


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def git_blobs(ref, paths):
    paths = list(paths)
    requests = ''.join(ref + ':' + p + '\n' for p in paths).encode()
    wire = subprocess.check_output(['git', 'cat-file', '--batch'], input=requests, cwd=ROOT)
    offset = 0
    result = {}
    for path in paths:
        end = wire.index(b'\n', offset)
        head = wire[offset:end].split()
        check(len(head) == 3 and head[1] == b'blob', 'Git blob header ' + path)
        size = int(head[2])
        start = end + 1
        result[path] = wire[start:start + size]
        offset = start + size + 1
    check(offset == len(wire), 'Git batch closed exactly')
    return result


manifest = read(NS / 'CONTENT_MANIFEST.json')
paths = [r['path'] for r in manifest['files']]
manifest_rel = (NS / 'CONTENT_MANIFEST.json').relative_to(ROOT).as_posix()
changed = git('diff', '--name-only', BASE, FINAL).decode().splitlines()
check(len(paths) == len(set(paths)) == 1642, 'unique 1642 manifest members')
check(set(changed) == set(paths) | {manifest_rel}, '1643 Git paths exactly closed')
check(all(p.startswith('verification/m5_task_consumption_001/') for p in changed), 'changes confined to batch')
blobs = git_blobs(FINAL, paths + [manifest_rel])
for row in manifest['files']:
    path = row['path']
    raw = (ROOT / path).read_bytes()
    check(len(raw) == row['bytes'] and sha(raw) == row['sha256'], 'manifest bytes ' + path)
    check(raw == blobs[path], 'fixed Git bytes ' + path)
check((NS / 'CONTENT_MANIFEST.json').read_bytes() == blobs[manifest_rel], 'manifest Git bytes')
check(git('status', '--porcelain') == b'', 'author worktree clean')
check(git('diff', '--name-only', BASE, FINAL, '--', 'human_eye_plugin') == b'', 'no product change')

archive = read(NS / 'RUNTIME_ARCHIVE.json')
check(len(archive['files']) == 1311, '1311 runtime files')
total_bytes = 0
for row in archive['files']:
    original = Path(row['original_path'])
    copy = NS / row['archive_path']
    check(original.resolve().is_relative_to(RUN.resolve()), 'runtime path boundary')
    check(copy.resolve().is_relative_to(NS.resolve()), 'archive path boundary')
    a, b = original.read_bytes(), copy.read_bytes()
    check(a == b and len(a) == row['bytes'] and sha(a) == row['sha256'], 'runtime exact ' + row['relative_path'])
    total_bytes += len(a)
check(total_bytes == archive['bytes'] == 16917573, 'runtime total bytes')

frozen = read(NS / 'FROZEN.json')
check(len(frozen['files']) == 928, '928 formal pins')
formal_local = {}
for row in frozen['files']:
    p = Path(row['path'])
    raw = p.read_bytes()
    check(len(raw) == row['bytes'] and sha(raw) == row['sha256'], 'frozen original ' + p.name)
    if p.resolve().is_relative_to(NS.resolve()):
        formal_local[p.relative_to(ROOT).as_posix()] = raw
formal_blobs = git_blobs(FREEZE, formal_local)
for path, raw in formal_local.items():
    check(raw == formal_blobs[path], 'formal source Git ' + path)

sources = {}
for group, build in [('A', 'verification/m4_target_acquisition_002/build_B'),
                     ('B', 'verification/m5_observe_measure_001/build_final')]:
    binding = read(NS / (group + '_RUN_BINDING.json'))
    source_rows = binding['source_manifest']
    check(len(source_rows) == 141, group + ' 141 source files')
    source_git = git_blobs(binding['preparation_git'], [r['path'] for r in source_rows])
    wheels = list((ROOT / build).glob('*.whl'))
    check(len(wheels) == 1, group + ' unique wheel')
    check(sha(wheels[0].read_bytes()) == binding['wheel_sha256'], group + ' wheel SHA')
    with zipfile.ZipFile(wheels[0]) as wheel:
        for row in source_rows:
            raw = (Path(binding['install_root']) / row['path']).read_bytes()
            check(sha(raw) == row['sha256'], group + ' installed source ' + row['path'])
            check(raw == source_git[row['path']] == wheel.read(row['path']), group + ' Git/wheel/install ' + row['path'])
    identity = {k: binding[k] for k in ('base_version', 'implementation_revision')}
    identity['files'] = source_rows
    check(sha(json.dumps(identity, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()) == binding['source_sha256'], group + ' aggregate source SHA')
    sources[group] = binding['source_sha256']

run = read(RUN / 'RUN_RESULT.json')
sequence = ['A1', 'B1', 'B2', 'A2', 'A3', 'B3']
check([r['slot_id'] for r in run['records']] == sequence, 'original six dispatch records')
check(run['actual_consumers'] == run['consumer_attempts'] == 5 and run['planned_slots'] == 6, 'five actual six planned')
check(run['formal_batch_attempts'] == 1 and run['outer_retries'] == run['replacement_samples'] == 0, 'one formal no replacements')
threads = []
rows = []
previous_close = None
for dispatch in run['records'][:5]:
    label = dispatch['slot_id']
    folder = RUN / 'formal' / label
    slot = read(folder / 'SLOT_RESULT.json')
    publication = read(folder / 'SLOT_PUBLICATION.json')
    consumer = read(folder / 'consumer/CONSUMER.json')
    timing = read(folder / 'consumer/FINAL_TIMING.json')
    check(slot['status'] == publication['status'] == dispatch['status'] == 'completed', label + ' completed originals')
    check(sha((folder / 'SLOT_RESULT.json').read_bytes()) == publication['result_sha256'] == dispatch['result_sha256'], label + ' result raw pin')
    check(sha((folder / 'SLOT_PUBLICATION.json').read_bytes()) == dispatch['publication_sha256'], label + ' publication pin')
    clocks = slot['clocks']
    started, published = publication['slot_started_ns'], publication['slot_result_published_ns']
    check(started == clocks['slot_started_ns'], label + ' original root start')
    check(published - started == publication['complete_slot_ns'] > 0, label + ' full slot reconstruction')
    check(clocks['consumer_deadline_ns'] == started + 450_000_000_000 and clocks['owned_deadline_ns'] == started + 600_000_000_000, label + ' original deadlines')
    check(started <= consumer['started_ns'] <= consumer['final_received_ns'] <= consumer['turn_completed_ns'] <= consumer['process_exit_ns'] <= consumer['cleanup_end_ns'] <= timing['consumer_record_closed_ns'] <= clocks['business_closed_ns'] <= clocks['cleanup_closed_ns'] <= published <= clocks['owned_deadline_ns'], label + ' all complete time bounds')
    if previous_close is not None:
        check(dispatch['dispatched_ns'] >= previous_close, label + ' serial dispatch')
    previous_close = dispatch['closed_ns']
    check(consumer['frozen_cli_argv'] == consumer['argv'], label + ' CLI frozen argv')
    check(consumer['valid_completion'] and consumer['safe_to_continue'] and consumer['exit_code'] == 0 and consumer['process_reaped'], label + ' CLI actual completion')
    check(not consumer['deadline_timer_fired'] and not consumer['process_cleanup']['kill_requested'], label + ' no forced task termination')
    check(consumer['process_cleanup']['confirmed'] and consumer['process_cleanup']['process_handle_closed'] and all(consumer['process_cleanup']['pipes_closed'].values()), label + ' CLI resources closed')
    thin = consumer['runtime_exit']
    check(thin['confirmed'] and thin['exited'] and thin['exit_code'] == 1 and thin['handle_closed'], label + ' thin actual exit1')
    check(not Path(consumer['runtime_binding']['STARTED_path']).with_name('EXIT.json').exists(), label + ' thin missing EXIT retained')
    cleanup = slot['cleanup']
    check(cleanup['actor_exit_code'] == 0 and cleanup['actor_process_handle_closed'], label + ' actor exited')
    close = read(folder / 'RUNTIME_CLOSE.json')
    check(close['Blender_close']['exit_code'] == 0 and close['Blender_close']['process_reaped'], label + ' Blender closed')
    check(close['MCP_retained_exit']['confirmed'] and close['MCP_retained_exit']['exited'] and close['MCP_retained_exit']['exit_code'] == 0 and close['MCP_retained_exit']['handle_closed'], label + ' MCP held exit')
    check(close['MCP_stdio_close']['confirmed'] and close['MCP_stdio_close']['reader_stopped'] and all(close['MCP_stdio_close']['pipes_closed'].values()), label + ' MCP pipes and reader')
    check(slot['source']['product_source141_sha256'] == sources[slot['group']], label + ' correct product runtime')
    stdout = (folder / 'consumer/stdout.raw.bin').read_bytes()
    events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
    terminals = [e for e in events if e.get('type') == 'turn.completed']
    thread = [e['thread_id'] for e in events if e.get('type') == 'thread.started']
    check(len(terminals) == len(thread) == 1 and terminals[0]['usage'] == consumer['usage'], label + ' original terminal usage')
    check(sha(stdout) == consumer['stdout_raw_sha256'] and len(stdout) == consumer['stdout_raw_bytes'], label + ' stdout original bytes')
    check(thread[0] == consumer['thread_id'], label + ' unique current CLI thread')
    threads.extend(thread)
    usage = terminals[0]['usage']
    raw_total = usage['input_tokens'] + usage['output_tokens']
    uncached = raw_total - usage['cached_input_tokens']
    tools = read(folder / 'owner/TOOLS.json')
    metrics = read(folder / 'owner/METRICS.json')
    public = [json.loads(line) for line in (folder / 'PUBLIC_REQUESTS.jsonl').read_bytes().splitlines() if line.strip()]
    check(tools['calls'] == len(tools['tools']) == metrics['tool_attempts'], label + ' external tool count')
    internal_indices = [index for t in tools['tools'] for index in t['internal_public_call_indices']]
    check(internal_indices == [p['internal_public_call_index'] for p in public], label + ' separate inner request attempts')
    image_blocks = sum(t['content_metrics']['image_blocks'] for t in tools['tools'])
    png_bytes = sum(t['content_metrics']['PNG_bytes'] for t in tools['tools'])
    check(image_blocks == 1 and png_bytes == 4112, label + ' one actual image delivery')
    rows.append(dict(slot=label, full_slot_ns=published-started, external_tools=tools['calls'], internal_requests=len(public), raw_input_plus_output=raw_total, uncached_input_plus_output=uncached, cached_input=usage['cached_input_tokens'], CLI_thread=thread[0], image_blocks=image_blocks, PNG_bytes=png_bytes))
check(len(threads) == len(set(threads)) == 5, 'five fresh CLI threads')

stop = read(RUN / 'ROOT_OPERATOR_STOP.json')
stop_raw = (RUN / 'ROOT_OPERATOR_STOP.json').read_bytes()
b3 = RUN / 'formal/B3'
check((b3 / 'ROOT_OPERATOR_STOP.json').read_bytes() == stop_raw, 'B3 stop raw clone')
check({p.relative_to(b3).as_posix() for p in b3.rglob('*') if p.is_file()} == {'ROOT_OPERATOR_STOP.json'}, 'B3 contains stop only')
check(stop['stopped_before_slot'] == 'B3' and stop['product_or_frozen_source_changed'] is False, 'explicit stop scope')
a3_dispatch, failed = run['records'][4:6]
check(a3_dispatch['dispatched_ns'] < stop['requested_ns'] < a3_dispatch['closed_ns'] <= failed['dispatched_ns'], 'stop during A3 before B3')
check(failed['status'] == 'failed' and failed['error']['type'] == 'FileExistsError' and failed['result_path'] is None and failed['publication_path'] is None, 'B3 original failure retained')
for rel, digest in stop['source_sha256'].items():
    check(sha((RUN / rel).read_bytes()) == digest, 'operator stop diagnostic input')

claims = [read(p) for p in (RUN / 'budget/claims').glob('*.json')]
counts = collections.Counter(c['kind'] for c in claims)
check(counts['Blender_start'] == 7 and counts['raster_attempt'] == 7 and counts['consumer_task'] == 5, '7 owned 7 raster 5 consumers')
check(all(c['label'] != 'B3' for c in claims), 'B3 has no budget claim')
rasters = collections.Counter()
for claim in claims:
    if claim['kind'] not in ('Blender_start', 'raster_attempt'):
        continue
    path = RUN / 'budget/settlements' / (claim['token'] + '.json')
    check(path.exists(), 'all runtime reservation outcomes settled')
    outcome = read(path)
    original = RUN / 'budget/claims' / (claim['token'] + '.json')
    check(outcome['claim_sha256'] == sha(original.read_bytes()), 'settlement source pin')
    if claim['kind'] == 'Blender_start':
        check(outcome['spawn_status'] == 'spawned' and type(outcome['pid']) is int, 'owned actual start known')
    else:
        check(outcome['actual_attempts'] == outcome['confirmed_attempts_lower_bound'] == 1, 'raster actual attempt known')
        rasters[claim['phase']] += 1
check(rasters == {'qualification': 2, 'formal': 5}, 'qualification/formal actual rasters')

decision = read(NS / 'DECISION.json')
check(decision['pairs'] == [] and decision['totals'] is None and decision['passed_frozen_gates'] is False, 'no ratio or total benefit declaration')
check(decision['quality_denominator'] == 6, 'full six denominator retained')
check(all(decision['gates'][k] is False for k in ('B_actual_joint_adoption','B_complete_correct','B_faster_pairs','B_total_raw_input_plus_output','complete_time_paired_median','same_source_comparable_usage')), 'numeric and B gates fail')
for row, saved in zip(rows, decision['rows'][:5]):
    check(row['slot'] == saved['slot_id'] and row['full_slot_ns'] == saved['complete_slot_ns'], row['slot'] + ' published observed cost matches')
    check(saved['original_usage_events'][0]['usage'] == read(RUN/'formal'/row['slot']/'consumer/CONSUMER.json')['usage'], row['slot'] + ' published usage event')
check(decision['rows'][5]['slot_id'] == 'B3' and decision['rows'][5]['complete_slot_ns'] is None, 'B3 no invented full slot time')

result = dict(status='passed_saved_scope_invalid_comparison_preserved', checks=count,
    fixed_git=FINAL, manifest_members=1642, git_paths=1643, runtime_files=1311,
    runtime_bytes=total_bytes, formal_pins=928, actual_consumers=5, denominator=6,
    rows=rows, pairs=[], totals=None, benefit_comparison_valid=False,
    B3=dict(original_status='failed', original_error='FileExistsError', actual_state='not_started', budget_claims=0),
    budget=dict(owned=7, rasters=7, consumers=5, pending_runtime_outcomes=0),
    source_files_per_product=141, new_Blender=0, new_raster=0, new_model=0,
    limitations=['Observed costs include confirmed harness interference.', 'No valid paired ranking or inferred missing B3.', 'Provider billing semantics and monetary fees remain unmeasured.'])
OUT.mkdir(parents=True, exist_ok=True)
(OUT/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k not in ('rows','limitations')},ensure_ascii=False))
