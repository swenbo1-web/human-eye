"""Check proof boundaries and the predeclared native optional archive scope."""
from __future__ import annotations

from collections import Counter
from fractions import Fraction
from pathlib import Path

from freeze import ROOT, pin, read, write
from inspect_domain import NARROW, WORK, caps


def publication_control():
    # Pure arithmetic example about the source publication predicate, not a new
    # staged mesh, measured product input, or origin of a baseline difference.
    h=Fraction(1,1<<52)
    L=1<<50
    a=(Fraction(1),Fraction(1))
    b=(1+L*h,1+(L+1)*h)
    point=(1+h,1+h)
    ints=(L,L+1)
    denom=L*L+(L+1)*(L+1)
    t=Fraction(2*L+1,denom)
    closest=tuple(x+t*(y-x) for x,y in zip(a,b,strict=True))
    mismatch=[x-y for x,y in zip(closest,point,strict=True)]
    assert Fraction(0)<t<Fraction(1)
    assert sum(e*i for e,i in zip(mismatch,ints,strict=True))==0
    d2=sum(x*x for x in mismatch)
    assert d2==h*h/denom and all(abs(e)<h/2 for e in mismatch)
    assert all(Fraction(float(v))==v for v in a+b+point)
    assert [float(v) for v in closest]==[float(v) for v in point]
    return {"scope":"analytic two affine primitives, only the source predicate for witness publication; no new evaluated asset",
            "counts_condition":caps(1,1),"lattice_exponent":52,"largest_coordinate_integer_bits":(L+1).bit_length(),
            "A_B_P":{name:list(map(str,val)) for name,val in (("segment_a",a),("segment_b",b),("point",point))},
            "positive_exact_gap_squared":str(d2),"projection_is_interior":True,
            "rounded_nearest_points_equal":True,"source_effect":"positive distance and equal rounded endpoints leaves witness unavailable",
            "version_difference_observed":False,"kernel_executed":False}


def optional(plan,matrix):
    defs={label:read(matrix["Yanyite"][label]["geometry"]["path"])["box_m"] for label in ("high","low")}
    descriptions=[]
    all_cells=[]
    hold=matrix["assembly"]["faces"]
    for root in plan["optional_inventory"]["ordinary_archive_roots"]:
        path=Path(root)
        counts=Counter()
        peak=0
        unknown=[]
        scope_file_count=0
        for wire in sorted(path.rglob("*.TX.bin")):
            doc=read(wire)
            if doc.get("method")!="tools/call":
                continue
            arg=doc.get("params",{})
            if arg.get("name")!="human_eye_scene_observe":
                continue
            scope_file_count+=1
            query=arg.get("arguments",{}).get("query",{})
            mode=query.get("mode")
            case=None
            P=None
            if mode in ("surface_scan","surface_nearest","overview") and any(tag in str(path) for tag in ("g60",)):
                case="primary G60 same 60 × 60 geometry" if mode!="overview" else "G60 overview (no pair-domain claim)"
                P=3600 if mode!="overview" else None
            elif mode=="source_region_measurement":
                box=query.get("region",{}).get("world_box_m")
                for label,value in defs.items():
                    if value==box:
                        case="primary Yanyite "+label
                        p,m=matrix["Yanyite"][label]["faces"]
                        P=p*m
            elif mode=="task":
                objects=[obj.get("name") for obj in query.get("objects",())]
                if objects==["Obj_014","Obj_003"]:
                    case="primary independent assembly"
                    P=hold[0]*hold[1]
            if case is None:
                unknown.append({"receipt":pin(wire),"mode":mode})
                continue
            if P is not None:
                peak=max(P,peak)
            counts[case]+=1
            all_cells.append({"request":pin(wire),"mode":mode,"classified_geometry":case,"potential_face_product":P})
        descriptions.append({"directory":root,"ordinary_observe_TX":scope_file_count,
                             "matched_class":dict(counts),"largest_known_pair_product":peak,
                             "unclassified":unknown})
    eligible_floor=(9*NARROW+9)//10
    assert not any(row["unclassified"] for row in descriptions), descriptions
    assert max(r["largest_known_pair_product"] for r in descriptions)<eligible_floor
    return {"scope":plan["optional_inventory"],"archive_roots":descriptions,
            "minimum_optional_pair_product":eligible_floor,
            "new_optional_native_pair":None,"reason":"all same-version native cases in frozen directories are primary and below fixed high-product floor",
            "counts_include_repeated_requests_not_new_solves":True,"raw_requests":all_cells}


def main():
    plan=read(ROOT/"FREEZE.json")
    matrix=read(ROOT/"MATRIX.json")
    out={"status":"pass_source_and_arithmetic_controls","matrix":pin(ROOT/"MATRIX.json"),
         "exact_narrow_boundary_128_square":caps(128,128),
         "next_square_129":caps(129,129),
         "exact_work_bound_60_square":caps(60,60,work_left=caps(60,60)["C_work_upper_if_ordinary_clean"]),
         "one_short_work_bound_60_square":caps(60,60,work_left=caps(60,60)["C_work_upper_if_ordinary_clean"]-1),
         "next_work_gate_meaning":"a failed sufficient test leaves the actual result unknown, not a failure prediction",
         "witness_control":publication_control(),"optional":optional(plan,matrix)}
    assert out["exact_narrow_boundary_128_square"]["narrow_bound_pass"]
    assert not out["next_square_129"]["narrow_bound_pass"]
    assert out["exact_work_bound_60_square"]["conditional_work_bound_pass"]
    assert not out["one_short_work_bound_60_square"]["conditional_work_bound_pass"]
    print(write(ROOT/"ARITH_INVENTORY.json",out))


if __name__=="__main__":
    main()
