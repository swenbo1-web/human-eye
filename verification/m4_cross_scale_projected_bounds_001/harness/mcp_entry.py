"""Use the original assembly observer and pass through the installed MCP entry."""

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
import budget  # Bind the six-slot ledger before loading the retained entry.
from common import PIXEL, load


if __name__ == '__main__':
    entry = load('_projected_bounds_mcp_entry', PIXEL / 'harness/mcp_entry.py')
    entry.main()
