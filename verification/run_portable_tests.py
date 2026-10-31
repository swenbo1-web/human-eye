"""Run the explicitly selected public source-only suite, without Blender."""
import sys
sys.dont_write_bytecode = True
from pathlib import Path
import json
import os
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.pop("HUMAN_EYE_TEST_BLENDER", None)
if __name__ == "__main__":
    selection = json.loads((ROOT / "verification/portable_modules.json").read_text(encoding="utf8"))
    names = selection["modules"]
    print(f"Running {len(names)} public source-only modules; optional Blender and archived evidence are excluded.", flush=True)
    suite = unittest.defaultTestLoader.loadTestsFromNames(names)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    raise SystemExit(not result.wasSuccessful())
