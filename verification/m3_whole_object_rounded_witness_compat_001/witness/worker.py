"""Route the unchanged sealed-capture worker to this batch's private output root."""

import argparse
from pathlib import Path
from runpy import run_path
import sys


HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parents[1] / 'm3_whole_object_rounded_witness_001'
ROOT = Path('D:/he_m3_whole_object_rounded_witness_compat_001/witness')


if __name__ == '__main__':
    worker = run_path(str(PREVIOUS / 'harness/worker.py'))
    worker['require'](sys.flags.isolated and sys.dont_write_bytecode, 'isolated_no_bytecode_interpreter_required')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', type=Path, required=True)
    parser.add_argument('--binding', type=Path, required=True)
    parser.add_argument('--case', choices=worker['LABELS'], required=True)
    parser.add_argument('--region-task-evidence', action='store_true')
    args = parser.parse_args()
    invoke = worker['worker']
    invoke.__globals__['EXTERNAL'] = ROOT
    raise SystemExit(invoke(args.worker, args.binding, args.case, args.region_task_evidence))
