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
        formal_states = {stage + "_" + route: file_identity(HERE / "private/sessions" / (stage + "_repair_" + route) / "session.json")
            for stage in ("v1", "v2") for route in ("facts", "native")}
        frozen = {}
        for route in ("facts", "native"):
            original = HERE / "private/sessions" / ("v1_repair_" + route)
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
            code = """assert np.array_equal(V,V0)
assert len(F_ids)==410 and len(I_ids)==274
with np.load(packet_path,allow_pickle=False) as p:
    assert np.array_equal(p['vertices'],V)
assert ':' not in packet_path and ':' not in payload_folder
assert len(image_roles)==8
for role in image_roles:
    pixels=read_image_pixels(role)
    assert pixels.dtype==np.uint8 and pixels.ndim==3 and pixels.shape[2]==3
    assert np.asarray(image_cameras[role]['world_to_image_affine_2_by_3']).shape==(2,3)
    print(role,pixels.shape,int(pixels.sum()))
print(version,V.shape,len(F_ids),len(I_ids))
"""
            computation = value(bridge.call(dict(name="execute_python", arguments=dict(code=code))))
            checks[route + "_actual_bounded_python_packet_read"] = computation["error"] is None
            checks[route + "_all_eight_PNG_pixels_are_readable_and_audited"] = len(computation.get("image_pixel_reads", [])) == 8
            reference = None
            if route == "facts":
                focused = value(bridge.call(dict(name="focus", arguments={})))
                checks["facts_default_focus_registers_core_support_exclusion_packets"] = len(bridge.reference_packets) >= 3
                target = focused["target"]["reference"]
                resolved = value(bridge.call(dict(name="resolve_ref", arguments=dict(reference=target))))
                descriptor = resolved["geometry_packet"]
                reference = descriptor
                code = "assert any(item['path']==" + repr(descriptor["path"]) + " for item in reference_packets)\nwith np.load(" + repr(descriptor["path"]) + ",allow_pickle=False) as p:\n    ids=p['source_ids']\n    assert np.array_equal(p['current_positions_world'],V[ids])\n    print(len(ids))\nfor item in reference_packets:\n    with np.load(item['path'],allow_pickle=False) as p:\n        assert np.array_equal(p['current_positions_world'],V[p['source_ids']])\n        if 'attention' in p:\n            assert p['per_view_score'].shape==(len(p['source_ids']),3)\n            print('correspondence',len(p['source_ids']),p['attention'].shape)"
                computed = value(bridge.call(dict(name="execute_python", arguments=dict(code=code))))
                checks["facts_delivered_relative_reference_is_readable_current_geometry"] = computed["error"] is None
            public = json.dumps([json.loads((audit / ("tool_" + str(call["index"]).zfill(2)) / "COMPLETE_RESULT.json").read_bytes()) for call in bridge.calls])
            checks[route + "_all_tool_metadata_paths_are_neutral"] = "m6_degrid" not in public.lower()
            checks[route + "_formal_session_bytes_unchanged"] = file_identity(original / "session.json") == frozen[route]
            checks[route + "_formal_session_caches_uncreated"] = not (original / "snapshots").exists() and not (original / "previews").exists()
            bridge.save(True)
            command, tools = argv_for(case, route, HERE / "private/consumers/v1/repair" / route, config)
            checks[route + "_normal_entrypoint_arguments_build"] = bool(command and tools)
            records.append(dict(route=route, protocol_session=str(session), formal_session=frozen[route],
                image_audit=image_audit, public_images=public_images, reference_packet=reference,
                tools=tools, bridge_directory=str(audit)))
        checks["both_routes_same_prompt_bytes"] = prompt == prompt_for(task, config)
        checks["both_routes_same_initial_image_metadata"] = records[0]["public_images"]["images"] == records[1]["public_images"]["images"]
        checks["all_four_formal_states_preserved"] = all(file_identity(HERE / "private/sessions" / (name.replace("_", "_repair_", 1)) / "session.json") == expected
            for name, expected in formal_states.items())
        checks["all_four_formal_caches_absent"] = all(not (HERE / "private/sessions" / (stage + "_repair_" + route) / name).exists()
            for stage in ("v1", "v2") for route in ("facts", "native") for name in ("snapshots", "previews"))
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
