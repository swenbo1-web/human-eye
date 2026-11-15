"""Check real current-case image and numerical tools without launching a Pro session."""

import argparse
import base64
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
from consumer_bridge import Bridge
from image_inputs import image_inputs


def decoded(result):
    return json.loads(next(block["text"] for block in result["content"] if block["type"] == "text"))


def main():
    started, cpu = time.perf_counter(), time.process_time()
    if (HERE / "BRIDGE_PREFLIGHT.json").exists():
        raise ValueError("real_bridge_preflight_already_completed")
    case = HERE / "private/consumer_cases/matched"
    expected_images = image_inputs(case)
    checks, records = {}, []
    for route in ("native", "facts"):
        session = HERE / "private/sessions" / ("protocol_matched_" + route)
        session.mkdir(exist_ok=False)
        (session / "payloads").mkdir()
        state = read(HERE / "private/sessions/v1_matched_native/session.json")
        shutil.copyfile(state["current_blend"], session / "before.blend")
        state["current_blend"] = str(session / "before.blend")
        state["current_blend_identity"] = identity(session / "before.blend")
        state["route"], state["stage"] = route, "protocol"
        write((session / "session.json").relative_to(HERE), state)
        audit = HERE / "private/bridge_preflight" / route
        bridge = Bridge(argparse.Namespace(case=case, session=session, audit=audit, route=route,
            max_tool_calls=12, python_timeout_s=45, python_output_chars=5000, fact_output_chars=18000))
        images = bridge.call(dict(name="images", arguments={}))
        blocks = [block for block in images["content"] if block["type"] == "image"]
        checks[route + "_eight_exact_PNG_blocks"] = len(blocks) == 8 and all(
            hashlib.sha256(base64.b64decode(block["data"])).hexdigest() == row["sha256"]
            for block, row in zip(blocks, expected_images))
        result = bridge.call(dict(name="execute_python", arguments=dict(code=
            "import numpy as np\n"
            "assert V.shape == V0.shape == (27304,3)\n"
            "assert np.array_equal(V,V0)\n"
            "assert len(F_ids)==410 and len(I_ids)==274\n"
            "assert np.isfinite(n0).all()\n"
            "print(save_edit(I_ids[:1], np.zeros((1,3)), mode='displacements_world'))\n")))
        checks[route + "_real_damaged_snapshot_and_payload"] = not result["isError"]
        if route == "facts":
            focus = decoded(bridge.call(dict(name="focus", arguments={})))
            checks["facts_current_focus"] = focus["task_geometry_roles"]["editable_I_points"] == 274
            reference = focus["editable"]["reference"]
            resolved = decoded(bridge.call(dict(name="resolve_ref", arguments=dict(reference=reference))))
            checks["facts_current_descriptor"] = "geometry_packet" in resolved
            result = bridge.call(dict(name="execute_python", arguments=dict(code=
                "import numpy as np\n"
                "assert len(reference_packets)==1\n"
                "with np.load(reference_packets[0]['path'],allow_pickle=False) as p:\n"
                "    assert np.array_equal(p['current_positions_world'],V[p['source_ids']])\n"
                "    print('current reference packet verified',len(p['source_ids']))\n")))
            checks["facts_delivered_descriptor_actually_readable"] = not result["isError"]
        bridge.save(True)
        checks[route + "_session_unmodified"] = read(session / "session.json")["version"] == 0
        checks[route + "_inputs_unchanged"] = read(audit / "BRIDGE_RESULT.json")["source_unchanged"]
        records.append(identity(audit / "BRIDGE_RESULT.json"))
    write("BRIDGE_PREFLIGHT.json", dict(status="pass" if all(checks.values()) else "fail",
        checks=checks, passed=sum(checks.values()), total=len(checks), bridges=records,
        actual_local_PNG_blocks=16, actual_Pro_sessions=0, actual_Blender_calls=0,
        wall_s=time.perf_counter() - started, cpu_s=time.process_time() - cpu))
    if not all(checks.values()):
        raise RuntimeError("current_case_bridge_preflight_failed")
    print("real current-case image, current-only numerical and facts packet preflight passed", flush=True)


if __name__ == "__main__":
    main()
