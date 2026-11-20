"""Retain the standard installed product wire observer and verify the live scope."""

import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
import admission
import budget
from common import EXTERNAL, ORDER, PRIOR, PRODUCT_BINDING, load_retained


def main():
    entry = load_retained('_m5_global_standard_installed_mcp', PRIOR / 'harness/mcp_entry.py')
    if entry.Budget is not budget.Budget:
        raise ValueError('installed_mcp_loaded_other_experiment_budget')
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError('pinned_interpreter_I_B_required')
    args = sys.argv[1:]
    if args == ['--dispatch-smoke']:
        print(json.dumps({'entry': str(Path(__file__).resolve()), 'admission': str(Path(admission.__file__).resolve()),
                          'budget': str(Path(budget.__file__).resolve()), 'schema': admission.SCHEMA,
                          'current_binding': str(PRODUCT_BINDING.resolve()), 'fresh_process_prepared_only': True}))
        return
    keys = ('--binding', '--config', '--ledger', '--evidence', '--phase', '--label', '--archive')
    options = dict(zip(args[::2], args[1::2], strict=True))
    if len(args) != 2 * len(keys) or set(options) != set(keys):
        raise ValueError('unregistered_installed_mcp_entry_arguments')
    label = options['--label']
    if label not in ORDER or options['--phase'] != 'qualification':
        raise ValueError('installed_mcp_outside_qualification_slot')
    slot = EXTERNAL / 'slots' / label
    paths = {'--binding': PRODUCT_BINDING, '--config': slot / 'PRODUCT_CONFIG.json',
             '--ledger': EXTERNAL / 'budget', '--evidence': slot / 'mcp_io', '--archive': slot / 'product_full'}
    if any(Path(options[name]).resolve() != path.resolve() for name, path in paths.items()):
        raise ValueError('installed_mcp_not_bound_to_current_qualification_slot')
    admission.registered_product()
    entry.main()


if __name__ == '__main__':
    main()
