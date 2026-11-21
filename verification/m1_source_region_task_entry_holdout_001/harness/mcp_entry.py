"""Run the unchanged installed wire observer with the registered arm binding."""

import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
import admission
import budget
from common import EXTERNAL, PRIOR, SLOTS, load_retained, product_for, read


def main():
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError('registered_isolated_interpreter_required')
    entry = load_retained('_task_entry_installed_observer', PRIOR / 'harness/mcp_entry.py')
    if entry.Budget is not budget.Budget:
        raise ValueError('task_entry_recording_wrong_ledger')
    arguments = sys.argv[1:]
    smoke = len(arguments) == 2 and arguments[0] == '--dispatch-smoke'
    options = {} if smoke else dict(zip(arguments[::2], arguments[1::2], strict=True))
    label = arguments[1] if smoke else options.get('--label')
    group, phase = SLOTS.get(label, (None, None))
    if group != 'P':
        raise ValueError('installed_mcp_not_bound_to_registered_task_entry_slot')
    product = product_for(label)
    slot = EXTERNAL / 'slots' / label
    state = slot / 'product_state.json'
    if smoke:
        print(json.dumps({'entry': str(Path(__file__).resolve()), 'admission': str(Path(admission.__file__).resolve()),
             'schema': admission.SCHEMA, 'current_binding': str(product['binding'].resolve()),
             'absolute_state_file': str(state.resolve()), 'source_sha256': product['source_sha256'],
             'fresh_process_prepared_only': True, 'label': label}))
        return
    paths = {'--binding': product['binding'], '--config': slot / 'PRODUCT_CONFIG.json',
             '--ledger': EXTERNAL / 'budget', '--evidence': slot / 'mcp_io', '--archive': slot / 'product_full'}
    if (len(arguments) != 14 or set(options) != set(paths) | {'--phase', '--label'}
            or options['--phase'] != phase
            or any(Path(options[key]).resolve() != path.resolve() for key, path in paths.items())):
        raise ValueError('installed_mcp_not_bound_to_registered_task_entry_slot')
    configured_state = Path(read(paths['--config'])['state_file'])
    if not configured_state.is_absolute() or configured_state != state or configured_state.resolve() != state:
        raise ValueError('installed_mcp_requires_its_own_absolute_state_path')
    admission.registered_product(label)
    entry.main()


if __name__ == '__main__':
    main()
