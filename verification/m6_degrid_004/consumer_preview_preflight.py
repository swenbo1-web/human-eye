"""One actual saved-control preview followed by its cached image delivery."""

import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import uuid

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from consumer_bridge import Bridge, file_identity, verify_image_response, write
from image_inputs import image_inputs


def main():
    started, cpu = time.perf_counter(), time.process_time()
    output = HERE / "private/preview_preflight" / uuid.uuid4().hex[:10]
    case = HERE / "private/consumer_cases/repair"
    session = HERE / "private/sessions/control_repair_restore"
    audit = output / "bridge"
    checks, calls, bridge = {}, [], None
    try:
        task = json.loads((case / "task.json").read_bytes())
        state_before = file_identity(session / "session.json")
        state = json.loads((session / "session.json").read_bytes())
        if state["version"] != 1 or state.get("pending") or (session / "previews").exists():
            raise ValueError("preview_preflight_requires_unpreviewed_saved_control_version_one")
        config = json.loads((HERE / "PLAN.json").read_bytes())["consumer"]
        bridge = Bridge(SimpleNamespace(case=case, session=session, audit=audit, route="native",
            max_tool_calls=2, python_timeout_s=config.get("python_timeout_s", 45),
            python_output_chars=config.get("python_output_chars", 5000),
            fact_output_chars=config.get("fact_output_chars", 18000)))
        rows = image_inputs(case)
        for position in range(2):
            reply = bridge.call(dict(name="images", arguments={}))
            payload = json.loads(reply["content"][0]["text"])
            if reply.get("isError"):
                raise AssertionError(payload)
            call = verify_image_response(audit / ("tool_" + str(position + 1).zfill(2)), task, rows, session)
            checks["delivery_" + str(position + 1) + "_four_actual_PNG_blocks"] = call["image_blocks"] == 4 and call["exact_source_PNG_bytes"]
            checks["delivery_" + str(position + 1) + "_neutral_public_paths"] = all(word not in reply["content"][0]["text"].lower()
                for word in ("degrid", "grid", "perturb", "seed", "noise", "source_spec", "clean_3d"))
            checks["delivery_" + str(position + 1) + "_actual_saved_version"] = call["version"] == 1 and call["saved_blend_sha256"] == state["current_blend_identity"]["sha256"]
            calls.append(call)
        checks["first_delivery_invoked_exactly_one_actual_render"] = calls[0]["preview"]["render_invoked"] and not calls[0]["preview"]["cache_hit"]
        checks["second_delivery_used_same_saved_version_cache"] = calls[1]["preview"]["cache_hit"] and not calls[1]["preview"]["render_invoked"]
        checks["saved_control_session_bytes_unchanged"] = file_identity(session / "session.json") == state_before
        checks["formal_consumer_caches_uncreated"] = all(not (HERE / "private/sessions" / ("run_repair_" + route) / name).exists()
            for route in ("facts", "native") for name in ("snapshots", "previews"))
        result = dict(status="pass" if all(checks.values()) else "fail", checks=checks, calls=calls,
            actual_Pro_sessions=0, actual_Blender_calls=sum(call["preview"]["render_invoked"] for call in calls),
            scope="Actual saved control version one, frozen cameras and scale. One render and one cached four-image delivery, with no geometry edits or formal consumer cache creation.")
    except BaseException as exception:
        import traceback
        result = dict(status="fail", checks=checks, calls=calls,
            error=dict(type=type(exception).__name__, message=str(exception)), traceback=traceback.format_exc(),
            actual_Pro_sessions=0, actual_Blender_calls=None)
    finally:
        if bridge is not None:
            bridge.save(True)
    result.update(wall_s=time.perf_counter()-started, parent_CPU_s=time.process_time()-cpu,
        evidence_directory=str(output.relative_to(HERE)))
    write(output / "RESULT.json", result)
    write(HERE / "CONSUMER_PREVIEW_PREFLIGHT.json", result)
    print(json.dumps(dict(status=result["status"], checks=len(checks), actual_Blender_calls=result["actual_Blender_calls"], wall_s=result["wall_s"], evidence=str(output))))
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
