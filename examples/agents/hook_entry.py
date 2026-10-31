"""Run source-checkout hooks without installing or rebuilding the package."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from human_eye_plugin.agent_hooks import main

if __name__ == "__main__":
    raise SystemExit(main())
