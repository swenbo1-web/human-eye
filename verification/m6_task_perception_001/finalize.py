"""Seal fixed task evidence, source identities and an exhaustive private inventory."""

import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from common import DATA,identity,read,write
from collect_costs import collect


def main():
    started,cpu=time.perf_counter(),time.process_time()
    checks=[]
    def check(name,condition):
        checks.append(dict(name=name,passed=bool(condition)))
        if not condition:
            raise ValueError(name)
    for row in read("PLAN_FREEZE.json")["files"]:
        raw=(HERE/row["path"]).read_bytes()
        check("frozen_"+row["path"],hashlib.sha256(raw).hexdigest()==row["sha256"])
        committed=subprocess.check_output(["git","show","3f79fe14bae4b438a57028122f5defe9b7ee35fd:verification/m6_task_perception_001/"+row["path"]],cwd=HERE.parents[1])
        check("plan_pretraining_committed_"+row["path"],raw==committed)
    binding=read("OPTIMIZATION_COMMIT.json")
    committed=subprocess.check_output(["git","show",binding["commit"]+":verification/m6_task_perception_001/OPTIMIZATION_BINDING.json"],cwd=HERE.parents[1])
    check("optimization_fixed_before_second_run",committed==(HERE/"OPTIMIZATION_BINDING.json").read_bytes())
    for row in read("OPTIMIZATION_BINDING.json")["files"]:
        check("unchanged_optimization_input_"+row["path"],identity(HERE/row["path"])["sha256"]==row["sha256"])
    for path in HERE.glob("*.py"):
        ast.parse(path.read_bytes(),filename=str(path))
    check("all_public_python_AST",True)
    import numpy as np
    import scipy
    import torch
    from model import configure_torch
    configure_torch()
    write("RUNTIME.json",dict(python=sys.version,numpy=np.__version__,scipy=scipy.__version__,torch=torch.__version__,
        worker_executable=str(HERE.parent/"m6_shape_train_001/private/venv/Scripts/python.exe"),
        read_only_dependency_target=str(HERE.parent/"m6_shape_pretrain_001/private/deps"),
        torch_threads=torch.get_num_threads(),interop_threads=torch.get_num_interop_threads(),GPU=False,installations=0))
    verify,focus,runtime,inspection=(read(name) for name in ("VERIFY.json","FOCUS_QA.json","RUNTIME_QA.json","INSPECT_REPORTS.json"))
    check("fixed_inference_verification42893",verify["status"]=="passed_fixed_inference_and_evidence_verification" and verify["check_count"]==42893 and not verify["failures"])
    check("only_two_trainings_no_optimizer_replays",verify["original_candidate_training_runs"]==2 and verify["original_steps_per_run"]==1200 and verify["training_replays"]==verify["optimizer_steps"]==0)
    check("1200_bitwise_inference_replays",verify["inference_replay"]["model_forward_calls"]==1200 and verify["inference_replay"]["maximum_absolute_probability_difference"]==0.)
    check("focus16_success",focus["status"]=="passed" and not focus["failures"])
    check("runtime9_success",runtime["status"]=="passed" and all(runtime["checks"].values()))
    check("all600_two_route_reports",inspection["observation_count"]==600 and inspection["structured_reports"]==1200 and inspection["unique_region_references"]==12127)
    for row in inspection["cases"]:
        for route in row["routes"].values():
            file=route["report"]
            check("typed_report_"+file["path"],identity(HERE/file["path"])["sha256"]==file["sha256"])
    consumers,score,author=(read(name) for name in ("CONSUMERS.json","CONSUMER_SCORES.json","AUTHOR_PLAN_REVIEW.json"))
    check("24exact_once_real_consumers",consumers["actual_task_route_attempts"]==24 and consumers["completed"]==24 and consumers["prompt_replays"]==0 and consumers["additional_Pro_probe_tasks"]==0)
    check("24scored_rows_primary",score["primary_denominator"]==score["actual_consumer_records"]==score["actual_CLAIM_files"]==24 and len(score["cases"])==24)
    check("23complete_nonempty_deliveries_retained_first_failure",sum(row["complete_nonempty_geometry_delivery"] for row in score["cases"])==23)
    check("all_source_inputs_unchanged",all(row["source_unchanged_verified"] for row in score["cases"]))
    check("first_native_confounded_retained",[row["task_id"]+"/"+row["route"] for row in score["cases"] if row["infrastructure_affected"]]==["t01/native"])
    check("author24_reviews_separate",author["reviewed_answers"]==24 and author["pending_answers"]==0 and author["summary_reviewed_only"]["pass"]==23 and author["summary_reviewed_only"]["partial"]==1)
    check("consumers_physically_closed",consumers["cleanup"]["observed_owned_processes"]==0 and consumers["cleanup"]["all_CLI_parents_reaped"] and consumers["cleanup"]["all_reader_threads_stopped"])
    check("graceful_bridge_close_unknown_retained",consumers["cleanup"]["bridge_closed_receipts"]==0)
    for row in score["cases"]:
        for field in ("final_evidence","receipt_evidence"):
            record=row[field]
            check("consumer_original_"+row["task_id"]+row["route"]+field,identity(HERE/record["path"])["sha256"]==record["sha256"])
    evaluation=read("EVALUATION.json")
    check("final_v2_not_adopted",evaluation["passed"] is False and evaluation["optimized_gates"]==verify["independent_original_gates"]["v2"])
    check("no_validation_denominator_changes",evaluation["same_denominators"] and verify["inventory"]["validation_dents"]==165 and verify["inventory"]["validation_normals"]==8)
    external=[DATA/"data_io.py",DATA/"DATASET_INDEX.json",DATA/"SPLIT.json",DATA/"MANIFEST.json",
        HERE.parent/"m6_perception_001/region_common.py",HERE.parent/"m6_shape_train_001/process_runner.py",
        HERE.parent/"plugin_version_llm_ab_001/run_consumers.py"]
    write("REUSED_INPUTS.json",dict(files=[identity(path) for path in external],
        old_DATA_manifest_all_files_verified_in="VERIFY.json",private_old_DATA_manifest_members=1392,old_data_changes=0,
        extra_data_or_Bunny_or_Armadillo_evaluation=0,read_only_runtime=True))
    costs=collect()
    check("numerical7200s_target4GiB",costs["numerical_controller_wall_sum_s"]<7200 and costs["maximum_sampled_simultaneous_tree_RSS_bytes"]<4*1024**3)
    for label,row in costs["phases"].items():
        source=row["controller"]["worker_source"]
        check("executed_source_"+label,identity(HERE/source)["sha256"]==row["controller"]["worker_source_sha256"])
    check("24consumer_budget",costs["consumer_task_count"]==24)
    write("COSTS.json",costs)
    write("FINAL_QA.json",dict(status="passed_bounded_task_delivery_candidate_rejected",check_count=len(checks),checks=checks,
        candidate_adoption=False,focus_reference_engineering_passed=True,consumer_tasks_completed=24,
        limitations=["fixed learned inspect gates failed", "first native task affected by4executor errors", "24graceful MCP EOF receipts unknown despite process absence", "fees and complete CLI treeCPU/RSS unmeasured", "one corpus three derived groups, no independent final test", "focus is explicit geometric binding and direct measurement"],
        wall_s_before_write=time.perf_counter()-started,cpu_s_before_write=time.process_time()-cpu,
        scope="identity/AST/source/report seal, numerical training and inference results unchanged"))
    excluded={"MANIFEST.json","HANDOFF.json","callback_payload.json"}
    public=[identity(path) for path in sorted(HERE.iterdir()) if path.is_file() and path.name not in excluded]
    private=[identity(path) for path in sorted((HERE/"private").rglob("*")) if path.is_file()]
    write("MANIFEST.json",dict(cycle_id="M6-TASK-PERCEPTION-001",public_files=public,private_files=private,
        scope="all batch files at sealing, manifest itself and postcommit handoff/callback receipt excluded",raw_arrays_or_weights_in_Git=0))
    print("final seal",len(checks),"checks",len(public),"public",len(private),"private",flush=True)


if __name__=="__main__":
    main()
