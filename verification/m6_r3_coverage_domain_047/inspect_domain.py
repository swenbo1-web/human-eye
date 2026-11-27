"""Reduce the frozen input and budget evidence without loading an installed solver."""
from __future__ import annotations

from fractions import Fraction
from hashlib import sha256
from itertools import combinations
from pathlib import Path

import numpy as np

from freeze import ROOT, check, pin, read, write

FACES=4096
NARROW=16384
WORK=1179648


def bound(n,m):
    # Both BVHs: (n*n+2*n-1) + per-tree (n+1), plus 5*n of
    # validation/referenced vertices/preparation. Normal priced paths only.
    return n*n+m*m+8*(n+m)+124*n*m+4


def caps(n,m,work_left=WORK,narrow_left=NARROW):
    upper=bound(n,m)
    return {"faces":[n,m],"potential_pairs":n*m,"minimum_original_narrow_residual_needed":n*m,
            "narrow_remaining":narrow_left,"work_remaining":work_left,"C_work_upper_if_ordinary_clean":upper,
            "face_admission":0<n and 0<m and n+m<=FACES,
            "narrow_bound_pass":n*m<=narrow_left,"conditional_work_bound_pass":upper<=work_left}


def bit_width(value):
    peak=max(abs(v) for v in value)
    return peak.bit_length()


def frame(coords):
    scalars=[tuple(Fraction(float(v)) for v in point) for point in coords]
    origin=scalars[0]
    shifts=[tuple(a-b for a,b in zip(p,origin,strict=True)) for p in scalars]
    e=max(v.denominator.bit_length()-1 for p in shifts for v in p)
    ints=[int(v*(1<<e)) for p in shifts for v in p]
    return {"canonical_exact_frame_exponent":e,"max_relative_integer_bits":bit_width(ints),
            "max_world_absolute_m":max(float(abs(x)) for q in scalars for x in q)}


def as_case(freeze,receipt_map):
    spec=read(check(freeze))
    geometry=read(check(spec["geometry"]))
    t=read(check(spec["exact_truth"]))
    n,m=[len(geometry[k]["faces"]) for k in ("left","right")]
    c=caps(n,m)
    c.update(geometry=spec["geometry"],exact_truth=spec["exact_truth"],canonical_pair=t["canonical_native_face_pair"],
             scope="archived normal first reply and independently frozen synthetic geometry",
             common_frame=frame(geometry["left"]["vertices_world"]+geometry["right"]["vertices_world"]))
    outcomes={}
    for a,ref in receipt_map.items():
        d=read(check(ref))
        sw=d["work"]["surface_work"]
        f=d["surface_fact"]
        outcomes[a]={"normal_observation":ref,"fact_state":f["status"],
                     "narrow":sw["narrow_phase_pairs"],"work":sw["work_units"],
                     "credit_spent":sw.get("witness_projection_credit_spent_units"),
                     "credit_end":sw.get("witness_projection_credit_balance"),
                     "published_distance":d["distance_m"],"unknown_reason":f.get("reason"),
                     "reported_witness":f.get("value",{}).get("nearest_witness"),
                     "measured_projection_pruned":sw.get("witness_projection_pruned_pairs",0)}
    c["outcomes"]=outcomes
    return c


def assembly(ref,archives):
    selected=read(check(ref))["selected"]
    shapes=read(check(selected["geometry"]))
    proof=read(check(selected["independent_truth"]))
    n,m=[len(shapes[k]["faces"]) for k in ("left","right")]
    values={}
    for a,rec in archives.items():
        s=read(check(rec))
        v=s["result"]
        values[a]={"archive":rec,"state":v["measurement_valid"],"distance":v["distance_m"],
                   "point_a":v["point_a_world"],"point_b":v["point_b_world"],
                   "narrow":s["work"]["narrow_phase_pairs"],"work":s["work"]["work_units"],
                   "credit":s["credits"],"scope":"043 frozen exact independent archive current source"}
    return {**caps(n,m),"scope":"original unrotated native assembly pair",
            "asset":selected["asset"],"proof":selected["independent_truth"],"truth_fields":list(proof),
            "common_frame":frame(shapes["left"]["vertices_world"]+shapes["right"]["vertices_world"]),
            "outcomes":values}


def regions(assets):
    r={}
    arms={a:read(check(assets[f"Yanyite_frozen_{a}"])) for a in "AC"}
    for label in ("high","low"):
        ref=assets[f"Yanyite_geometry_{label}"]
        raw=read(check(ref))
        truth=raw["independent_truth"]
        n,m=[len(raw[k]["faces"]) for k in ("left","right")]
        c=caps(n,m)
        c.update(geometry=ref,exact_sq=truth["distance_squared_exact_m2"],canonical_pair=truth["canonical_native_pair"],
                 scope="same source region archived direct and separately shared modes; native live note separate",
                 common_frame=frame(raw["left"]["vertices_world"]+raw["right"]["vertices_world"]))
        items={}
        for a,v in arms.items():
            selected,=[j for j in v["cases"] if j["case_id"]=="Yanyite_"+label]
            direct=selected["direct"]
            w=direct["work"]
            result=direct["value"]
            items[a]={"receipt":assets[f"Yanyite_frozen_{a}"],
                      "narrow":w["narrow_phase_pairs"],"work":w["work_units"],
                      "prepared_tree_used":w.get("shared_trees"),"witness_triangle":direct["native_pair"],
                      "measured":result["measurement_valid"],"distance":result["distance_m"],
                      "point_a":result["point_a_world"],"point_b":result["point_b_world"],
                      "scope":"archived replay of exact input, not timing claim"}
        c["outcomes"]=items
        r[label]=c
    negative=read(check(assets["Yanyite_low_prepaid"]))
    c=caps(174,12,work_left=negative["fixed_remaining"])
    assert negative["fixed_limit"]==WORK
    assert WORK-negative["prepaid"]==negative["fixed_remaining"]==8356
    c.update(scope="archived intentionally charged ledger, not a normal fresh call",
             source=assets["Yanyite_low_prepaid"],outcomes={a:v for a,v in negative["outcomes"].items()})
    r["prepaid"]=c
    return r


def g60(assets):
    snap=read(check(assets["G60_native_original"]))
    normal=read(check(assets["G60_plain"]))
    meshes={}
    for row in snap["objects"]:
        local=np.asarray(row["vertices_local"],dtype="<f8")
        mat=np.asarray(row["matrix_world"],dtype="<f8")
        faces=np.asarray(row["triangles"],dtype="<i4")
        # Same explicit binary64 additions as the historically bound 036/045
        # fixture normalization, independently regenerated from raw matrix data.
        world=(((local[:,0,None]*mat[None,:3,0]+local[:,1,None]*mat[None,:3,1])
                +local[:,2,None]*mat[None,:3,2])+mat[None,:3,3])*snap["unit_scale_m"]
        refs=np.unique(faces)
        meshes[row["name"]]={"face_count":len(faces),"coords":world[refs].tolist(),
          "lo":world[refs].min(axis=0).tolist(),"hi":world[refs].max(axis=0).tolist(),
          "world_hash":sha256(np.asarray(world,dtype="<f8").tobytes()).hexdigest(),
          "face_hash":sha256(faces.tobytes()).hexdigest()}
    host_groups=[]
    for row in normal["groups"]:
        source=check(row["raw"])
        parent=source.parent
        before=read(parent/"BEFORE.json")
        after=read(parent/"AFTER.json")
        assert before["pid"]==after["pid"] and not before["background"] and before["main_thread"]
        assert set(before["geometry"])==set(after["geometry"])==set(meshes)
        for fit in (before["geometry"],after["geometry"]):
            for name,data in fit.items():
                assert data["world_sha256"]==meshes[name]["world_hash"]
                assert data["triangles_sha256"]==meshes[name]["face_hash"]
        host_groups.append({"group":row["group"],"before":pin(parent/"BEFORE.json"),"after":pin(parent/"AFTER.json")})
    assert len(host_groups)==6
    pairs=[]
    for a,b in combinations(sorted(meshes),2):
        x,y=meshes[a],meshes[b]
        # Exact comparison of the float64 endpoints, not an after-solve result filter.
        sep=[max(Fraction(l)-Fraction(h),Fraction(m)-Fraction(k),Fraction(0))
             for l,h,m,k in zip(x["lo"],y["hi"],y["lo"],x["hi"],strict=True)]
        gap=sum(s*s for s in sep)
        f=frame(x["coords"]+y["coords"])
        pairs.append({**caps(x["face_count"],y["face_count"]),"pair":[a,b],
                      "absolute_aabb_gap_squared_exact":str(gap),"positive_AABB_gap":gap>0,**f})
    assert len(pairs)==66 and all(q["potential_pairs"]==3600 for q in pairs)
    return {"scope":"geometry-side proof condition only, no kernel or clock invoked by this reducer",
            "archive":assets["G60_native_original"],"bound_host_snapshots":host_groups,"pair_bounds":pairs,
            "largest_relative_frame_bits":max(x["max_relative_integer_bits"] for x in pairs),
            "largest_relative_frame_exp":max(x["canonical_exact_frame_exponent"] for x in pairs),
            "positive_AABB_gap_pairs":sum(x["positive_AABB_gap"] for x in pairs),
            "work_qualified_pairs":sum(x["conditional_work_bound_pass"] for x in pairs),
            "narrow_qualified_pairs":sum(x["narrow_bound_pass"] for x in pairs),
            "counts_do_not_prove":"point/witness publication, total product request, or deadline"}


def main():
    manifest=read(ROOT/"FREEZE.json")
    p=manifest["primary"]
    for ref in p.values():
        check(ref)
    result={"status":"pass_arithmetic_and_archives_only","plan":pin(ROOT/"FREEZE.json"),
            "ordinary_125":as_case(p["125_freeze"],{a:p[f"125_ordinary_{a}"] for a in "AC"}),
            "ordinary_129":as_case(p["129_freeze"],{a:p[f"129_ordinary_{a}"] for a in "AC"}),
            "assembly":assembly(p["real_assembly_holdout"],{a:p[f"assembly_archived_{a}"] for a in "AC"}),
            "Yanyite":regions(p),"G60_geometry":g60(p),
            "new_runtime_solver_calls":0,"new_Blend_processes":0,"new_timing_samples":0}
    print(write(ROOT/"MATRIX.json",result))


if __name__=="__main__":
    main()
