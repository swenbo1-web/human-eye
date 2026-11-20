"""Run the retained single-slot lifecycle using only this batch's admission."""

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
import admission
from common import EXTERNAL, GLOBAL, NS, ORDER, load_retained


previous = load_retained('_m5_projection_recovery_slot_source', GLOBAL / 'harness/run_slot.py')
if previous.admission is not admission or (previous.EXTERNAL, previous.NS, previous.ORDER) != (EXTERNAL, NS, ORDER):
    raise ValueError('slot_runner_loaded_another_experiment')
previous.__file__ = __file__


if __name__ == '__main__':
    raise SystemExit(previous.main())
