"""Read optimized support packets in an isolated real-data Python session."""

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
from consumer_bridge import Bridge
from python_executor import LOCAL_SUPPORT_FIELDS, validate_read_only_packet
import numpy as np


def value(response):
    payload = json.loads(response["content"][0]["text"])
    if response.get("isError") or payload.get("truncated"):
        raise AssertionError(payload)
    return payload


def main():
    started, cpu = time.perf_counter(), time.process_time()
    output = HERE / "private/local_support_runtime_preflight" / uuid.uuid4().hex[:10]
    output.mkdir(parents=True)
    snapshot = read("STAGE_V1_SNAPSHOT.json")
    checks = {}
    for row in snapshot["files"]:
        if identity(HERE / row["path"])["sha256"] != row["sha256"]:
            raise ValueError("v1_snapshot_member_changed_before_runtime_preflight")
    formal = {route: identity(HERE / "private/sessions" / ("v2_repair_" + route) / "session.json")
        for route in ("native", "facts")}
    state = read("private/sessions/v2_repair_facts/session.json")
    if state["version"] != 0 or state.get("operations") or state.get("pending"):
        raise ValueError("v2_formal_session_must_still_be_unstarted")
    session = HERE / "private/sessions" / ("ls_" + output.name)
    write(session / "session.json", state)
    case = HERE / "private/consumer_cases/repair"
    config = read("PLAN.json")["consumer"]
    bridge = Bridge(SimpleNamespace(case=case, session=session, audit=output / "bridge", route="facts",
        max_tool_calls=12, python_timeout_s=config.get("python_timeout_s", 45),
        python_output_chars=config.get("python_output_chars", 5000), fact_output_chars=config.get("fact_output_chars", 18000)))
    try:
        value(bridge.call(dict(name="images", arguments={})))
        focused = value(bridge.call(dict(name="focus", arguments={})))
        checks["optimized_focus_fits_frozen_text_budget"] = not bridge.calls[-1]["truncated"]
        regions = focused["image_correspondence"]["regions"]
        core = regions["active_core"]["geometry_packet"]
        outer = regions["low_difference_outer_support"]["geometry_packet"]
        exclusion = regions["full_mesh_exclusion"]["geometry_packet"]
        checks["three_default_packets_registered"] = len(bridge.reference_packets) == 3
        code = """with np.load(reference_packets[0]['path'],allow_pickle=False) as core, np.load(reference_packets[1]['path'],allow_pickle=False) as outer, np.load(reference_packets[2]['path'],allow_pickle=False) as exclusion:
    targets=outer['fit_target_source_ids']
    mask=outer['fit_target_support_mask']
    assert np.array_equal(targets,core['source_ids'])
    assert mask.dtype==np.bool_ and mask.shape==(len(outer['source_ids']),69)
    assert np.array_equal(mask.sum(axis=0),outer['fit_target_support_count'])
    assert np.all(outer['fit_target_support_count']<=32)
    assert not np.isin(outer['source_ids'],exclusion['source_ids']).any()
    assert np.array_equal(outer['current_positions_world'],V[outer['source_ids']])
    assert len(image_roles)==8 and read_image_pixels('current_forearm_front').dtype==np.uint8
    print('local_support_packet',len(targets),mask.shape,outer['fit_target_support_count'].min(),outer['fit_target_support_count'].max())
"""
        computed = value(bridge.call(dict(name="execute_python", arguments=dict(code=code))))
        checks["actual_current_geometry_local_packets_and_PNG_readable"] = computed["error"] is None
        resolved = value(bridge.call(dict(name="resolve_ref", arguments=dict(reference=regions["low_difference_outer_support"]["reference"]))))
        checks["resolved_outer_packet_matches_default_descriptor"] = resolved["geometry_packet"] == outer
        private_focus = read(output / "bridge/tool_02/PRIVATE_RESULT.json")
        original = private_focus["image_correspondence"]["regions"]["low_difference_outer_support"]["geometry_packet"]
        with np.load(original["path"], allow_pickle=False) as archive:
            fields = dict(archive)
        current = bridge.snapshot_fields(state)
        directory = Path(original["path"]).parent

        def descriptor_for(label, arrays):
            path = directory / ("a" + hashlib.sha256(label.encode()).hexdigest() + ".npz")
            np.savez_compressed(path, **arrays)
            raw = path.read_bytes()
            return dict(original, path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                arrays={key: dict(dtype=str(array.dtype), shape=list(array.shape)) for key, array in arrays.items()})

        legacy = {key: array for key, array in fields.items() if key not in LOCAL_SUPPORT_FIELDS}
        validate_read_only_packet(descriptor_for("legacy_image_packet", legacy), session, 0, current)
        checks["legacy_image_packet_still_valid"] = True
        mutations = {}
        partial = dict(fields)
        partial.pop("fit_target_support_count")
        mutations["partial_field_group"] = partial
        for key in ("fit_target_support_count", "fit_target_design_rank", "fit_target_condition_number",
                    "fit_target_nearest_distance_m", "fit_target_farthest_distance_m", "fit_target_angular_bins",
                    "fit_target_max_angular_gap_rad", "fit_target_normal_dot_minimum"):
            changed = {name: array.copy() for name, array in fields.items()}
            changed[key][0] += 1
            mutations[key] = changed
        changed = {name: array.copy() for name, array in fields.items()}
        changed["fit_target_support_mask"][0, 0] = ~changed["fit_target_support_mask"][0, 0]
        mutations["membership"] = changed
        changed = {name: array.copy() for name, array in fields.items()}
        changed["fit_target_normals"][0] *= -1
        mutations["target_normals"] = changed
        changed = {name: array.copy() for name, array in fields.items()}
        changed["fit_target_source_ids"][0] = changed["fit_target_source_ids"][1]
        mutations["duplicate_target"] = changed
        for label, changed in mutations.items():
            try:
                validate_read_only_packet(descriptor_for("invalid_" + label, changed), session, 0, current)
                checks["rejected_" + label] = False
            except ValueError:
                checks["rejected_" + label] = True
        checks["v1_snapshot_all_members_preserved"] = all(identity(HERE / row["path"])["sha256"] == row["sha256"] for row in snapshot["files"])
        checks["v2_formal_states_preserved"] = all(identity(HERE / "private/sessions" / ("v2_repair_" + route) / "session.json") == original for route, original in formal.items())
        checks["v2_formal_caches_absent"] = all(not (HERE / "private/sessions" / ("v2_repair_" + route) / folder).exists()
            for route in ("native", "facts") for folder in ("snapshots", "previews"))
        result = dict(status="pass" if all(checks.values()) else "fail", checks=checks,
            registered_packets=[core, outer, exclusion], source=identity(Path(__file__)),
            wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu,
            actual_Pro_calls=0, actual_Blender_calls=0, hidden_geometry_or_labels_read=False,
            evidence_directory=str(output.relative_to(HERE)))
    except BaseException as exception:
        import traceback
        result = dict(status="fail", checks=checks, error=dict(type=type(exception).__name__, message=str(exception)),
            traceback=traceback.format_exc(), wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu,
            actual_Pro_calls=0, actual_Blender_calls=0, evidence_directory=str(output.relative_to(HERE)))
    finally:
        bridge.save(True)
    write(output / "RESULT.json", result)
    write("LOCAL_SUPPORT_RUNTIME_PREFLIGHT.json", result)
    print(json.dumps({key: result[key] for key in ("status", "wall_s", "CPU_s", "evidence_directory")}))
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
