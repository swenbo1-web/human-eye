"""Run the frozen blocker candidate using the accepted dense lifecycle."""

import argparse
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
import admission  # Bind the blocker admission before loading the dense runner.
from common import DENSE, ORDER, load


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('slot', choices=ORDER)
    label = parser.parse_args().slot
    current_path = sys.path[:]
    try:
        retained = load('_bound_blocker_retained_slot', DENSE / 'harness/run_slot.py')
    finally:
        sys.path[:] = current_path
    return retained.run(label)


if __name__ == '__main__':
    raise SystemExit(main())
