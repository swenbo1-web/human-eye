"""Retain numerical phase attempts with a single-thread two-hour budget."""

import os
for name in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"):
    os.environ[name]="1"
os.environ["PYTHONDONTWRITEBYTECODE"]="1"
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import time

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("_refine_monitor",HERE.parent/"m6_shape_train_001/process_runner.py")
monitor=importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)
monitor.HERE=HERE


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("phase",choices=("prepare_sources","prepare_geometry","reference_control","tool_preflight","evaluate","verify","score"))
    parser.add_argument("--label")
    args=parser.parse_args()
    label=args.label or args.phase
    directory=HERE/"private/processes"
    directory.mkdir(parents=True,exist_ok=True)
    if (directory/(label+".json")).exists() or (directory/(label+".controller.json")).exists():
        raise RuntimeError("phase_label_already_attempted")
    rows=[json.loads(path.read_bytes()) for path in directory.glob("*.controller.json")]
    used=sum(row["wall_s"] for row in rows)
    if used>=7200:
        raise RuntimeError("numerical_budget_exhausted")
    script=HERE/(args.phase+".py")
    archive=HERE/"private/executed"/(label+".py")
    archive.parent.mkdir(parents=True,exist_ok=True)
    archive.write_bytes(script.read_bytes())
    if args.phase in ("evaluate","verify","score"):
        for row in json.loads((HERE/"PLAN_FREEZE.json").read_bytes())["files"]:
            if hashlib.sha256((HERE/row["path"]).read_bytes()).hexdigest()!=row["sha256"]:
                raise ValueError("frozen_plan_changed_"+row["path"])
    started=time.perf_counter()
    python=HERE.parent/"m6_shape_train_001/private/venv/Scripts/python.exe"
    result=monitor.run([str(python),"-I","-B","-X","utf8",str(script)],label,timeout_s=7200-used,rss_limit_bytes=4*1024**3)
    record=dict(phase=args.phase,label=label,wall_s=time.perf_counter()-started,numerical_used_before_s=used,
        worker_source=archive.relative_to(HERE).as_posix(),worker_source_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),returncode=result["returncode"],
        scope="single-thread numerical phase, Blender/consumer child costs also separately identified by their own job receipts, no exclusive benchmark")
    (directory/(label+".controller.json")).write_text(json.dumps(record,indent=2)+"\n",encoding="utf8",newline="\n")
    if result["returncode"]:
        raise SystemExit(result["returncode"])


if __name__=="__main__":
    main()
