"""Read final preparation inputs and common budgets without starting a runtime."""

import argparse
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import types
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load(path, name):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), "exec", dont_inherit=True), module.__dict__)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    destination = HERE / args.output
    assert destination.parent.resolve() == HERE.resolve() and not destination.exists()
    plan_raw = (BATCH / "PLAN.json").read_bytes()
    plan = json.loads(plan_raw)
    expected = {"model": "gpt-6.1-sol", "requested_effort": "medium", "max_session_seconds": 450,
        "total_cell_seconds": 570, "actor_startup_seconds": 40, "tool_attempts": 32,
        "physical_RPC_limit": 128, "tool_response_bytes": 1048576, "tool_timeout_s": 30,
        "code_bytes": 262144, "image_count": 1, "new_images": 0, "tool_images": 0, "model_retries": 0}
    assert all(plan[key] == value for key, value in expected.items())
    assert not (BATCH / "GO.json").exists() and not (BATCH / "STARTED.json").exists()

    def forbidden(*args, **kwargs):
        raise AssertionError("external process or socket forbidden")

    with patch.object(subprocess, "Popen", side_effect=forbidden), patch.object(subprocess, "run", side_effect=forbidden), patch.object(socket, "socket", side_effect=forbidden):
        driver = load(BATCH / "runtime/driver.py", "_sgc_final_input_driver")
        transport = load(BATCH / "runtime/consumer_transport.py", "_sgc_final_input_transport")
        driver.go_contract({"task": driver.CYCLE, "authorized": True, "plan_sha256": sha(plan_raw), "max_consumers": 9}, plan, sha(plan_raw))
        for slot in plan["sequence"]:
            _, ready, profile = driver.arm_runtime(plan, slot)
            assert json.loads((BATCH / "installations" / (profile + "_READY.json")).read_bytes()) == ready
        for profile in ("P", "G"):
            schemas = json.loads((BATCH / "schemas" / (profile + "_PUBLIC_TOOLS.json")).read_bytes())
            assert {tool["name"] for tool in schemas} == {"human_eye_spatial_relations", "human_eye_surface_nearest"}
            relations = next(tool for tool in schemas if tool["name"] == "human_eye_spatial_relations")
            assert ("geometry" in relations["inputSchema"]["properties"]) is (profile == "G")
        image = transport.initial_image_metadata(plan)
        assert sha(transport.EXE.read_bytes()) == plan["CLI_sha256"]
    assert (BATCH / "PLAN.json").read_bytes() == plan_raw
    report = {"passed": True, "cycle_id": driver.CYCLE, "PLAN_sha256": sha(plan_raw),
        "common_parameters": expected, "frozen_arm_mappings": 9, "P_G_schema_delta": "geometry opt-in present only on G",
        "initial_image": image, "GO_file_created": False, "GO_test_scope": "in-memory synthetic authorization object only",
        "model_consumers": 0, "Blender_sessions": 0, "real_product_calls": 0,
        "source_sha256": sha(Path(__file__).read_bytes()), "Pro_entitlement_verified": False}
    with destination.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps({"passed": True, "output": str(destination), "model_consumers": 0}))


if __name__ == "__main__":
    main()
