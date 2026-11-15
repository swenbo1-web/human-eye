"""Root-only builder controller, charging one start against the 10/36 limits."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from budget import Budget, save


PLAN = HERE.parent / "fixtures/INPUT_PLAN.json"
BINARY_SHA256 = "284f4041f98e113f3dc10654a7193ffaaa9bfdfec8b87fa116620a48b5f6d4cb"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--blender", type=Path, default=Path("D:/Tools/blender5.2/blender.exe"))
    options = parser.parse_args()
    output = options.output.resolve()
    if not output.is_relative_to(Path("D:/he_m4_camera_001").resolve()):
        raise ValueError("camera_owned_asset_output_outside_batch")
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter_ns()
    plan = json.loads(PLAN.read_bytes())
    for pin in plan["source_pins"]:
        if digest(pin["path"]) != pin["sha256"]:
            raise ValueError("camera_frozen_source_changed")
    if digest(options.blender) != BINARY_SHA256:
        raise ValueError("camera_builder_binary_changed")
    shutil.copyfile(plan["sources"]["peripheral"]["path"], output / "peripheral.blend")
    shutil.copyfile(plan["sources"]["peripheral_geometry"]["path"], output / "peripheral.GEOMETRY.json")
    budget = Budget(options.ledger)
    claim = budget.reserve("Blender_start", "camera_fixed_asset_builder")
    builder = HERE.parent / "fixtures/build_assets.py"
    command = [str(options.blender), "--factory-startup", "--disable-autoexec", "--background",
               "--python-exit-code", "1", "--python", str(builder), "--", str(PLAN), str(output)]
    process = None
    result = {"schema": "m4-camera-asset-preparation-v1", "started_ns": started,
              "command": command, "budget_start_claim": claim,
              "input_plan_sha256": digest(PLAN), "builder_sha256": digest(builder), "passed": False}
    try:
        with (output / "BUILDER_STDOUT.bin").open("xb") as out, (output / "BUILDER_STDERR.bin").open("xb") as err:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), shell=False)
            result["pid"] = process.pid
            result["exit_code"] = process.wait(timeout=120)
        if process.returncode != 0:
            raise RuntimeError("camera_owned_asset_builder_failed")
        derivation = json.loads((output / "DERIVATION.json").read_bytes())
        inputs = []
        for name in ("extreme", "origin", "peripheral"):
            asset = output / (name + ".blend")
            geometry = output / (name + ".GEOMETRY.json")
            target = next(row["target"] for row in plan["inputs"] if row["name"] == name)
            inputs.append({"name": name, "asset": str(asset), "asset_sha256": digest(asset),
                           "geometry": str(geometry), "geometry_sha256": digest(geometry), "target": target})
        if inputs[-1]["asset_sha256"] != plan["sources"]["peripheral"]["sha256"]:
            raise ValueError("camera_peripheral_copy_changed")
        for pin in plan["source_pins"]:
            if digest(pin["path"]) != pin["sha256"]:
                raise ValueError("camera_original_input_modified")
        save(output / "ASSETS.json", {"schema": "m4-camera-owned-assets-v1", "inputs": inputs,
             "input_plan_sha256": digest(PLAN), "derivation": derivation,
             "derivation_sha256": digest(output / "DERIVATION.json")})
        result["passed"] = True
    except BaseException as error:
        result["error"] = {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=5)
            result["forced_kill"] = True
    finally:
        budget.settle_start(claim, pid=None if process is None else process.pid,
                            spawn_status="not_spawned" if process is None else "spawned",
                            outcome="passed" if result["passed"] else "failed")
        result["closed_ns"] = time.perf_counter_ns()
        result["elapsed_ns"] = result["closed_ns"] - started
        save(output / "PREPARATION.json", result)
    print(json.dumps({"passed": result["passed"], "output": str(output), "new_Blender_start_attempts": 1}))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
