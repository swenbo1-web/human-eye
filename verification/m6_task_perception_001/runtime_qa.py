"""Exercise cold, cached and direct-focus normal runtime entry points."""

import json
from pathlib import Path
import subprocess
import sys
import time
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from common import read,write,identity
import numpy as np


def main():
    started,cpu=time.perf_counter(),time.process_time()
    folder=HERE/"private/runtime_qa"
    folder.mkdir(parents=True,exist_ok=False)
    python=HERE.parent/"m6_shape_train_001/private/venv/Scripts/python.exe"
    records=[]
    def invoke(name,arguments):
        before=time.perf_counter()
        result=subprocess.run([str(python),"-I","-B","-X","utf8",str(HERE/"prototype.py"),*arguments],capture_output=True)
        (folder/(name+".stdout.json")).write_bytes(result.stdout)
        (folder/(name+".stderr.txt")).write_bytes(result.stderr)
        records.append(dict(label=name,wall_s=time.perf_counter()-before,returncode=result.returncode,stdout_bytes=len(result.stdout)))
        if result.returncode:
            raise RuntimeError("runtime_entrypoint_failed_"+name)
        return json.loads(result.stdout)
    asset=HERE/"private/consumer_cases/t01/input.npz"
    first=invoke("cold_inspect",["--input",str(asset),"--entrypoint","inspect"])
    second=invoke("cached_inspect",["--input",str(asset),"--entrypoint","inspect"])
    focused=invoke("direct_focus",["--input",str(HERE/"private/consumer_cases/t02/input.npz"),"--entrypoint","focus"])
    reference=first["inspection_scope"]["reference"]
    resolved=invoke("resolve_current_scope",["--request-directory",first["runtime"]["request_directory"],"--resolve-reference",reference])
    task=read("private/consumer_cases/t01/task.json")
    with np.load(HERE/"private/predictions"/(task["geometry_alias"]+".npz")) as expected:
        expected_probability=expected["optimized_probability"]
    request_directory=Path(first["runtime"]["request_directory"])
    with np.load(request_directory/"prediction.npz") as actual:
        actual_probability=actual["optimized_probability"]
    with np.load(asset) as input_package:
        expected_ids=input_package["F_ids"].astype(np.int64)
        expected_positions=input_package["vertices"][expected_ids]
    checks=dict(cold_executes_real_current_features_and_model=first["runtime"]["model_called"] and not first["runtime"]["preparation_cached"],
        second_uses_version_bound_cache=not second["runtime"]["model_called"] and second["runtime"]["preparation_cached"],
        cold_and_batch_prediction_bitwise=np.array_equal(expected_probability,actual_probability),
        cache_preserves_identical_attention=first["attention"]==second["attention"],
        focus_reads_without_model=not focused["runtime"]["model_called"] and not focused["anomaly_threshold_applied"],
        focus_import_does_not_prepare_features=not (Path(focused["runtime"]["request_directory"])/"features.npz").exists(),
        resolver_exact_source_ids=np.array_equal(np.array(resolved["source_ids"]),expected_ids),
        resolver_exact_current_positions=np.array_equal(np.array(resolved["current_positions_native"]),expected_positions),
        runtime_reads_zero_supervision=first["runtime"]["labels_or_reference_coordinates_read"]==focused["runtime"]["labels_or_reference_coordinates_read"]==0)
    report=dict(status="passed" if all(checks.values()) else "failed",checks={key:bool(value) for key,value in checks.items()},
                actual_current_input=identity(asset),requests=records,cold_runtime=first["runtime"],cached_runtime=second["runtime"],focus_runtime=focused["runtime"],
                model_training_runs=0,new_runtime_model_forwards=1,wall_s_before_write=time.perf_counter()-started,cpu_s_before_write=time.process_time()-cpu,
                scope="four independent subprocess entrypoint calls, first real feature/model preparation and warm-cache/direct-focus/resolver costs, current geometry unchanged")
    write("RUNTIME_QA.json",report)
    print(report["status"],checks,flush=True)


if __name__=="__main__":
    main()
