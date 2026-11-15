"""Verify saved-version image delivery using the isolated completed control."""

import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import uuid

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from consumer_bridge import Bridge, checked_identity, file_identity, verify_image_response, write
from image_inputs import image_inputs


def main():
    started, cpu = time.perf_counter(), time.process_time()
    output = HERE / "private/preview_preflight" / uuid.uuid4().hex[:10]
    case = HERE / "private/consumer_cases/matched"
    session = HERE / "private/sessions/control_matched_restore"
    state = json.loads((session / "session.json").read_bytes())
    if state["version"] != 1 or state.get("pending"):
        raise ValueError("completed_isolated_control_version_one_required")
    initial = image_inputs(case)
    before = {str(path):file_identity(path) for path in (session / "session.json", Path(state["current_blend"]))}
    preview_directory = session / "previews/v1"
    if (preview_directory / "PREVIEW.json").exists():
        raise ValueError("preserve_existing_preview_preflight_and_inspect_before_rerun")
    output.mkdir(parents=True, exist_ok=False)
    bridge = Bridge(SimpleNamespace(case=case, session=session, audit=output / "bridge", route="native",
        max_tool_calls=12, python_timeout_s=45, python_output_chars=5000, fact_output_chars=18000))
    responses, deliveries = [], []
    for index in (1, 2):
        response = bridge.call(dict(name="images", arguments={}))
        if response.get("isError"):
            raise RuntimeError(response["content"][0]["text"])
        responses.append(response)
        deliveries.append(verify_image_response(output / "bridge" / ("tool_" + str(index).zfill(2)), bridge.task, initial, session))
    bridge.save(True)
    metadata = [json.loads(response["content"][0]["text"]) for response in responses]
    checks = dict(
        frozen_initial_eight_bindings=len(initial) == len(bridge.task["images"]) == 8,
        first_delivery_four_actual_current_views=deliveries[0]["image_blocks"] == 4 and deliveries[0]["delivery_kind"] == "saved_version_preview",
        second_delivery_four_actual_current_views=deliveries[1]["image_blocks"] == 4 and deliveries[1]["delivery_kind"] == "saved_version_preview",
        first_call_renders_exactly_once=deliveries[0]["preview"]["render_invoked"] and not deliveries[0]["preview"]["cache_hit"],
        second_call_reuses_successful_render=not deliveries[1]["preview"]["render_invoked"] and deliveries[1]["preview"]["cache_hit"],
        preview_metadata_and_PNG_SHA_identical=metadata[0] == metadata[1],
        both_exact_saved_control_SHA=all(item["saved_blend_sha256"] == before[state["current_blend"]]["sha256"] for item in deliveries),
        both_bound_to_version_one=all(item["version"] == 1 for item in deliveries),
        complete_response_has_no_source_original_handle=all("source_original" not in json.dumps(item) for item in metadata),
        control_session_and_saved_model_unchanged=all(file_identity(Path(path)) == identity for path, identity in before.items()),
        initial_PNG_bytes_unchanged=image_inputs(case) == initial,
    )
    frozen = json.loads((HERE / "TOOL_FREEZE.json").read_bytes())
    changed = {"consumer_bridge.py", "consumer_runner.py", "analyze_consumers.py"}
    for row in frozen["files"]:
        path = Path(row["path"])
        path = path if path.is_absolute() else HERE / path
        if path.name not in changed:
            checks["frozen_" + path.name] = file_identity(path)["sha256"] == row["sha256"]
    render_run = json.loads(checked_identity(deliveries[0]["preview"]["render_run"]).read_bytes())
    result = dict(status="pass" if all(checks.values()) else "fail", checks=checks,
        actual_Pro_sessions=0, actual_Blender_render_calls=sum(item["preview"]["render_invoked"] for item in deliveries),
        isolated_control_only=True, formal_consumer_sessions_prewarmed=False, deliveries=deliveries,
        render_run=render_run, private_evidence=str(output.relative_to(HERE)),
        wall_s=time.perf_counter()-started, parent_CPU_s=time.process_time()-cpu,
        source_identities=[file_identity(HERE / name) for name in (*sorted(changed), "preview_preflight.py")])
    write(output / "RESULT.json", result)
    write(HERE / "PREVIEW_PREFLIGHT.json", result)
    print(json.dumps(dict(status=result["status"], checks=len(checks), actual_Blender_render_calls=result["actual_Blender_render_calls"], wall_s=result["wall_s"])), flush=True)
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
