"""Offline independent inspection of existing fake-CLI integration evidence."""
from pathlib import Path
import hashlib
import json
import zipfile

AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
B = AUTHOR / 'verification/m4_surface_scan_continuity_001_fix1'
OUT = Path(__file__).resolve().parent
CHECKS, INPUTS = [], {}

def raw(p):
    data = p.read_bytes()
    INPUTS[str(p)] = hashlib.sha256(data).hexdigest()
    return data

def read(p):
    return json.loads(raw(p))

def ck(name, value):
    CHECKS.append({'name': name, 'passed': bool(value)})

cases = []
for p in sorted((B / 'consumer/offline/attempt_03').glob('*/CASE.json')):
    case = read(p)['test']
    folder = p.parent / 'episode'
    result = read(folder / 'EPISODE_RESULT.json')
    timing = read(folder / 'FINAL_TIMING.json')
    ck(case + '_elapsed', timing['business_receipts_closed_ns'] - timing['started_ns'] == timing['full_episode_wall_ns'])
    ck(case + '_one_finish', result['owner_finish']['finish_calls'] == 1 and result['owner_finish']['confirmed'])
    ck(case + '_no_usage_claim', result['usage_aggregation'] is None and result['model_continuity_attestation'] == 'pending_actual_consumer')
    normal = case in ('test_native_three_turn_loop_and_archives', 'test_compact_three_turn_loop_and_archives')
    if normal:
        ck(case + '_three_slots', result['counts'] == {'completed': 3, 'failed': 0, 'not_run': 0} and result['qualified_execution'] and timing['qualified_execution'])
        ck(case + '_one_edit', result['owner_finish']['registered_edits'] == 1)
        consumers = [r['consumer'] for r in result['turns']]
        ck(case + '_retained_thread_work_endpoint', all(len({r[k] for r in consumers}) == 1 for k in ('thread_id', 'shared_work', 'endpoint')))
        ck(case + '_three_processes', len({r['consumer_pid'] for r in consumers}) == 3)
        for index, consumer in enumerate(consumers, 1):
            label = case + '_' + str(index)
            argv = consumer['frozen_cli_argv']
            ck(label + '_persist_resume', '--ephemeral' not in argv and ('resume' in argv) == (index > 1))
            ck(label + '_thread_binding', consumer['expected_thread_id'] == (None if index == 1 else consumers[0]['thread_id']))
            ck(label + '_process_only_cleanup', consumer['process_reaped'] and consumer['readers_stopped'] and consumer['bridge_cleanup']['confirmed'])
            ck(label + '_budget', consumer['deadline_ns'] <= result['episode_deadline_ns'] and consumer['cleanup_end_ns'] < consumer['deadline_ns'])
            ck(label + '_synthetic_only', consumer['execution_kind'] == 'synthetic_local_process' and consumer['usage_aggregation'] is None)
            ck(label + '_raw_binding', not consumer['archive']['business_binding_errors'])
        binding = read(folder / 'quality/PRIVATE_BINDING.json')
        for prefix, filename in [('consumer', 'CONSUMER_ORIGINALS.zip'), ('owner', 'OWNER_ORIGINALS.zip')]:
            archive = folder / 'quality' / filename
            ck(case + '_' + prefix + '_archive', hashlib.sha256(raw(archive)).hexdigest() == binding[prefix + '_archive_sha256'])
            with zipfile.ZipFile(archive) as z:
                actual = {name: hashlib.sha256(z.read(name)).hexdigest() for name in z.namelist()}
            ck(case + '_' + prefix + '_members', actual == binding[prefix + '_originals'])
        ck(case + '_public_envelope', hashlib.sha256(raw(folder / 'quality/public/EPISODE.json')).hexdigest() == binding['public_envelope_sha256'])
    else:
        ck(case + '_failure_not_hidden', result['qualified_execution'] is False)
        if case == 'test_provider_disabled_path_never_launches_consumer':
            ck(case + '_not_run', result['counts'] == {'completed': 0, 'failed': 0, 'not_run': 3})
        elif case == 'test_archive_failure_keeps_completed_turns_and_failed_episode':
            ck(case + '_preserved_execution', result['counts'] == {'completed': 3, 'failed': 0, 'not_run': 0} and result['archive_status'] == 'failed')
        else:
            ck(case + '_no_replacement', result['counts'] == {'completed': 1, 'failed': 1, 'not_run': 1})
    cases.append({'case': case, 'counts': result['counts'], 'qualified_execution': result['qualified_execution']})

source = raw(B / 'runtime/consumer_transport.py').decode('utf8')
coordinator = raw(B / 'consumer/episode.py').decode('utf8')
ck('actual_loop_calls_resume_and_parser', 'cli.argv_for_turn(' in source and 'cli.summarize_turn(' in source and 'subprocess.Popen(argv' in source)
ck('actual_coordinator_calls_loop', 'transport.consume_turn(' in coordinator and 'expected_thread_id=expected_thread' in coordinator)
ck('actual_launch_disabled_by_default', "plan.get('model_consumer_enabled') is not True" in source)
result = {'fixed_delivery': '1875bf45c09e8cca606f4de3fd8f0e821cc0d8a5', 'checks': len(CHECKS), 'failed': [r for r in CHECKS if not r['passed']], 'detail': CHECKS, 'cases': cases, 'input_sha256': INPUTS, 'new_Blender_product_model_API_runs': 0, 'scope': 'Reads prior synthetic integration originals, source and archive contents; does not launch any CLI or independently prove real model resume.'}
(OUT / 'CONSUMER_REVIEW.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8', newline='\n')
print(json.dumps({'checks': result['checks'], 'failed': result['failed']}))
raise SystemExit(bool(result['failed']))
