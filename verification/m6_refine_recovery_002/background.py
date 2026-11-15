"""Run one owned factory-background Blender job and preserve its complete attempt."""

import importlib.util
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import BLENDER,HERE,identity,read,write


def run_job(script_name,job,label,timeout_s=240):
    folder=HERE/"private/jobs"/label
    folder.mkdir(parents=True,exist_ok=False)
    job_path=folder/"job.json"
    job=dict(job)
    job["receipt_path"]=str(folder/"receipt.json")
    write(job_path.relative_to(HERE),job)
    script=HERE/script_name
    (folder/script_name).write_bytes(script.read_bytes())
    spec=importlib.util.spec_from_file_location("_refine_job_monitor_"+label,HERE.parent/"m6_shape_train_001/process_runner.py")
    monitor=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)
    monitor.HERE=HERE
    command=[str(BLENDER),"--factory-startup","--disable-autoexec","--background","--threads","1"]
    if job.get("operation")!="create_baseline":
        command.append(str(job["current_blend"]))
    command += ["--python-exit-code","23","--python",str(script),"--","--job",str(job_path)]
    started=time.perf_counter()
    record=monitor.run(command,"b_"+label,timeout_s=timeout_s,rss_limit_bytes=4*1024**3)
    result=dict(label=label,script=identity(script),job=identity(job_path),wall_s=time.perf_counter()-started,
        process=record,receipt_path=job["receipt_path"],category="Blender background execution, nested under numerical/consumer caller when applicable")
    if Path(job["receipt_path"]).exists():
        result["receipt"]=read(Path(job["receipt_path"]))
    write((folder/"run.json").relative_to(HERE),result)
    if record["returncode"]:
        raise RuntimeError("background_job_failed_inspect_saved_state_"+label)
    if "receipt" not in result:
        raise RuntimeError("background_receipt_missing_read_actual_output_before_retry_"+label)
    return result


def prepare_baselines():
    outputs=[]
    for case in read("SOURCES.json")["cases"]:
        directory=HERE/"private/cases"/case["case_id"]
        common=dict(case_id=case["case_id"],object_name=case["object_name"],base_npz=case["initial_seed"],
            current_blend=case["base_blend_path"],source_original=case["source_original"])
        if case["source_type"]=="face":
            outputs.append(run_job("blender_edit.py",dict(common,operation="create_baseline",output_blend=case["base_blend_path"]),"s02_create"))
        outputs.append(run_job("blender_read.py",dict(common,readback_npz=str(directory/"baseline_readback.npz"),
            scene_signature_json=str(directory/"baseline_scene.json"),local_obj=str(directory/"before_local.obj")),case["case_id"]+"_baseline_read"))
    write("BASELINES.json",dict(jobs=[dict(label=row["label"],wall_s=row["wall_s"],receipt=row["receipt"]) for row in outputs],
        source_original_changed=False,background_only=True))


if __name__=="__main__":
    prepare_baselines()
