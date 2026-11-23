"""Launch the pinned installed MCP with the retained production observer."""

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
from host import LIVE_M2, load


if __name__ == '__main__':
    sys.path.append(str(LIVE_M2))
    raise SystemExit(load('_yanyite_bilateral_installed_worker', LIVE_M2/'mcp_entry.py').main())
