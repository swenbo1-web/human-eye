"""Run one frozen arm with the working dense host and natural CLI lifecycle."""

import argparse
import ast
import json
from pathlib import Path
import sys
from types import FunctionType


sys.path.insert(0, str(Path(__file__).resolve().parent))
import admission
from common import (ASSET, EXTERNAL, FORMAL, HERE, NS, ORDER, PRODUCT_BINDING, PRODUCT_SCHEMA, SEAL, SLOTS,
                    binding_for, catalogue_for, evidence_enabled, load_retained, product_for, read)


source_path = FORMAL / 'harness/run_slot.py'
previous = load_retained('_region_task_retained_dense_slot', source_path)
if (previous.EXTERNAL != EXTERNAL or previous.NS != NS or previous.SLOTS is not SLOTS
        or previous.validate_admission is not admission.validate_admission):
    raise ValueError('slot_runner_bound_to_wrong_region_task_experiment')
tree = ast.parse(source_path.read_bytes(), filename=str(source_path))
function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'run')
imports = [node for node in ast.walk(function) if isinstance(node, ast.ImportFrom) and node.module == 'consumer']
if len(imports) != 1 or [item.name for item in imports[0].names] != ['consume_slot']:
    raise ValueError('retained_natural_consumer_import_changed')
imports[0].module = 'consumer.driver'
old_catalogue = ast.parse("read(PRODUCT_BINDING.parent / 'TOOLS_SCHEMA.json')", mode='eval').body
matches = [node for node in ast.walk(function) if isinstance(node, ast.Call)
           and ast.dump(node, include_attributes=False) == ast.dump(old_catalogue, include_attributes=False)]
if len(matches) != 1:
    raise ValueError('retained_catalogue_check_anchor_changed')
matches[0].args = [ast.Call(func=ast.Name(id='catalogue_for', ctx=ast.Load()),
                          args=[ast.Name(id='label', ctx=ast.Load())], keywords=[])]
scope = dict(vars(previous), catalogue_for=catalogue_for)
exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])),
             str(source_path), 'exec'), scope)
retained_run = scope['run']


def run(label):
    selected = binding_for(label)
    arm_scope = dict(retained_run.__globals__, PRODUCT_BINDING=selected)
    return FunctionType(retained_run.__code__, arm_scope)(label)


def prepare_dispatch(label):
    binding = read(binding_for(label))
    shared = read(SEAL / 'SHARED_DEPENDENCY.json')
    sys.path[:0] = [str(NS), binding['dependency_root'], shared['dependency_root']]
    from bridge import Owner, TOOL_NAMES
    from consumer.driver import consume_slot
    from frame_device import FrameDevice
    from runtime import Runtime

    if (Path(sys.modules[Runtime.__module__].__file__).resolve() != HERE / 'runtime.py'
            or Path(sys.modules[Owner.__module__].__file__).resolve() != HERE / 'bridge.py'
            or Path(sys.modules[consume_slot.__module__].__file__).resolve() != NS / 'consumer/driver.py'):
        raise ValueError('actual_region_task_dispatch_loaded_wrong_namespace')
    return {'fresh_process_prepared_only': True, 'slot': label, 'group': SLOTS[label][0],
            'entry': str(Path(__file__).resolve()), 'admission': str(Path(admission.__file__).resolve()),
            'schema': admission.SCHEMA, 'run_root': str(EXTERNAL.resolve()), 'asset': str(ASSET.resolve()),
            'product': admission.registered_product(label), 'tools': sorted(TOOL_NAMES[SLOTS[label][0]]),
            'actual_catalogue_path': (str(catalogue_for(label).resolve()) if catalogue_for(label) is not None else None),
            'actual_product_schema': str(PRODUCT_SCHEMA.resolve()),
            'actual_product_binding': str(binding_for(label).resolve()),
            'endpoint_flag': '--region-task-evidence' if evidence_enabled(label) else None,
            'mcp_entry': str(HERE / 'mcp_entry.py'), 'outer_bridge': str(sys.modules[Owner.__module__].__file__),
            'consumer_driver': str(Path(sys.modules[consume_slot.__module__].__file__).resolve()),
            'frame_device': str(sys.modules[FrameDevice.__module__].__file__),
            'workspace_sources': sorted({str(Path(module.__file__).resolve()) for module in sys.modules.copy().values()
                 if getattr(module, '__file__', None) and Path(module.__file__).resolve().is_relative_to(NS.parent.parent)})}


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
