"""Verify frozen evidence and execution closure without scoring or cost analysis."""

import hashlib
import json
from pathlib import Path


BATCH = Path(__file__).resolve().parent.parent
ROOT = BATCH.parents[1]


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    plan = read(BATCH / 'PLAN.json')
    assert read(BATCH / 'FREEZE.json')['plan_sha256'] == sha(BATCH / 'PLAN.json')
    assert read(BATCH / 'GO.json')['plan_sha256'] == sha(BATCH / 'PLAN.json')
    for name, expected in plan['dispatch_input_sha256'].items():
        assert sha(BATCH / name) == expected, name
    for name, expected in plan['external_input_sha256'].items():
        assert sha(Path(name)) == expected, name
    protected = read(BATCH / 'preflight/PROTECTED_BEFORE.json')
    for name, expected in protected.items():
        actual = sha(Path(name)) if Path(name).is_file() else None
        assert actual == expected, name
    binding = read(BATCH / 'preflight/SOURCE_BINDING.json')
    ready = read(BATCH / 'installations/P_READY.json')
    assert len(binding['source_manifest']) == plan['source_count'] == 137
    for row in binding['source_manifest']:
        assert sha(ROOT / row['path']) == row['sha256'], row['path']
        assert sha(Path(ready['install_root']) / row['path']) == row['sha256'], row['path']
    assert sha(Path(ready['entry'])) == ready['launcher_sha256']
    assert sha(Path(ready['release']) / 'admin/RUNTIME_BINDING.json') == ready['binding_sha256']

    result = read(BATCH / 'RUN_RESULT.json')
    assert result['stop'] is None and result['no_replacements']
    assert result['all_planned_dispatched'] and result['started_cells'] == 6
    assert len(result['records']) == len(plan['sequence']) == 6
    for row, slot in zip(result['records'], plan['sequence'], strict=True):
        assert all(row[key] == value for key, value in slot.items())
        assert row['errors'] == [] and row['within_570s']
        assert not row.get('product_channel_poisoned', False)
        consumer = row['consumer']
        for key in ('valid_completion', 'safe_to_continue', 'process_reaped', 'readers_stopped',
                    'cli_output_file_present', 'cli_output_matches_public_final'):
            assert consumer[key], (row['cell'], key)
        assert consumer['status'] == 'completed' and consumer['exit_code'] == 0
        for key in ('errors', 'unexpected_tool_deviations', 'bridge_protocol_errors'):
            assert consumer[key] == [], (row['cell'], key)
        assert not consumer['deadline_timer_fired'] and not consumer['mutation_unknown']
        for key in ('public_image_count', 'public_image_bytes', 'input_image_count', 'input_image_bytes'):
            assert consumer[key] == 0, (row['cell'], key)
        assert '--image' not in consumer['argv']
        assert consumer['input_sha256'] == plan['inputs']['prompt_sha256']
        finish = row['finish']
        assert finish['confirmed'] and finish['exit_code'] == 0
        assert finish['finish_signal_error'] is None
        close = finish['close']
        assert close['confirmed'] and close['errors'] == []
        assert close['geometry_unchanged'] and close['asset_unchanged']
        assert close['zero_new_images_budget_met'] and not close['image_construction']['observed']
        assert close['native_close']['process_reaped'] and close['native_close']['exit_code'] == 0
        assert not close['worker_closed']['poisoned']
        if close['product_runtime_exit'] is not None:
            runtime = close['product_runtime_exit']
            assert runtime['confirmed'] and runtime['exited'] and runtime['exit_code'] == 0
            assert runtime['handle_closed']
            assert close['plugin_close']['confirmed'] and close['plugin_close']['reader_stopped']

    public = BATCH / 'runtime/handoff_01/public'
    provenance = read(BATCH / 'runtime/handoff_01/private/PROVENANCE.json')
    actual_files = {path.relative_to(public).as_posix(): sha(path)
                    for path in public.rglob('*') if path.is_file()}
    assert actual_files == provenance['public_files_sha256']
    index = read(public / 'INDEX.json')
    assert index['fixed_slots'] == 6 and len(index['answers']) == 6
    assert not index['scoring_performed']
    assert all(row['execution_record_state'] == 'completed' for row in index['answers'])
    assert all(row['answer_state'] == 'present' for row in index['answers'])
    manifest = [{'path': name, 'bytes': (public / name).stat().st_size, 'sha256': digest}
                for name, digest in sorted(actual_files.items())]
    canonical = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf8')
    packet_sha = hashlib.sha256(canonical).hexdigest()
    save(BATCH / 'PUBLIC_PACKET_MANIFEST.json', {
        'algorithm': 'sha256 of UTF-8 compact sorted-key JSON file list, paths sorted lexically',
        'public_directory': public.relative_to(BATCH).as_posix(),
        'files': manifest,
        'packet_sha256': packet_sha,
    })
    save(BATCH / 'POSTRUN_INTEGRITY.json', {
        'cycle_id': plan['cycle_id'], 'plan_sha256': sha(BATCH / 'PLAN.json'),
        'completed': 6, 'execution_failed': 0, 'not_run': 0, 'execution_anomalies': [],
        'frozen_dispatch_inputs_unchanged': True, 'frozen_external_inputs_unchanged': True,
        'protected_inputs_unchanged': True, 'source_and_installation_files_verified': 137,
        'all_registered_processes_closed': True, 'all_recorded_geometry_and_assets_unchanged': True,
        'initial_images': 0, 'recorded_new_images': 0,
        'image_scope': 'Recorded original helper scan and render hooks. Arbitrary Python uses the existing audit boundary.',
        'public_provenance_hashes_match': True, 'public_packet_sha256': packet_sha,
        'scoring_performed': False, 'cost_analysis_performed': False,
        'model_or_product_calls_by_this_verifier': 0,
    })
    print(json.dumps({'completed': 6, 'execution_failed': 0, 'not_run': 0,
                      'public_packet_sha256': packet_sha, 'scoring_performed': False}))


if __name__ == '__main__':
    main()
