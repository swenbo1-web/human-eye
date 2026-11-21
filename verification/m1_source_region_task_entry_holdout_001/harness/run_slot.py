"""Run an owned slot with the registered per-arm install and inherited lifecycle."""

import argparse
import json
from pathlib import Path
import sys
from types import FunctionType


sys.path.insert(0,str(Path(__file__).resolve().parent))
import admission
from common import ASSET, EXTERNAL, NS, ORDER, SEAL, SLOTS, V, load_retained, product_for, read


PRIOR = V/'m1_source_region_first_packet_consumption_001'
previous = load_retained('_task_entry_inherited_slot_runner',PRIOR/'harness/run_slot.py')


def prepare_dispatch(label):
    choice = product_for(label)
    binding = read(choice['binding'])
    shared = read(SEAL/'SHARED_DEPENDENCY.json')
    sys.path[:0] = [str(NS),binding['dependency_root'],shared['dependency_root']]
    from bridge import Owner, tool_names
    from consumer.driver import consume_slot
    from frame_device import FrameDevice
    from runtime import Runtime

    return {'entry':str(Path(__file__).resolve()),'fresh_process_prepared_only':True,'slot':label,
            'group':SLOTS[label][0],'schema':admission.SCHEMA,'product':admission.registered_product(label),
            'asset':str(ASSET.resolve()),'run_root':str(EXTERNAL.resolve()),'tools':sorted(tool_names(label)),
            'selected_binding':str(choice['binding']),'selected_schema':str(choice['schema']),
            'mcp_entry':str(NS/'harness/mcp_entry.py'),
            'loaded':{item.__name__:str(Path(sys.modules[item.__module__].__file__).resolve())
                      for item in (FrameDevice,Owner,Runtime,consume_slot)}}


def run(label):
    bound = product_for(label)
    base = previous.run
    if base.__globals__['validate_admission'] is not admission.validate_admission:
        raise ValueError('retained_slot_runner_not_bound_to_task_entry_admission')
    scope = dict(base.__globals__,PRODUCT_BINDING=bound['binding'])
    return FunctionType(base.__code__,scope)(label)


if __name__=='__main__':
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError('use_fixed_interpreter_with_I_B')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('slot',choices=ORDER)
    parser.add_argument('--dispatch-smoke',action='store_true')
    args = parser.parse_args()
    if args.dispatch_smoke:
        print(json.dumps(prepare_dispatch(args.slot)))
    else:
        raise SystemExit(run(args.slot))
