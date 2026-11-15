"""Verify exact no-change table deduplication against frozen v1 actual results."""

import ast
import copy
import json
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from common import identity,read,write


def function(source, filename):
    tree=ast.parse(source,filename=str(filename))
    node=next(row for row in tree.body if isinstance(row,ast.FunctionDef) and row.name=="short_quality")
    namespace={"__file__":str(HERE/"session_api.py"),"__name__":"_frozen_quality_projection"}
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(filename),"exec"),namespace)
    return namespace["short_quality"],tree


def serialized(value):
    return json.dumps(value,ensure_ascii=True,allow_nan=False)


def expanded(value):
    result=copy.deepcopy(value)
    for row in result["contours"]["definitions"].values():
        if row.pop("before_equals_after") is not True:
            raise AssertionError("explicit_equal_marker_required")
        row["before"]=copy.deepcopy(row["after"])
    return result


def main():
    started,cpu=time.perf_counter(),time.process_time()
    freeze=read("TOOL_FREEZE.json")
    row=next(value for value in freeze["files"] if value["path"]=="session_api.py")
    frozen_api_sha256=row["sha256"]
    old_path=HERE/row["archived"]["path"]
    if identity(old_path)["sha256"]!=row["sha256"]:
        raise AssertionError("frozen_API_archive_changed")
    old,old_tree=function(old_path.read_text(encoding="utf8"),old_path)
    new,new_tree=function((HERE/"session_api.py").read_text(encoding="utf8"),HERE/"session_api.py")
    old_other_nodes=[ast.dump(node,include_attributes=False) for node in old_tree.body if not(isinstance(node,ast.FunctionDef) and node.name=="short_quality")]
    new_other_nodes=[ast.dump(node,include_attributes=False) for node in new_tree.body if not(isinstance(node,ast.FunctionDef) and node.name=="short_quality")]
    checks={"only_short_quality_AST_changed":old_other_nodes==new_other_nodes}
    output=HERE/"private/optimization_preflight"
    output.mkdir(parents=True,exist_ok=False)
    results=[]
    inputs=[]
    actual_noedit=[]
    for route in ("native","facts"):
        directory=HERE/"private/sessions"/("v1_forearm_"+route)
        paths=sorted((directory/"readbacks").glob("*/QUALITY.json"))
        if len(paths)!=1:
            raise ValueError("exact_one_actual_v1_readback_expected")
        path=paths[0]
        inputs.append(identity(path))
        raw=read(path)
        actual_noedit.append(raw)
        original=copy.deepcopy(raw)
        before,after=old(raw),new(raw)
        for name in ("primary","alternative"):
            first=before["contours"]["definitions"][name]
            second=after["contours"]["definitions"][name]
            checks[route+"_"+name+"_old_tables_exact_equal"]=first["before"]==first["after"]
            checks[route+"_"+name+"_current_complete_table_exact"]=second["after"]==first["after"]
            checks[route+"_"+name+"_all_errors_MAE_max_exact"]=second["after"]["errors"]==first["after"]["errors"]
            checks[route+"_"+name+"_improvements_preserved_false"]=second["improvements"]==first["improvements"] and second["improvement_established"] is False
            checks[route+"_"+name+"_equality_marker"]=second["before_equals_after"] is True and "before" not in second
        checks[route+"_all_technical_fields_unchanged"]=all(after[key]==before[key] for key in before if key!="contours")
        checks[route+"_expanded_response_deep_equals_v1"]=expanded(after)==before
        checks[route+"_raw_input_not_mutated"]=raw==original
        before_bytes,after_bytes=len(serialized(before).encode()),len(serialized(after).encode())
        bridge=HERE/"private/consumers/v1/forearm"/route/"bridge"
        tool_path=next(folder for folder in bridge.glob("tool_*") if read(folder/"REQUEST.json")["name"]=="save_readback")
        complete=read(tool_path/"COMPLETE_RESULT.json")
        complete_after=copy.deepcopy(complete)
        complete_after["quality"]=after
        original_response=read(tool_path/"RESPONSE.json")["content"][0]["text"]
        checks[route+"_actual_tool_response_reserialization_exact"]=serialized(complete)==original_response
        tool_before=len(original_response.encode())
        tool_after=len(serialized(complete_after).encode())
        checks[route+"_response_bytes_decreased"]=after_bytes<before_bytes and tool_after<tool_before
        write(output/(route+"_SHORT_BEFORE.json"),before)
        write(output/(route+"_SHORT_AFTER.json"),after)
        results.append(dict(route=route,actual_quality=identity(path),actual_response=identity(tool_path/"RESPONSE.json"),
            quality_before_bytes=before_bytes,quality_after_bytes=after_bytes,actual_tool_before_bytes=tool_before,projected_tool_after_bytes=tool_after,
            tool_bytes_saved=tool_before-tool_after))
    probe_path=HERE/"private/sessions/real_api_preflight_02_forearm/versions/001/independent00/QUALITY.json"
    probe=read(probe_path)
    inputs.append(identity(probe_path))
    checks["actual_tiny_edit_is_nonzero"]=probe["displacement"]["changed_vertices"]>0
    checks["actual_nonzero_probe_full_response_deep_equal"]=new(probe)==old(probe) and serialized(new(probe))==serialized(old(probe))
    fallback={}
    unequal=copy.deepcopy(actual_noedit[0])
    unequal["contours"]["definitions"]["primary"]["after"]["stations"][0]["model"]["outer"]+=1e-9
    fallback["unequal_primary_table"]=unequal
    changed=copy.deepcopy(actual_noedit[0]);changed["displacement"]["changed_vertices"]=1
    fallback["nonzero_with_equal_projected_tables"]=changed
    unknown=copy.deepcopy(actual_noedit[0]);unknown["contours"]["status"]="unknown"
    fallback["unknown_contour_status"]=unknown
    absent=copy.deepcopy(actual_noedit[0]);absent.pop("contours")
    fallback["missing_contours"]=absent
    null=copy.deepcopy(actual_noedit[0]);null["contours"]=None
    fallback["null_contours"]=null
    missing=copy.deepcopy(actual_noedit[0]);missing["contours"]["definitions"].pop("alternative")
    fallback["incomplete_two_definitions"]=missing
    missing_before=copy.deepcopy(actual_noedit[0]);missing_before["contours"]["definitions"]["alternative"].pop("before")
    fallback["unknown_before_table"]=missing_before
    for name,raw in fallback.items():
        snapshot=copy.deepcopy(raw)
        checks[name+"_fallback_exact"]=new(raw)==old(raw) and serialized(new(raw))==serialized(old(raw))
        checks[name+"_input_unchanged"]=raw==snapshot
    for row in inputs:
        checks["actual_raw_file_unchanged_"+row["path"]]=identity(HERE/row["path"])["sha256"]==row["sha256"]
    binding=read("OPTIMIZATION_BINDING.json")
    for row in binding["initial_results"]:
        for field in ("consumer","session"):
            expected=row[field]
            checks["bound_v1_"+row["route"]+"_"+field+"_bytes_unchanged"]=identity(HERE/expected["path"])["sha256"]==expected["sha256"]
    checks["frozen_v1_API_archive_unchanged"]=identity(old_path)["sha256"]==frozen_api_sha256
    measured_started,measured_cpu=time.perf_counter(),time.process_time()
    repeats=100
    for _ in range(repeats):
        for raw in actual_noedit:
            new(raw)
    timing=dict(repeats_per_actual_result=repeats,results_per_repeat=2,wall_s=time.perf_counter()-measured_started,CPU_s=time.process_time()-measured_cpu,
        scope="Function-only warm local projection, excludes JSON serialization and model consumption")
    total_before=sum(row["actual_tool_before_bytes"] for row in results)
    total_after=sum(row["projected_tool_after_bytes"] for row in results)
    summary=dict(status="pass" if all(checks.values()) else "fail",checks=checks,checks_total=len(checks),actual_v1_results=results,
        actual_v1_readback_response_bytes=total_before,projected_same_response_bytes=total_after,bytes_saved=total_before-total_after,
        reduction_percent=100*(total_before-total_after)/total_before,
        actual_nonzero_probe=identity(probe_path),source_before=identity(old_path),source_after=identity(HERE/"session_api.py"),
        wall_s=time.perf_counter()-started,parent_CPU_s=time.process_time()-cpu,microtiming=timing,
        Pro_sessions=0,Blender_calls=0,model_or_geometry_changes=0,
        interpretation="Both definitions retain one complete exact current table, errors and improvement flags. Explicit before_equals_after reconstructs the original response exactly. Changed or uncertain data retain v1 schema. Full raw QUALITY files are untouched.")
    write("OPTIMIZATION_PREFLIGHT.json",summary)
    print(summary["status"],len(checks),total_before,total_after,summary["reduction_percent"],flush=True)
    if not all(checks.values()):
        raise SystemExit(1)


if __name__=="__main__":
    main()
