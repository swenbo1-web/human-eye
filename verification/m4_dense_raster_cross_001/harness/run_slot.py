"""Open one frozen dense engineering slot using the recovered dispatch."""

import argparse
import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
import admission
import common
from common import ARMS, ORDER, PIXEL_BASE, load_retained


previous = load_retained('_dense_raster_recovered_slot', PIXEL_BASE / 'harness/run_slot.py')
prepare_runner = previous.prepare_runner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('slot', choices=ORDER)
    parser.add_argument('--dispatch-smoke', action='store_true')
    args = parser.parse_args()
    runner = prepare_runner(args.slot)
    if args.dispatch_smoke:
        if not sys.flags.isolated or not sys.dont_write_bytecode:
            raise ValueError('pinned_interpreter_I_B_required')
        print(json.dumps({'slot': args.slot, 'arm': ARMS[args.slot],
                         'admission': str(Path(admission.__file__).resolve()),
                         'binding': str(runner.__globals__['PRODUCT_BINDING'].resolve()),
                         'product_source_sha256': common.SOURCE_SHA,
                         'fresh_process_prepared_only': True}))
        return 0
    return runner(args.slot)


if __name__ == '__main__':
    raise SystemExit(main())
