"""Replay the published g10 exact-width and over-face rejection on installed A/C/F."""
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
RAW = Path("D:/HumanEye/runs/M6-049-R3-FINAL-REPLACEMENT")
PIN = RAW/"candidate/PINS.json"
OUT = RAW/"g10_existing_rejection"
REV = "6c93f2375d1073b33e721a168f1fcf610ac6dbdc"
CASE_SOURCE = "verification/degenerate_surface_001/tests/test_degenerate_surface.py"


def save(path,value):
    with path.open("x",encoding="utf8",newline="\n") as out:
        json.dump(value,out,indent=2,allow_nan=False)
        out.write("\n")


def child(plan_path,arm):
    plan = json.loads(plan_path.read_bytes())
    binding = json.loads(Path(plan["bindings"][arm]).read_bytes())
    site = Path(binding["site_packages"])
    assert len(binding["source_files"]) in (143,145)
    for file in binding["source_files"]:
        assert hashlib.sha256((site/file["path"]).read_bytes()).hexdigest()==file["sha256"]
    sys.path.insert(0,str(site))
    from human_eye_plugin import surface_proximity as kernel
    from human_eye_plugin.runtime_identity import runtime_identity
    assert kernel.MAX_BITS==4096
    assert kernel.MAX_NARROW_PHASE_PAIRS==16384 and kernel.MAX_WORK_UNITS==1179648
    assert runtime_identity(mode="live")["source_sha256"]==binding["identity"]["source_sha256"]
    assert Path(kernel.__file__).resolve()==(site/"human_eye_plugin/surface_proximity.py").resolve()

    # Use the original test's finite binary64 values and closed triangle hulls.
    smallest, high = math.ldexp(1., -1074), math.ldexp(1., 1023)
    point = SimpleNamespace(vertices=((smallest,0.,0.),),faces=((0,0,0),))
    segment = SimpleNamespace(vertices=((high,0.,0.),(high,1.,0.)),faces=((0,1,1),))

    class CountOnlyFaces:
        def __len__(self):
            return 4097

        def __iter__(self):
            raise AssertionError("Over-budget face data expanded")

    point0 = SimpleNamespace(vertices=((0.,0.,0.),),faces=((0,0,0),))
    over = SimpleNamespace(vertices=point0.vertices,faces=CountOnlyFaces())
    observations = {}
    for name,left,right,expected in (
        ("bit_width", point,segment,"surface_exact_bit_budget"),
        ("face_limit", point0,over,"surface_geometry_work_limit"),
    ):
        end = time.perf_counter_ns()+30_000_000_000
        def checkpoint(phase):
            if time.perf_counter_ns()>=end:
                raise TimeoutError(phase)
        result = kernel.measure_surface_proximity(left,right,checkpoint,retain_exact_rank=True)
        assert result["measurement_valid"] is False and result["reason"]==expected
        assert all(result[k] is None for k in ("distance_m","point_a_world","point_b_world","direction_a_to_b"))
        observations[name]={"result":result,"expected":expected}
    print(json.dumps(observations,allow_nan=False))


def run():
    pins = json.loads(PIN.read_bytes())
    fixed = subprocess.check_output(["git","show",REV+":"+CASE_SOURCE],cwd=HERE)
    assert b"smallest, high = math.ldexp(1., -1074), math.ldexp(1., 1023)" in fixed
    assert b"Over-budget face data expanded" in fixed
    OUT.mkdir()
    (OUT/"ORIGINAL_TEST.py").write_bytes(fixed)
    plan = OUT/"PLAN.json"
    save(plan,{"original_source":CASE_SOURCE,"base":REV,"sha256":hashlib.sha256(fixed).hexdigest(),
               "scope":"two existing g10 cases, no new geometry optimization or timing",
               "bindings":{"A":pins["baseline_A"]["path"],"C":pins["baseline_C"]["path"],"F":pins["binding"]["path"]}})
    passed = {}
    for arm in "ACF":
        reply = subprocess.run([sys.executable,"-I","-B","-X","utf8",__file__,"child",str(plan),arm],
                               capture_output=True,timeout=70)
        (OUT/(arm+".stdout")).write_bytes(reply.stdout)
        (OUT/(arm+".stderr")).write_bytes(reply.stderr)
        passed[arm] = {"exit_code":reply.returncode,"observations":json.loads(reply.stdout) if reply.stdout else None}
    status = "pass" if all(r["exit_code"]==0 for r in passed.values()) else "fail"
    save(OUT/"RESULTS.json",{"status":status,"calls_planned":6,"arms":passed,"new_blender":0,"samples":0})
    print(status)
    return int(status!="pass")


if __name__=="__main__":
    if len(sys.argv)>1:
        child(Path(sys.argv[2]),sys.argv[3])
    else:
        raise SystemExit(run())

