"""Post-run raw-only boundary verification and index; no host/kernel diagnostics."""
from __future__ import annotations

from copy import deepcopy
import difflib
from hashlib import file_digest
import importlib.util
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
RAW=Path("D:/HumanEye/runs/M6-045-R3-REPLACEMENT-ENTRY/boundary")
OUT=RAW/"attempt_001"


def read(path):return json.loads(Path(path).read_bytes())


def pin(path):
    path=Path(path).resolve(strict=True)
    with path.open("rb") as stream:digest=file_digest(stream,"sha256").hexdigest()
    return dict(path=str(path),bytes=path.stat().st_size,sha256=digest)


def need(value,reason):
    if not value:raise ValueError("045_boundary_audit_"+reason)


def save(path,value):
    with Path(path).open("x",encoding="utf-8",newline="\n") as stream:
        json.dump(value,stream,indent=2,ensure_ascii=False,allow_nan=False);stream.write("\n")
    return pin(path)


def module():
    spec=importlib.util.spec_from_file_location("_045_boundary_post_only",HERE/"run.py")
    value=importlib.util.module_from_spec(spec);sys.modules[spec.name]=value;spec.loader.exec_module(value)
    return value


def main():
    rt=module();plan=read(RAW/"PLAN.json");result=read(OUT/"RESULTS.json")
    need(result["status"]=="pass" and not result["errors"] and result["plan"]==pin(RAW/"PLAN.json"),"valid_original_run")
    for ref in (*plan["fixed"].values(),*plan["sources"].values(),*plan["reused_044_tooling"].values()):
        need(pin(ref["path"])==ref,"frozen_sources")
    geometry=read(plan["fixed"]["FINAL_GEOMETRY.json"]["path"])
    truth=read(plan["fixed"]["FINAL_INDEPENDENT_TRUTH.json"]["path"])
    captures={label:read(OUT/(label+".json")) for label in ("SAVED_RAM","BEFORE","AFTER")}
    need(rt.binary(captures["BEFORE"])==rt.binary(captures["AFTER"]),"readonly_full_scene")
    need(result["writer_pid"]!=result["reader_pid"] and pin(result["saved_artifact"]["path"])==result["saved_artifact"],"independent_saved_artifact")
    for label,value in captures.items():
        need(value["source"]["main_thread"] and not value["source"]["background"] and value["source"]["scale_length"]==1.0,
             "actual_ordinary_native_source")
        need(value["source"]["pid"]==result["writer_pid" if label=="SAVED_RAM" else "reader_pid"],"capture_PID")
        meshes={row["name"]:row for row in value["objects"] if row["type"]=="MESH"}
        need(set(meshes)=={"Pressure_Inner","Pressure_Outer"},"original_names")
        for key in ("left","right"):
            source=geometry[key];row=meshes[source["name"]]
            need(rt.binary(row["matrix_world"])==rt.binary([[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]),"identity_matrix")
            for mode in ("native","evaluated"):
                mesh=row[mode]
                need(rt.binary(mesh["vertices_local"])==rt.binary(source["vertices_world"])==rt.binary(mesh["vertices_world_m"]),"coordinate_bytes")
                need(mesh["triangles"]==source["faces"]==mesh["native_polygon_vertices"] and
                     mesh["triangle_polygons"]==mesh["source_triangle_rows"]==list(range(129)),"original_native_face_rows")
    profiles={}
    for arm in "ABC":
        folder=OUT/arm;cell=read(folder/"CELL.json")
        need(cell==result["cells"][arm] and cell["valid"] and not cell["errors"],"original_cell")
        rt.validate(folder,cell,plan)
        close=read(folder/"client/CLOSE.json")
        need(close==cell["product_close"] and close["method"]=="eof" and close["exit_code"]==0,"original_EOF")
        need(cell["business_ns"]==cell["body_decoded_ns"]-cell["answer"]["timing"]["started_ns"]>0,"actual_reply_clock")
        work=cell["work"];surface=work["surface_work"]
        need(work["surface_pair_count"]==1 and work["closed_solid_pair_count"]==0 and
             work["surface_pair_cache_hit"] is False and work["result_cache_hit"] is False,"full_new_pair")
        need(surface["shared_trees"] is False and surface["tree_builds"]==2,"ordinary_surface_path")
        if arm=="A":
            need(cell["distance_known"] and cell["surface_fact"]["status"]=="measured" and
                 cell["distance_m"]==truth["distance_m"],"A_exact_known")
            witness=cell["surface_fact"]["value"]["nearest_witness"]
            need(rt.binary(witness["a"])==rt.binary(truth["point_a_world"]) and
                 rt.binary(witness["b"])==rt.binary(truth["point_b_world"]),"unique_exact_points")
            need(surface["narrow_phase_pairs"]+surface["witness_projection_pruned_pairs"]==16641,"A_actual_pair_coverage")
        else:
            sf=cell["surface_fact"]
            need(not cell["distance_known"] and sf["status"]=="unknown" and sf["reason"]=="surface_pair_budget" and
                 "distance_m" not in sf.get("value",{}) and "nearest_witness" not in sf.get("value",{}),"valid_unknown_no_partial_distance")
            need(surface["narrow_phase_pairs"]==surface["witness_projection_completed_exact"]==16384 and
                 surface["triangle_pairs"]==surface["leaf_pair_visits"]==16385 and surface["work_units"]<1179648,
                 "original_narrow_limit_not_total_work")
        profiles[arm]=dict(known=cell["distance_known"],distance_m=cell["distance_m"],reason=cell.get("unknown_reason"),
            public_status=cell["public_status"],surface_fact=cell["surface_fact"],surface_work=surface,
            work=work,business_ms=cell["business_ns"]/1e6,client_start_through_EOF_and_archive_ms=cell["through_EOF_ns"]/1e6,
            actual_product_CPU_read_window_s=cell["product_after"]["cpu_s"]-cell["product_before"]["cpu_s"],
            observed_product_lifetime_peak_working_set_bytes=cell["product_after"]["peak_working_set_bytes"],
            request=cell["request"],response=cell["response"],cell=pin(folder/"CELL.json"))
    for name in ("writer_close","reader_close"):
        close=result[name]
        need(close["status"]=="pass" and close["process_reaped"] and close["exit_code"]==0 and close["forced"] is None and
             not close["released_port"]["owned_listener"] and close["source_unchanged"] and close["owned_copy_unchanged"],"normal_GUI_cleanup")
    pid=read(RAW/"POST_PROCESS_CHECK.json")
    need(pid["all_expected_pids_absent"] and len(pid["expected_owned_pids"])==8 and not pid["currently_existing_expected_ids"],"owned_PID_absence")
    comparisons=result["coverage_comparisons"]
    need(comparisons["A_to_B"]["newly_unknown"] and comparisons["A_to_C"]["newly_unknown"] and not
         comparisons["B_to_C"]["newly_unknown"],"all_three_coverage_comparisons")
    b,c=profiles["B"]["surface_work"],profiles["C"]["surface_work"]
    differences={key:{"B":b.get(key),"C":c.get(key)} for key in sorted(set(b)|set(c)) if b.get(key)!=c.get(key)}
    prior=HERE.parents[1]/"m6_r3_fresh_budget_044/live_pressure/run.py"
    delta="".join(difflib.unified_diff(prior.read_text(encoding="utf-8").splitlines(True),(HERE/"run.py").read_text(encoding="utf-8").splitlines(True),
                                     fromfile="044/live_pressure/run.py",tofile="045/boundary/run.py"))
    with (HERE/"CLIENT_ADAPTATION.patch").open("x",encoding="utf-8",newline="\n") as stream:stream.write(delta)
    summary=dict(schema="m6-045-boundary-closeout-v1",status="pass",status_scope="Verified evidence and lifecycle; coverage is reported separately, not replacement approval",
        original_result=pin(OUT/"RESULTS.json"),plan=pin(RAW/"PLAN.json"),profiles=profiles,coverage_comparisons=comparisons,
        coverage_verdict="032 answers exactly; both original R3 and 043 candidate add an ordinary-query unknown at the unchanged narrow-phase limit",
        independent_canonical_native_face_pair=truth["canonical_native_face_pair"],
        native_index_scope="Independent unique witness and complete original source mapping; the ordinary task fact does not expose native row IDs",
        possible_triangle_pairs=16641,original_limits=plan["original_limits"],B_C_surface_work_differences=differences,
        saved_private_artifact=result["saved_artifact"],writer_pid=result["writer_pid"],reader_pid=result["reader_pid"],
        PID_absence=pin(RAW/"POST_PROCESS_CHECK.json"),full_native_and_QA_lifecycle_s=result["full_lifecycle_wall_ns"]/1e9,
        counts=dict(ordinary_GUI_launches=2,installed_product_services=3,ordinary_first_task_calls=3,saved_private_assets=1,
                    business_retries=0,standalone_diagnostics=0,new_densities=0,new_calibrations=0,model_turns=0),
        retained_125_positive=pin(Path("D:/HumanEye/runs/M6-044-R3-FRESH-BUDGET/live_pressure/CLOSEOUT.json")),
        analytical_source=pin(Path(__file__)),client_adaptation=pin(HERE/"CLIENT_ADAPTATION.patch"),
        resource_scope="Single descriptive boundary observations. CPU sampled after initialization through reply; individual process-lifetime peaks only. The inherited client close envelope includes original line-packet archive and is not an OS process-lifetime measurement. No simultaneous tree memory peak or total startup/exit/controller CPU claimed.")
    closeout=save(RAW/"CLOSEOUT.json",summary)
    print(save(HERE/"RESULTS.json",{key:summary[key] for key in ("schema","status","status_scope","original_result","plan","coverage_comparisons",
        "coverage_verdict","possible_triangle_pairs","original_limits","saved_private_artifact","PID_absence","full_native_and_QA_lifecycle_s","counts","resource_scope")}|{"raw_closeout":closeout}))
    raw_files=[pin(path) for path in sorted(RAW.rglob("*")) if path.is_file() and path.name!="INDEX.json"]
    sources=[pin(path) for path in sorted(HERE.rglob("*")) if path.is_file() and path.name!="INDEX.json"]
    index=save(RAW/"INDEX.json",dict(schema="m6-045-boundary-raw-index-v1",files=raw_files,source_files=sources,
        raw_file_count=len(raw_files),raw_bytes=sum(row["bytes"] for row in raw_files),active_owned_processes=0))
    print(save(HERE/"INDEX.json",dict(schema="m6-045-boundary-delivery-v1",status="complete",raw_index=index,source_files=sources,
        raw_file_count=len(raw_files),raw_bytes=sum(row["bytes"] for row in raw_files),active_owned_processes=0)))


if __name__=="__main__":main()
