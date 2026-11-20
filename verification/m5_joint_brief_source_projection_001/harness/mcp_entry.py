"""Run the same installed wire recorder under this batch's binding and limits."""

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
import admission
import budget
from common import EXTERNAL, GLOBAL, ORDER, load_retained


previous = load_retained('_m5_projection_mcp_source', GLOBAL / 'harness/mcp_entry.py')
if (previous.admission is not admission or previous.budget is not budget
        or (previous.EXTERNAL, previous.ORDER) != (EXTERNAL, ORDER)):
    raise ValueError('installed_mcp_loaded_another_experiment')
previous.__file__ = __file__


if __name__ == '__main__':
    previous.main()
