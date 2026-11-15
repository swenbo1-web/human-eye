"""Check ordinary import opcode compatibility without any external runtime."""

import hashlib
import importlib.util
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("_target_import_boundary", HERE / "native_tools.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
rows = []
for code in ("import math\nassert math.sqrt(9)==3", "from fractions import Fraction\nassert Fraction(1,2)+Fraction(1,2)==1"):
    row = {"code": code, "passed": False}
    try:
        module.validate_code(code)
        exec(code, {"__builtins__": module.public_builtins()})
        row["passed"] = True
    except BaseException as error:
        row["error"] = {"type": type(error).__name__, "message": str(error)}
    rows.append(row)
result = {"passed": all(row["passed"] for row in rows), "checks": rows,
    "source_sha256": hashlib.sha256((HERE / "native_tools.py").read_bytes()).hexdigest(),
    "actual_Blender_starts": 0, "actual_model_calls": 0, "actual_CLI_calls": 0, "actual_rasters": 0}
target = HERE / sys.argv[1]
with target.open("x", encoding="utf-8") as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps(result))
