"""Pass through the accepted installed MCP entry with the qualification ledger."""

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
import budget  # Bind this ledger before the retained entry imports its ledger.
from common import PIXEL, load


if __name__ == '__main__':
    entry = load('_dense_panel_mcp_entry', PIXEL / 'harness/mcp_entry.py')
    entry.main()
