"""Run the installed public wire recorder only for the registered P slot."""

import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
import admission
import budget
from common import EXTERNAL, PRIOR, PRODUCT_BINDING, load_retained, read


def main():
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError('registered_isolated_interpreter_required')
    entry = load_retained('_perf050_transfer_installed_observer', PRIOR / 'harness/mcp_entry.py')
    if entry.Budget is not budget.Budget:
        raise ValueError('candidate_recording_wrong_ledger')
    slot = EXTERNAL / 'slots/P2'
    state = slot / 'product_state.json'
    if sys.argv[1:] == ['--dispatch-smoke']:
        print(json.dumps({'entry': str(Path(__file__).resolve()), 'admission': str(Path(admission.__file__).resolve()),
             'schema': admission.SCHEMA, 'current_binding': str(PRODUCT_BINDING.resolve()),
             'absolute_state_file': str(state.resolve()),
             'fresh_process_prepared_only': True, 'label': 'P2'}))
        return
    arguments = sys.argv[1:]
    options = dict(zip(arguments[::2], arguments[1::2], strict=True))
    paths = {'--binding': PRODUCT_BINDING, '--config': slot / 'PRODUCT_CONFIG.json',
             '--ledger': EXTERNAL / 'budget', '--evidence': slot / 'mcp_io', '--archive': slot / 'product_full'}
    if (len(arguments) != 14 or set(options) != set(paths) | {'--phase', '--label'}
            or (options['--label'], options['--phase']) != ('P2', 'formal')
            or any(Path(options[key]).resolve() != path.resolve() for key, path in paths.items())):
        raise ValueError('installed_mcp_not_bound_to_registered_pilot_slot')
    configured_state = Path(read(paths['--config'])['state_file'])
    if not configured_state.is_absolute() or configured_state != state or configured_state.resolve() != state:
        raise ValueError('installed_mcp_requires_its_own_absolute_state_path')
    admission.registered_product()
    entry.main()


if __name__ == '__main__':
    main()
