"""Compare the final model-proposed raw saved file with calibration alpha one."""

import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
from evaluate import packet


def absolute(value):
    path = Path(value)
    return path if path.is_absolute() else HERE / path


def main():
    started, cpu = time.perf_counter(), time.process_time()
    raw = read("PROPOSAL_FREEZE.json")["proposal"]
    proposal = raw["proposal_id"]
    result = read("CALIBRATION_v2_"+proposal+".json")
    full = next(row for row in result["candidates"] if row["alpha"] == 1)
    first, second = packet(absolute(raw["readback"]["path"])), packet(absolute(full["readback"]["path"]))
    checks = dict(same_payload_bytes=absolute(raw["payload"]["path"]).read_bytes() == absolute(full["payload"]["path"]).read_bytes(),
        same_readback_fields=set(first) == set(second))
    for key in sorted(first):
        checks["saved array "+key] = key in second and first[key].dtype == second[key].dtype and first[key].shape == second[key].shape and first[key].tobytes() == second[key].tobytes()
    raw_views = {row["role"]: row for row in raw["images"] if "whole" not in row["role"]}
    requests = []
    for row in full["images"]:
        old = raw_views[row["role"]]
        checks["matched camera "+row["role"]] = old["camera"] == row["camera"]
        requests.append(dict(role=row["role"], first=str(absolute(old["path"])), second=str(absolute(row["path"]))))
    code = """import json,sys
from PIL import Image
rows=json.loads(sys.stdin.read())
for row in rows:
    with Image.open(row.pop('first')) as im: a=im.convert('RGBA')
    with Image.open(row.pop('second')) as im: b=im.convert('RGBA')
    row['RGBA_equal']=a.size==b.size and a.tobytes()==b.tobytes()
print(json.dumps(rows))
"""
    python = "C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
    process = subprocess.run([python, "-I", "-B", "-X", "utf8", "-c", code], input=json.dumps(requests).encode(), capture_output=True, check=True)
    pixels = json.loads(process.stdout)
    for row in pixels:
        checks["exact RGBA "+row["role"]] = row["RGBA_equal"]
    output = dict(cycle_id="M6-CALIBRATION-TRANSFER-007", status="pass" if all(checks.values()) else "fail",
        checks=checks, passed=sum(checks.values()), total=len(checks), pixel_pairs=pixels,
        raw_proposal_freeze=identity(HERE / "PROPOSAL_FREEZE.json"), calibration=identity(HERE / ("CALIBRATION_v2_"+proposal+".json")),
        wall_s=time.perf_counter()-started, CPU_s=time.process_time()-cpu, new_Pro=0, new_Blender=0,
        scope="Same one actual proposal raw saved result versus independently executed fixed alpha1. Complete readback arrays, payload bytes, frozen cameras and actual RGBA checked.")
    write("RAW_CALIBRATION_COMPARISON.json", output)
    print(dict(status=output["status"],passed=output["passed"],total=output["total"]))
    if output["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
