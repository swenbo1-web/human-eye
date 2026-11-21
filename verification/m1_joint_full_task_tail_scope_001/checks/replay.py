"""Keep the accepted single-distance and legacy compatibility packets byte-identical."""

import argparse
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys


PRIOR = 'm1_joint_full_task_tail_001'
OLD_COMMIT = '54f3a7974'
BASE_SOURCE = '5da861b729604309aa2c7aff7b0974d1ed08bfe7c95b8d8956f0c86241d09e8a'
BASE_GIT_PREFIX = '475ae93a'
HISTORIC_STAGE_SHA = {
    'Far00': '1806676984b4b3892184ec1f6be619cd3c7e5a26862f7fe98f7281062cf34a09',
    'M09': '58778dae7e82a3923e7c5dfb2c41abf3359e956c0d2baaff8ae4ca440d600043',
}


def require(value, code):
    if not value:
        raise ValueError(code)


def main(repo, base_path, candidate, report_path, wires):
    v = repo / 'verification' / PRIOR
    previous = v.relative_to(repo).as_posix()

    def old_blob(relative):
        return subprocess.check_output(['git', 'show', OLD_COMMIT + ':' + previous + '/' + relative],
                                       cwd=repo)

    controls_file = 'checks/controls.py'
    source_file = 'checks/check.py'
    for pinned in (source_file, controls_file, 'checks/REPLAY.json', 'checks/CONTROLS.json'):
        require((v / pinned).read_bytes() == old_blob(pinned), 'prior_review_git_blob_changed/' + pinned)
    archive = run_path(str(v / source_file))
    controls = run_path(str(v / controls_file))
    emit, read, pin, digest, mcp = (archive[key] for key in ('emit','read','pin','digest','mcp_bytes'))
    base = read(base_path)
    install = read(candidate)
    require(base['source_sha256'] == BASE_SOURCE and base['preparation_git'].startswith(BASE_GIT_PREFIX)
            and len(base['source_manifest']) == len(install['source_manifest']) == 143
            and install['source_sha256'] != base['source_sha256'],
            'actual_A_B_install_identity_or_source_manifest_not_fixed')
    require(not wires.exists() and not report_path.exists(), 'fresh_control_output_location_required')
    wires.mkdir(parents=True)
    stages = wires / 'stages'
    stages.mkdir()
    baseline = archive['run_worker'](repo, base_path, wires / 'A')
    proposed = archive['run_worker'](repo, candidate, wires / 'B')
    require(baseline['source_sha256'] == BASE_SOURCE and proposed['source_sha256'] == install['source_sha256']
            and baseline['source_pins'] == proposed['source_pins'],
            'current_one_or_both_installed_replay_sources_changed')
    cases = {}
    for key, known_sha in HISTORIC_STAGE_SHA.items():
        a, b = [worker['cases'][key] for worker in (baseline, proposed)]
        original = old_blob('evidence/' + key + '-actual_B_replay.bin')
        require(digest(original) == known_sha
                and mcp(a['replayed']) == mcp(b['replayed']) == original
                and a['archived'] == b['archived']
                and a['catalogue'] == b['catalogue']
                and a['task_truth'] == b['task_truth']
                and a['whole_producer_sha256'] == b['whole_producer_sha256']
                and archive['body'](b['replayed']['result']).get('task_result') == b['task_truth']
                and list(archive['body'](b['replayed']['result']))[-1] == 'task_result',
                'single_distance_actual_replay_no_longer_matches_accepted_475_packet/' + key)
        old_stages, old_images, old_unknown = archive['cli_checks'](repo, a['replayed']['result'])
        known, images, unknown = archive['cli_checks'](repo, b['replayed']['result'], stages, key)
        for single, replayed in zip(old_stages, known, strict=True):
            normalized = {k: val for k, val in replayed.items() if k != 'actual_replay_stage'}
            require(single == normalized and replayed['all_required'], 'single_distance_fixed_CLI_witness_or_whole_fact_lost')
        require(old_images == images and old_unknown == unknown and len(known) == 6,
                'single_distance_unknown_region_or_original_image_chain_changed')
        if a['standalone'] is not None:
            require(mcp(a['standalone']['reply']) == mcp(b['standalone']['reply']),
                    'Far00_independent_followup_replay_changed')
        cases[key] = {'frozen_old_B': {'reference': previous + '/evidence/' + key + '-actual_B_replay.bin',
                                      'sha256': known_sha, 'bytes': len(original)},
                      'live_serialized_archival_A': a['replayed_packet'], 'live_serialized_archival_B': b['replayed_packet'],
                      'history_archived_callback': a['outer'], 'witness_membership': a['current_witness_membership'],
                      'complete_original_images': images, 'retained_unknown_regions': unknown,
                      'six_CLI_stages': known, 'equal_actual_tools_list': True,
                      'A_B_exact_same_bytes': True,
                      'full_body_UTF8_bytes': len(b['replayed']['result']['content'][0]['text'].encode()),
                      'serialized_handler_median_ns': {'A': a['serialized_elapsed_ns_median'], 'B': b['serialized_elapsed_ns_median']},
                      'serialized_handler_trials_per_arm': 21}

    # The accepted engineering compatibility run uses the real writer, which
    # also checks EOF/close and whether each selector reached the archived producer.
    control_a = controls['spawn_worker'](repo, base_path, wires / 'compat_A')
    control_b = controls['spawn_worker'](repo, candidate, wires / 'compat_B')
    require(control_a['source_sha256'] == BASE_SOURCE and control_b['source_sha256'] == install['source_sha256']
            and control_a['source_pins'] == control_b['source_pins']
            and control_a['outputs'].keys() == control_b['outputs'].keys(), 'existing_control_bindings_changed')
    check_cases = {}
    for control, a in control_a['outputs'].items():
        b = control_b['outputs'][control]
        pa, pb = (Path(out['RX']['path']) for out in (a,b))
        require(pa.read_bytes() == pb.read_bytes()
                and a['actual_stdio_close_verified'] and b['actual_stdio_close_verified'],
                'legacy_compatibility_actual_wire_changed/' + control)
        if control == 'unknown_measurement_preserved':
            reply = read(pb)
            value = archive['body'](reply['result'])
            unknown = value['task_result']['facts']['surface_proximity']
            require(set(value['task_result']['facts']) == {'surface_proximity'}
                    and unknown == {'status': 'unknown', 'value': None,
                                   'reason': 'synthetic_control_unknown_measurement'}
                    and list(value)[-1] == 'task_result',
                    'surface_proximity_only_unknown_reason_or_scope_not_preserved')
            replayed, _, _ = archive['cli_checks'](repo, reply['result'], stages, 'unknown')
            require(len(replayed) == 6 and all(row['all_required'] for row in replayed),
                    'single_distance_unknown_not_preserved_through_CLI')
            check_cases[control] = {'A': a, 'B': b, 'all_bytes_equal': True, 'unknown_is_synthetic': True,
                                    'actual_unknown_fact': unknown, 'six_CLI_stages': replayed}
        else:
            check_cases[control] = {'A': a, 'B': b, 'all_bytes_equal': True}

    sources = [pin(base_path), pin(candidate), pin(Path(__file__))]
    sources += [pin(v / path) for path in (source_file, controls_file, 'checks/REPLAY.json', 'checks/CONTROLS.json')]
    source_pins = {item['path']: item for item in
                   sources + baseline['source_pins'] + control_a['source_pins']}
    value = {'schema': 'm1-joint-full-task-tail-scope-actual-positive-v1', 'passed': True,
             'historical_evidence_commit': subprocess.check_output(
                 ['git', 'rev-parse', OLD_COMMIT], cwd=repo).decode().strip(),
             'A_product': {'commit': base['preparation_git'], 'run_source': BASE_SOURCE},
             'B_product': {'commit': install['preparation_git'], 'run_source': install['source_sha256']},
             'two_real_positive_slots_replayed': 2, 'positive_CLI_stage_checks': 12,
             'old_and_new_Git_qualified_single_replies_exactly_equal': True,
             'replies': cases, 'previous_compatibility_wire_count': len(check_cases),
             'previous_compatibility_wires_byte_identical': check_cases,
             'source_pins': list(source_pins.values()), 'Blender_starts': 0, 'model_starts': 0,
             'asset_rebuilds': 0, 'new_rasters': 0, 'paid_API': 0,
             'scope': 'The successful two historical requests and existing controls. New multi-fact tests are recorded separately.'}
    result = emit(report_path, json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2).encode() + b'\n')
    print(result, flush=True)


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'use_isolated_Python_-I_-B')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--wire-dir', type=Path, required=True)
    args = parser.parse_args()
    root = args.repo.resolve(strict=True)
    a = args.baseline or root / 'verification' / PRIOR / 'install/PRODUCT_RUN_BINDING.json'
    main(root, a, args.candidate, args.output, args.wire_dir)
