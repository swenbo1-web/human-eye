"""Bind the selected arm before entering the retained owned lifecycle."""

import argparse
import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
import admission
import budget
from common import BINDINGS, EXTERNAL, FORMAL, GLOBAL, HERE, NS, ORDER, PRODUCT_SCHEMA, SEAL, load_retained, read, select


def prepare(label):
    binding = select(label)
    previous = load_retained('_m4_active_view_retained_live_slot', GLOBAL / 'harness/run_slot.py')
    if (previous.admission is not admission or (previous.EXTERNAL, previous.NS, previous.ORDER) != (EXTERNAL, NS, ORDER)
            or previous.PRODUCT_BINDING != BINDINGS[label] or previous.PRODUCT_GIT != binding['commit']):
        raise ValueError('active_view_slot_runner_bound_to_another_experiment')
    previous.__file__ = __file__
    return previous


def main():
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError('pinned_interpreter_I_B_required')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('slot', choices=ORDER)
    parser.add_argument('--dispatch-smoke', action='store_true')
    args = parser.parse_args()
    previous = prepare(args.slot)
    if args.dispatch_smoke:
        previous.prepare_runner()
        binding = read(BINDINGS[args.slot])
        shared = read(SEAL / 'SHARED_DEPENDENCY.json')
        sys.path[1:1] = [str(FORMAL), binding['dependency_root'], shared['dependency_root']]
        import batch
        import runtime

        source = runtime.Runtime._start_public_mcp.__globals__
        if (source['HERE'] != HERE or source['PRODUCT_SCHEMA'] != PRODUCT_SCHEMA
                or source['SOURCE_SHA'] != binding['source_sha256']):
            raise ValueError('runtime_did_not_boot_selected_arm_schema_and_identity')
        print(json.dumps({'label': args.slot, 'slot': args.slot, 'entry': str(Path(__file__).resolve()),
              'admission': str(Path(admission.__file__).resolve()), 'schema': admission.SCHEMA,
              'current_binding': str(BINDINGS[args.slot].resolve()), 'run_root': str(EXTERNAL.resolve()),
              'actual_product_schema': str(source['PRODUCT_SCHEMA'].resolve()),
              'mcp_entry': str(source['HERE'] / 'mcp_entry.py'), 'current_product': admission.product(args.slot),
              'wrapper': [batch.outer_message(args.slot, phase) for phase in ('cold', 'hot')],
              'fresh_process_prepared_only': True}))
        return 0
    return previous.run(args.slot)


if __name__ == '__main__':
    raise SystemExit(main())
