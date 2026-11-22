"""Drive the five static relation cases through the held production MCP transport."""
import argparse
from pathlib import Path
from runpy import run_path
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from fixtures import EXTERNAL, LABELS, PRIOR, fixture, pin, require, save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binding', type=Path, required=True)
    parser.add_argument('--mode', choices=('standard', 'evidence'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    binding = args.binding.resolve(strict=True)
    require(output.is_relative_to(EXTERNAL) and output != EXTERNAL, 'exclusive_relation_arm_directory_required')
    output.mkdir(parents=True, exist_ok=False)
    baseline_driver = PRIOR / 'harness/run.py'
    run_case = run_path(str(baseline_driver))['case']
    run_case.__globals__.update(HERE=HERE, fixture=fixture)
    sources = [pin(path) for path in (HERE / 'fixtures.py', HERE / 'worker.py',
               HERE / 'run.py', HERE / 'score.py', baseline_driver, run_case.__globals__['TRANSPORT'])]
    save(output / 'SOURCE.json', {'files': sources, 'binding': pin(binding),
                                  'labels': list(LABELS), 'mode': args.mode})
    received = []
    for label in LABELS:
        received.append(run_case(output / 'cases' / label, binding, label, args.mode == 'evidence'))
        if not received[-1]['passed']:
            break
    passed = len(received) == len(LABELS) and all(row['passed'] for row in received)
    save(output / 'INDEX.json', {'planned': list(LABELS), 'actual': received, 'passed': passed,
                                 'unrun': list(LABELS[len(received):]), 'binding': pin(binding),
                                 'mode': args.mode, 'actual_Blender_starts': 0,
                                 'actual_models': 0, 'actual_rasters': 0})
    print(f'{output.name}: {sum(row["passed"] for row in received)}/{len(LABELS)} processes')
    return 0 if passed else 1


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'isolated_no_bytecode_interpreter_required')
    raise SystemExit(main())
