"""Local real-array regression for the reference metrics and versioned facts."""

import copy
import json
from pathlib import Path
import sys
import time
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from common import identity,read,write
from evaluate import evaluate_packets
from quality import geometry_quality,current_sections
import facts_api
import numpy as np


def main():
    started,cpu=time.perf_counter(),time.process_time()
    output=HERE/"private/quality_preflight"
    output.mkdir(parents=True,exist_ok=False)
    case=HERE/"private/cases/forearm"
    with np.load(case/"initial.npz",allow_pickle=False) as archive:
        initial={key:archive[key] for key in archive.files}
    spec=read(case/"spec.json")
    scene=read(case/"baseline_scene.json")
    checks={}
    baseline=evaluate_packets(case/"initial.npz",case/"initial.npz",case/"initial.npz",case/"spec.json",
        before_state_path=case/"baseline_scene.json",after_state_path=case/"baseline_scene.json")
    write(output/"BASELINE.json",baseline)
    checks["zero_edit_technical_pass"]=baseline["status"]=="pass"
    checks["zero_edit_both_improvements_false"]=baseline["contours"]["geometry_improvement_established"]==dict(primary=False,alternative=False)
    old=read(HERE.parent/"m6_reference_refine_001/OBSERVATION.json")
    for name,old_key in (("primary","primary_stations"),("alternative","alternative_stations")):
        current=baseline["contours"]["definitions"][name]["after"]["stations"]
        checks[name+"_existing_outer_and_width_reproduced"]=all(abs(a["model"]["outer"]-b["model_outer"])<1e-12 and abs(a["model"]["width"]-b["model_width"])<1e-12 for a,b in zip(current,old[old_key]))
        checks[name+"_axis_width_decomposition"]=all(abs(a["signed_residual"]["outer"]-(a["signed_residual"]["centerline"]+.5*a["signed_residual"]["width"]))<1e-12 for a in current)
    changed=copy.deepcopy(initial)
    vertex=int(initial["I_ids"][len(initial["I_ids"])//2])
    changed["vertices_local"][vertex,1]+=np.float32(1e-6)
    transform=changed["matrix_world"]
    changed["vertices"]=changed["vertices_local"].astype(float) @ transform[:3,:3].T+transform[:3,3]
    changed["vertices_world"]=changed["vertices"]
    np.savez_compressed(output/"tiny_saved_precision.npz",**changed)
    tiny=evaluate_packets(case/"initial.npz",output/"tiny_saved_precision.npz",case/"initial.npz",case/"spec.json",
        before_state_path=case/"baseline_scene.json",after_state_path=case/"baseline_scene.json")
    write(output/"TINY.json",tiny)
    checks["tiny_edit_technical_pass"]=tiny["status"]=="pass"
    checks["tiny_edit_full_exact_scan"]=tiny["geometry"]["self_intersection"]["exact_pair_scan_executed"]
    checks["tiny_edit_budget_and_domain"]=tiny["checks"]["cumulative_displacement_budget"] and tiny["displacement"]["changed_outside_I"]==0
    def local_result(value):
        return geometry_quality(initial,value,initial,spec,scene,scene,check_intersections=False)
    outside=copy.deepcopy(initial)
    protected=int(initial["protected_ids"][0])
    outside["vertices_local"][protected,0]=np.nextafter(outside["vertices_local"][protected,0],np.float32(np.inf))
    outside["vertices"]=outside["vertices_local"].astype(float) @ transform[:3,:3].T+transform[:3,3]
    outside_result=local_result(outside)
    checks["one_native_bit_outside_I_fails"]=outside_result["checks"]["outside_I_local_float32_bitwise"] is False
    too_large=copy.deepcopy(initial)
    too_large["vertices"][vertex,1]+=2*spec["max_cumulative_displacement_m"]
    checks["cumulative_budget_fails"]=local_result(too_large)["checks"]["cumulative_displacement_budget"] is False
    altered=copy.deepcopy(initial)
    altered["source_ids"][0]+=1
    checks["source_ID_mapping_change_fails"]=local_result(altered)["checks"]["source_vertex_ids"] is False
    altered=copy.deepcopy(initial)
    altered["poly_vertices"][0]+=1
    checks["native_polygon_change_fails"]=local_result(altered)["checks"]["native_polygon_vertices"] is False
    # Use a dedicated local state and cache so the four real consumers stay cold.
    session=HERE/"private/sessions/quality_preflight"
    session.mkdir(parents=True,exist_ok=False)
    state=dict(case_id="forearm",version=0,current_npz=str(case/"initial.npz"),initial_npz=str(case/"initial.npz"),source_spec=str(case/"spec.json"))
    focus=facts_api.focus(session,state)
    resolved=facts_api.resolve_ref(session,state,focus["target"]["reference"])
    checks["focus_target_is_full_F599"]=resolved["source_ids"]==initial["F_source_ids"].tolist()
    checks["focus_editable_I_exact"]=focus["editable_source_ids"]==initial["I_ids"].tolist()
    checks["focus_nonempty_I"]=focus["task_geometry_roles"]["editable_I_points"]>0
    checks["resolved_positions_are_actual_world"]=np.array_equal(np.array(resolved["current_positions_world"]),initial["vertices"][initial["F_source_ids"]])
    projections=facts_api.project_sections(session,state)
    checks["project_sections_dual_definitions"]=set(projections["definitions"])=={"primary","alternative"}
    checks["project_sections_current_version"]=projections["session_binding"]["session_version"]==0
    newer=dict(state,version=1,current_npz=str(output/"tiny_saved_precision.npz"))
    try:
        facts_api.resolve_ref(session,newer,focus["target"]["reference"])
    except ValueError as error:
        checks["stale_reference_rejected"]=str(error)=="region_reference_outside_current_session_version"
    other=HERE/"private/sessions/quality_other"
    other.mkdir(parents=True,exist_ok=False)
    try:
        facts_api.resolve_ref(other,state,focus["target"]["reference"])
    except ValueError as error:
        checks["cross_session_reference_rejected"]=str(error)=="region_reference_outside_current_session_version"
    result=dict(status="pass" if all(checks.values()) else "fail",checks=checks,passed=sum(checks.values()),total=len(checks),
        wall_s=time.perf_counter()-started,cpu_s=time.process_time()-cpu,actual_Pro_calls=0,actual_Blender_calls=0,
        full_actual_array_inputs=True, exact_intersection_scans=2, explicit_local_skip_cases="Only guard mutations use check_intersections=False; baseline and tiny saved-precision arrays use default full check",
        source_identities=[identity(HERE/name) for name in ("quality.py","evaluate.py","facts_api.py","quality_preflight.py")])
    write(output/"FOCUS.json",focus)
    write(output/"RESOLVED.json",resolved)
    write(output/"SECTIONS.json",projections)
    write("QUALITY_PREFLIGHT.json",result)
    print(json.dumps(dict(status=result["status"],passed=result["passed"],total=result["total"],wall_s=result["wall_s"])),flush=True)
    if result["status"]!="pass":
        raise SystemExit(1)


if __name__=="__main__":
    main()
