"""Independently match the saved, reopened pressure scene to the frozen case."""
from fractions import Fraction
from pathlib import Path
import argparse
import json
import math

from recompute import ROOT, LIMITS, check, dump, pin, read, rounded_rational_points, sums


def verify(folder):
    result=read(folder/"RESULTS.json")
    assert result["status"]=="pass" and result["all_known"] and not result["B_success_C_unknown"]
    assert result["actual_saved_geometry_verified"] and result["scene_preserved"]
    assert result["writer_pid"]!=result["reader_pid"]
    assert result["full_lifecycle_wall_ns"]==result["ended_ns"]-result["started_ns"]
    for phase in ("writer","reader"):
        close=result[phase+"_close"]
        assert close["pid"]==result[phase+"_pid"] and close["process_reaped"] and close["exit_code"]==0
        assert not close["released_port"]["any_listener"] and close["owned_copy_unchanged"]
    plan=read(check(result["plan"]))
    assert plan["cycle_id"]==ROOT.name
    artifact=read(folder/"SAVED_ARTIFACT.json")
    assert artifact["asset"]==result["saved_artifact"]
    check(artifact["asset"])
    ready=read(ROOT/"pressure/FINAL_FREEZE.json")
    assert ready["geometry"]==artifact["geometry"]
    shape=read(check(ready["geometry"]))
    truth=read(check(ready["exact_truth"]))
    order=[shape["left"]["name"],shape["right"]["name"]]
    by_name={shape[k]["name"]:shape[k] for k in ("left","right")}
    before,after=map(lambda n:read(folder/(n+".json")),("BEFORE","AFTER"))
    assert before==after
    for label,phase in (("SAVED_RAM","writer"),("BEFORE","reader"),("AFTER","reader")):
        sample=read(folder/(label+".json"))
        src=sample["source"]
        assert src["pid"]==result[phase+"_pid"] and not src["background"] and src["main_thread"]
        assert (src["frame"],src["subframe"],src["scale_length"])==(1,0,1)
        if phase=="reader":
            assert pin(src["asset"])["sha256"]==artifact["asset"]["sha256"]
        assert sorted(x["name"] for x in sample["objects"])==sorted(order)
        for obj in sample["objects"]:
            wanted=by_name[obj["name"]]
            got=obj["evaluated"]
            assert obj["visible"] and not obj["modifier_types"] and obj["parent"] is None
            assert obj["matrix_world"]==[[float(i==j) for j in range(4)] for i in range(4)]
            assert got["vertices_world_m"]==got["vertices_local"]==wanted["vertices_world"]
            assert got["triangles"]==got["native_polygon_vertices"]==wanted["faces"]
            assert got["source_triangle_rows"]==list(range(len(wanted["faces"])))
    outcomes={}
    native=[]
    for arm in "ABC":
        cell=read(folder/arm/"CELL.json")
        base=read(ROOT/"pressure/final_plain_001"/arm/"RESULT.json")
        sent=read(check(cell["request"]))
        check(cell["response"])
        query=sent["params"]["arguments"]["query"]
        assert [obj["name"] for obj in query["objects"]]==order
        assert query["requested_facts"]==["surface_proximity"]
        assert cell["valid"] and not cell["entry_rejected"] and cell["distance_known"]
        trace=cell["trace"]
        assert trace["pid"]==cell["product_pid"] and cell["host_pid"]==result["reader_pid"]
        assert trace["annotations"]["build_id"]=="sha256:"+base["identity"]["source_sha256"]
        assert trace["annotations"]["delivery"]=="stdio_write_completed"
        assert trace["annotations"]["mcp_native_image_block_count"]==0
        assert cell["product_close"]["method"]=="eof" and cell["product_close"]["exit_code"]==0
        assert cell["independent_canonical_native_face_pair"]==truth["canonical_native_face_pair"]
        f=cell["surface_fact"]
        assert f["status"]=="measured" and cell["distance_m"]==math.sqrt(float(Fraction(truth["distance_squared_exact"])))
        value=f["value"]["nearest_witness"]
        assert rounded_rational_points(truth["unique_witness_world_exact"])==[value["a"],value["b"]]
        work=cell["work"]
        assert work["surface_pair_count"]==1 and work["closed_solid_pair_count"]==0
        assert not work["surface_pair_cache_hit"] and not work["result_cache_hit"]
        s=work["surface_work"]
        native.append(s)
        plain=base["work"].copy()
        checks=plain.pop("witness_triangle_checks")
        assert checks==2
        plain["work_units"]-=checks
        assert plain==s
        assert cell["body_decoded_ns"]-cell["answer"]["timing"]["started_ns"]==cell["business_ns"]
        outcomes[arm]={"source":base["identity"],"work":sums(s),
                       "work_fraction":str(Fraction(s["work_units"],LIMITS["work_units"])),
                       "narrow_fraction":str(Fraction(s["narrow_phase_pairs"],LIMITS["narrow_phase_pairs"])),
                       "known":True,"business_ns":cell["business_ns"],"through_EOF_ns":cell["through_EOF_ns"]}
    assert sums(native[1])==sums(native[2])
    b,c=native[1:]
    changes={k:[b.get(k),c.get(k)] for k in sorted(set(b)|set(c)) if b.get(k)!=c.get(k)}
    assert changes and all(k.startswith('witness_projection_') for k in changes)
    return {"status":"pass","scope":"Blender-saved synthetic geometry reopened in an independent ordinary GUI",
            "frozen_input":pin(ROOT/"pressure/FINAL_FREEZE.json"),"artifact":artifact["asset"],
            "reader_receipt":pin(folder/"RESULTS.json"),"cases":outcomes,
            "actual_setup_to_cleanup_wall_ns":result["full_lifecycle_wall_ns"],
            "kernel_vs_ordinary_work_delta":{"all_arms":2,"ordinary_witness_fields":"exact points; source row independently bound",
                                             "public_kernel_extra":"explicit native witness triangle membership checks"},
            "optional_projection_counter_differences_B_C":changes,
            "unknown_regression_observed":False,"reopened_source_geometry_verified":True}


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("folder",type=Path)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    print(dump(args.output,verify(args.folder)))
