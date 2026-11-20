"""Run the previous installed observation entry with the strict probe ledger."""

from pathlib import Path
import runpy
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
import budget
from common import GLOBAL_HARNESS


if __name__ == '__main__':
    runpy.run_path(str(GLOBAL_HARNESS / 'mcp_entry.py'), run_name='__main__')
