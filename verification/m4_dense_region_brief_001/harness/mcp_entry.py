"""Preserve the installed MCP wire and timing through the dense QA ledger."""

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
import budget  # Bind this ledger before the retained entry imports it.
from common import PIXEL, load


if __name__ == '__main__':
    entry = load('_dense_region_brief_mcp_entry', PIXEL / 'harness/mcp_entry.py')
    entry.main()
