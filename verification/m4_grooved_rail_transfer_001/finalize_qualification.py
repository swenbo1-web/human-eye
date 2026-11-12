"""Bind the completed single-asset qualification and its preparation ledger."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    review = read(HERE / 'review/RESULTS.json')
    assert review['passed'], 'independent_review_unresolved'
    for name, digest in review['files_sha256'].items():
        assert sha(HERE / name) == digest, name
    final_binding = read(HERE / 'review/FINAL_BINDING.json')
    assert final_binding['passed'], 'qualification_summary_review_unresolved'
    for name, digest in final_binding['files_sha256'].items():
        assert sha(HERE / name) == digest, name
    freeze = read(HERE / 'FREEZE.json')
    for item in freeze['specifications']:
        assert sha(HERE / item['copy']) == item['sha256']
    source = read(HERE / 'SOURCE_BINDING.json')
    for row in source['source_manifest']:
        assert sha(ROOT / row['path']) == row['sha256']
        assert sha(Path(source['reused_installation']['install_root']) / row['path']) == row['sha256']
    for name, digest in read(HERE / 'PROTECTED_BEFORE.json').items():
        assert sha(Path(name)) == digest, name
    asset = read(HERE / 'asset/ASSET_BINDING.json')
    assert sha(HERE / asset['asset']) == asset['asset_sha256']
    assert sha(HERE / asset['QA_asset_copy']) == asset['asset_sha256']
    assert sha(HERE / asset['snapshot']) == asset['snapshot_sha256']
    truth = read(HERE / 'oracle/TRUTH.json')
    assert truth['actual_snapshot_sha256'] == asset['snapshot_sha256']
    preparation = read(HERE / 'worker/PREPARATION.json')
    assert preparation['errors'] == []
    for receipt in (preparation['builder'], preparation['QA_close']):
        assert receipt['process_reaped'] and receipt['exit_code'] == 0
    assert preparation['QA_close']['response']['status'] == 'closed'
    runs = [json.loads(line) for line in (HERE / 'oracle/RUNS.jsonl').read_text(encoding='utf8').splitlines() if line]
    assert len(runs) == 1 and runs[0]['truth_sha256'] == sha(HERE / 'oracle/TRUTH.json')
    ended = datetime.now(timezone.utc)
    ledger = {
        'frozen_utc': freeze['frozen_utc'], 'finalizer_input_checks_ended_utc': ended.isoformat(),
        'recorded_freeze_to_finalizer_input_checks_window_s': (ended - datetime.fromisoformat(freeze['frozen_utc'])).total_seconds(),
        'window_scope': 'Local freeze through preparation, independent offline oracle, review and finalizer input checks. Excludes subsequent ledger/ready/manifest publication, Git and callback. Earlier reading and coordinator/reviewer resource fees are unmeasured.',
        'asset_controller_wall_s': preparation['elapsed_ns'] / 1e9,
        'builder_wall_s_nested_in_controller': preparation['builder']['elapsed_ns'] / 1e9,
        'QA_close_wall_s_nested_in_controller': preparation['QA_close']['elapsed_ns'] / 1e9,
        'oracle_analysis_wall_s': truth['analysis_elapsed_ns'] / 1e9,
        'oracle_with_publication_wall_s': runs[0]['elapsed_through_publication_ns'] / 1e9,
        'timing_overlap': 'Builder and close are inside controller. Oracle analysis is inside oracle publication window. These work windows fall within freeze-to-finalizer-input-checks and remain separate.',
        'owned_Blender_processes': preparation['Blender_sessions_started_or_attempted'],
        'geometric_candidates': 1, 'construction_failures': len(preparation['errors']),
        'oracle_runs': len(runs), 'oracle_exceptions': sum(row['exception'] is not None for row in runs),
        'evaluation_consumers': 0, 'product_pretests': 0, 'images': 0,
        'coordinator_and_review_resource_cost': None, 'monetary_fee_status': 'unmeasured',
    }
    save(HERE / 'PREPARATION_LEDGER.json', ledger)
    result = {
        'stage': 'M4-GROOVED-RAIL-TRANSFER-001_QUALIFICATION_READY',
        'qualification_status': truth['qualification_status'], 'independent_review_passed': review['passed'],
        'parent_commit': freeze['parent_commit'], 'baseline_commit': freeze['baseline_commit'],
        'product_commit': source['product_commit'], 'source_count': source['source_count'],
        'source_sha256': source['source_sha256'], 'counts': truth['counts'],
        'asset_sha256': asset['asset_sha256'], 'actual_snapshot_sha256': asset['snapshot_sha256'],
        'truth_sha256': sha(HERE / 'oracle/TRUTH.json'),
        'design_sha256': sha(HERE / 'spec/DESIGN.md'), 'plan_sha256': sha(HERE / 'spec/PLAN.md'),
        'independent_review_sha256': sha(HERE / 'review/RESULTS.json'),
        'independent_final_binding_sha256': sha(HERE / 'review/FINAL_BINDING.json'),
        'preparation_ledger_sha256': sha(HERE / 'PREPARATION_LEDGER.json'),
        'qualification_checks': truth['qualification_checks'],
        'failed_qualification_checks': [row['check'] for row in truth['qualification_checks'] if not row['passed']],
        'worker_close_confirmed': True, 'geometry_candidates': 1,
        'evaluation_consumers': 0, 'product_pretests': 0, 'images': 0,
        'representation': freeze['implementation_representation'],
        'scope': 'One deliberately constructed small nonconvex assembly and independent actual-geometry qualification.',
        'next_gate': 'Administrator reviews this frozen input before dispatching the later fixed six-consumer phase.',
    }
    save(HERE / 'QUALIFICATION_READY.json', result)
    paths = sorted((path for path in HERE.rglob('*') if path.is_file()),
                   key=lambda path: path.relative_to(HERE).as_posix())
    assert not any('__pycache__' in path.parts or path.suffix in ('.pyc', '.pyo') for path in paths)
    save(HERE / 'QUALIFICATION_MANIFEST.json', {
        'scope': 'All qualification files before this manifest. No product or consumer trial results.',
        'files': [{'path': path.relative_to(HERE).as_posix(), 'bytes': path.stat().st_size,
                   'sha256': sha(path)} for path in paths],
    })
    print(json.dumps({'qualification_status': truth['qualification_status'], 'counts': truth['counts'],
                      'files_indexed': len(paths), 'owned_workers_closed': True}))


if __name__ == '__main__':
    main()
