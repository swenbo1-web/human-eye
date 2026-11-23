"""Run the retained observed production MCP worker with the new pair binding."""

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
from host import PREVIOUS, load


def main():
    # The retained entry imports `host`, already bound to the current pair here.
    # Its lazy timing import resolves to the original meter in PREVIOUS.
    original_path = sys.path[:]
    try:
        entry = load('_resident_delta_retained_entry', PREVIOUS/'mcp_entry.py')
        return entry.main()
    finally:
        sys.path[:] = original_path


if __name__ == '__main__':
    raise SystemExit(main())
