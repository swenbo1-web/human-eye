"""Run one registered projected-bounds slot through the proven assembly lifecycle."""

import argparse
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
import admission  # Bind this batch before the retained runner imports it.
from common import ORDER, PIXEL, load


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('slot', choices=ORDER)
    selected = parser.parse_args().slot
    # The retained runner prepends its own directory for direct CLI use.
    current_path = sys.path[:]
    try:
        runner = load('_projected_bounds_slot', PIXEL / 'harness/run_slot.py')
    finally:
        sys.path[:] = current_path
    return runner.run(selected)


if __name__ == '__main__':
    raise SystemExit(main())
