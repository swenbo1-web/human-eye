"""Measure actual public full serialization with fixed historical producer tapes."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import runpy
import statistics
import subprocess
import sys
from time import perf_counter_ns


NS = Path(__file__).resolve().parents[1]
V = NS.parent
SERIALIZER = V / 'm1_source_region_final_image_001/checks/serializer.py'
BASELINE = V / 'm1_pair_distance_entry_001/install/PRODUCT_RUN_BINDING.json'
CANDIDATE = NS / 'install/PRODUCT_RUN_BINDING.json'
CASES = {
    'Far00': Path('D:/he_perf050_dense_pair_transfer_001/slots/P1'),
    'M09': Path('D:/he_perf050_target_observation_first_image_p2/slots/P2'),
}
SAMPLES = 24


def pin(path):
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha256(raw).hexdigest()}


def worker(binding_path):
    binding = json.loads(binding_path.read_bytes())
    sys.path[:0] = [binding['install_root'], binding['dependency_root']]
    from human_eye_plugin import live_spatial_mcp
    from human_eye_plugin.runtime_identity import runtime_identity

    if (runtime_identity()['source_sha256'] != binding['source_sha256']
            or not Path(live_spatial_mcp.__file__).resolve().is_relative_to(binding['install_root'])):
        raise ValueError('wrong_actual_serializer_install')
    replay = runpy.run_path(str(SERIALIZER))

    class Tape(replay['SavedProducer']):
        def record_event(self, event, **data):
            if event == 'active_observation_mcp_content':
                self.delivery = data['image_delivery']

    cases = {}
    for label, folder in CASES.items():
        req_path = folder / 'product_calls/call_001/REQUEST.json'
        source_path = folder / 'product_full/call_001/SERVICE_RESULT.json'
        req, source = (json.loads(file.read_bytes()) for file in (req_path, source_path))
        rows = []
        for iteration in range(6 + SAMPLES):
            tape = Tape(source, req['params']['arguments'], folder / 'product_state.json')
            server = live_spatial_mcp.LiveSpatialMCPServer(tape, default_session_id=source['session_id'])
            started = perf_counter_ns()
            result = server.handle_jsonrpc_message(req)
            elapsed = perf_counter_ns() - started
            audit = tape.delivery
            text = result['result']['content'][0]['text']
            finished = tuple(json.loads(text))[-1] == 'task_result'
            expect_after = binding_path == CANDIDATE
            if audit['status'] != 'constructed' or result['result']['isError'] or tape.observations != 1:
                raise ValueError('actual_full_serialization_did_not_complete/' + audit['status'])
            if finished != expect_after or len(text.encode()) != {'Far00': 30121, 'M09': 28679}[label]:
                raise ValueError('full_case_order_or_length_changed')
            if iteration >= 6:
                rows.append({'dispatch_ns': elapsed, 'serializer_ns': audit['elapsed_ns'],
                             'PNG_read_ns': sum(item['read_ns'] for item in audit['frames']),
                             'PNG_validate_ns': sum(item['validate_ns'] for item in audit['frames']),
                             'base64_ns': sum(item['base64_ns'] for item in audit['frames'])})
        cases[label] = {'pins': [pin(req_path), pin(source_path)], 'samples': rows}
    return {'source_sha256': binding['source_sha256'], 'cases': cases}


def stats(values):
    order = sorted(values)
    return {'median_ns': statistics.median(order), 'p95_ns': order[(95 * len(order) + 99) // 100 - 1],
            'minimum_ns': order[0], 'maximum_ns': order[-1]}


def collect(output):
    schedule = ('A', 'B', 'B', 'A', 'A', 'B')
    versions = {'A': BASELINE, 'B': CANDIDATE}
    runs = {arm: [] for arm in versions}
    for arm in schedule:
        command = [sys.executable, '-IB', str(Path(__file__).resolve()), '--worker', str(versions[arm])]
        runs[arm].append(json.loads(subprocess.check_output(command, timeout=45)))
    measurements = {}
    for arm, workers in runs.items():
        measurements[arm] = {}
        for case in CASES:
            samples = [row for run in workers for row in run['cases'][case]['samples']]
            measurements[arm][case] = {name: stats([row[name] for row in samples]) for name in samples[0]}
    receipt = {'schema': 'm1-joint-full-task-tail-dispatch-cost-v1', 'process_order': schedule,
        'samples_per_arm_and_case': SAMPLES * 3, 'warmups_per_process_and_case': 6,
        'installation_pins': {arm: pin(path) for arm, path in versions.items()},
        'raw': runs, 'summary': measurements,
        'scope': 'Warm-filesystem actual public MCP dispatch and native image formatter with saved service data. '
                 'No Blender, new rasters, model, remote time, or service solve measured.'}
    with output.open('x', encoding='utf8', newline='\n') as sink:
        json.dump(receipt, sink, ensure_ascii=False, indent=2, allow_nan=False)
        sink.write('\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', type=Path)
    parser.add_argument('--output', type=Path, default=NS / 'checks/COST.json')
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(args.worker), allow_nan=False))
    else:
        collect(args.output)
