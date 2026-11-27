"""Freeze one positive distance witness and disjoint, overlapping-box triangle bands."""
from __future__ import annotations

import argparse
from fractions import Fraction
from math import isqrt
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = Path("D:/HumanEye/runs/M6-044-R3-FRESH-BUDGET")
PRESSURE = ROOT / "pressure"
sys.path.insert(0, str(HERE.parent/"m6_r3_region_attribution_043"))
from common import check, dump, pin, read

SMALL = 48
CAPS = {"faces":4096, "narrow_phase_pairs":16384, "work_units":1179648}
DELTA = Fraction(1, 256)
THICKNESS = Fraction(1, 2048)
STEP = Fraction(1, 512)
A0, B0 = Fraction(1), Fraction(4)


def world(s, t, h=0):
    return (s+t+h, s-t+h, s-2*h)


def as_mesh(name, triangles):
    points = [list(map(float, p)) for face in triangles for p in face]
    return {"name":name, "vertices_world":points,
            "faces":[[3*i,3*i+1,3*i+2] for i in range(len(triangles))]}


def geometry(n):
    a = [tuple(world(s,A0+i*STEP+t) for s,t in ((-64,0),(64,0),(0,THICKNESS)))
         for i in range(n)]
    b = [tuple(world(s,B0+i*STEP+t) for s,t in ((-128,0),(128,0),(0,THICKNESS)))
         for i in range(n-1)]
    last_t = A0+(n-1)*STEP+THICKNESS
    b.append(tuple(world(s,last_t+t,DELTA) for s,t in ((0,0),(-128,Fraction(1,2)),(128,Fraction(1,2)))))
    return {"case":"oblique_triangle_bands","source_kind":"synthetic_distinct_non_degenerate_triangle_unions",
            "unit":"m","subdivision_n":n,"left":as_mesh("Pressure_Inner",a),"right":as_mesh("Pressure_Outer",b)}


def prove(doc):
    """Prove exact world distance from serialized bytes using plane separation and t intervals."""
    left, right = [], []
    for name, container in (("left",left),("right",right)):
        mesh=doc[name]
        vertices=[tuple(map(Fraction,v)) for v in mesh["vertices_world"]]
        assert len(vertices)==3*len(mesh["faces"]) and len(set(vertices))==len(vertices)
        for ids in mesh["faces"]:
            p,q,r=[vertices[i] for i in ids]
            a,b=[tuple(x-y for x,y in zip(z,p)) for z in (q,r)]
            assert any(a[i]*b[j]!=a[j]*b[i] for i,j in ((0,1),(1,2),(2,0)))
            container.append((p,q,r))
    n=doc["subdivision_n"]
    assert n==len(left)==len(right) and n*2<=CAPS["faces"]
    assert len({frozenset(row) for row in left+right})==2*n
    # t and n·p are independent exact linear functionals of the serialized vertices.
    t=lambda p:(p[0]-p[1])/2
    normal=lambda p:p[0]+p[1]-2*p[2]
    low=lambda mesh,k:min(v[k] for row in mesh for v in row)
    high=lambda mesh,k:max(v[k] for row in mesh for v in row)
    assert all(low(right,k)<low(left,k)<=high(left,k)<high(right,k) for k in range(3))
    assert all(normal(p)==0 for face in left+right[:-1] for p in face)
    tmin_b=min(t(p) for face in right[:-1] for p in face)
    tmax_a=max(t(p) for face in left for p in face)
    a_matches=[(i,p) for i,face in enumerate(left) for p in face if t(p)==tmax_a]
    assert len(a_matches)==1 and a_matches[0][0]==n-1
    assert all(normal(p)==6*DELTA for p in right[-1])
    b_matches=[p for p in right[-1] if t(p)==tmax_a]
    assert len(b_matches)==1 and all(t(p)>=tmax_a for p in right[-1])
    a,b=a_matches[0][1],b_matches[0]
    assert tuple(y-x for x,y in zip(a,b)) == (DELTA,DELTA,-2*DELTA)
    sq=6*DELTA**2
    main_distance_lower=2*(tmin_b-tmax_a)**2
    assert tmin_b>tmax_a and main_distance_lower>sq
    # All individual AABBs overlap all opposite AABBs, independently of actual geometry.
    for axis in range(3):
        l=[(min(p[axis] for p in f), max(p[axis] for p in f)) for f in left]
        r=[(min(p[axis] for p in f), max(p[axis] for p in f)) for f in right]
        assert max(p[0] for p in l)<=min(p[1] for p in r)
        assert max(p[0] for p in r)<=min(p[1] for p in l)
    return {"proof":"main bands separated by t=(x-y)/2. The last outer triangle lies on a parallel plane at squared normal distance 6δ²; the projected t domains share exactly one vertex, proving uniqueness.",
            "distance_squared_exact":str(sq), "canonical_native_face_pair":[n-1,n-1],
            "unique_witness_world_exact":[list(map(str,a)),list(map(str,b))],
            "other_band_distance_squared_lower":str(main_distance_lower),
            "actual_distinct_faces":[n,n],"native_root_strict_containment":True,
            "all_cross_aabbs_overlap":True,
            "independent_of_candidate_version":True}


def freeze_small(inventory):
    receipt=read(inventory)
    assert receipt["eligible_existing_near_limit"]==0
    PRESSURE.mkdir(parents=True,exist_ok=False)
    definition={"cycle_id":ROOT.name,"input_inventory":pin(inventory),"generator":pin(__file__),
                "limits":CAPS,"B_calibration_once_n":SMALL, "runner":pin(HERE/"run_budget.py"), "controller":pin(HERE/"execute.py"),
                "selector": {"linear_proxy":"all observed B work and narrow cost scale as (n/48)^2, including fixed costs",
                             "target_utilization":"96/100","rounding":"floor square root of the stricter floor, max 256",
                             "do_not_reselect":True},
                "public_function":"measure_surface_proximity","deadline_s":30.0,
                "projection_mode":"installed default","prepaid":0,
                "arms":["A","B","C"],"target_density_is_estimate_not_answer_selection":True,
                "ordinary_retry_condition":"B known and C unknown/wrong from public kernel; same frozen bytes only"}
    p=PRESSURE/"CALIBRATION_48.json"
    doc=geometry(SMALL)
    ref=dump(p,doc)
    proof=dump(PRESSURE/"CALIBRATION_TRUTH.json",prove(read(p)))
    print(dump(PRESSURE/"SELECTION_RULE.json",dict(definition,calibration_geometry=ref,calibration_truth=proof)))


def freeze_final(cal):
    design=read(PRESSURE/"SELECTION_RULE.json")
    assert check(design["generator"])==Path(__file__).resolve()
    r=read(cal)
    assert r["arm"]=="B" and r["scope"]=="plain_public_kernel" and r["input"]==design["calibration_geometry"]
    assert r["result"]["measurement_valid"] is True
    for key in ("narrow_phase_pairs","work_units"):
        assert 0<r["work"][key]<CAPS[key]
    upper={key:isqrt((CAPS[key]*96*SMALL*SMALL)//(100*r["work"][key]))
           for key in ("narrow_phase_pairs","work_units")}
    n=min(256,*upper.values())
    assert n>SMALL
    doc=geometry(n)
    p=PRESSURE/"FINAL_GEOMETRY.json"
    ref=dump(p,doc)
    t=dump(PRESSURE/"FINAL_INDEPENDENT_TRUTH.json",prove(read(p)))
    planned={k:str(Fraction(r["work"][k]*n*n,SMALL*SMALL)) for k in upper}
    print(dump(PRESSURE/"FINAL_FREEZE.json",
               dict(status="frozen_before_final_C", selection_rule=pin(PRESSURE/"SELECTION_RULE.json"),
                    calibration=pin(cal), n=n, upper_bounds=upper, projected_counts=planned,
                    geometry=ref, exact_truth=t, limits=CAPS, planned_arms=["A","B","C"],
                    source_kind=doc["source_kind"], request_budget_s=30., admissible_public_surface=True)))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage",choices=("calibration","final"))
    parser.add_argument("receipt",type=Path)
    args=parser.parse_args()
    (freeze_small if args.stage=="calibration" else freeze_final)(args.receipt)
