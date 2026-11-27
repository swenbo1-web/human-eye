"""047 archived G60 accounting only: no product, Blender or numerical kernel."""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
from statistics import median
import struct
import sys

HERE=Path(__file__).resolve().parent
RAW=Path("D:/HumanEye/runs/M6-047-R3-COVERAGE-DOMAIN/g60")
FREEZE=RAW/"ARCHIVE_FREEZE.json"
RUN_FREEZE=RAW/"RECOMPUTE_FREEZE.json"


def read(path):return json.loads(Path(path).read_bytes())


def pin(path):
    path=Path(path).resolve(strict=True)
    with path.open("rb") as stream:digest=hashlib.file_digest(stream,"sha256").hexdigest()
    return dict(path=str(path),bytes=path.stat().st_size,sha256=digest)


def need(value,reason):
    if not value:raise ValueError("047_g60_"+reason)


def save(path,value):
    path=Path(path).resolve();need(path.is_relative_to(RAW.resolve()),"write_scope")
    with path.open("x",encoding="utf-8",newline="\n") as stream:
        json.dump(value,stream,indent=2,ensure_ascii=False,allow_nan=False);stream.write("\n")
    return pin(path)


def binary(value):
    if type(value) is float:return {"binary64":value.hex()}
    if isinstance(value,list):return [binary(x) for x in value]
    if isinstance(value,dict):return {k:binary(v) for k,v in value.items()}
    return value


def check(ref):
    need(pin(ref["path"])==ref,"changed:"+ref["path"])
    return Path(ref["path"])


def module(path):
    spec=importlib.util.spec_from_file_location("_047_existing_045_readonly_verifier",path)
    value=importlib.util.module_from_spec(spec);sys.modules[spec.name]=value;spec.loader.exec_module(value)
    return value


def prepare():
    frozen=read(FREEZE)
    need(frozen["status"]=="frozen_before_recompute","prior_sample_freeze")
    plan=dict(schema="m6-047-g60-recompute-freeze-v1",status="frozen_before_recompute",
        frozen_utc=datetime.now(timezone.utc).isoformat(),sample_freeze=pin(FREEZE),
        script=pin(Path(__file__)),
        operations=["hash/recheck archived bytes", "execute old stdlib-only g60_verify.audit on the original raw result",
                    "recover original world-f64 arrays from frozen local-f64/matrices using the original explicit operation order, verify every hash against six actual snapshots",
                    "read original public/audit pair ledgers and source-key representations", "compute historical descriptive statistics"],
        geometry_recovery="Original fixture only, no generated mesh or solver. Ordered local/face/world byte hashes must match every native snapshot.",
        timing_scope="Per-query and complete historical phases only. Per-pair compute time and nearest cache-key digest remain unmeasured.",
        frozen_key_correction="Both nearest and scan retain_exact_rank=True. They differ in ordered geometry where applicable and ordinary read/full-mesh versus typed scan-resource dependency representation, not the rank flag.",
        Blender=0,product=0,kernel=0,timing_runs=0,new_assets=0)
    print(save(RUN_FREEZE,plan))


def array_sha(values,code):
    return hashlib.sha256(b"".join(struct.pack("<"+code,v) for row in values for v in row)).hexdigest()


def recover_geometry(plan,samples):
    fixture=read(check(plan["snapshot_fixture"]))
    source_rows=fixture["objects"]
    objects={}
    for row in source_rows:
        name=row["name"];local=row["vertices_local"];matrix=row["matrix_world"];faces=row["triangles"]
        scale=plan["scale"]
        world=[[(((v[0]*matrix[a][0]+v[1]*matrix[a][1])+v[2]*matrix[a][2])+matrix[a][3])*scale
                for a in range(3)] for v in local]
        hashes=dict(local_sha256=array_sha(local,"d"),world_sha256=array_sha(world,"d"),triangles_sha256=array_sha(faces,"i"))
        for sample in samples:
            snap=read(sample["before"]["path"])["geometry"][name]
            need(all(hashes[key]==snap[key] for key in hashes) and binary(matrix)==binary(snap["matrix"]) and
                 len(local)==snap["vertices"] and len(faces)==snap["triangles"],"actual_native_array_hash:"+name)
        objects[name]=dict(vertices_world_m=world,vertices_local=local,triangles=faces,matrix_world=matrix,
            source_triangle_rows=list(range(len(faces))),native_polygon_ids=None,
            native_polygon_scope="Not present in the archived native hash snapshot/fixture; no mapping invented",
            hashes=hashes,vertices=len(local),triangle_count=len(faces))
    return dict(schema="m6-047-archived-g60-geometry-recovery-v1",source_fixture=plan["snapshot_fixture"],
        source_asset=plan["asset"],frame=plan["frame"],subframe=plan["subframe"],scale_length=plan["scale"],
        objects=objects,matched_actual_ordinary_snapshots=[sample["before"] for sample in samples],
        arithmetic="(((x*m0+y*m1)+z*m2)+translation)*scale, original binary64 order; all ordered byte hashes checked",
        kernel_calls=0,Blender_calls=0,new_assets=0)


def endpoint(oid,names,snapshot):
    name=names[oid];row=snapshot["geometry"][name]
    return dict(object_id=oid,name=name,instance=row["instance"],vertices=row["vertices"],faces=row["triangles"],
                world_f64_sha256=row["world_sha256"],triangles_i32_sha256=row["triangles_sha256"],
                local_f64_sha256=row["local_sha256"],matrix_world=row["matrix"])


def numeric_summary(rows,key):
    values=[row[key] for row in rows if type(row.get(key)) in (int,float)]
    return dict(reported_count=len(values),unmeasured_count=len(rows)-len(values),
                sum=sum(values) if values else None,min=min(values) if values else None,
                max=max(values) if values else None,median=median(values) if values else None)


def source_call_options(frozen):
    answer={}
    for arm,paths in frozen["call_path_sources"].items():
        result={}
        for label,file_name,fn_name in (("nearest","task_query.py","surface_nearest_result"),
                                       ("scan","surface_scan.py","surface_scan_result")):
            tree=ast.parse(check(paths[file_name]).read_text(encoding="utf-8"))
            functions=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name==fn_name]
            need(len(functions)==1,"static_callsite_function")
            calls=[node for node in ast.walk(functions[0]) if isinstance(node,ast.Call) and
                   isinstance(node.func,ast.Name) and node.func.id=="_surface_pair_measurement"]
            need(len(calls)==1,"single_static_measurement_callsite")
            keywords={kw.arg:ast.unparse(kw.value) for kw in calls[0].keywords}
            need(keywords.get("retain_exact_rank")=="True" and
                 keywords.get("_surface_scan")==("True" if label=="scan" else None),"exact_rank_and_scan_source")
            result[label]=dict(source=paths[file_name],line=calls[0].lineno,keywords=keywords)
        result["cache_key"]={"source":paths["scene_cache.py"],
            "ordered":True,"includes":["algorithm_version","parameters","focal representation","reference representation"],
            "nearest_representation":"ordinary read_resource_version when bound, otherwise full mesh metadata",
            "scan_representation":"surface_scan_resource_dependency when the logged dependency binding is used",
            "algorithm_rank_flag_difference":False,
            "nearest_actual_digest":"unmeasured in this archive","scan_actual_digest":"logged per original pair"}
        answer[arm]=result
    return answer


def run():
    run_plan=read(RUN_FREEZE);need(run_plan["status"]=="frozen_before_recompute","run_freeze")
    check(run_plan["script"]);frozen=read(check(run_plan["sample_freeze"]))
    for ref in frozen["archive_files"]:check(ref)
    for ref in frozen["source_files"].values():check(ref)
    old=Path(frozen["archive_root"]);plan=read(old/"g60/PLAN.json")
    verifier_path=next(Path(ref["path"]) for ref in frozen["source_files"].values() if Path(ref["path"]).name=="g60_verify.py")
    verifier=module(verifier_path)
    verified=verifier.audit(old/"g60/main_001/RESULTS.json")
    need(verified["status"]=="pass" and verified["actual_cells"]==18 and verified["actual_business_reads"]==54,"original_045_audit")
    verified_ref=save(RAW/"VERIFY_045_RECOMPUTED.json",verified)
    prior_verified=read(old/"g60/verification/ATTEMPT_002.json")
    for key in ("business","process_lifetime","workflow","client_full","phase_comparisons"):
        need(verified[key]==prior_verified[key],"archived_phase_recomputation:"+key)
    geometry=recover_geometry(plan,frozen["samples"])
    geometry_ref=save(RAW/"NATIVE_GEOMETRY.json",geometry)
    requests=[];calls=[];duplicates=[];cells=[]
    for sample in frozen["samples"]:
        group=read(sample["group"]["path"]);snapshot=read(sample["before"]["path"])
        mesh_names={name for name,row in snapshot["geometry"].items() if row["type"]=="MESH"}
        for arm in "ABC":
            cell=read(sample["cells"][arm]["cell"]["path"])
            overview=next(row for row in cell["rows"] if row["step"]=="overview")
            names={obj["object_id"]:obj["name"] for obj in overview["result"]["objects"]}
            need(set(names.values())==mesh_names,"native_public_inventory")
            per_cell={};mode_rows={row["step"]:row for row in cell["rows"]}
            for row in cell["rows"]:
                step=row["step"];body=row["result"];work=row["observe"].get("task_work")
                coverage=body.get("coverage");spans=row["telemetry"]["spans"]
                host=[s["duration_ns"] for s in spans if s["name"]=="host.capture"]
                reducer=[s["duration_ns"] for s in spans if s["name"]=="observation.surface_"+step]
                request_id=f"G{sample['group_index']:02d}/{arm}/{step}"
                report=dict(id=request_id,group=sample["group_index"],order=sample["order"],arm=arm,step=step,
                    host_pid=group["host_pid"],product_pid=cell["product_pid"],body_status=body.get("status"),
                    coverage=coverage,result_cache_hit=work.get("result_cache_hit") if isinstance(work,dict) else None,
                    task_work_reported=isinstance(work,dict),published_overview_exact_pair_count=body.get("query_result",{}).get("exact_pair_count") if step=="overview" else None,
                    possible_object_pairs=(len(mesh_names)-1 if step=="nearest" else len(mesh_names)*(len(mesh_names)-1)//2 if step=="scan" else None),
                    kernel_calls=work.get("kernel_calls") if isinstance(work,dict) else None,
                    pair_calls=work.get("pair_calls") if isinstance(work,dict) else None,
                    pair_cache_hits=work.get("cache_hits") if isinstance(work,dict) else None,
                    continuation_hits=work.get("continuation_hits") if isinstance(work,dict) else None,
                    strict_skips=(coverage.get("strictly_excluded") if step=="nearest" else coverage.get("bound_excluded") if step=="scan" else None),
                    unknown=(coverage.get("unresolved") if step=="nearest" else coverage.get("unknown") if step=="scan" else None),
                    deferred=coverage.get("deferred") if step=="scan" else None,
                    complete_body_ns=row["body_decoded_ns"]-row["timing"]["started_ns"],
                    stdio_rpc_ns=row["timing"]["client_full_ns"],trace_ns=row["telemetry"]["duration_ns"],
                    host_capture_span_ns=host[0] if len(host)==1 else None,
                    reducer_inclusive_span_ns=reducer[0] if len(reducer)==1 else None,
                    reducer_timing_scope="includes validation/normalization/cache/measurement, not per-pair or pure-kernel time" if reducer else None,
                    request=row["request"],response=row["response"],cell=sample["cells"][arm]["cell"])
                requests.append(report)
                if not isinstance(work,dict):
                    need(step=="overview","missing_measurement_work")
                    continue
                entries=[]
                dispositions={tuple(item["object_ids"]):item for item in work.get("dispositions",[])}
                for key,pair_work in work["pairs"].items():
                    ids=[body["focal"]["id"],key] if step=="nearest" else json.loads(key)
                    ends=[endpoint(oid,names,snapshot) for oid in ids]
                    native=pair_work.get("surface_work")
                    disposition=dispositions.get(tuple(ids))
                    entry=dict(id=request_id+"/"+"|".join(ids),request_id=request_id,group=sample["group_index"],arm=arm,step=step,
                        ordered_object_ids=ids,ordered_names=[item["name"] for item in ends],source_endpoints=ends,
                        potential_native_triangle_pairs=ends[0]["faces"]*ends[1]["faces"],
                        actual_compute_calls=pair_work.get("surface_pair_count"),pair_cache_hit=pair_work.get("surface_pair_cache_hit"),
                        native_narrow_phase_pairs=native.get("narrow_phase_pairs") if isinstance(native,dict) else None,
                        work_units=native.get("work_units") if isinstance(native,dict) else None,
                        prepared_triangles=native.get("prepared_triangles") if isinstance(native,dict) else None,
                        validated_faces=native.get("validated_faces") if isinstance(native,dict) else None,
                        tree_builds=native.get("tree_builds") if isinstance(native,dict) else None,
                        shared_trees=native.get("shared_trees") if isinstance(native,dict) else None,
                        surface_work=native,scan_disposition=disposition,
                        cache_key_digest=pair_work.get("surface_dependency_key") if step=="scan" else None,
                        cache_key_digest_observed=step=="scan" and pair_work.get("surface_dependency_key") is not None,
                        scan_dependency_used=pair_work.get("surface_dependency_used") if step=="scan" else None,
                        scan_dependency_cache_hit=pair_work.get("surface_dependency_cache_hit") if step=="scan" else None,
                        scan_dependency_objects=pair_work.get("surface_dependency_objects") if step=="scan" else None,
                        per_call_compute_ns=None,per_call_timing_status="not_archived",
                        per_call_public_distance_m=disposition.get("distance_m") if isinstance(disposition,dict) else None,
                        independent_geometry_proof=geometry_ref,
                        individual_nonbest_nearest_value_scope="Not published individually; only the bound original complete coverage and work ledger are available" if step=="nearest" else None)
                    entries.append(entry);calls.append(entry)
                need(sum(e["actual_compute_calls"] for e in entries)==work["kernel_calls"] and len(entries)==work["pair_calls"],"actual_compute_ledger")
                need(sum(e["pair_cache_hit"] is True for e in entries)==work["cache_hits"],"pair_cache_ledger")
                report["pair_ledger_entries"]=len(entries)
                if step=="scan":
                    need(len(dispositions)==report["possible_object_pairs"] and
                         sum(item["status"]=="bound_excluded" for item in dispositions.values())==report["strict_skips"],"scan_complete_dispositions")
                    report["measurement_cache_before"]=work.get("measurement_cache_before")
                    report["measurement_cache_after"]=work.get("measurement_cache_after")
                per_cell[step]=entries
            scans={tuple(sorted(e["ordered_object_ids"])):e for e in per_cell["scan"]}
            for entry in per_cell["nearest"]:
                other=scans.get(tuple(sorted(entry["ordered_object_ids"])))
                need(other is not None,"overlapping_logical_pair_available")
                by_id=lambda e:{x["object_id"]:(x["world_f64_sha256"],x["triangles_i32_sha256"],x["vertices"],x["faces"],x["instance"]) for x in e["source_endpoints"]}
                same=by_id(entry)==by_id(other);need(same,"duplicate_geometry_binding")
                duplicates.append(dict(group=sample["group_index"],arm=arm,nearest_call=entry["id"],scan_call=other["id"],
                    unordered_names=sorted(entry["ordered_names"]),same_unordered_bound_source_geometry=same,
                    same_ordered_source_geometry=entry["ordered_object_ids"]==other["ordered_object_ids"],
                    nearest_actual_cache_key_digest=None,scan_actual_cache_key_digest=other["cache_key_digest"],same_logged_cache_key=None,
                    key_comparison="nearest digest unmeasured; source ordinary-mesh versus scan dependency preimages differ, both retain exact rank",
                    nearest_pair_cache_hit=entry["pair_cache_hit"],scan_pair_cache_hit=other["pair_cache_hit"],
                    nearest_scene_revision=mode_rows["nearest"]["result"]["binding"]["scene_revision"],
                    scan_scene_revision=mode_rows["scan"]["result"]["binding"]["scene_revision"],
                    native_geometry=geometry_ref))
            cells.append(dict(group=sample["group_index"],arm=arm,host_pid=group["host_pid"],
                business_ns=cell["business_ns"],workflow_ns=cell["workflow_ns"],
                os_survival_ns=cell["lifecycle"]["os_survival_ns"],
                actual_compute_calls=sum(e["actual_compute_calls"] for values in per_cell.values() for e in values),
                distinct_unordered_object_pairs=len({tuple(sorted(e["ordered_object_ids"])) for values in per_cell.values() for e in values}),
                source_cell=sample["cells"][arm]["cell"]))
    need(len(requests)==54 and len(cells)==18 and len({sample["group_index"] for sample in frozen["samples"]})==6,"complete_archival_denominator")
    paths=source_call_options(frozen)
    refs=dict(requests=save(RAW/"REQUESTS.json",requests),calls=save(RAW/"PAIR_CALLS.json",calls),
              duplicates=save(RAW/"CROSS_MODE_DUPLICATES.json",duplicates),source_paths=save(RAW/"CACHE_PATHS.json",paths),
              geometry=geometry_ref,original_verifier=verified_ref)
    summaries={}
    for arm in "ABC":
        reqs=[r for r in requests if r["arm"]==arm];per_calls=[r for r in calls if r["arm"]==arm];dups=[r for r in duplicates if r["arm"]==arm]
        by_step={}
        for step in ("overview","nearest","scan"):
            rows=[r for r in reqs if r["step"]==step]
            phase_calls=[r for r in per_calls if r["step"]==step]
            by_step[step]=dict(original_replies=len(rows),task_work_reported=sum(r["task_work_reported"] for r in rows),
                possible_object_pairs=numeric_summary(rows,"possible_object_pairs"),actual_compute_calls=numeric_summary(rows,"kernel_calls"),
                pair_calls=numeric_summary(rows,"pair_calls"),pair_cache_hits=numeric_summary(rows,"pair_cache_hits"),
                strict_skips=numeric_summary(rows,"strict_skips"),unknown=numeric_summary(rows,"unknown"),deferred=numeric_summary(rows,"deferred"),
                continuation_hits=numeric_summary(rows,"continuation_hits"),potential_native_triangle_pairs=numeric_summary(phase_calls,"potential_native_triangle_pairs"),
                native_narrow_phase_pairs=numeric_summary(phase_calls,"native_narrow_phase_pairs"),work_units=numeric_summary(phase_calls,"work_units"),
                prepared_triangles=numeric_summary(phase_calls,"prepared_triangles"),validated_faces=numeric_summary(phase_calls,"validated_faces"),
                tree_builds=numeric_summary(phase_calls,"tree_builds"),
                complete_body_ns=numeric_summary(rows,"complete_body_ns"),stdio_rpc_ns=numeric_summary(rows,"stdio_rpc_ns"),
                host_capture_span_ns=numeric_summary(rows,"host_capture_span_ns"),reducer_inclusive_span_ns=numeric_summary(rows,"reducer_inclusive_span_ns"),
                per_call_timing_measured=sum(r["per_call_compute_ns"] is not None for r in phase_calls))
        own_cells=[c for c in cells if c["arm"]==arm]
        summaries[arm]=dict(steps=by_step,services=len(own_cells),actual_compute_calls=sum(c["actual_compute_calls"] for c in own_cells),
            cross_nearest_scan_duplicate_geometry_calls=len(dups),same_order_duplicate_geometry=sum(d["same_ordered_source_geometry"] for d in dups),
            reversed_order_duplicate_geometry=sum(not d["same_ordered_source_geometry"] for d in dups),
            duplicate_logged_key_comparisons_measured=0,
            historical_business_median_ns=median(c["business_ns"] for c in own_cells),historical_process_survival_median_ns=median(c["os_survival_ns"] for c in own_cells),
            historical_client_complete_median_ns=median(c["workflow_ns"] for c in own_cells))
    observed_limits=dict(native_face_counts=sorted({e["faces"] for c in calls for e in c["source_endpoints"]}),
        per_call_triangle_product=sorted({c["potential_native_triangle_pairs"] for c in calls}),
        actual_narrow_phase_pairs=numeric_summary(calls,"native_narrow_phase_pairs"),work_units=numeric_summary(calls,"work_units"),
        narrow_limit=16384,work_limit=1179648,statement="Observed face products/counters only; a mathematical sufficient full-work/bit-width bound is outside this archival subtask.")
    summary=dict(schema="m6-047-g60-archive-recompute-v1",status="pass",sample_freeze=pin(FREEZE),recompute_freeze=pin(RUN_FREEZE),
        source=pin(Path(__file__)),references=refs,ordinary_hosts=6,services=18,original_replies=54,actual_compute_calls=sum(c["actual_compute_calls"] for c in cells),
        primary_comparison=["A","C"],retained_version="B",by_arm=summaries,observed_limits=observed_limits,
        historical_complete_phase_comparisons={k:verified[k] for k in ("business","process_lifetime","client_full","workflow","phase_comparisons")},
        historical_native_and_exit_proof=verified["closeout"],coverage_and_timing_gaps=[
            "Overview task_work is absent; no surface-kernel count is inferred from that absence.",
            "Nearest per-pair cache-key digests and all per-call compute timings were not archived.",
            "Scan dependency digests are real per-call records; equality with an unobserved nearest digest is unmeasured.",
            "Duplicate source geometry is independently hash-bound, but ordered pairs and mesh-key representation may differ.",
            "Nonbest nearest individual distances/witnesses were not published; their closure is the original complete coverage plus audit, not a new per-pair numerical oracle.",
            "World/native triangle rows are preserved; original polygon IDs are absent from the hash snapshots/fixture.",
            "Reducer timing includes preparation, lookup and common work. Historical complete-phase gains do not establish hybrid routing speed.",
            "This subtask proves archive/counter/source congruence, not a full-work, integer-width, publication or wall-clock guarantee."],
        newly_run=dict(Blender=0,product=0,kernel=0,timing_runs=0,new_assets=0,new_route=0))
    print(save(RAW/"RESULTS.json",summary))
    # Small repository receipt; complete ledgers and phases stay in the raw scope.
    report={key:summary[key] for key in ("schema","status","sample_freeze","recompute_freeze","ordinary_hosts","services","original_replies",
        "actual_compute_calls","primary_comparison","retained_version","by_arm","observed_limits","coverage_and_timing_gaps","newly_run")}
    report["raw_result"]=pin(RAW/"RESULTS.json")
    with (HERE/"RESULTS.json").open("x",encoding="utf-8",newline="\n") as stream:
        json.dump(report,stream,indent=2,ensure_ascii=False,allow_nan=False);stream.write("\n")
    print(pin(HERE/"RESULTS.json"))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("mode",choices=("prepare","run"))
    args=parser.parse_args();prepare() if args.mode=="prepare" else run()
