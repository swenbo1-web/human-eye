"""Verify one fixed local-support refinement using current-only isolated inputs."""

import hashlib
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import read, write
import numpy as np
import facts_api
from localized_support import build_local_support


def same_arrays(first, second):
    return first.dtype == second.dtype and first.shape == second.shape and first.tobytes() == second.tobytes()


def load_arrays(path):
    with np.load(path, allow_pickle=False) as archive:
        return dict(archive)


def main():
    started, cpu = time.perf_counter(), time.process_time()
    checks = []

    def check(name, value):
        checks.append(dict(name=name, passed=bool(value)))

    folder = HERE / "private/optimized_support_preflight"
    folder.mkdir(exist_ok=False)
    initial = HERE / "private/cases/repair/initial.npz"
    state = dict(version=0, case_id="repair", source_spec=str(HERE / "private/cases/repair/spec.json"),
        current_npz=str(initial), initial_npz=str(initial))
    session = folder / "isolated_session"
    session.mkdir()
    rows = read("IMAGE_BINDING.json")["images"]
    focused = facts_api.focus(session, state, image_rows=rows)
    write(folder / "FOCUS.json", focused)
    outer = focused["image_correspondence"]["regions"]["low_difference_outer_support"]
    outer_packet = load_arrays(outer["geometry_packet"]["path"])
    prototype, directory, alias, *_ = facts_api.prepare(session, state)
    geometry = prototype._load_geometry(alias)
    new_correspondence = load_arrays(directory / "correspondence/ARRAYS.npz")
    old_correspondence = load_arrays(HERE / "private/correspondence_preflight/baseline/ARRAYS.npz")
    check("attention implementation exact v1 source", hashlib.sha256((HERE / "correspondence.py").read_bytes()).hexdigest()
        == "a2a70c2d35eb22dd4304fc0e5c735c33897562a2377d03957feeabf7016b3597")
    check("all correspondence arrays bitwise preserved", set(new_correspondence) == set(old_correspondence)
        and all(same_arrays(new_correspondence[key], old_correspondence[key]) for key in old_correspondence))
    check("core 69 and full positive exclusion retained", len(new_correspondence["active_core_source_ids"]) == 69
        and len(new_correspondence["positive_attention_source_ids"]) == 94)
    targets = outer_packet["fit_target_source_ids"]
    support_ids = outer_packet["source_ids"]
    membership = outer_packet["fit_target_support_mask"]
    check("core source IDs key membership columns", np.array_equal(targets, np.sort(new_correspondence["active_core_source_ids"])))
    check("outer pool unchanged 209", np.array_equal(support_ids, np.sort(old_correspondence["fit_support_source_ids"])) and len(support_ids) == 209)
    check("membership axes and dtype", membership.shape == (209, 69) and membership.dtype == np.bool_)
    check("count equals selected membership", np.array_equal(outer_packet["fit_target_support_count"], membership.sum(axis=0)))
    check("per target maximum 32", np.all(outer_packet["fit_target_support_count"] <= 32))
    check("target normals current raw area weighted", same_arrays(outer_packet["fit_target_normals"], geometry["normals"][targets]))
    check("outer normals current raw area weighted", same_arrays(outer_packet["current_vertex_normals"], geometry["normals"][support_ids]))
    displacement = geometry["vertices"][support_ids, None] - geometry["vertices"][targets][None]
    distance = np.linalg.norm(displacement, axis=2)
    dots = geometry["normals"][support_ids] @ geometry["normals"][targets].T
    check("selected support distance and normal gate", np.all(distance[membership] <= .032) and np.all(dots[membership] > .55))
    check("selected supports exclude all positive attention", not np.intersect1d(support_ids[membership.any(axis=1)],
        new_correspondence["positive_attention_source_ids"]).size)
    recomputed, summary = build_local_support(geometry["vertices"], geometry["normals"], support_ids, targets)
    check("local outputs deterministic", all(same_arrays(value, outer_packet[key]) for key, value in recomputed.items()))
    check("local diagnostic arrays finite", all(np.isfinite(value).all() for value in recomputed.values()))
    check("deficient condition sentinel valid", np.all(outer_packet["fit_target_condition_number"][outer_packet["fit_target_design_rank"] < 6] == -1))
    empty_arrays, _ = build_local_support(geometry["vertices"], geometry["normals"], support_ids[:0], targets[:1])
    check("empty support has explicit diagnostics", empty_arrays["fit_target_support_count"][0] == 0
        and empty_arrays["fit_target_design_rank"][0] == 0 and empty_arrays["fit_target_condition_number"][0] == -1)
    resolved = facts_api.resolve_ref(session, state, outer["reference"], image_rows=rows)
    check("localized reference resolves exact packet", resolved["geometry_packet"] == outer["geometry_packet"])
    prior_focus_path = HERE / "private/consumers/v1/repair/facts/bridge/tool_02/PRIVATE_RESULT.json"
    prior_focus = json.loads(prior_focus_path.read_bytes())
    previous_regions = prior_focus["image_correspondence"]["regions"]
    for role in ("active_core", "low_difference_outer_support", "full_mesh_exclusion"):
        old_packet = load_arrays(previous_regions[role]["geometry_packet"]["path"])
        new_packet = load_arrays(focused["image_correspondence"]["regions"][role]["geometry_packet"]["path"])
        check("v1 " + role + " existing fields unchanged", all(same_arrays(value, new_packet[key]) for key, value in old_packet.items()))
    chars = len(json.dumps(focused, ensure_ascii=True))
    check("default focus within 18000 characters", chars <= 18000)
    result = dict(status="pass" if all(row["passed"] for row in checks) else "fail", checks=checks,
        passed=sum(row["passed"] for row in checks), total=len(checks), default_focus_JSON_chars=chars,
        source_sha256=hashlib.sha256((HERE / "localized_support.py").read_bytes()).hexdigest(),
        outer_packet=outer["geometry_packet"], local_summary=summary,
        correspondence_arrays=str(directory / "correspondence/ARRAYS.npz"),
        v1_correspondence_arrays=str(HERE / "private/correspondence_preflight/baseline/ARRAYS.npz"),
        source_geometry=str(initial), session=str(session), input_scope="current geometry, matched PNG and camera metadata only",
        fitting_operation="No surface fit, displacement or edit is executed. The output is target-local membership and coverage diagnostics.",
        wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu, Pro_calls=0, Blender_calls=0)
    write("OPTIMIZED_SUPPORT_PREFLIGHT.json", result)
    print({key: result[key] for key in ("status", "passed", "total", "default_focus_JSON_chars", "wall_s")})
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
