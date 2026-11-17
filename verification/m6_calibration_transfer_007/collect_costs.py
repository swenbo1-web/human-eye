"""Measured new-model common prefix and frozen-calibrator incremental costs."""

from collections import Counter
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write

START_EPOCH = 1794875546.4374871
ACCOUNTING_SOURCE = HERE.parent / "m6_image_correspondence_005/collect_costs.py"


def collect():
    started, cpu = time.perf_counter(), time.process_time()
    spec = importlib.util.spec_from_file_location("_transfer_accounting", ACCOUNTING_SOURCE)
    helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helpers)
    helpers.HERE = HERE
    roots = helpers.collect_roots()
    bpy = []
    seen = set()
    for path in sorted((HERE / "private/processes").glob("*.json")):
        record = read(path)
        command = record.get("command") or []
        if not command or Path(command[0]).name.casefold() != "blender.exe":
            continue
        key = (record.get("pid"), record.get("label"), tuple(command))
        if key in seen:
            continue
        seen.add(key)
        bpy.append(dict(record=identity(path), **helpers.process_fields(record)))
    scripts = Counter()
    for row in bpy:
        command = row["command"]
        name = command[command.index("--python") + 1] if "--python" in command else "unknown"
        scripts[Path(name).name] += 1
    consumers = []
    for path in sorted((HERE / "private/consumers").rglob("CONSUMER.json")):
        record = read(path)
        consumers.append(dict(record=identity(path), observation=record))
    claims = [dict(record=identity(path), observation=read(path)) for path in sorted((HERE / "private/consumers").rglob("CLAIM.json"))]
    tools = helpers.collect_tools(list((HERE / "private/consumers").rglob("COST.json")))
    python = [helpers.collect_python(path) for path in sorted((HERE / "private").rglob("EXECUTION.json"))
        if (path.parent / "CODE.py").exists() and isinstance(read(path), dict)]
    actual_python = [row for row in python if row["record"]["path"].replace("\\", "/").startswith("private/consumers/")]
    support_python = [row for row in python if row not in actual_python]
    protocol = []
    for path in sorted((HERE / "private/protocol").glob("*/RESULT.json")):
        record = read(path)
        protocol.append(dict(record=identity(path), observation=record))
    jobs = [dict(record=identity(path), observation=read(path)) for path in sorted((HERE / "private/jobs").glob("*/run.json"))]
    evidence = []
    for path in sorted(HERE.glob("*.json")):
        if path.name in {"COSTS.json", "MANIFEST.json", "HANDOFF.json"} or path.name.startswith("COSTS"):
            continue
        evidence.append(dict(record=identity(path), timings=helpers.timing_observations(read(path))))
    measured = {path.stem: dict(record=identity(path), **helpers.process_fields(read(path)))
        for path in sorted((HERE / "private/measured").glob("*.json"))}
    prefix = measured.get("consumer_raw_001")
    incremental = measured.get("calibration_v2_raw_001")
    comparison = None
    if prefix and incremental:
        comparison = dict(raw_proposal=dict(wall_s=prefix["full_process_wall_s"], tree_CPU_s=prefix["tree_cpu_s"], peak_tree_RSS_bytes=prefix["tree_sampled_peak_working_set_bytes"]),
            calibration_increment=dict(wall_s=incremental["full_process_wall_s"], tree_CPU_s=incremental["tree_cpu_s"], peak_tree_RSS_bytes=incremental["tree_sampled_peak_working_set_bytes"]),
            proposal_plus_calibration=dict(wall_s=prefix["full_process_wall_s"]+incremental["full_process_wall_s"], tree_CPU_s=prefix["tree_cpu_s"]+incremental["tree_cpu_s"], peak_tree_RSS_bytes=max(prefix["tree_sampled_peak_working_set_bytes"],incremental["tree_sampled_peak_working_set_bytes"])),
            common_setup_and_control={key:value for key,value in measured.items() if key in ("asset_preparation", "asset_preparation_retry", "prepare_consumer_001")},
            accounting="The same one model and raw submission/readback/preview form the shared prefix. Cold calibration is a sequential increment. Asset construction, matching images, hidden reachability control and neutral input preparation are separate shared setup. Mock/API/QA/scoring/authoring costs remain implementation evidence.")
    now = time.time()
    return dict(cycle_id="M6-CALIBRATION-TRANSFER-007", snapshot_UTC=datetime.now(timezone.utc).isoformat(),
        end_to_end=dict(start_epoch=START_EPOCH, snapshot_epoch=now, elapsed_through_snapshot_s=now-START_EPOCH,
            scope="Input preparation, actual assets/control/PNG, one model session and raw submission/preview, frozen V2 calibration and independent QA/authoring/waits. Commit/callback tail in HANDOFF."),
        new_Pro_consumers=max(len(consumers), len(claims)), consumer_records=len(consumers), started_claims=len(claims), training=0, Google_API_calls=0, new_paid_API_calls=0, formal_deployment=0,
        consumers=consumers, claims=claims, tool_calls=tools, tool_totals=helpers.tool_summary(tools),
        actual_consumer_python=actual_python, actual_consumer_python_totals=helpers.python_summary(actual_python),
        support_python_executions=support_python, support_python_totals=helpers.python_summary(support_python),
        path_cost_comparison=comparison,
        protocol_clients=protocol, measured_by_label=measured,
        owned_Blender=dict(process_count=len(bpy), by_script=dict(scripts), process_totals=helpers.process_summary(bpy),
            process_launches=bpy, job_receipts=jobs), monitored_numerical_roots=roots, additional_evidence=evidence,
        phase_label_note="Inherited accounting helper categorizes a runner without --stage as consumer_unknown. The unique consumer_raw_001 label identifies the only raw model session explicitly.",
        current_source_identities=[identity(path) for path in sorted(HERE.glob("*.py"))], reused_accounting_source=identity(ACCOUNTING_SOURCE),
        comparison_scope="One actual proposal. Model generation and actual raw submission/preview form the shared prefix. Deterministic calibration adds its actual protocol wall/CPU/RSS. Asset construction, matching images and private control are shared setup and reported separately.",
        accounting=["Nested tools, jobs, Python workers, protocol and process measurements retain their scopes. Whole-process cumulative CPU counted once, per-step batch deltas remain observations.",
            "Raw alpha1 and calibration alpha1 retain separate actual files and identity/camera/coordinate comparisons when newly executed. Full new execution costs remain included.",
            "Historical 005/006 source identities are fixed reuse references. Their historical model calls do not count as new calls."],
        unknown=dict(root_model_usage=None, collaboration_model_usage=None, provider_fees=None, whole_task_CPU_s=None,
            whole_task_peak_RSS_bytes=None, average_cross_asset_quality_gain=None),
        collector_wall_s=time.perf_counter()-started, collector_CPU_s=time.process_time()-cpu)


if __name__ == "__main__":
    result = collect()
    write("COSTS.json", result)
    print(dict(new_Pro=result["new_Pro_consumers"], claims=result["started_claims"], Blender=result["owned_Blender"]["process_count"]))
