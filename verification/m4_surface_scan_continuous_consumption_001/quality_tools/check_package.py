"""Check anonymous projection bindings without judging content or cost."""

import argparse
import importlib.util
from pathlib import Path
import zipfile


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('_continuous_quality_checker_pack', HERE / 'pack_quality.py')
pack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pack)


def check_package(output):
    output = Path(output).resolve()
    public = output / 'public'
    binding_raw = (output / 'private/BINDING.json').read_bytes()
    binding = pack.decode(binding_raw)
    receipt = pack.read_json(output / 'PACKAGE_RECEIPT.json')
    index = pack.read_json(public / 'INDEX.json')
    mapping = pack.validate_mapping(binding['mapping'])
    failures, checks = [], []

    def check(condition, label):
        checks.append({'check': label, 'passed': bool(condition)})
        if not condition:
            failures.append(label)

    check(receipt['private_binding_sha256'] == pack.sha(binding_raw), 'private_binding_receipt')
    check(receipt['archive_sha256'] == pack.sha((output / 'ANONYMOUS_QUALITY.zip').read_bytes()), 'public_zip_receipt')
    actual_public = {path.relative_to(public).as_posix(): {'bytes': path.stat().st_size,
                     'sha256': pack.sha(path.read_bytes())} for path in public.rglob('*') if path.is_file()}
    check(actual_public == binding['public_files'], 'complete_public_inventory')
    with zipfile.ZipFile(output / 'ANONYMOUS_QUALITY.zip') as bundle:
        check(len(bundle.namelist()) == len(set(bundle.namelist())), 'no_duplicate_public_zip_members')
        check(set(bundle.namelist()) == set(actual_public), 'public_zip_exact_inventory')
        check(all(bundle.read(name) == (public / name).read_bytes() for name in bundle.namelist()), 'public_zip_exact_bytes')
    mapping_raw = Path(binding['mapping_path']).read_bytes()
    check(pack.sha(mapping_raw) == binding['mapping_sha256'], 'frozen_mapping_original_bytes')
    check(pack.decode(mapping_raw) == binding['mapping'], 'mapping_private_copy')
    run_raw = Path(binding['run_result_path']).read_bytes()
    check(pack.sha(run_raw) == binding['run_result_sha256'], 'formal_run_result_original_bytes')
    check(pack.sha((Path(binding['batch']) / 'PLAN.json').read_bytes()) == binding['plan_sha256'], 'frozen_plan_original_bytes')
    check(all(pack.sha((pack.ROOT / name).read_bytes()) == digest
              for name, digest in binding['reused_sources'].items()), 'reused_projection_and_scoring_bytes')
    check(pack.sha((HERE / 'pack_quality.py').read_bytes()) == binding['pack_source_sha256'], 'packer_source_bytes')
    check(index['planned_episodes'] == 6 and index['planned_turns'] == 18, 'fixed_denominators')
    expected_order = sorted(row['anonymous_episode_id'] for row in mapping)
    check(index['anonymous_episode_order'] == expected_order, 'anonymous_order_independent_of_dispatch')
    check(index['content_quality'] == 'unscored' and receipt['quality'] == 'unscored', 'content_unscored')
    check(binding['cost_unsealed'] is False and receipt['cost_unsealed'] is False, 'cost_sealed')
    check(all(actual_public[name]['sha256'] == digest for name, digest in index['fixed_quality_materials'].items()),
          'fixed_public_quality_materials')
    for name, digest in pack.MATERIALS.items():
        check(actual_public['scoring/' + name]['sha256'] == digest, 'truth_or_snapshot:' + name)
    for name, digest in pack.PROMPTS:
        check(actual_public['tasks/' + name]['sha256'] == digest, 'complete_prompt:' + name)
    private_by_anon = {row['anonymous_episode_id']: row for row in binding['episodes']}
    totals = {'completed': 0, 'failed': 0, 'not_run': 0}
    episode_totals = {'completed': 0, 'execution_failure': 0, 'not_run': 0}
    map_by_anon = {row['anonymous_episode_id']: row for row in mapping}
    for anon in expected_order:
        episode = pack.read_json(public / anon / 'EPISODE.json')
        private = private_by_anon[anon]
        check(episode['anonymous_episode_id'] == anon, anon + ':episode_binding')
        check(len(episode['turns']) == 3, anon + ':three_slots')
        check(episode['content_quality'] == 'unscored', anon + ':episode_unscored')
        episode_totals[episode['execution_state']] += 1
        original = private['original_sources']
        if original is not None:
            folder = Path(original['folder'])
            archive = folder / 'ORIGINALS.zip'
            manifest_path = folder / 'RUNTIME_MANIFEST.json'
            archive_available = (archive.exists() and manifest_path.exists()
                                 and 'archive_sha256' in original and 'manifest_sha256' in original)
            check(archive_available, anon + ':outer_archive_and_manifest_available')
            if archive_available:
                check(pack.sha(archive.read_bytes()) == original['archive_sha256'], anon + ':outer_archive')
                check(pack.sha(manifest_path.read_bytes()) == original['manifest_sha256'], anon + ':outer_manifest')
                manifest = pack.read_json(manifest_path)
                with zipfile.ZipFile(archive) as bundle:
                    members = {name: {'bytes': len(bundle.read(name)), 'sha256': pack.sha(bundle.read(name))}
                               for name in bundle.namelist()}
                    check(members == original['members'] == manifest['members'], anon + ':all_original_members')
                    check(all(members.get(name) == meta for name, meta in private['used_sources'].items()),
                          anon + ':every_projected_source_bound')
            check(not private['source_issues'], anon + ':source_consistency')
            timing_available = (folder / 'FINAL_TIMING.json').exists() and 'outer_timing_sha256' in private
            check(timing_available, anon + ':outer_authoritative_timing_available')
            timing = {}
            if timing_available:
                timing_raw = (folder / 'FINAL_TIMING.json').read_bytes()
                check(pack.sha(timing_raw) == private['outer_timing_sha256'], anon + ':outer_authoritative_timing_bytes')
                timing = pack.decode(timing_raw)
                check(episode['outer_valid_completion'] == timing.get('outer_valid_completion'), anon + ':outer_timing_projection')
            check(all((folder / name).exists() and pack.sha((folder / name).read_bytes()) == meta['sha256']
                      for name, meta in private['outer_receipts'].items()), anon + ':outer_receipt_binding')
            if episode['execution_state'] == 'completed':
                check(timing.get('outer_valid_completion') is True and not episode['outer_errors']
                      and not episode['coordinator_errors'] and all(turn['valid_completion'] for turn in episode['turns']),
                      anon + ':strict_episode_completion')
        else:
            check(episode['entered'] is False, anon + ':no_unbound_entered_episode')
        counts = {'completed': 0, 'failed': 0, 'not_run': 0}
        for index_turn, turn in enumerate(episode['turns'], 1):
            prefix = anon + ':turn_' + str(index_turn)
            directory = public / anon / ('turn_' + str(index_turn))
            check(pack.read_json(directory / 'TURN.json') == turn, prefix + ':envelope_bytes')
            check(turn['turn_index'] == index_turn and turn['turn_label'] == pack.LABELS[index_turn - 1],
                  prefix + ':fixed_turn_order')
            check(turn['anonymous_turn_id'] == map_by_anon[anon]['anonymous_turn_ids'][index_turn - 1],
                  prefix + ':anonymous_turn_binding')
            check(turn['content_quality'] == 'unscored', prefix + ':unscored')
            check(not ({'group', 'cell', 'pair', 'argv', 'usage', 'thread_id', 'deadline_ns', 'folder'} & set(turn)),
                  prefix + ':no_known_admin_turn_fields')
            counts[turn['execution_state']] += 1
            private_turn = private['turns'][index_turn - 1]
            answer = directory / 'answer.txt'
            if private_turn.get('not_run'):
                check(turn['execution_state'] == 'not_run' and not answer.exists(), prefix + ':not_run_preserved')
            else:
                check(turn['execution_state'] != 'not_run', prefix + ':entered_failure_preserved')
                check(answer.exists() == turn['final_present'], prefix + ':confirmed_final_presence')
                if answer.exists():
                    check(pack.sha(answer.read_bytes()) == private_turn['answer_sha256'], prefix + ':exact_answer_bytes')
                    check(original['members'].get(private_turn['final_member'], {}).get('sha256') == private_turn['answer_sha256'],
                          prefix + ':answer_original_binding')
                evidence = directory / 'tool_evidence.json'
                check(pack.sha(evidence.read_bytes()) == private_turn['business_projection']['published_tool_evidence_sha256'],
                      prefix + ':full_business_projection')
            if turn['valid_completion']:
                check(turn['execution_state'] == 'completed' and turn['final_present']
                      and not turn['errors'] and not turn['summary_errors'] and not turn['public_error_events']
                      and not turn['source_consistency_issues'], prefix + ':strict_turn_completion')
        check(counts == episode['counts'], anon + ':turn_counts')
        for state in totals:
            totals[state] += counts[state]
    check(totals == index['counts'] == receipt['counts'] and sum(totals.values()) == 18, 'eighteen_slot_counts')
    check(episode_totals == index['episode_counts'] and sum(episode_totals.values()) == 6, 'six_episode_counts')
    return {'schema': 'continuous_quality_binding_check_v1', 'passed': not failures,
            'failures': failures, 'checks': checks, 'planned_episodes': 6, 'planned_turns': 18,
            'counts': totals, 'episode_counts': episode_totals, 'quality': 'unscored', 'cost_unsealed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    result = check_package(args.output)
    if args.receipt:
        pack.put(args.receipt, pack.encoded(result))
    print(pack.encoded(result).decode(), end='')
    raise SystemExit(0 if result['passed'] else 1)
