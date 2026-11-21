"""Run the genuine installed public MCP wire recorder for exactly one arm."""

import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
import admission
import budget
from common import BINDINGS, EXTERNAL, ORDER, PRIOR, PRODUCT_SCHEMA, load_retained, product, select


def main():
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError('pinned_interpreter_I_B_required')
    entry = load_retained('_m4_active_view_original_installed_entry', PRIOR / 'harness/mcp_entry.py')
    if entry.Budget is not budget.Budget:
        raise ValueError('installed_entry_loaded_another_budget')
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == '--dispatch-smoke' and args[1] in ORDER:
        label = args[1]
        print(json.dumps({'entry': str(Path(__file__).resolve()), 'admission': str(Path(admission.__file__).resolve()),
              'label': label, 'schema': admission.SCHEMA, 'current_binding': str(BINDINGS[label].resolve()),
              'current_product': product(label), 'actual_schema': str(PRODUCT_SCHEMA.resolve()),
              'fresh_process_prepared_only': True}))
        return
    keys = {'--binding', '--config', '--ledger', '--evidence', '--phase', '--label', '--archive'}
    options = dict(zip(args[::2], args[1::2], strict=True))
    if len(args) != 2 * len(keys) or set(options) != keys:
        raise ValueError('unregistered_installed_active_view_child_arguments')
    label = options['--label']
    if label not in ORDER or options['--phase'] != 'qualification':
        raise ValueError('installed_child_outside_registered_active_view_arm')
    slot = EXTERNAL / 'slots' / label
    paths = {'--binding': BINDINGS[label], '--config': slot / 'PRODUCT_CONFIG.json',
             '--ledger': EXTERNAL / 'budget', '--evidence': slot / 'mcp_io', '--archive': slot / 'product_full'}
    if any(Path(options[key]).resolve() != path.resolve() for key, path in paths.items()):
        raise ValueError('installed_active_view_child_paths_changed')
    select(label)
    entry.main()


if __name__ == '__main__':
    main()
