"""Use the original installed MCP and passive evidence in the formal ledger."""

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
import budget
from common import OLD, load


if __name__ == '__main__':
    load('_rail_original_mcp_entry', OLD / 'harness/mcp_entry.py').main()
