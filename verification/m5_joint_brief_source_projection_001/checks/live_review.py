"""Recheck actual original packets and the single projected joint observation."""

import argparse
import ast
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
BASE = V / 'm5_global_observe_measure_qualification_001'
BASE_RUN = Path('D:/he_m5_global_observe_measure_qualification_001')
BASE_ARCHIVE_SHA = '8d584ee6444fc46f7d2756057178ff8bee0bf13e2902c37e43d2772e8e91cfdd'
BASE_FREEZE_SHA = '023256f3195113d417dad1fafb3f3a05c6df65356bb0c8326f9e7e0601cd9246'
BASE_RECONCILIATION_SHA = '4b48b5323c7f76528b585c3154dfa783929c288119c4caf9b9c31f656ea81f84'
RUN = Path('D:/he_m5_joint_brief_source_projection_001')
ASSET = Path('D:/he_m4_cross_scale_assembly_transfer_001/slots/QP/native/input.blend').resolve()
MAX_OUTER = 10_800
sys.path.insert(0, str(BASE / 'checks'))


def load(name, path):
    spec = spec_from_file_location(name, path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prior = load('_previous_m5_judgment', BASE / 'checks/live_review.py')
read, require, digest, verified = prior.read, prior.require, prior.digest, prior.verified
BINDING = NS / 'install/PRODUCT_RUN_BINDING.json'


def bind_terminal():
    """Bind the accepted scorer to this launcher's actual SHA-checked asset path."""
    retained = prior.pixel['score']
    original = retained['bound_terminal']
    path = Path(original.__code__.co_filename)
    source = path.read_text(encoding='utf-8')
    node = next(item for item in ast.parse(source).body
                if isinstance(item, ast.FunctionDef) and item.name == 'bound_terminal')
    body = ast.get_source_segment(source, node)
    asset_line = "original = Path(asset['asset_path']).resolve()"
    archive_line = "verified(previous_path, archived['sha256'], original.parents[1])"
    require(body.count(asset_line) == body.count(archive_line) == body.count(retained['before']) == 1,
            'retained_independent_source_anchors_changed')
    require(digest(path.read_bytes()) == retained['SOURCE_SHA'], 'retained_terminal_scorer_source_changed')
    verified(ASSET, prior.ASSET_SHA, ASSET.parent)
    body = body.replace(retained['before'], retained['after']).replace(asset_line, 'original = FIXED_ASSET')
    body = body.replace(archive_line,
                        "verified(previous_path, archived['sha256'], Path(asset['asset_path']).resolve().parents[1])")
    namespace = dict(original.__globals__, FIXED_ASSET=ASSET)
    exec(compile(body, str(path), 'exec'), namespace)
    retained['bound_terminal'] = namespace['bound_terminal']
    return path


def check_asset(slot):
    for name in ('SLOT_STARTED.json', 'SLOT_RESULT.json'):
        record = read(slot / name)
        require(Path(record['asset_path']).resolve() == ASSET and record['asset_sha256'] == prior.ASSET_SHA,
                'registered_current_asset_path_or_hash_drift/' + name)


def replay_in(directory, runtime, call):
    """Keep the old raw files intact while replaying the accepted helper."""
    original = prior.cli_replay

    def here(result, path, label, *, note_only=False):
        slot = path.relative_to(runtime / 'slots').parts[0]
        return original(result, directory / slot / label, label, note_only=note_only)

    prior.cli_replay = here
    try:
        return call()
    finally:
        prior.cli_replay = original


def preflight():
    bound_source = bind_terminal()
    old_receipt = BASE / 'checks/OFFLINE_LIVE_RECONCILIATION.json'
    old_frozen = BASE / 'FROZEN.json'
    require(digest(old_frozen.read_bytes()) == BASE_FREEZE_SHA and
            digest(old_receipt.read_bytes()) == BASE_RECONCILIATION_SHA and read(old_receipt)['passed'],
            'accepted_reference_qualification_changed')
    archive_reader, archive_pins = prior.frozen_archive(BASE / 'RUNTIME_INDEX.json', BASE_RUN, BASE_ARCHIVE_SHA)
    for row in read(BASE / 'RUNTIME_INDEX.json')['files']:
        archive_reader(BASE_RUN / row['path'])
    _, reference_frames, frame_pins = prior.historical()
    installed = prior.install_proof()
    checked = []
    for label in ('A', 'B'):
        check_asset(BASE_RUN / 'slots' / label)
        slot = {'label': label, 'passed': False}
        replay_in(HERE / 'historical_CLI_REPLAY', BASE_RUN,
                  lambda: prior.review_slot(BASE_RUN, label, BASE_FREEZE_SHA, installed,
                                            prior.truth(), reference_frames, slot))
        require(slot['passed'] and slot['outer_batch']['actual_CLI_envelope']['passed'],
                'accepted_reference_must_replay_its_original_public_and_outer_packets/' + label)
        checked.append(slot)
    saved = read(old_receipt)
    require(checked == saved['slots'], 'replayed_full_A_B_review_differs_from_accepted_evidence')
    recovered_cost = BASE / 'RESOURCE_RECHECK.json'
    costs = read(recovered_cost)['rows']
    require([len(row['public_packets']) for row in costs] == [2, 1] and
            all(not row['cost_issues'] for row in costs), 'old_raw_receipt_index_or_resource_proof_changed')
    inputs = [Path(__file__), old_receipt, old_frozen, BASE / 'RUNTIME_INDEX.json', BASE_RUN / 'ORIGINAL_RUNTIME.zip',
              recovered_cost, bound_source, ASSET, prior.GEOMETRY, prior.TRUTH, prior.BINDING,
              prior.PIXEL_PATH, prior.BLOCKER_PATH, prior.BRIEF_PATH, prior.PROOF_PATH, prior.POLICY_PATH,
              BASE / 'truth/measurement.py', BASE / 'truth/MEASUREMENT_TRUTH.json',
              BASE / 'checks/live_observation.py', BASE / 'checks/live_wire.py', BASE / 'checks/live_review.py',
              *(BASE / 'inputs' / (kind + '.json') for kind in ('OBSERVE', 'MEASURE', 'JOINT'))]
    pins = {**frame_pins, **archive_pins, **{str(path.resolve()): prior.pin(path) for path in inputs}}
    return {'passed': True, 'fixed_asset_sha256': prior.ASSET_SHA, 'actual_original_asset_path': str(ASSET),
            'original_reference_archive_sha256': BASE_ARCHIVE_SHA, 'original_reference_review_sha256': BASE_RECONCILIATION_SHA,
            'actual_new_Blender_slots': 0, 'actual_model_runs': 0, 'original_rechecked': checked,
            'actual_reference_frames': reference_frames, 'actual_reference_owned_slots': 2,
            'source_pins': [pins[path] for path in sorted(pins)]}


def candidate_install():
    binding = read(BINDING)
    require(binding['historical_preparation_git'] == prior.PRODUCT and
            binding['historical_source_sha256'] == prior.SOURCE and
            binding['changed_product_sources'] == ['human_eye_plugin/live_spatial_mcp.py'] and
            binding['unchanged_product_sources'] == 142, 'candidate_has_more_than_the_registered_projection_change')
    prior.BINDING, prior.PRODUCT = BINDING, binding['preparation_git']
    prior.SOURCE, prior.WHEEL = binding['source_sha256'], binding['wheel_sha256']
    prior.verify_measurement.__globals__['SOURCE_SHA'] = prior.SOURCE
    return prior.install_proof()


def post_projection(slot, token, installed, reference, output, result):
    status, publication, terminal, lifecycle = prior.closed_slot(slot, token, installed, 1)
    events = prior.json_lines(slot / 'PUBLIC_REQUESTS.jsonl')
    meters = [row for row in prior.json_lines(slot / 'mcp_io/MCP_IO.jsonl') if row['method'] == 'tools/call']
    event, = events
    meter, = meters
    expected = read(BASE / 'inputs/JOINT.json')
    wire = prior.raw_wire(slot, event, meter, expected)
    audit = prior.host_trace(slot, event, prior.json_lines(slot / 'product_audit.jsonl'), wire)
    exposed, internal = wire['result'], wire['producer']
    body = json.loads(exposed['content'][0]['text'])
    public_cli = prior.cli_replay(exposed, output / 'joint', 'joint')
    wrapped = replay_in(output, slot.parents[1],
                        lambda: prior.outer(slot, ('joint',), status, [wire], events))
    outer_cli = wrapped['actual_CLI_envelope']
    record = reference['original_rechecked'][1]
    before, after = record['outer_batch']['actual_CLI_envelope']['body_UTF8_bytes'], outer_cli['body_UTF8_bytes']
    baseline_a = reference['original_rechecked'][0]['outer_batch']['actual_CLI_envelope']['body_UTF8_bytes']
    delivery_ok = public_cli['passed'] and outer_cli['passed']
    limit_ok = after <= MAX_OUTER
    raster_stages = [frame['stages']['actual_raster'] for frame in internal['constructed_frames']]
    result.update(status='completed', product_source_sha256=installed['source_sha256'], wire=wire['wire'],
                  wire_timing=wire['timing'], read_context=wire['context'], audit=audit, public_CLI=public_cli,
                  outer_batch=wrapped, observed_publications={
                      'slot_result_sha256': publication['result_sha256'],
                      'slot_publication_sha256': digest((slot / 'SLOT_PUBLICATION.json').read_bytes())},
                  current_source=lifecycle,
                  pure_raster_ms=sum(prior.elapsed(stage['started_ns'], stage['closed_ns']) for stage in raster_stages),
                  owned_window_ms=prior.elapsed(status['started_ns'], publication['published_ns']),
                  startup_ms=prior.elapsed(status['started_ns'], status['ready_ns']),
                  cleanup_ms=prior.elapsed(status['cleanup_started_ns'], publication['published_ns']),
                  outer_size_gate={'passed': limit_ok, 'old_B_UTF8_bytes': before, 'old_A_UTF8_bytes': baseline_a,
                      'actual_new_B_UTF8_bytes': after, 'outer_saving_UTF8_bytes': before - after,
                      'ceiling_UTF8_bytes': MAX_OUTER, 'headroom_with_maximum_header_UTF8_bytes': 12000 - 35 - after},
                  fixed_CLI_delivery_passed=delivery_ok)
    observation = prior.verify_observation(slot, exposed, internal, terminal, installed, prior.truth())
    require(prior.compare_frames(observation['frames']) ==
            prior.compare_frames(reference['actual_reference_frames']),
            'current_original_images_or_NPZ_differ_from_registered_assembly')
    require(all(observation[key] == record['observation'][key] for key in (
                'blockers', 'public_states', 'selected_png_sha256')),
            'assembly_reference_observation_facts_or_blocker_identity_changed')
    result['observation'] = observation

    decoder = load('_reconstruct_current_joint_packet', HERE / 'offline_decode.py')
    task = decoder.decode_task(body)
    require(body['task_result']['schema_version'] == 'active-observation-region-task-result-v1',
            'actual_successful_joint_brief_was_not_projected')
    prior.public_task_equal(task, internal['task_result'])
    checker = prior.checker
    evidence_audit = checker['Audit']()
    captures, commands = checker['decode_captures'](slot, installed, evidence_audit)
    parent = checker['current_capture'](captures, internal['binding'], evidence_audit)
    task_work = internal['work']['task_query']
    require(len(captures) == len(commands) == 1 and
            task_work['reused_observation_objects'] == task_work['geometry_alias_reuses'] == 2 and
            task_work['surface_pair_count'] == 1 and task_work['supplemental_objects'] ==
            task_work.get('supplemental_capture_calls', 0) == task_work.get('additional_raster_attempts', 0) == 0,
            'joint_path_did_not_use_single_capture_or_original_measurement_scope')
    measure = prior.verify_measurement(task, terminal, parent_binding=internal['binding'], parent_capture=parent)
    require(measure['bindings']['independent_capture_binding_checked'],
            'published_measure_does_not_bind_original_current_triangles')
    result.update(passed=delivery_ok and limit_ok, measurement=measure,
                  full_measurement_reconstruction_exact=True, distinct_nested_projection=True,
                  same_generation_capture=parent['capture_state'], actual_host_capture_count=len(commands))


def review(runtime, freeze_path):
    token = digest(freeze_path.read_bytes())
    slot = runtime / 'slots/B'
    result = {'label': 'B', 'status': 'failed' if slot.exists() else 'unrun', 'passed': False}
    observed = sum(path.is_dir() for path in (runtime / 'slots').iterdir()) if (runtime / 'slots').is_dir() else 0
    if slot.exists():
        try:
            bind_terminal()
            check_asset(slot)
            installed = candidate_install()
            frozen = read(freeze_path)
            stamp = frozen['product']
            require(frozen['slots'] == ['B'] and
                    all(stamp[name] == installed[key] for name, key in (
                        ('commit', 'preparation_git'), ('source_sha256', 'source_sha256'), ('wheel_sha256', 'wheel_sha256'))),
                    'frozen_slot_or_installed_candidate_identity_changed')
            post_projection(slot, token, installed, read(HERE / 'LIVE_PREFLIGHT.json'),
                            runtime / 'preflight/CLI_REPLAY', result)
        except Exception as exc:
            result.update(error_type=type(exc).__name__, error=str(exc))
    return {'schema': 'm5-joint-brief-source-projection-live-review-v1', 'freeze_sha256': token,
            'passed': result['passed'] and observed == 1, 'slots': [result],
            'denominators': {'registered_owned': 1, 'actual_owned_slot_directories': observed,
                             'observed_public_requests': len(prior.json_lines(slot / 'PUBLIC_REQUESTS.jsonl')),
                             'observed_outer_batches': int((slot / 'batch/QUALIFICATION_BATCH.json').is_file()),
                             'proven_actual_frames': len(result.get('observation', {}).get('frames', [])),
                             'model_consumers': read(slot / 'SLOT_RESULT.json')['model_consumers']
                              if (slot / 'SLOT_RESULT.json').is_file() else 0}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--runtime', type=Path, default=RUN)
    parser.add_argument('--freeze', type=Path, default=NS / 'FROZEN.json')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    data = preflight() if args.preflight else review(args.runtime, args.freeze)
    output = args.output or HERE / ('LIVE_PREFLIGHT.json' if args.preflight else 'LIVE_REVIEW.json')
    with output.open('xb') as handle:
        handle.write(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False, default=str).encode() + b'\n')
    print(json.dumps({'passed': data['passed'], 'sha256': digest(output.read_bytes()),
                      'slots': [{key: item[key] for key in ('label', 'status', 'passed', 'error') if key in item}
                                for item in data.get('slots', data.get('original_rechecked', []))]}))
    return 0 if data['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
