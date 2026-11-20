"""Use the original installed MCP entry without product instrumentation."""

import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
import budget
from common import PRIOR, load_retained


def main():
    entry = load_retained('_dense_raster_retained_mcp_entry', PRIOR / 'harness/mcp_entry.py')
    if entry.Budget is not budget.Budget:
        raise ValueError('retained_MCP_did_not_bind_current_budget')
    if sys.argv[1:] == ['--dispatch-smoke']:
        if not sys.flags.isolated or not sys.dont_write_bytecode:
            raise ValueError('pinned_interpreter_I_B_required')
        print(json.dumps({'budget': str(Path(budget.__file__).resolve()),
                          'entry': str(Path(entry.__file__).resolve()),
                          'fresh_process_prepared_only': True}))
        return
    entry.main()


if __name__ == '__main__':
    main()
