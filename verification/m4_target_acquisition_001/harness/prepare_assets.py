"""Root-only execution prepares frozen owned assets with one charged Blender start."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent))
from budget import Budget, save


HERE = Path(__file__).resolve().parent
PLAN = HERE.parent / "fixtures/INPUT_PLAN.json"
BINARY_SHA256 = "284f4041f98e113f3dc10654a7193ffaaa9bfdfec8b87fa116620a48b5f6d4cb"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--blender", type=Path, default=Path("D:/Tools/blender5.2/blender.exe"))
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(Path("D:/he_m4_target_001").resolve()):
        raise ValueError("owned_asset_output_outside_batch")
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter_ns()
    plan = json.loads(PLAN.read_bytes())
    for pin in plan["source_pins"]:
        if digest(pin["path"]) != pin["sha256"]:
            raise ValueError("input_plan_source_changed")
    if digest(args.blender) != BINARY_SHA256:
        raise ValueError("asset_builder_binary_changed")
    inputs = {row["name"]: row for row in plan["inputs"]}
    peripheral = output / "peripheral.blend"
    shutil.copyfile(inputs["peripheral"]["source"], peripheral)
    simple_copy = output / "simple_boxes_source.blend"
    shutil.copyfile(inputs["focal_only"]["source"], simple_copy)
    source_pins = {row["path"]: row["sha256"] for row in plan["source_pins"]}
    config = {"source_pins": plan["source_pins"],
              "simple_source_sha256": source_pins[inputs["focal_only"]["source"]],
              "rack_source": inputs["rack"]["source"]}
    save(output / "BUILDER_CONFIG.json", config)
    old_inputs = next(pin for pin in plan["source_pins"] if pin["path"].endswith("INPUTS.json"))
    source = next(row for row in json.loads(Path(old_inputs["path"]).read_bytes())["inputs"]
                  if row["name"] == "peripheral")
    geometry = {"objects": [dict(row, asset_object_ordinal=index, name_full=row["name"],
                                     library_path="", source_triangles=row["polygons"])
                             for index, row in enumerate(source["oracle"])],
                "frame": source["frame"], "subframe": 0.0,
                "scale_length": source["scale_length"], "unit_system": "METRIC",
                "source": old_inputs, "new_Blender_reads": 0}
    if any(len(face) != 3 for row in geometry["objects"] for face in row["source_triangles"]):
        raise ValueError("peripheral_old_oracle_not_direct_triangles")
    save(output / "peripheral.GEOMETRY.json", geometry)
    budget = Budget(args.ledger)
    token = budget.reserve("Blender_start", "fixed_asset_builder")
    builder = HERE.parent / "fixtures/build_assets.py"
    command = [str(args.blender), "--factory-startup", "--disable-autoexec", "--background",
               "--python-exit-code", "1", "--python", str(builder), "--",
               str(output / "BUILDER_CONFIG.json"), str(output)]
    process = None
    result = {"started_ns": started, "command": command, "budget_start_claim": token,
              "input_plan_sha256": digest(PLAN), "builder_sha256": digest(builder), "passed": False}
    try:
        with (output / "BUILDER_STDOUT.bin").open("xb") as out, (output / "BUILDER_STDERR.bin").open("xb") as err:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), shell=False)
            result["pid"] = process.pid
            result["exit_code"] = process.wait(timeout=120)
        if process.returncode != 0:
            raise RuntimeError("owned_asset_builder_failed")
        derivation = json.loads((output / "DERIVATION.json").read_bytes())
        assets = []
        for name in ("peripheral", "focal_only", "rack"):
            asset = output / (name + ".blend")
            facts = output / (name + ".GEOMETRY.json")
            assets.append({"name": name, "asset": str(asset), "asset_sha256": digest(asset),
                           "geometry": str(facts), "geometry_sha256": digest(facts),
                           "target": inputs[name]["target"], "performance": inputs[name]["performance"]})
        if assets[0]["asset_sha256"] != source_pins[inputs["peripheral"]["source"]]:
            raise ValueError("peripheral_copy_changed")
        for pin in plan["source_pins"]:
            if digest(pin["path"]) != pin["sha256"]:
                raise ValueError("original_asset_changed")
        save(output / "ASSETS.json", {"schema": "m4-target-owned-assets-v1", "inputs": assets,
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
        budget.settle_start(token, pid=None if process is None else process.pid,
                            spawn_status="not_spawned" if process is None else "spawned",
                            outcome="passed" if result["passed"] else "failed")
        result["closed_ns"] = time.perf_counter_ns()
        result["elapsed_ns"] = result["closed_ns"] - started
        save(output / "PREPARATION.json", result)
    if not result["passed"]:
        raise RuntimeError("asset_preparation_failed_receipt_retained")
    print(json.dumps({"passed": True, "assets": str(output / "ASSETS.json"), "new_Blender_starts": 1}))


if __name__ == "__main__":
    main()
