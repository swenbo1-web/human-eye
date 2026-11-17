"""Read actual neutral inputs through the consumer bridge without a Pro call."""

import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import uuid

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
from consumer_bridge import Bridge, verify_image_response
from consumer_runner import argv_for, prompt_for, validate_config
from python_executor import execute
import numpy as np


def value(reply):
    result = json.loads(reply["content"][0]["text"])
    if reply.get("isError") or result.get("truncated"):
        raise AssertionError(result)
    return result


def main():
    started, cpu = time.perf_counter(), time.process_time()
    output = HERE / "private/consumer_case_preflight" / uuid.uuid4().hex[:10]
    output.mkdir(parents=True)
    case = HERE / "private/consumer_cases/sample_07"
    formal = HERE / "private/sessions/raw_sample_07_facts"
    before = identity(formal / "session.json")
    state = read(formal / "session.json")
    assert state["version"] == 0 and state.get("pending") is None and not state["operations"]
    session = HERE / "private/sessions" / ("case_probe_" + output.name)
    write(session / "session.json", state)
    config = read("CONSUMER_PLAN.json")["consumer"]
    validate_config(config)
    bridge = Bridge(SimpleNamespace(case=case, session=session, audit=output / "bridge", route="facts",
        max_tool_calls=12, python_timeout_s=config["python_timeout_s"], python_output_chars=config["python_output_chars"],
        fact_output_chars=config["fact_output_chars"]))
    checks = {}
    try:
        task = read(case / "task.json")
        command, tools = argv_for(case, "facts", HERE / "private/consumers/raw/sample_07/facts", config)
        checks["fixed_seven_tools_no_shell"] = tools == ["images", "execute_python", "submit_edit", "state", "save_readback", "focus", "resolve_ref"]
        checks["single_model_medium"] = config["model"] == "gpt-6.1-sol" and config["reasoning_effort"] == "medium"
        checks["public_prompt_neutral_no_private_source_hints"] = all(term not in prompt_for(task, config).decode().lower()
            for term in ("cat_reference", "cat_transfer", "lattice", "decimal", "generation_parameters", "support43", "source_spec", "control_restore", "clean_vertices"))
        value(bridge.call(dict(name="images", arguments={})))
        checks["actual_eight_image_bytes_bound"] = verify_image_response(output / "bridge/tool_01", bridge.task, bridge.images, session)["exact_source_PNG_bytes"]
        focus = value(bridge.call(dict(name="focus", arguments={})))
        checks["actual_focus_within_frozen_text_budget"] = not bridge.calls[-1]["truncated"]
        checks["actual_focus_unit_source_native"] = focus["session_binding"]["unit"].startswith("source_native")
        checks["actual_current_correspondence_274_candidates_69_core"] = focus["image_correspondence"]["candidate_points"] == 274 and focus["image_correspondence"]["core_budget"] == 69
        code = """assert V.shape == (7207,3) and faces.shape == (14410,3)
assert len(F_ids)==384 and len(I_ids)==274 and np.array_equal(V,V0)
assert len(image_roles)==8 and len(reference_packets)>0
for role in (image_roles[1],image_roles[5]):
    image=read_image_pixels(role)
    assert image.dtype==np.uint8 and image.shape==(640,640,3)
with np.load(packet_path,allow_pickle=False) as packet:
    assert np.array_equal(packet['vertices'],V)
print('actual saved current packet, two actual RGB reads and delivered reference packets accessible',version,len(reference_packets))
"""
        result = value(bridge.call(dict(name="execute_python", arguments=dict(code=code))))
        checks["actual_packet_pixels_and_reference_access"] = result.get("error") is None and not result["created_payloads"]
        snapshot, safe_task = bridge.snapshot()
        private = HERE / "private/construction/p0/readback.npz"
        denied, record = execute("np.load(" + repr(str(private)) + ",allow_pickle=False)", snapshot, safe_task,
            session / "payloads", output / "private_access_denied")
        checks["private_normal_path_denied_and_audited"] = bool(denied.get("error")) and record.get("worker", {}).get("access_policy", {}).get("denied_accesses", 0) == 1
        checks["untouched_real_raw_session"] = identity(formal / "session.json") == before
        checks["probe_did_not_create_proposal"] = not list((session / "payloads").glob("p*.npz"))
    finally:
        bridge.save(True)
    result = dict(status="pass" if all(checks.values()) else "fail", checks=checks, passed=sum(checks.values()), total=len(checks),
        actual_Pro_sessions=0, actual_Blender_calls=0, wall_s=time.perf_counter()-started, CPU_s=time.process_time()-cpu,
        evidence=str(output.relative_to(HERE)), formal_session_unchanged=True, prompt=identity(output / "PROMPT.txt") if (output / "PROMPT.txt").exists() else None)
    write("CONSUMER_CASE_PREFLIGHT.json", result)
    print(result["status"], result["passed"], result["total"], flush=True)
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
