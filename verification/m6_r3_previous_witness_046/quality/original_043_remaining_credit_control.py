"""One supplemental internal stress control. No caller supplies a precharge in this public API."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path("D:/HumanEye/runs/M6-043-R3-REGION-ATTRIBUTION")
INPUT = ROOT/"holdouts/inputs/Yanyite_low.json"
INPUT_SHA = "57bf59c7ddf2bc61451cf62c30e32db6a456ced6bed92adb69956f498f5236a7"
B_C_WORK = (8169,8543)
REMAINING = sum(B_C_WORK)//2
LIMIT = 1179648


def trial(arm):
    site = Path(json.loads((ROOT/"live/g60/PLAN_03.json").read_bytes())["arms"][arm]["site_packages"])
    binding = json.loads((site.parent/"admin/RUNTIME_BINDING.json").read_bytes())
    for row in binding["source_files"]:
        assert hashlib.sha256((site/row["path"]).read_bytes()).hexdigest() == row["sha256"]
    assert hashlib.sha256(INPUT.read_bytes()).hexdigest()==INPUT_SHA
    case = json.loads(INPUT.read_bytes())
    sys.path.insert(0,str(site))
    from human_eye_plugin import surface_proximity as kernel
    from human_eye_plugin.active_observation_images import _meshes_from_objects
    assert Path(kernel.__file__).resolve()==(site/"human_eye_plugin/surface_proximity.py").resolve()
    assert kernel.MAX_WORK_UNITS == LIMIT
    original = kernel._Work

    class WithPriorWork(original):
        def __init__(self, checkpoint, stats):
            super().__init__(checkpoint,stats)
            self.consume(LIMIT-REMAINING,"diagnostic_prior_work")

    results={}
    for name,work in (("fresh",original),("one_precharge",WithPriorWork)):
        objects=[(m["vertices_world"],m["faces"],(case["case_id"],side),m["name"])
                 for side in ("left","right") for m in [case[side]]]
        left,right = _meshes_from_objects(objects)
        stats={}
        with patch.object(kernel,"_Work",work):
            v=kernel.measure_surface_proximity(left,right,lambda _:None,diagnostics=stats,
                                               retain_witness_triangles=True,_prepared_holder={})
        results[name]={k:v.get(k) for k in ("measurement_valid","reason","distance_m","_exact_distance_sq",
                                            "point_a_world","point_b_world","witness_triangle_indices","exact_witness_triangles")}
        results[name]["work"]={k:stats.get(k) for k in ("work_units","narrow_phase_pairs","witness_projection_tests")}
    assert results["fresh"]["work"]["work_units"] == B_C_WORK["BC".index(arm)]
    return results


if __name__=="__main__":
    if len(sys.argv)>1:
        print(json.dumps(trial(sys.argv[1])))
    else:
        output={a:json.loads(subprocess.check_output([sys.executable,"-I","-B",__file__,a])) for a in "BC"}
        result=dict(case_sha256=INPUT_SHA,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    scope="Only _Work initialization has a synthetic prior debit. Ordinary production requests start with a fresh per-pair budget.",
                    fixed_limit=LIMIT, fixed_remaining=REMAINING, prepaid=LIMIT-REMAINING, outcomes=output)
        out=Path(__file__).with_name("REMAINING_CREDIT_043.json")
        out.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
        print(out)
