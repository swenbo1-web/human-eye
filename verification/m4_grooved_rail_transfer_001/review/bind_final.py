"""Bind the statically reviewed final summary without running its publisher."""

import ast
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert not (HERE / 'FINAL_BINDING.json').exists()
    files = ('REPORT.md', 'finalize_qualification.py', 'review/RESULTS.json',
             'review/REPORT.md', 'review/bind_final.py')
    bound = {name: sha(BATCH / name) for name in files}
    review = read(HERE / 'RESULTS.json')
    truth = read(BATCH / 'oracle/TRUTH.json')
    preparation = read(BATCH / 'worker/PREPARATION.json')
    runs = [json.loads(raw) for raw in (BATCH / 'oracle/RUNS.jsonl').read_bytes().splitlines() if raw]
    manifest = read(BATCH / 'worker/SOURCE_OUTPUT_MANIFEST.json')
    finalizer = (BATCH / 'finalize_qualification.py').read_text(encoding='utf8')
    tree = ast.parse(finalizer)
    imports = {node.names[0].name for node in tree.body if isinstance(node, ast.Import)}
    checks = {
        'independent_qualification_passed': review['passed'] is True and not review['blocking_findings'] and not review['incomplete_items'],
        'all_final_qualification_inputs_still_match': all(sha(BATCH / name) == expected for name, expected in review['files_sha256'].items()),
        'all_asset_worker_final_outputs_still_match': all(sha(BATCH / record['path']) == record['sha256'] for record in manifest['asset_worker_files_excluding_this_manifest']),
        'root_summary_actual_truth_bound': truth['qualification_status'] == 'passed'
            and sha(BATCH / 'oracle/TRUTH.json') == '2d072197f67f2d9860cb2ceb86c2782a7d4d2c3a71f1ed6d8be2487afc0eaa74',
        'preparation_window_arithmetic': preparation['ended_ns'] - preparation['started_ns'] == preparation['elapsed_ns'] == 1747819600,
        'oracle_analysis_window_arithmetic': truth['analysis_ended_ns'] - truth['started_ns'] == truth['analysis_elapsed_ns'] == 876328800,
        'oracle_publication_window_arithmetic': len(runs) == 1 and runs[0]['publication_ended_ns'] - runs[0]['started_ns'] == runs[0]['elapsed_through_publication_ns'] == 915346000,
        'nested_windows_kept_separate': preparation['builder']['elapsed_ns'] == 606214300 and preparation['QA_close']['elapsed_ns'] == 139973000,
        'finalizer_has_no_product_or_process_import': imports == {'hashlib', 'json'},
        'finalizer_timestamp_scope_explicit': 'finalizer_input_checks_ended_utc' in finalizer
            and 'recorded_freeze_to_finalizer_input_checks_window_s' in finalizer
            and 'Excludes subsequent ledger/ready/manifest publication, Git and callback.' in finalizer,
        'final_files_stable_through_binding': all(sha(BATCH / name) == expected for name, expected in bound.items()),
    }
    result = {'passed': all(checks.values()), 'files_sha256': bound, 'checks': checks,
        'blocking_findings': [name for name, passed in checks.items() if not passed], 'incomplete_items': [],
        'static_review_notes': [
            'Root REPORT.md was read in full and its actual counts, features, distances and source hashes match the independent certificates and oracle.',
            'The finalizer verifies both review bindings, protected sources and installation, actual asset/read-copy/snapshot, and owned builder/QA shutdown receipts before publication.',
            'The ledger uses source clock boundaries. Builder and QA close remain inside the controller window, and oracle analysis remains inside its publication window.',
            'The finalizer timestamp ends after input checks. Later ledger/READY/manifest publication, Git and callback remain outside that window.',
            'Exclusive file creation protects existing summaries. The final manifest includes all prior qualification files, ledger and READY, with explicit lexical path sorting.',
            'This static review leaves the finalizer unexecuted for the parent to publish and check.'],
        'reviewer_model_Blender_product_runs': 0, 'reviewer_finalizer_runs': 0,
        'original_asset_oracle_review_results_modified': 0}
    with (HERE / 'FINAL_BINDING.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': result['passed'], 'checks': len(checks), 'bound_files': len(bound),
                      'blocking_findings': result['blocking_findings']}))


if __name__ == '__main__':
    main()
