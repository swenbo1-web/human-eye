"""First new-account 129 observation on the installed, frozen D runtime."""
from __future__ import annotations

from fractions import Fraction
from hashlib import file_digest
import json
import math
from pathlib import Path
import sys
import time
import traceback
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent
ROOT=Path("D:/HumanEye/runs/M6-046-R3-PREVIOUS-WITNESS")
D=ROOT/"candidate/PINS.json"
BASE=ROOT.parent/"M6-045-R3-REPLACEMENT-ENTRY/oracle/FINAL_FREEZE.json"


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    path=Path(path).resolve(strict=True)
    with path.open("rb") as stream:
        return {"path":str(path),"bytes":path.stat().st_size,"sha256":file_digest(stream,"sha256").hexdigest()}


def check(ref):
    assert pin(ref["path"])==ref
    return Path(ref["path"])


def write(path,value):
    with Path(path).open("x",encoding="utf-8",newline="\n") as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False)
        f.write("\n")
    return pin(path)


def bound_D():
    meta=read(D)
    assert meta["design"]==pin(ROOT/"DESIGN.json")
    design=read(check(meta["design"]))
    assert design["development"]["freeze"]==pin(BASE)
    check(design["holdout"])
    definition=read(check(meta["binding"]))
    site=Path(meta["site"])
    for row in definition["source_files"]:
        assert pin(site/row["path"])["sha256"]==row["sha256"]
    assert len(definition["source_files"])==143
    sys.path.insert(0,str(site))
    from human_eye_plugin import surface_proximity
    from human_eye_plugin.runtime_identity import runtime_identity
    ident=runtime_identity(mode="live")
    assert ident["source_sha256"]==meta["source_sha256"] and ident["distribution_version"]==meta["identity"]["distribution_version"]
    assert Path(surface_proximity.__file__).resolve()==check(meta["changed_kernel"])
    return surface_proximity


def mesh(d):
    return SimpleNamespace(name=d["name"], object_id=d["name"],
                           vertices=tuple(map(tuple,d["vertices_world"])),
                           faces=tuple(map(tuple,d["faces"])))


def inputs():
    frozen=read(BASE)
    return read(check(frozen["geometry"])), read(check(frozen["exact_truth"]))


def prior_mesh_pair(data):
    return mesh(data["left"]),mesh(data["right"])


def matches(result,truth):
    if not result["measurement_valid"]:
        assert result["distance_m"] is None and result["point_a_world"] is None and result["point_b_world"] is None
        return False
    n,d,e=result["_exact_distance_sq"]
    q=Fraction(n,d)*(Fraction(2)**e)
    assert q==Fraction(truth["distance_squared_exact"])
    assert result["distance_m"]==math.sqrt(float(q))
    w=result.get("exact_witness_triangles")
    assert (w["indices"] if w else result["witness_triangle_indices"])==truth["canonical_native_face_pair"]
    assert [list(map(Fraction,result[k])) for k in ("point_a_world","point_b_world")] == [
            list(map(Fraction,row)) for row in truth["unique_witness_world_exact"]]
    return True


def clock(deadline,observed):
    def cp(stage):
        observed["last"]=stage
        if "first" not in observed:
            observed["first"]=stage
        if time.monotonic_ns()>=deadline:
            raise TimeoutError(stage)
    return cp


def main():
    out=ROOT/"numeric/first_129"
    out.mkdir(parents=True)
    kernel=bound_D()
    assert [kernel.MAX_FACES,kernel.MAX_NARROW_PHASE_PAIRS,kernel.MAX_WORK_UNITS]==[4096,16384,1179648]
    data,truth=inputs()
    left,right=prior_mesh_pair(data)
    assert len(left.faces)==len(right.faces)==129
    start=time.monotonic_ns()
    cpu=time.process_time_ns()
    deadline=start+30_000_000_000
    checkpoints={}
    receipt={"installation":pin(D),"scope":"untouched public D kernel in first fresh process",
             "frozen_geometry_and_truth":pin(BASE),"status":"invalid","deadline_ns":deadline,
             "work_initialization":"original _Work, no context precharge or mutation"}
    checkpoint=clock(deadline,checkpoints)
    try:
        result=kernel.measure_surface_proximity(left,right,checkpoint,retain_exact_rank=True,retain_witness_triangles=True)
        elapsed=time.monotonic_ns()-start
        assert elapsed<30_000_000_000
        receipt["result"]=result
        receipt["status"]="pass" if matches(result,truth) else "unknown"
    except Exception:
        receipt["error"]=traceback.format_exc()
    receipt.update(checkpoints=checkpoints,process_measured_wall_ns=time.monotonic_ns()-start,
                   process_measured_cpu_ns=time.process_time_ns()-cpu)
    print(write(out/"RESULT.json",receipt),flush=True)
    return int(receipt["status"]=="invalid")


if __name__=="__main__":
    raise SystemExit(main())
