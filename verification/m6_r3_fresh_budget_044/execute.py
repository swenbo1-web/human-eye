"""Start an isolated process for each fixed 044 receipt and preserve raw output."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"m6_r3_region_attribution_043"))
from common import PYTHON, dump, pin, read

ROOT=Path("D:/HumanEye/runs/M6-044-R3-FRESH-BUDGET")
PRESSURE=ROOT/"pressure"


def execute(phase,out):
    phase_specs={
        "family-diagnostic":("ABC",ROOT/"oracle/GEOMETRY.json",ROOT/"oracle/TRUTH.json",None),
        "calibrate":("B",PRESSURE/"CALIBRATION_48.json",PRESSURE/"CALIBRATION_TRUTH.json",PRESSURE/"SELECTION_RULE.json"),
        "pressure":("ABC",PRESSURE/"FINAL_GEOMETRY.json",PRESSURE/"FINAL_INDEPENDENT_TRUTH.json",PRESSURE/"FINAL_FREEZE.json"),
        "pressure-diagnostic":("BC",PRESSURE/"FINAL_GEOMETRY.json",PRESSURE/"FINAL_INDEPENDENT_TRUTH.json",PRESSURE/"FINAL_FREEZE.json"),
    }
    arms,input_path,truth,freeze=phase_specs[phase]
    assert out.resolve().is_relative_to(ROOT.resolve())
    assert all(p.is_file() for p in (input_path,truth))
    out.mkdir(parents=True,exist_ok=False)
    env={k:v for k,v in os.environ.items() if not k.upper().startswith(("HUMAN_EYE_","PYTHON"))}
    env.update({k:"1" for k in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS")})
    began=time.monotonic_ns()
    cases=[]
    for arm in arms:
        path=out/arm
        starting=time.monotonic_ns()
        cmd=[str(PYTHON),"-E","-s","-B",str(HERE/"run_budget.py"),"--phase",phase,"--arm",arm,"--input",
             str(input_path),"--truth",str(truth),"--output",str(path)]
        if freeze is not None:
            cmd+=["--freeze",str(freeze)]
        with (out/(arm+".stdout")).open("xb") as f, (out/(arm+".stderr")).open("xb") as err:
            process=subprocess.Popen(cmd,cwd=out,env=env,stdin=subprocess.DEVNULL,stdout=f,stderr=err,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            code=process.wait()
        stopped=time.monotonic_ns()
        receipt=pin(path/"RESULT.json") if (path/"RESULT.json").exists() else None
        row={"arm":arm,"argv":cmd,"launcher_pid":process.pid,"launcher_reaped":process.poll() is not None,
             "status":"observed" if code==0 else "failed","exit_code":code,"receipt":receipt,
             "full_start_ns":starting,"full_end_ns":stopped,"full_process_ns":stopped-starting,
             "stdout":pin(out/(arm+".stdout")),"stderr":pin(out/(arm+".stderr"))}
        cases.append(row)
        print(phase,arm,row["status"],flush=True)
        if code!=0:
            break
    observed=sum(row["status"]=="observed" for row in cases)
    print(dump(out/"RESULT.json",{"phase":phase,"expected":list(arms),"launched":cases,
                "observations":observed,"all_reaped":all(row["launcher_reaped"] for row in cases),
                "complete_window_ns":time.monotonic_ns()-began,
                "status":"complete" if observed==len(arms) else "incomplete"}))
    return int(observed!=len(arms))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("phase",choices=("family-diagnostic","calibrate","pressure","pressure-diagnostic"))
    p.add_argument("output",type=Path)
    args=p.parse_args()
    raise SystemExit(execute(args.phase,args.output))
