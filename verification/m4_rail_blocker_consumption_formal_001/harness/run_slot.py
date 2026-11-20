"""Launch one formal-only label with retained execution and cleanup."""

import argparse
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
import admission
import consumer
import runtime
from common import OLD, ORDER, load


run = load('_rail_original_slot_executor', OLD / 'harness/run_slot.py').run


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('slot', choices=ORDER)
    raise SystemExit(run(parser.parse_args().slot))
