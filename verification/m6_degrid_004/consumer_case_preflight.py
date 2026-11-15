"""Read-only Bridge checks on the actual case in separate protocol sessions."""

import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import uuid

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from consumer_bridge import Bridge, file_identity, verify_image_response, write
from consumer_runner import argv_for, prompt_for, validate_config
from image_inputs import image_inputs
import numpy as np


def value(response):
    payload = json.loads(response["content"][0]["text"])
    if response.get("isError"):
        raise AssertionError(payload)
    return payload


def main():
    started, cpu = time.perf_counter(), time.process_time()
    serial = uuid.uuid4().hex[:10]
    output = HERE / "private/case_preflight" / serial
    output.mkdir(parents=True, exist_ok=False)
    checks, records, bridges = {}, [], []
    try:
        case = HERE / "private/consumer_cases/repair"
        task = json.loads((case / "task.json").read_bytes())
        config = json.loads((HERE / "PLAN.json").read_bytes())["consumer"]
        validate_config(config)
        rows = image_inputs(case)
        checks["eight_actual_initial_PNGs"] = len(rows) == 8
        checks["task_images_use_case_relative_paths"] = all(item["path"].startswith("images/") for item in task["images"])
        prompt = prompt_for(task, config)
        (output / "PROMPT.txt").write_bytes(prompt)
        checks["prompt_has_no_construction_or_condition_hint"] = all(word not in prompt.lower()
            for word in (b"m6_degrid", b"seed", b"noise", b"grid", b"4096", b"8192", b"source_spec"))
        with np.load(case / "input.npz", allow_pickle=False) as archive:
            baseline = {key: archive[key] for key in ("vertices_world", "faces", "source_ids", "n0")}
        frozen = {}
        for route in ("facts", "native"):
            original = HERE / "private/sessions" / ("run_repair_" + route)
            frozen[route] = file_identity(original / "session.json")
            state = json.loads((original / "session.json").read_bytes())
            if state["version"] != 0 or state.get("operations") or state.get("pending"):
                raise ValueError("actual_preflight_requires_unstarted_version_zero_consumer_sessions")
            session = HERE / "private/sessions" / ("protocol_case_" + serial + "_" + route)
            write(session / "session.json", state)
            audit = output / route
            bridge = Bridge(SimpleNamespace(case=case, session=session, audit=audit, route=route,
                max_tool_calls=12, python_timeout_s=config.get("python_timeout_s", 45),
                python_output_chars=config.get("python_output_chars", 5000),
                fact_output_chars=config.get("fact_output_chars", 18000)))
            bridges.append(bridge)
            reply = bridge.call(dict(name="images", arguments={}))
            public_images = value(reply)
            image_audit = verify_image_response(audit / "tool_01", task, rows, session)
            checks[route + "_actual_image_blocks_exact"] = image_audit["exact_source_PNG_bytes"]
            checks[route + "_image_metadata_paths_are_neutral"] = "m6_degrid" not in reply["content"][0]["text"].lower()
            fields = bridge.snapshot_fields(state)
            checks[route + "_packet_uses_actual_initial_geometry"] = np.array_equal(fields["vertices"], baseline["vertices_world"]) and np.array_equal(fields["initial_vertices"], baseline["vertices_world"])
            checks[route + "_packet_uses_actual_initial_normals"] = np.array_equal(fields["n0"], baseline["n0"])
            code = "assert np.array_equal(V,V0)\nassert len(F_ids)==410 and len(I_ids)==274\nwith np.load(packet_path,allow_pickle=False) as p:\n    assert np.array_equal(p['vertices'],V)\nassert ':' not in packet_path and ':' not in payload_folder\nprint(version,V.shape,len(F_ids),len(I_ids))"
            computation = value(bridge.call(dict(name="execute_python", arguments=dict(code=code))))
            checks[route + "_actual_bounded_python_packet_read"] = computation["error"] is None
            reference = None
            if route == "facts":
                focused = value(bridge.call(dict(name="focus", arguments={})))
                target = focused["target"]["reference"]
                resolved = value(bridge.call(dict(name="resolve_ref", arguments=dict(reference=target))))
                descriptor = resolved["geometry_packet"]
                reference = descriptor
                code = "assert reference_packets[0]['path']==" + repr(descriptor["path"]) + "\nwith np.load(" + repr(descriptor["path"]) + ",allow_pickle=False) as p:\n    ids=p['source_ids']\n    assert np.array_equal(p['current_positions_world'],V[ids])\n    print(len(ids))"
                computed = value(bridge.call(dict(name="execute_python", arguments=dict(code=code))))
                checks["facts_delivered_relative_reference_is_readable_current_geometry"] = computed["error"] is None
            public = json.dumps([json.loads((audit / ("tool_" + str(call["index"]).zfill(2)) / "COMPLETE_RESULT.json").read_bytes()) for call in bridge.calls])
            checks[route + "_all_tool_metadata_paths_are_neutral"] = "m6_degrid" not in public.lower()
            checks[route + "_formal_session_bytes_unchanged"] = file_identity(original / "session.json") == frozen[route]
            checks[route + "_formal_session_caches_uncreated"] = not (original / "snapshots").exists() and not (original / "previews").exists()
            bridge.save(True)
            command, tools = argv_for(case, route, HERE / "private/consumers/run/repair" / route, config)
            checks[route + "_normal_entrypoint_arguments_build"] = bool(command and tools)
            records.append(dict(route=route, protocol_session=str(session), formal_session=frozen[route],
                image_audit=image_audit, public_images=public_images, reference_packet=reference,
                tools=tools, bridge_directory=str(audit)))
        checks["both_routes_same_prompt_bytes"] = prompt == prompt_for(task, config)
        checks["both_routes_same_initial_image_metadata"] = records[0]["public_images"]["images"] == records[1]["public_images"]["images"]
        result = dict(status="pass" if all(checks.values()) else "fail", checks=checks, records=records,
            prompt_sha256=hashlib.sha256(prompt).hexdigest(), actual_Pro_sessions=0, actual_Blender_calls=0,
            wall_s=time.perf_counter()-started, parent_CPU_s=time.process_time()-cpu,
            evidence_directory=str(output.relative_to(HERE)), scope="Actual current case and images, separate read-only protocol sessions. Formal consumer snapshot and preview caches remain absent.")
    except BaseException as exception:
        import traceback
        result = dict(status="fail", checks=checks, error=dict(type=type(exception).__name__, message=str(exception)),
            traceback=traceback.format_exc(), actual_Pro_sessions=0, actual_Blender_calls=0,
            wall_s=time.perf_counter()-started, parent_CPU_s=time.process_time()-cpu)
    finally:
        for bridge in bridges:
            bridge.save(True)
    write(output / "RESULT.json", result)
    write(HERE / "CONSUMER_CASE_PREFLIGHT.json", result)
    print(json.dumps(dict(status=result["status"], checks=len(checks), wall_s=result["wall_s"], evidence=str(output))))
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
