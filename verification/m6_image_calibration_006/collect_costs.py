"""Collect current calibration costs and identity-only historical source references."""

from collections import Counter
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write

START_EPOCH = 1794788664.5798278
LEGACY_SOURCE = HERE.parent / "m6_image_correspondence_005/collect_costs.py"


def process_helpers():
    specification = importlib.util.spec_from_file_location("_calibration_process_accounting", LEGACY_SOURCE)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    module.HERE = HERE
    return module


def collect():
    started, cpu = time.perf_counter(), time.process_time()
    helpers = process_helpers()
    roots = helpers.collect_roots()
    launches = {}
    for path in sorted((HERE / "private/processes").glob("*.json")):
        record = read(path)
        command = record.get("command") or []
        if not command or Path(command[0]).name.casefold() != "blender.exe":
            continue
        key = (record.get("pid"), record.get("label"), tuple(command))
        launches[key] = dict(record=identity(path), **helpers.process_fields(record))
    bpy = list(launches.values())
    job_rows = []
    for path in sorted((HERE / "private/jobs").glob("*/run.json")):
        record = read(path)
        job_rows.append(dict(record=identity(path), label=record.get("label"), script=record.get("script"),
            job=record.get("job"), wall_s=record.get("wall_s"), process=record.get("process"),
            receipt_path=record.get("receipt_path"), receipt=record.get("receipt")))
    calibration = []
    for path in sorted(HERE.glob("CALIBRATION_v*_*.json")):
        record = read(path)
        calibration.append(dict(record=identity(path), observation=record))
    protocol = []
    for path in sorted((HERE / "private/protocol").glob("*/RESULT.json")):
        record = read(path)
        response = record.get("response", {})
        result = response.get("result", {})
        params = record.get("request", {}).get("params", {})
        protocol.append(dict(record=identity(path), method=record.get("method"), stage=params.get("stage"),
            proposal_id=params.get("proposal_id"), process_returncode=record.get("process_returncode"),
            wall_s=record.get("wall_s"), parent_CPU_s=record.get("CPU_s"), reused=result.get("reused"),
            new_Blender_jobs=result.get("new_Blender_jobs"), error=response.get("error"),
            returned_result=result.get("result_reference"), source_client=record.get("client_source"),
            source_service=record.get("service_source"), request=record.get("request_identity"),
            stdout=record.get("stdout_identity"), stderr=record.get("stderr_identity")))
    evidence = []
    excluded = {"COSTS.json", "MANIFEST.json", "HANDOFF.json"}
    for path in sorted(HERE.glob("*.json")):
        if path.name in excluded or path.name.startswith(("CALIBRATION_v", "COSTS")):
            continue
        record = read(path)
        evidence.append(dict(record=identity(path), timings=helpers.timing_observations(record)))
    source = read("SOURCE_BINDING.json")
    history = []
    previous = HERE.parent / "m6_image_correspondence_005"
    for proposal in source["proposals"]:
        state = read(proposal["source_session"]["path"])
        consumer_path = previous / "private/consumers" / state["stage"] / "repair" / state["route"] / "CONSUMER.json"
        record = read(consumer_path)
        history.append(dict(proposal_id=proposal["proposal_id"], source=identity(consumer_path),
            wall_s=record.get("wall_s"), usage=record.get("usage"), fees=record.get("fees"),
            accounting="Shared historical proposal-generation source. These calls belong to 005."))
    by_script = Counter()
    for row in bpy:
        command = row["command"]
        script = command[command.index("--python") + 1] if "--python" in command else "unknown"
        by_script[Path(script).name] += 1
    now = time.time()
    return dict(cycle_id="M6-IMAGE-CALIBRATION-006", snapshot_UTC=datetime.fromtimestamp(now, timezone.utc).isoformat(),
        end_to_end=dict(start_epoch=START_EPOCH, snapshot_epoch=now, elapsed_through_cost_snapshot_s=now - START_EPOCH,
            scope="Preparation, protocol clients, all current cold/warm calibration, QA, independent scoring, optimization and authoring/waits through this snapshot. Commit/callback tail is recorded separately."),
        new_Pro_consumers=0, training=0, Google_API_calls=0, new_paid_API_calls=0, formal_deployment=0,
        actual_protocol_client_scope="Real local protocol clients invoke deterministic calibration. Historical LLM proposal generation is separately referenced.",
        historical_shared_generation=history,
        historical_midpoint=dict(source_binding=identity(HERE / "MIDPOINT_SOURCE_BINDING.json"),
            recorded_original_Blender_processes=3, recorded_original_wall_s=read("MIDPOINT_RESULT.json")["wall_s"],
            accounting="Shared planning control. Current midpoint QA adds numerical checks without replaying those historical Blender processes."),
        owned_Blender=dict(process_count=len(bpy), by_script=dict(by_script), process_totals=helpers.process_summary(bpy),
            process_launches=bpy, job_receipts=job_rows,
            accounting="Each unique owned Blender PID/label/command launch counted once. Multi-operation batch receipts retain per-operation deltas. Whole-process cumulative resources are counted once."),
        monitored_numerical_roots=roots, calibration_results=calibration, protocol_clients=protocol,
        additional_evidence=evidence,
        current_source_identities=[identity(path) for path in sorted(HERE.glob("*.py"))],
        reused_accounting_source=identity(LEGACY_SOURCE),
        unmeasured=dict(root_model_usage=None, collaboration_model_usage=None, model_and_provider_fees=None,
            whole_task_CPU_s=None, whole_task_peak_RSS_bytes=None,
            end_to_end_LLM_consumer_speedup=None),
        accounting=["Nested operation, job, worker and protocol timers retain their scope. There is no additive grand total across them.",
            "Root tree CPU includes children. Blender CPU and per-operation CPU deltas remain subsets. RSS aggregates use maxima.",
            "Monitor-copy and process/job receipt aliases preserve evidence. PID reuse is separated using observed stdout creation/lifetime intervals.",
            "Current input references avoid duplicating the old 005 evidence archive. Raw current files are listed by the batch manifest."],
        collector_wall_s=time.perf_counter() - started, collector_CPU_s=time.process_time() - cpu)


if __name__ == "__main__":
    result = collect()
    write("COSTS.json", result)
    print(dict(new_Pro=0, Blender_processes=result["owned_Blender"]["process_count"],
        calibration_records=len(result["calibration_results"]), elapsed_s=result["end_to_end"]["elapsed_through_cost_snapshot_s"]))
