"""Run the registered candidate slot through the accepted dense QA lifecycle."""

import argparse
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
import admission  # Bind the current admission before loading the retained runner.
from common import DENSE, ORDER, load


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('slot', choices=ORDER)
    label = parser.parse_args().slot
    current_path = sys.path[:]
    try:
        retained = load('_dense_region_brief_retained_slot', DENSE / 'harness/run_slot.py')
    finally:
        # The retained entry prepends its own directory when loaded.
        sys.path[:] = current_path
    return retained.run(label)


if __name__ == '__main__':
    raise SystemExit(main())
