"""Run the pinned installed entry with this batch's shared budget."""

from pathlib import Path
import runpy
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
import budget  # Bound before the retained entry imports its ledger.
from common import PRIOR


if __name__ == '__main__':
    runpy.run_path(str(PRIOR / 'harness/mcp_entry.py'), run_name='__main__')
