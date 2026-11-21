"""Run one frozen pilot slot with the established owned lifecycle."""

import argparse
import ast
import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
import admission
from common import (ASSET, EXTERNAL, FORMAL, HERE, NS, ORDER, PRODUCT_BINDING, PRODUCT_SCHEMA, SEAL, SLOTS,
                    load_retained, read)


source_path = FORMAL / 'harness/run_slot.py'
previous = load_retained('_perf050_p2_dense_run_slot', source_path)
if (previous.EXTERNAL != EXTERNAL or previous.NS != NS or previous.SLOTS is not SLOTS
        or previous.validate_admission is not admission.validate_admission):
    raise ValueError('slot_runner_bound_to_wrong_experiment')
tree = ast.parse(source_path.read_bytes(), filename=str(source_path))
function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'run')
imports = [node for node in ast.walk(function) if isinstance(node, ast.ImportFrom) and node.module == 'consumer']
if len(imports) != 1 or [item.name for item in imports[0].names] != ['consume_slot']:
    raise ValueError('retained_consumer_import_changed')
imports[0].module = 'consumer.driver'
scope = dict(vars(previous))
exec(compile(ast.Module(body=[function], type_ignores=[]), str(source_path), 'exec'), scope)
run = scope['run']


def prepare_dispatch(label):
    binding = read(PRODUCT_BINDING)
    shared = read(SEAL / 'SHARED_DEPENDENCY.json')
    sys.path[:0] = [str(NS), binding['dependency_root'], shared['dependency_root']]
    from bridge import Owner, TOOL_NAMES
    from consumer.driver import consume_slot
    from frame_device import FrameDevice
    from runtime import Runtime

    source = Runtime._start_public_mcp.__globals__
    if (source['HERE'] != HERE or source['PRODUCT_SCHEMA'] != PRODUCT_SCHEMA
            or source['SOURCE_SHA'] != binding['source_sha256']
            or Path(sys.modules[Runtime.__module__].__file__).parent != HERE
            or Path(sys.modules[consume_slot.__module__].__file__).resolve() != NS / 'consumer/driver.py'):
        raise ValueError('actual_startup_scopes_differ_from_frozen_pilot')
    return {'fresh_process_prepared_only': True, 'slot': label, 'group': SLOTS[label][0],
            'entry': str(Path(__file__).resolve()), 'admission': str(Path(admission.__file__).resolve()),
            'schema': admission.SCHEMA, 'run_root': str(EXTERNAL.resolve()), 'asset': str(ASSET.resolve()),
            'product': admission.registered_product(), 'tools': sorted(TOOL_NAMES[SLOTS[label][0]]),
            'actual_product_schema': str(source['PRODUCT_SCHEMA'].resolve()),
            'mcp_entry': str(source['HERE'] / 'mcp_entry.py'), 'outer_bridge': str(sys.modules[Owner.__module__].__file__),
            'consumer_driver': str(Path(sys.modules[consume_slot.__module__].__file__).resolve()),
            'frame_device': str(sys.modules[FrameDevice.__module__].__file__)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('slot', choices=ORDER)
    parser.add_argument('--dispatch-smoke', action='store_true')
    args = parser.parse_args()
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError('registered_isolated_interpreter_required')
    if args.dispatch_smoke:
        print(json.dumps(prepare_dispatch(args.slot)))
        return 0
    return run(args.slot)


if __name__ == '__main__':
    raise SystemExit(main())
