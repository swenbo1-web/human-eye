"""Current-input numerical and version/reference checks without target labels."""

import hashlib
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import read, write
import numpy as np
from correspondence import compute_correspondence
import facts_api


def main():
    started, cpu = time.perf_counter(), time.process_time()
    folder = HERE / "private/correspondence_preflight"
    folder.mkdir(parents=True, exist_ok=True)
    checks = []

    def check(name, value):
        checks.append(dict(name=name, passed=bool(value)))

    def rejects(name, callback):
        try:
            callback()
        except ValueError:
            check(name, True)
        else:
            check(name, False)

    with np.load(HERE / "private/cases/repair/initial.npz", allow_pickle=False) as archive:
        packet = dict(archive)
    image_rows = read("IMAGE_BINDING.json")["images"]
    baseline = compute_correspondence(packet, image_rows, HERE, folder / "baseline")
    warm = compute_correspondence(packet, image_rows, HERE, folder / "baseline")
    arrays, summary = baseline["arrays"], baseline["summary"]
    check("fixed core 69", len(arrays["active_core_source_ids"]) == 69)
    check("editable incident-face visibility 234", summary["incident_face_visible_editable_points"] == 234)
    check("editable positive attention 77", summary["positive_attention_editable_points"] == 77)
    check("complete-mesh positive attention 94", summary["positive_attention_full_mesh_points"] == 94)
    check("stable score/source ranking", np.array_equal(arrays["ranked_source_ids"], packet["I_ids"][np.lexsort((packet["I_ids"], -arrays["attention"][packet["I_ids"]]))]))
    check("all positive attention excluded", np.isin(arrays["positive_attention_source_ids"], arrays["fit_exclusion_source_ids"]).all())
    check("supports exclude positive and core", not np.intersect1d(arrays["fit_support_source_ids"], arrays["fit_exclusion_source_ids"]).size)
    check("supports observed and zero attention", np.all(arrays["incident_face_visible"][arrays["fit_support_source_ids"]].any(axis=1))
        and np.all(arrays["attention"][arrays["fit_support_source_ids"]] == 0))
    check("support candidates available", len(arrays["fit_support_source_ids"]) > 0)
    check("core and transition remain editable", np.isin(arrays["active_core_source_ids"], packet["I_ids"]).all()
        and np.isin(arrays["transition_source_ids"], packet["I_ids"]).all())
    check("cache is exact array reuse", warm["cost"]["cache_hit"] and all(np.array_equal(arrays[key], warm["arrays"][key]) for key in arrays))
    check("triangle polygon source mapping", np.array_equal(arrays["triangle_source_ids"], packet["faces"])
        and np.array_equal(arrays["triangle_polygon_ids"], packet["triangle_polygon_ids"]))
    formal = HERE / "private/sessions/v1_repair_facts/session.json"
    before = hashlib.sha256(formal.read_bytes()).hexdigest()
    state = json.loads(formal.read_bytes())
    session = folder / "focus_session"
    session.mkdir(exist_ok=True)
    focused = facts_api.focus(session, state, image_rows=image_rows)
    regions = focused["image_correspondence"]["regions"]
    check("five image regions returned", len(regions) == 5)
    for name, region in regions.items():
        resolved = facts_api.resolve_ref(session, state, region["reference"], image_rows=image_rows)
        check(name + " packet matches resolve", region.get("geometry_packet", resolved["geometry_packet"]) == resolved["geometry_packet"])
    old = facts_api.resolve_ref(session, state, focused["editable"]["reference"])
    check("existing geometry reference retained", old["geometry"]["points"] == 274)
    rejects("other session cannot resolve reference", lambda: facts_api.resolve_ref(folder / "other_session", state,
        regions["active_core"]["reference"], image_rows=image_rows))
    rejects("new version requires actual saved image rows", lambda: facts_api.focus(session, dict(state, version=1)))
    check("formal session state untouched", before == hashlib.sha256(formal.read_bytes()).hexdigest())
    public_chars = len(json.dumps(focused, ensure_ascii=True))
    check("default focus fits fact output budget", public_chars <= 18000)
    result = dict(status="pass" if all(row["passed"] for row in checks) else "fail", checks=checks,
        passed=sum(row["passed"] for row in checks), total=len(checks),
        baseline_summary=summary, first_call=baseline["cost"], same_version_reuse=warm["cost"],
        default_focus_JSON_chars=public_chars, formal_state_untouched=True,
        baseline_arrays=str(folder / "baseline/ARRAYS.npz"),
        wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu,
        input_scope="Current mesh, PNGs and camera metadata only; private target labels are not read",
        Pro_calls=0, Blender_calls=0)
    original_attempt = folder / "ATTEMPT_001.json"
    if original_attempt.exists():
        original = json.loads(original_attempt.read_bytes())
        result["initial_recorded_compute"] = original["first_call"]
        result["initial_attempt"] = dict(path=str(original_attempt), status=original["status"],
            passed=original["passed"], total=original["total"], issue="Default focus text exceeded its output budget")
    write("CORRESPONDENCE_PREFLIGHT.json", result)
    print({key: result[key] for key in ("status", "passed", "total", "default_focus_JSON_chars", "wall_s")})
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
