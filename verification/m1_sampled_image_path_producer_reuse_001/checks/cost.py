"""Measure two isolated sampled-image serializers over the original producer evidence."""

import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from queue import Empty, Queue
from runpy import run_path
from statistics import median
import subprocess
import sys
from threading import Thread
from time import perf_counter_ns
from types import SimpleNamespace


V = Path(__file__).resolve().parents[2]
PREVIOUS = V / 'm1_source_region_sampled_image_path_001'
BASELINE = PREVIOUS / 'install/PRODUCT_RUN_BINDING.json'
BASELINE_GIT = '9b43ecebba66fdc0f1efb1d06be4d5b7cb976266'
BASELINE_SOURCE = 'a8ddc3b672c6b32c3a69711ecbc847d9761315ccb6239e447d7006df2c35b982'
BASELINE_WHEEL = 'c50af0c7331186abe1f005e932b3b581c16a5281e2b839766dfbc3cde7fb441f'
REPLAY = PREVIOUS / 'checks/positives.py'
PLAN = '0a69beabcddc39a464bc2b2b0cc223d90fa1460a'
SCHEDULE = ('A', 'B', 'B', 'A', 'B', 'A', 'A', 'B')
WARMUPS = 6
WARM = 36
BINDING_ANNOTATIONS = ('runtime_source_sha256', 'source_status', 'disk_status', 'source_check_scope')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def read(path):
    return json.loads(path.read_bytes())


def digest(data):
    return sha256(data).hexdigest()


def pin(path):
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': digest(data)}


def save(path, value):
    with path.open('xb') as stream:
        stream.write((json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode())


def private_observation(public):
    original = deepcopy(public)
    for key in ('task_result', 'session_id', 'request_trace'):
        original.pop(key)
    for key in BINDING_ANNOTATIONS:
        original['binding'].pop(key, None)
    original['work'] = deepcopy(original['generation_work'])
    original['stages'] = deepcopy(original['generation_stages'])
    return original


def worker(binding_file, record_file):
    benchmark = run_path(str(REPLAY))
    binding = read(binding_file)
    sys.path[:0] = [binding['install_root'], binding['dependency_root']]
    from human_eye_plugin import live_spatial_mcp, source_region
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.read_context import ReadContext
    from human_eye_plugin.runtime_identity import runtime_identity

    identity = runtime_identity()
    require(identity['source_kind'] == 'installed_distribution'
            and identity['source_sha256'] == binding['source_sha256']
            and Path(live_spatial_mcp.__file__).resolve().is_relative_to(Path(binding['install_root']).resolve()),
            'measurement_loaded_the_wrong_runtime')
    frozen = read(benchmark['SOURCE'])
    arguments = read(benchmark['REQ'])['params']['arguments']
    pane, = frozen['frames']
    image_path = Path(pane['image_path'])

    def reject_construction(_view):
        raise RuntimeError('timing_must_not_start_a_raster')

    class RestoredService:
        request_budget_s = None
        _request_budget = LiveSpatialService._request_budget
        request_error_fields = staticmethod(LiveSpatialService.request_error_fields)
        _source_region_sample_directory = getattr(LiveSpatialService, '_source_region_sample_directory', None)
        _source_region_sample_path = getattr(LiveSpatialService, '_source_region_sample_path', None)

        def __init__(self):
            self.state_path = benchmark['SLOT'] / 'product_state.json'
            self.calls = 0
            self.closed = False
            self.audit = None
            self.budget = []
            self.prepared = SimpleNamespace(observation=private_observation(frozen),
                binding=deepcopy(frozen['binding']), region_ref=deepcopy(frozen['region_ref']),
                images=SimpleNamespace(output_directory=image_path.parent))
            self._read_context = ReadContext()
            self._read_context.activate(self.prepared.binding, 'source_region')
            ref = self.prepared.region_ref['region_id']
            self._read_context.prepared('source_regions', lambda: {'regions': {ref: self.prepared}, 'aliases': {}})

        def observe(self, _session, *, query, include_image, **_unused):
            require(query == arguments['query'] and include_image is True, 'wrong_exact_public_request')
            self.calls += 1
            if self.calls == 1:
                return deepcopy(frozen)
            result = source_region.observe_region(self.prepared, None, include_image=True,
                construction_callback=reject_construction)
            require(result['work']['raster_attempts'] == 0 and result['work']['frame_reuses'] == 1,
                    'installed_observe_region_did_not_reuse_the_producer')
            # Add the fields attached by the service after observe_region returns.
            result['task_result'] = deepcopy(frozen['task_result'])
            result['session_id'] = frozen['session_id']
            result['binding'].update({key: frozen['binding'][key] for key in BINDING_ANNOTATIONS
                                      if key in frozen['binding']})
            return result

        def record_event(self, event, **data):
            require(event == 'source_region_mcp_content' and self.audit is None, 'unexpected_audit_record')
            self.audit = data['image_delivery']

        def _check_request_budget(self, phase, *, publication=False):
            self.budget.append((phase, publication))

        def close(self):
            self.closed = True

    service = RestoredService()
    samples = []
    path_intervals = []
    path_helper = live_spatial_mcp._source_region_sample_image_path

    def metered_path(*args, **kwargs):
        started_ns = perf_counter_ns()
        path = path_helper(*args, **kwargs)
        path_intervals.append(perf_counter_ns() - started_ns)
        require(path == image_path.as_posix(), 'timed_helper_did_not_return_the_original_path')
        return path

    class MeteredInput:
        def __init__(self, source):
            self.source = source
            self.started_ns = None

        def readline(self, limit):
            value = self.source.readline(limit)
            self.started_ns = perf_counter_ns()
            return value

    class MeteredOutput:
        def __init__(self, sink, source):
            self.sink = sink
            self.source = source

        def write(self, data):
            return self.sink.write(data)

        def flush(self):
            self.sink.flush()
            completed_ns = perf_counter_ns()
            if service.audit is not None:
                audit = service.audit
                frame, = audit['frames']
                require(audit['native_blocks_constructed'] == 1 and frame['PNG_bytes_read'] == 4015
                        and len(path_intervals) == len(samples) + 1, 'timed_samples_changed_public_image_work')
                samples.append({'path_helper_ns': path_intervals[-1], 'serializer_ns': audit['elapsed_ns'],
                                'stdio_server_ns': completed_ns - self.source.started_ns,
                                'PNG_read_ns': frame['read_ns'], 'PNG_validate_ns': frame['validate_ns'],
                                'PNG_base64_ns': frame['base64_ns']})
                service.audit = None

    live_spatial_mcp._source_region_sample_image_path = metered_path
    live_spatial_mcp._configure_utf8_stdio()
    incoming = MeteredInput(sys.stdin.buffer)
    live_spatial_mcp.run_stdio_mcp_server(service, input_stream=incoming, output_stream=MeteredOutput(sys.stdout, incoming))
    require(service.closed and service.calls == len(samples)
            and service.budget == [('before_task_publication', False), ('before_stdio_write', True)] * len(samples),
            'timed_stdio_did_not_reach_the_real_publication_and_eof')
    save(record_file, {'actual_source_sha256': identity['source_sha256'], 'closure': service.closed, 'raw': samples})


def run_block(binding, out, sample_request, cold_response, warm_response, cold_only=False):
    receipts = Queue()
    raw = out / 'WORKER.json'
    argv = [sys.executable, '-IB', str(Path(__file__).resolve()), '--worker', str(binding), '--record', str(raw)]
    child = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def read_replies():
        for line in child.stdout:
            receipts.put((perf_counter_ns(), line))
        receipts.put((perf_counter_ns(), b''))

    thread = Thread(target=read_replies, daemon=True)
    thread.start()

    def exchange(request, expect):
        started_ns = perf_counter_ns()
        child.stdin.write(request)
        child.stdin.flush()
        try:
            completed_ns, line = receipts.get(timeout=20)
        except Empty as exc:
            raise RuntimeError('timed_installed_mcp_reply_timeout') from exc
        if line != expect:
            (out / 'UNEXPECTED_RESPONSE.bin').write_bytes(line)
            raise ValueError('timed_actual_wire_changed')
        return completed_ns - started_ns

    try:
        exchange(b'{"jsonrpc":"2.0","id":"bench-ready","method":"ping"}\n',
                 b'{"jsonrpc": "2.0", "id": "bench-ready", "result": {}}\r\n')
        roundtrips = [exchange(sample_request, cold_response)]
        if not cold_only:
            roundtrips.extend(exchange(sample_request, warm_response) for _ in range(WARMUPS + WARM))
        child.stdin.close()
        require(child.wait(timeout=20) == 0, 'timed_installed_mcp_worker_failed')
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)
        (out / 'STDERR.bin').write_bytes(child.stderr.read())
        child.stdin.close()
        child.stdout.close()
        child.stderr.close()
        thread.join(timeout=2)
    rows = read(raw)
    require(rows['actual_source_sha256'] == read(binding)['source_sha256'] and rows['closure']
            and len(roundtrips) == len(rows['raw']), 'timing_block_did_not_match_its_owned_worker')
    measurements = [dict(values, stdio_pipe_roundtrip_ns=ns) for values, ns in zip(rows['raw'], roundtrips, strict=True)]
    return {'binding': pin(binding), 'worker_timing': pin(raw), 'cold': measurements[0],
            'discarded_warmups': measurements[1:1+WARMUPS], 'warm': measurements[1+WARMUPS:]}


def summarize(rows):
    def stats(values):
        ordered = sorted(values)
        p95_index = (len(ordered) * 95 + 99) // 100 - 1
        return {'median': median(ordered), 'p95': ordered[p95_index]}
    return {field: stats([row[field] for row in rows]) for field in rows[0]}


def measure(candidate, output):
    before, after = map(read, (BASELINE, candidate))
    require((before['preparation_git'], before['source_sha256'], before['wheel_sha256']) ==
            (BASELINE_GIT, BASELINE_SOURCE, BASELINE_WHEEL), 'wrong_pinned_baseline')
    require(after['historical_preparation_git'] == BASELINE_GIT and after['preparation_git'] != BASELINE_GIT,
            'candidate_is_not_the_single_child_of_the_pinned_baseline')
    require(before['dependency_root'] == after['dependency_root'], 'disparate_dependency_install')
    for arm in (before, after):
        require(len(arm['source_manifest']) == 143 and pin(Path(arm['wheel_path']))['sha256'] == arm['wheel_sha256'],
                'unexpected_wheel_or_source_count')
    proof = run_path(str(REPLAY))
    _, _, originals = proof['frozen_media']()
    request = proof['REQ'].read_bytes().rstrip(b'\r\n') + b'\n'
    cold = PREVIOUS / 'evidence/CANDIDATE_COLD_RX.bin'
    warm = PREVIOUS / 'evidence/CANDIDATE_WARM_RX.bin'
    cold_response = cold.read_bytes()
    # The historical warm replay used a synthetic request ID. Reuse the
    # original request ID throughout the timing stream, with one call in flight.
    warm_reply = read(warm)
    warm_reply['id'] = json.loads(request)['id']
    warm_response = (json.dumps(warm_reply, ensure_ascii=True, allow_nan=False) + '\r\n').encode()
    output.mkdir(parents=True, exist_ok=False)
    arms = {'A': BASELINE, 'B': candidate}
    blocks = []
    for seq, arm in enumerate(SCHEDULE, 1):
        out = output / f'{seq:02d}_{arm}'
        out.mkdir()
        block = run_block(arms[arm], out, request, cold_response, warm_response)
        blocks.append(dict(block, arm=arm, sequence=seq))
    summary = {arm: {phase: summarize([row for block in blocks if block['arm'] == arm
                                      for row in ([block[phase]] if phase == 'cold' else block[phase])])
                     for phase in ('cold', 'warm')} for arm in arms}
    block_pairs = []
    for left, right in zip(blocks[::2], blocks[1::2], strict=True):
        a, b = (left, right) if left['arm'] == 'A' else (right, left)
        a_stats, b_stats = (summarize(block['warm']) for block in (a, b))
        block_pairs.append({'order': left['arm'] + right['arm'], 'sequences': [left['sequence'], right['sequence']],
            'B_minus_A_warm_median_ns': {key: b_stats[key]['median'] - a_stats[key]['median'] for key in a_stats}})
    result = {'schema': 'sampled-image-path-producer-reuse-piped-replay-cost-v1', 'plan_git': PLAN,
              'process_schedule': list(SCHEDULE), 'cold_replays_per_arm': SCHEDULE.count('A'),
              'discarded_warmups_per_block': WARMUPS, 'warm_replays_per_arm': SCHEDULE.count('A') * WARM,
              'preserved_whole_wire': True, 'exact_cold_warm_RX_sha256': {'cold': digest(cold_response),
                  'warm_same_id': digest(warm_response)}, 'input_pins': [pin(Path(__file__)), pin(Path(sys.executable)),
                  pin(REPLAY), pin(cold), pin(warm), *originals], 'blocks': blocks, 'summary_ns': summary,
              'paired_adjacent_blocks': block_pairs, 'new_Blender': 0, 'new_rasters': 0, 'new_models': 0,
              'timing_scope': {'cold': 'First frozen producer replay after a readiness ping, without import/startup or raster.',
                  'warm': 'Actual installed observe_region cache hit, with restored service reply fields.',
                  'path_helper': 'Original installed helper including its private producer lookup.',
                  'stdio_server': 'Request line read completed through native flush completed, including actual public encoding.',
                  'stdio_pipe_roundtrip': 'Controller write through receipt of entire line, including OS and reader-thread scheduling.'}}
    save(output / 'COST.json', result)
    print(json.dumps({'output': pin(output/'COST.json'), 'summary_ns': summary, 'paired_adjacent_blocks': block_pairs}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--worker', type=Path)
    parser.add_argument('--record', type=Path)
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode, 'use_pinned_interpreter_I_B')
    if args.worker:
        worker(args.worker, args.record)
    else:
        measure(args.candidate.resolve(strict=True), args.output.resolve())
