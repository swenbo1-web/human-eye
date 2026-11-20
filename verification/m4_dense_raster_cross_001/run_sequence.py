"""Run the reviewed sequence in this namespace, with no replacement slots."""

import json
from pathlib import Path
import sys


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
import admission
from common import EXTERNAL, ORDER, PIXEL_BASE, load_retained


previous = load_retained('_dense_raster_recovered_sequence', PIXEL_BASE / 'run_sequence.py')
previous.NS = NS
if (previous.verify_freeze is not admission.verify_freeze or previous.publication is not admission.publication
        or previous.can_continue is not admission.can_continue or previous.EXTERNAL != EXTERNAL
        or previous.ORDER != ORDER):
    raise ValueError('sequence_must_bind_current_admission_and_run_root')


def main():
    if sys.argv[1:] == ['--dispatch-smoke']:
        if not sys.flags.isolated or not sys.dont_write_bytecode:
            raise ValueError('registered_isolated_interpreter_required')
        print(json.dumps({'status': 'prepared', 'fresh_process_prepared_only': True,
                          'run_root': str(EXTERNAL.resolve()), 'order': list(ORDER),
                          'schema': admission.SCHEMA, 'products': admission.registered_products()}))
        return 0
    if sys.argv[1:]:
        raise ValueError('unregistered_sequence_arguments')
    return previous.sequence()


if __name__ == '__main__':
    raise SystemExit(main())
