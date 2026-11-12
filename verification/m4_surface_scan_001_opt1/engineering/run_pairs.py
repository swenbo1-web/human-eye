"""Run the fixed AB/BA/AB/BA/AB engineering plan after the candidate gate."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import traceback
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HERE, INITIAL, ROOT, WORKER, QUAL, qualification_binding, save, sha
from sequence import run_sequence, ACTOR, RUNTIME
from summarize import summarize

ORDERS = ['AB', 'BA', 'AB', 'BA', 'AB']
OLD_COMMIT = 'c6355a01a4c6ee204a0d676cd9309f02428fe3ba'
OLD_SOURCE = 'b3654f6f943c3fb6feff0011397c0a8c20872e41f35973e6baf53e3a5e277314'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--old-ready', type=Path, default=INITIAL/'installation/run_01/READY.json')
    parser.add_argument('--new-ready', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    assert output.is_relative_to(HERE)
    output.mkdir(parents=True, exist_ok=False)
    planned = [{'pair': index, 'version': version, 'state': state, 'status': 'not_attempted'}
               for index, order in enumerate(ORDERS, 1) for version in order
               for state in ('cold', 'repeat', 'edit')]
    save(output/'PLANNED_ROWS.json', planned)
    try:
        qualification, promised = qualification_binding()
        readies = {'A': json.loads(args.old_ready.read_bytes()), 'B': json.loads(args.new_ready.read_bytes())}
        assert readies['A']['commit'] == OLD_COMMIT and readies['A']['source_sha256'] == OLD_SOURCE
        assert readies['B']['commit'] == args.commit and readies['B']['source_sha256'] == args.source_sha256
        paths = [*HERE.glob('*.py'), HERE/'METERED_HELPER_PROVENANCE.json',
            QUAL/'QUALIFICATION_READY.json', QUAL/'SOURCE_OUTPUT_MANIFEST.json',
            QUAL/'export_snapshot.py', ACTOR, RUNTIME,
            ROOT/'verification/native_plugin_complex_003/actor.py',
            ROOT/'verification/m4_grooved_rail_transfer_001/oracle/exact_geometry.py',
            args.old_ready, args.new_ready]
        files = {str(path.resolve()): sha(path) for path in paths}
        files.update(promised)
        for ready in readies.values():
            fixed = json.loads(Path(ready['fixed_inputs']).read_bytes())
            for row in fixed['manifest']:
                path = Path(ready['install_root'])/row['path']
                assert sha(path) == row['sha256']
                files[str(path)] = row['sha256']
        binding = {'schema': 'm4-scan-opt1-five-pairs-v1', 'readies': readies,
            'qualification': qualification, 'files': files, 'pair_orders': ORDERS,
            'planned_business_rows': planned, 'request_budget_s': 30, 'client_timeout_s': 35,
            'evaluation_consumers': 0, 'images': 0, 'automatic_retries': 0,
            'cold_semantics': 'no prior product geometry or measurement request',
            'qa_quality_check': 'after each measured request, before dispatching the next state',
            'AL_context_bound': False, 'AL_host_epoch': 5, 'AL_task_registered': False,
            'started_utc': datetime.now(timezone.utc).isoformat()}
        save(output/'INPUT_BINDINGS.json', binding)
    except BaseException as error:
        save(output/'PREPARATION_FAILURE.json', {'error': str(error), 'traceback': traceback.format_exc()})
        save(output/'SUMMARY.json', summarize(output))
        raise
    if not args.run:
        print(json.dumps({'prepared_only': True, 'product_calls': 0}))
        return 0
    stopped = False
    for index, order in enumerate(ORDERS, 1):
        for version in order:
            destination = output/('pair_'+str(index).zfill(2))/version
            destination.parent.mkdir(exist_ok=True)
            result = run_sequence(index, destination, readies[version], binding)
            if not result['passed']:
                stopped = True
                break
        if stopped:
            break
    summary_started = time.perf_counter_ns()
    summary = summarize(output)
    summary['offline_summary_analysis_ns'] = time.perf_counter_ns()-summary_started
    save(output/'SUMMARY.json', summary)
    print(json.dumps({'all_quality_passed': summary['quality_passed'],
                      'all_engineering_gates_passed': summary['all_gates_passed'],
                      'planned_rows': 30, 'actual_rows': summary['actual_business_rows']}))
    return 0 if summary['all_gates_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
