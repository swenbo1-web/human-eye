"""Dispatch the frozen B qualification once through the proven sequential entry."""

from pathlib import Path
import sys


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
import admission
from common import EXTERNAL, GLOBAL, ORDER, load_retained


previous = load_retained('_m5_projection_sequence_source', GLOBAL / 'run_sequence.py')
if previous.admission is not admission or (previous.EXTERNAL, previous.ORDER) != (EXTERNAL, ORDER):
    raise ValueError('sequence_runner_loaded_another_experiment')
previous.NS = NS
previous.__file__ = __file__


if __name__ == '__main__':
    raise SystemExit(previous.main())
