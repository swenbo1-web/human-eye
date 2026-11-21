"""Verify the one stopped qualification without modifying its frozen code or reopening a slot."""

from hashlib import sha256
import importlib.util
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys


NS = Path(__file__).resolve().parents[1]
RUN = Path('D:/he_perf050_source_scope_rank_transfer_001')
LABELS = ('QN', 'QP', 'N1', 'P1')


def read(path):
    return json.loads(path.read_bytes())


def pin(path):
    data = path.read_bytes()
    return {'path':str(path), 'bytes':len(data), 'sha256':sha256(data).hexdigest()}


def require(value, reason):
    if not value:
        raise ValueError(reason)


def geometry(slot, result):
    oracle = run_path(str(NS/'checks/truth.py'))
    meshes, _ = oracle['frozen_meshes']()
    before_path = slot/'initial_capture/TERMINAL_SOURCE.json'
    after_path = slot/'TERMINAL_SOURCE.json'
    before, after = read(before_path), read(after_path)
    initial = oracle['verifies_geometry'](before, meshes)
    final = oracle['verifies_geometry'](after, meshes)
    require(initial == final and before['source']['pid'] == after['source']['pid']
            and Path(before['source']['asset_copy']) == Path(after['source']['asset_copy']) == slot/'native/input.blend',
            'closed_slot_no_longer_binds_to_same_owned_source')
    require(pin(before_path)['sha256'] == result['initial_source']['sha256']
            and pin(after_path)['sha256'] == result['terminal_source']['sha256'], 'current_source_receipts_changed')
    copy = pin(slot/'native/input.blend')
    require(copy['sha256'] == oracle['ASSET_SHA'] == result['asset_sha256'], 'source_asset_changed')
    return {'initial':pin(before_path), 'terminal':pin(after_path), 'owned_asset_copy':copy, 'match':initial,
            'same_owned_pid':before['source']['pid']}


def importer_control(freeze, result):
    product = read(NS.parent/'m1_joint_full_task_tail_scope_001/install/PRODUCT_RUN_BINDING.json')
    shared = read(NS.parent/'m5_harness_recovery_001/SHARED_DEPENDENCY.json')
    # Recreate only the original module lookup. No owner, Blender, tool or model is started.
    code = '''
import json
from pathlib import Path
import sys
sys.path[:0]=sys.argv[1:5]
import runtime
try:
    from runtime import transport
except ImportError as exc:
    original = {'type':type(exc).__name__,'message':str(exc)}
else:
    raise RuntimeError('archived_IMPORT_error_did_not_reproduce')
retained = runtime.previous.transport.StdioClient
print(json.dumps({'import_error':original,'loaded_runtime':runtime.__file__,
                  'retained_client_class':retained.__qualname__,'retained_client_source':retained.__init__.__code__.co_filename}))
'''
    root = NS.parents[1]
    argv = [sys.executable,'-IB','-c',code,str(NS),product['dependency_root'],shared['dependency_root'],str(NS/'harness')]
    replay = json.loads(subprocess.check_output(argv, cwd=root, timeout=35))
    failure = result['errors'][0]
    require(replay['import_error'] == {key:failure[key] for key in ('type','message')}
            and Path(replay['loaded_runtime']) == NS/'harness/runtime.py', 'source_failure_replay_changed')
    client = Path(replay['retained_client_source']).resolve(strict=True)
    want = next(entry for entry in freeze['direct_inputs'] if Path(entry['path']) == client)
    require(pin(client) == want, 'retained_client_is_not_the_frozen_client')
    replay['frozen_client_receipt'] = want
    return replay


def main():
    frozen_path = NS/'FROZEN.json'
    frozen = read(frozen_path)
    require(frozen['slots'] == list(LABELS), 'original_denominator_changed')
    for row in frozen['direct_inputs']:
        require(pin(Path(row['path'])) == row, 'frozen_source_mutation/' + row['path'])
    slot = RUN/'slots/QN'
    result_path = slot/'SLOT_RESULT.json'
    result, receipt = read(result_path), read(slot/'SLOT_PUBLICATION.json')
    journal_path = RUN/'preflight/FORMAL_SEQUENCE.jsonl'
    journal = [json.loads(line) for line in journal_path.read_bytes().splitlines()]
    closed = result['closure_verification']
    require(receipt['result_sha256'] == pin(result_path)['sha256'] == journal[-1]['result_sha256']
            and journal[-1]['safe_to_continue'] is False and len(journal) == 2
            and receipt['status'] == result['status'] == 'failed' and receipt['owned_budget_passed'] is True
            and closed['status'] == 'ready_closed' and closed['passed'] is True
            and result['independent_before_after']['passed'] is True and result['model_consumers'] == 0
            and result['actual_model_admitted'] is False and result['diagnostic_calls'] == []
            and list((RUN/'slots').iterdir()) == [slot], 'unexpected_live_execution_or_closure')
    details = geometry(slot, result)
    offline = importer_control(frozen, result)
    costs = {'full_owned_window_ms':receipt['complete_slot_ns']/1e6,
             'freeze_admission_ms':result['admission_verification_ns']/1e6,
             'startup_and_ready_after_admission_ms':(result['ready_ns'] - result['started_ns'] - result['admission_verification_ns'])/1e6,
             'ready_to_cleanup_ms':(result['cleanup_started_ns'] - result['ready_ns'])/1e6,
             'cleanup_to_publication_ms':(receipt['published_ns'] - result['cleanup_started_ns'])/1e6,
             'budget_counts':result['budget']['counts'], 'tool_calls':0, 'public_PNGs':0, 'CLI_usage_events':None}
    report = {'schema':'perf050-source-scope-rank-transfer-001-stopped-v1', 'qualification_passed':False,
              'cause':'qualification_runtime_import_before_any_business_call', 'freeze':pin(frozen_path),
              'slots':[{'label':label, 'status':'failed' if label == 'QN' else 'unrun',
                        'owned_started':int(label == 'QN'),'models_started':0} for label in LABELS],
              'frozen_control':offline, 'source_match':details, 'costs':costs,
              'observed_receipts':[pin(p) for p in (result_path,slot/'SLOT_PUBLICATION.json',slot/'RUNTIME_CLOSE.json',journal_path)],
              'provider_wall_clock':None, 'provider_usage':None, 'provider_billing':None,
              'product_diff_files':0, 'product_builds':0, 'replacements':0, 'asset_rebuilds':0,
              'Google_calls':0, 'extra_API_calls':0, 'extra_costs':0}
    with (NS/'checks/STOPPED.json').open('x', encoding='utf8', newline='\n') as target:
        json.dump(report, target, ensure_ascii=False, indent=2, allow_nan=False)
        target.write('\n')
    print(json.dumps(costs, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
