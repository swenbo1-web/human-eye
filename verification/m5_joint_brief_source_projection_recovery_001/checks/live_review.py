"""Review only the recovery slot while retaining the original evidence and scorer."""

import argparse
from copy import deepcopy
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


HERE = Path(__file__).resolve().parent
NS = HERE.parent
ORIGINAL = NS.parent / 'm5_joint_brief_source_projection_001'
ORIGINAL_RUN = Path('D:/he_m5_joint_brief_source_projection_001')
RUN = Path('D:/he_m5_joint_brief_source_projection_recovery_001')


def load(name, path):
    spec = spec_from_file_location(name, path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


projection = load('_sealed_joint_projection_scorer', ORIGINAL / 'checks/live_review.py')
prior = projection.prior
read, require, digest = projection.read, projection.require, projection.digest
REFERENCE = ORIGINAL / 'checks/LIVE_PREFLIGHT.json'
OLD_FAILURE = ORIGINAL / 'checks/LIVE_REVIEW.json'


def reconcile_publication(slot, freeze, frozen, result, published):
    started = read(slot / 'SLOT_STARTED.json')
    owned_budget_passed = published['published_ns'] < result['owned_deadline_ns']
    require(started['freeze_sha256'] == result['freeze_sha256'] == freeze and
            started['label'] == result['label'] == published['label'] == slot.name == 'B' and
            started['started_ns'] == result['started_ns'] == published['started_ns'] and
            published['owned_budget_passed'] is owned_budget_passed and
            published['status'] == (result['status'] if owned_budget_passed else 'failed') and
            all(started[key] == result[key] == started['started_ns'] + frozen[seconds] * 10**9
                for key, seconds in (('task_deadline_ns', 'task_s'), ('owned_deadline_ns', 'owned_s'))) and
            published['result_sha256'] == digest((slot / 'SLOT_RESULT.json').read_bytes()) and
            result['product_git'] == frozen['product']['commit'] and
            result['product_source_sha256'] == frozen['product']['source_sha256'] and
            result['product_binding_sha256'] == digest(projection.BINDING.read_bytes()) and
            result['asset_sha256'] == frozen['asset_sha256'], 'published_slot_or_frozen_identity_changed')
    projection.check_asset(slot)


def review_deadlines(slot, state, publication):
    (event,) = prior.json_lines(slot / 'PUBLIC_REQUESTS.jsonl')
    batch = slot / 'batch/rpc_03'
    outer = read(batch / 'RECEIPT.json')
    canonical = projection.BASE_RUN / 'slots/B/batch/rpc_03/TCP_TX.bin'
    require(read(batch / 'TCP_TX.bin')['args']['message'] == read(canonical)['args']['message'],
            'actual_outer_batch_used_a_different_execute_request')
    closed = read(slot / 'RUNTIME_CLOSE.json')
    task, owned = state['task_deadline_ns'], state['owned_deadline_ns']
    public = event['receipt']
    require(state['ready_ns'] <= outer['started_ns'] <= event['started_ns'] <= public['started_ns'] <=
            public['received_complete_ns'] <= public['closed_ns'] <= event['closed_ns'] <=
            outer['received_complete_ns'] <= outer['closed_ns'] < task,
            'actual_public_or_outer_request_outside_original_task_deadline')
    exit_ns = {key: closed[key]['observed_ns'] for key in ('Blender_exit', 'public_MCP_exit')}
    owner = state['outer_owner_close']
    require(owner['confirmed'] and not owner['errors'] and state['cleanup_started_ns'] <= owner['closed_ns'] <=
            closed['closed_ns'] <= state['closed_ns'] <= publication['published_ns'] < owned and
            all(state['cleanup_started_ns'] <= observed <= closed['closed_ns'] for observed in exit_ns.values()),
            'actual_process_closes_or_publication_outside_original_owned_deadline')
    return {'passed': True, 'task_deadline_ns': task, 'owned_deadline_ns': owned,
            'public_endpoint_closed_ns': public['closed_ns'], 'outer_endpoint_closed_ns': outer['closed_ns'],
            'outer_owner_closed_ns': owner['closed_ns'], 'process_exit_observed_ns': exit_ns,
            'published_ns': publication['published_ns']}


def account(slot, result=None, frames=0):
    result = result or {}
    counts = (result.get('budget') or {}).get('counts', {})
    public_path = slot / 'PUBLIC_REQUESTS.jsonl'
    meter_path = slot / 'mcp_io/MCP_IO.jsonl'
    public = prior.json_lines(public_path) if public_path.is_file() else []
    meters = prior.json_lines(meter_path) if meter_path.is_file() else []
    outer = slot / 'batch/QUALIFICATION_BATCH.json'
    return {'registered_owned': 1, 'Blender_start_attempts': counts.get('Blender_start_attempts', 0),
            'Blender_spawned_confirmed': counts.get('Blender_spawned_confirmed', 0),
            'observed_public_requests': len(public),
            'observed_MCP_tools_calls': sum(row['method'] == 'tools/call' for row in meters),
            'observed_outer_batches': int(outer.is_file()), 'business_admissions': counts.get('business_admissions', 0),
            'raster_attempts': counts.get('all_raster_actual', 0), 'proven_actual_frames': frames,
            'model_consumers': result.get('model_consumers', 0), 'paid_API_calls': result.get('paid_API_calls', 0)}


def review_failure(slot, state, publication, denominator):
    require(publication['status'] == 'failed' and (state['errors'] or not publication['owned_budget_passed']),
            'failed_slot_must_keep_original_stage_and_reason')
    started, published = state['started_ns'], publication['published_ns']
    cleanup = state.get('cleanup_started_ns')
    require(published >= started and publication['complete_slot_ns'] == published - started and
            (cleanup is None or started <= cleanup <= published), 'failed_slot_timing_changed')
    out = {'label': 'B', 'status': 'failed', 'runtime_result_status': state['status'], 'passed': False,
           'failure_evidence_verified': True, 'published_within_owned_deadline': publication['owned_budget_passed'],
           'errors': state['errors'], 'observed_publications': {'slot_result_sha256': publication['result_sha256'],
               'slot_publication_sha256': digest((slot / 'SLOT_PUBLICATION.json').read_bytes())},
           'owned_window_ms': (published - started) / 1e6, 'actual_budget': state.get('budget'),
           'terminal_source_present': (slot / 'TERMINAL_SOURCE.json').is_file(),
           'actual_business_seen': any(denominator[key] for key in ('observed_public_requests',
               'observed_MCP_tools_calls', 'observed_outer_batches', 'business_admissions', 'raster_attempts'))}
    if cleanup is not None:
        out.update(precleanup_window_ms=(cleanup - started) / 1e6, cleanup_ms=(published - cleanup) / 1e6)
    if (slot / 'RUNTIME_CLOSE.json').is_file():
        close = read(slot / 'RUNTIME_CLOSE.json')
        exits = {name: close.get(name) for name in ('Blender_exit', 'public_MCP_exit')}
        blender = close.get('Blender_status') or {}
        terminal = blender.get('closed') or {}
        ready = blender.get('ready') or {}
        fingerprint = terminal.get('initial_geometry_fingerprint')
        if fingerprint is not None:
            require(fingerprint == ready.get('initial_fingerprint') and terminal.get('pid') == ready.get('pid'),
                    'early_failure_fingerprint_or_owned_pid_not_bound')
        out['closure'] = {'recorded': True, 'exit_receipts': exits, 'errors': close.get('errors', []),
                          'initial_fingerprint': fingerprint,
                          'final_fingerprint': terminal.get('final_geometry_fingerprint'),
                          'fingerprint_unchanged': fingerprint is not None and
                              fingerprint == terminal.get('final_geometry_fingerprint'),
                          'source_file_unchanged': blender.get('source_file_unchanged'),
                          'independent_verification': state.get('closure_verification')}
    else:
        out['closure'] = {'recorded': False}
    return out


def review(runtime, freeze_path):
    freeze = digest(freeze_path.read_bytes())
    frozen = read(freeze_path)
    slot = runtime / 'slots/B'
    names = sorted(path.name for path in slot.parent.iterdir() if path.is_dir()) if slot.parent.is_dir() else []
    result = {'label': 'B', 'status': 'unconfirmed' if 'B' in names else 'unrun', 'passed': False}
    state = None
    if (slot / 'SLOT_PUBLICATION.json').is_file():
        try:
            state, publication = (read(slot / name) for name in ('SLOT_RESULT.json', 'SLOT_PUBLICATION.json'))
            result.update(status=publication['status'], runtime_result_status=state['status'], errors=state['errors'])
            reconcile_publication(slot, freeze, frozen, state, publication)
            if publication['status'] == 'failed':
                result = review_failure(slot, state, publication, account(slot, state))
            else:
                projection.bind_terminal()
                installed = projection.candidate_install()
                require(frozen['product']['wheel_sha256'] == installed['wheel_sha256'], 'frozen_wheel_changed')
                result['original_deadlines'] = review_deadlines(slot, state, publication)
                projection.post_projection(slot, freeze, installed, read(REFERENCE),
                                           runtime / 'preflight/CLI_REPLAY', result)
                require(result['actual_host_capture_count'] == 1, 'successful_slot_missing_actual_capture')
        except Exception as exc:
            result.update(passed=False, review_error_type=type(exc).__name__, review_error=str(exc))
    counts = account(slot, state, len(result.get('observation', {}).get('frames', [])))
    counts.update(actual_owned_slot_directories=len(names), replacement_slots=0 if names in ([], ['B']) else len(names),
                  product_geometry_captures=result.get('actual_host_capture_count', 0),
                  failed_slots=int(result['status'] == 'failed'), completed_slots=int(result['status'] == 'completed'))
    accepted = (result['passed'] and names == ['B'] and counts['Blender_start_attempts'] ==
                counts['observed_public_requests'] == counts['observed_MCP_tools_calls'] ==
                counts['observed_outer_batches'] == counts['business_admissions'] == 1 and
                counts['raster_attempts'] == counts['proven_actual_frames'] == 3 and
                counts['model_consumers'] == counts['paid_API_calls'] == 0)
    counts['qualified_slots'] = int(accepted)
    return {'schema': 'm5-joint-brief-source-projection-recovery-live-review-v1', 'freeze_sha256': freeze,
            'passed': accepted, 'slots': [result], 'denominators': counts}


def preflight():
    pins = {}

    def pin(path):
        path = Path(path).resolve()
        pins[path] = prior.pin(path)
        return pins[path]

    failure = review(ORIGINAL_RUN, ORIGINAL / 'FROZEN.json')
    original_failed = read(OLD_FAILURE)
    failed, = failure['slots']
    require(not failure['passed'] and failed['failure_evidence_verified'] and
            failed['observed_publications']['slot_result_sha256'] == original_failed['slots'][0]['result_sha256'] and
            not failed['actual_business_seen'] and not failed['terminal_source_present'] and
            failed['closure']['fingerprint_unchanged'] and not failure['denominators']['proven_actual_frames'],
            'old_genuine_early_failure_did_not_reconcile_without_missing_success_paths')

    ref = read(REFERENCE)
    require(ref['passed'] and all(pin(row['path']) == row for row in ref['source_pins']),
            'historical_successful_reference_inputs_changed')
    projection.bind_terminal()
    installed = prior.install_proof()
    runtime, slot = projection.BASE_RUN, projection.BASE_RUN / 'slots/B'
    actual = {'label': 'B', 'passed': False}
    timeline = review_deadlines(slot, read(slot / 'SLOT_RESULT.json'), read(slot / 'SLOT_PUBLICATION.json'))
    with TemporaryDirectory(prefix='he_m5_joint_projection_score_') as temp:
        directory = Path(temp)
        projection.replay_in(directory / 'historical', runtime, lambda: prior.review_slot(
            runtime, 'B', projection.BASE_FREEZE_SHA, installed, prior.truth(), ref['actual_reference_frames'], actual))
        require(actual == ref['original_rechecked'][1], 'old_successful_wire_and_scorer_no_longer_agree')
        worker = ORIGINAL / 'checks/offline_assembly.py'
        completed = subprocess.check_output([sys.executable, '-I', '-B', str(worker), '--worker',
                                             str(projection.BINDING)], timeout=45)
        candidate = json.loads(completed)['actual']
        body = json.loads(candidate['content'][0]['text'])
        _, _, terminal, _ = prior.closed_slot(slot, projection.BASE_FREEZE_SHA, installed, 1)
        archive = slot / 'product_full/call_001/SERVICE_RESULT.json'
        producer = read(archive)
        observed = prior.verify_observation(slot, candidate, producer, terminal, installed, prior.truth())
        require(observed == actual['observation'], 'candidate_replay_changed_real_observation_or_images')
        decoder_path = ORIGINAL / 'checks/offline_decode.py'
        task = load('_recovery_offline_decode', decoder_path).decode_task(body)
        prior.public_task_equal(task, producer['task_result'])

        outer_source = slot / 'batch/rpc_03/RECEIPT.json'
        outer = deepcopy(read(outer_source)['response']['result'])
        wrapper = json.loads(outer['content'][0]['text'])
        wrapper['stdout'] = 'M5_GLOBAL_JOINT:' + candidate['content'][0]['text'] + '\n'
        outer['content'][0]['text'] = json.dumps(wrapper, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        public_cli = prior.cli_replay(candidate, directory / 'public_replay', 'joint')
        outer_cli = prior.cli_replay(outer, directory / 'outer_replay', 'outer', note_only=True)
        expected_path = ORIGINAL / 'checks/ASSEMBLY_OFFLINE.json'
        size = read(expected_path)
        require(public_cli['passed'] and outer_cli['passed'] and
                public_cli['body_UTF8_bytes'] == size['new_public_bytes'] and
                outer_cli['body_UTF8_bytes'] == size['new_outer_bytes'] <= projection.MAX_OUTER and
                outer['content'][1:] == candidate['content'][1:], 'candidate_route_reconstruction_changed_size_or_delivery')

    for path in (Path(__file__), ORIGINAL / 'FROZEN.json', OLD_FAILURE, REFERENCE, worker, decoder_path,
                 archive, outer_source, outer_source.with_name('TCP_TX.bin'), expected_path, projection.BINDING,
                 ORIGINAL / 'checks/live_review.py', ORIGINAL_RUN / 'slots/B/SLOT_RESULT.json',
                 ORIGINAL_RUN / 'slots/B/SLOT_PUBLICATION.json', ORIGINAL_RUN / 'slots/B/SLOT_STARTED.json',
                 ORIGINAL_RUN / 'slots/B/RUNTIME_CLOSE.json'):
        pin(path)
    return {'passed': True, 'actual_new_Blender_slots': 0, 'actual_model_runs': 0,
            'sealed_failure_replayed': {'freeze_sha256': failure['freeze_sha256'], 'slot': failed,
                                      'denominators': failure['denominators']},
            'sealed_actual_success_replayed': {'reference_slots': ['B'], 'historical_result': actual['passed'],
                 'original_frames': len(observed['frames']), 'projected_task_reconstructed': True,
                 'historical_original_deadline_result': timeline,
                 'candidate_public_body_bytes': public_cli['body_UTF8_bytes'],
                 'candidate_outer_body_bytes': outer_cli['body_UTF8_bytes'], 'both_CLI_replays_passed': True},
            'source_pins': [pins[path] for path in sorted(pins, key=str)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--runtime', type=Path, default=RUN)
    parser.add_argument('--freeze', type=Path, default=NS / 'FROZEN.json')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    data = preflight() if args.preflight else review(args.runtime.resolve(), args.freeze)
    destination = args.output or HERE / ('LIVE_PREFLIGHT.json' if args.preflight else 'LIVE_REVIEW.json')
    with destination.open('xb') as output:
        output.write(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False).encode() + b'\n')
    print(f'{destination.name} {digest(destination.read_bytes())} passed={data["passed"]}')
    return 0 if data['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
