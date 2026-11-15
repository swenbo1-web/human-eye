"""Collect measured enclosing scopes and retain nested costs without summing twice."""

from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write


def collect():
    controllers = [read(path) for path in sorted((HERE / "private/processes").glob("*.controller.json"))]
    phases = []
    for row in controllers:
        process = read("private/processes/" + row["label"] + ".json")
        phases.append(dict(label=row["label"], wall_s=row["wall_s"], returncode=row["returncode"],
            tree_cpu_s=process.get("tree_cpu_s"), tree_sampled_peak_working_set_bytes=process.get("tree_sampled_peak_working_set_bytes")))
    consumers, calls, workers = [], [], []
    for path in sorted((HERE / "private/consumers").glob("*/*/*/CONSUMER.json")):
        row = read(path)
        consumers.append(dict(stage=path.parents[2].name, case_id=row["task_id"], route=row["route"], status=row["status"],
            wall_s=row["wall_s"], prompt_to_final_s=row["prompt_to_final_s"], usage=row.get("usage"),
            fees=row.get("fees"), public_image_count=row.get("public_image_count"), public_image_bytes=row.get("public_image_bytes"),
            source=identity(path), cleanup=row.get("process_cleanup"), readers_stopped=row.get("readers_stopped")))
        bridge_path = path.parent / "bridge/BRIDGE_RESULT.json"
        if bridge_path.exists():
            bridge = read(bridge_path)
            for call in bridge["calls"]:
                calls.append(dict(stage=path.parents[2].name, case_id=row["task_id"], route=row["route"], **call))
                if "execution" in call:
                    execution = call["execution"]
                    worker = execution.get("worker") or {}
                    workers.append(dict(stage=path.parents[2].name, case_id=row["task_id"], route=row["route"],
                        wall_s=execution["wall_s"], worker_wall_s=worker.get("worker_wall_s_before_write"),
                        CPU_s=worker.get("process", {}).get("CPU_s"), peak_working_set_bytes=worker.get("process", {}).get("peak_working_set_bytes"),
                        input_JSON_bytes=execution["input_JSON_bytes"], transport=execution.get("transport", "inline_geometry_JSON")))
    jobs = []
    for path in sorted((HERE / "private/jobs").glob("*/run.json")):
        row = read(path)
        process = row["process"]
        jobs.append(dict(label=row["label"], script=row["script"]["path"], wall_s=row["wall_s"], returncode=process["returncode"],
            tree_cpu_s=process.get("tree_cpu_s"), tree_sampled_peak_working_set_bytes=process.get("tree_sampled_peak_working_set_bytes"),
            receipt_exists=Path(row["receipt_path"]).exists(), source=identity(path)))
    usages = [row["usage"] for row in consumers if row["usage"]]
    totals = {key:sum(row.get(key, 0) for row in usages) for key in sorted({key for row in usages for key in row})}
    disk = [(path, path.stat().st_size) for path in HERE.rglob("*") if path.is_file() and path.name not in ("MANIFEST.json", "HANDOFF.json")]
    pngs = [(path, size) for path, size in disk if path.suffix.lower() == ".png"]
    standalone = []
    for filename in ("private/smoke/RESULT.json", "private/smoke_facts/RESULT.json", "FACTS_PREFLIGHT.json",
                     "private/smoke/QUALITY_REGRESSION.json", "private/smoke/VERIFY_QUALITY_SMOKE.json", "AUDIT_IMPLEMENTATION.json", "TRANSPORT_BENCHMARK.json"):
        path = HERE / filename
        if path.exists():
            report = read(path)
            standalone.append(dict(source=identity(path), wall_s=report.get("wall_s"), cpu_s=report.get("cpu_s"),
                aggregate_cost=report.get("cost"), overlap="AUDIT_IMPLEMENTATION includes RECOVERY_REGRESSION and its listed failed attempts" if filename == "AUDIT_IMPLEMENTATION.json" else None))
    benchmark_runs = HERE / "private/transport_benchmark/RUNS.json"
    if benchmark_runs.exists():
        standalone.append(dict(source=identity(benchmark_runs), report=read(benchmark_runs),
            overlap="Contains the final TRANSPORT_BENCHMARK and its earlier retained local trial, count each run once"))
    failed = [dict(source=identity(path), report=read(path)) for path in sorted((HERE / "private/smoke").glob("*ATTEMPT*.json"))]
    render_records = [identity(path) for path in (HERE / "RENDER_PREFLIGHT.json", HERE / "private/reference/render_v2_preview.json",
        HERE / "private/jobs/s02_reference_after_render_v2_preview_mid/run.json", HERE / "private/results/VIEWABLES_v1.json", HERE / "VIEWABLES.json") if path.exists()]
    raw = dict(numerical_enclosing_phases=phases, consumers=consumers, nested_tool_calls=calls, nested_python_workers=workers,
        Blender_jobs=jobs, standalone_numerical_reports=standalone, failed_local_attempts=failed,
        render_enclosing_records=render_records,
        early_recovery_observations=[dict(operation="background import before any Blender job", wall_s=.1528406, CPU_s=None, resolution="insert script directory under Python -I", source=identity(HERE / "private/recovery/background_initial.py")),
            dict(operation="consumer preflight PowerShell quoting command before worker launch", wall_s=.073, CPU_s=None, resolution="structured source-file invocation")],
        scope="numerical, consumer, Blender and Python lists overlap by nesting; each list is a separate view")
    write("private/costs/FULL_COSTS.json", raw)
    output = dict(training_runs=0, actual_Pro_sessions=len(consumers), consumer_wall_s=sum(row["wall_s"] for row in consumers),
        consumer_wall_by_stage={stage:sum(row["wall_s"] for row in consumers if row["stage"] == stage) for stage in ("v1", "v2")},
        numerical_controller_inclusive_wall_s=sum(row["wall_s"] for row in phases), numerical_controller_inclusive_CPU_s=sum(row["tree_cpu_s"] or 0 for row in phases),
        numerical_controller_max_sampled_tree_RSS_bytes=max((row["tree_sampled_peak_working_set_bytes"] or 0 for row in phases), default=0),
        numerical_budget_s=7200, numerical_target_RSS_bytes=4*1024**3,
        Blender_calls=len(jobs), Blender_nested_wall_s=sum(row["wall_s"] for row in jobs),
        Blender_nested_CPU_s=sum(row["tree_cpu_s"] or 0 for row in jobs), Blender_max_sampled_tree_RSS_bytes=max((row["tree_sampled_peak_working_set_bytes"] or 0 for row in jobs), default=0),
        Python_consumer_calls=len(workers), Python_consumer_nested_wall_s=sum(row["wall_s"] for row in workers),
        Python_consumer_nested_CPU_s=sum(row["CPU_s"] or 0 for row in workers),
        Python_consumer_max_peak_RSS_bytes=max((row["peak_working_set_bytes"] or 0 for row in workers), default=0),
        Python_geometry_request_JSON_bytes=sum(row["input_JSON_bytes"] for row in workers), usage=totals,
        monetary_fees=None, model_resolved_settings=None, provider_internal_requests=None, provider_hidden_retries=None,
        unknowns=["provider-side monetary fees and hidden retries", "consumer CLI whole-tree CPU/RSS", "short-lived descendants missed by 50ms process sampling", "root reasoning and source-editing wall time"],
        local_images=dict(count=len(pngs), bytes=sum(size for _, size in pngs), all_versions_retained=True),
        standalone_numerical_reports=standalone, failed_local_attempts=failed,
        rendering_enclosing_records=render_records,
        consumer_performance=identity(HERE / "CONSUMER_PERFORMANCE.json"), process_cleanup=read("private/PROCESS_CLEANUP.json"),
        disk_snapshot=dict(files=len(disk), bytes=sum(size for _, size in disk), scope="before final manifest and HANDOFF; includes raw evidence, archived sources and failed attempts"),
        accounting="Consumer wall and numerical-controller wall are enclosing scopes. Blender and Python rows are nested in callers or standalone preflight/render scopes. Never add these totals to form an end-to-end runtime.",
        standalone_preflight_evidence=[identity(path) for path in (HERE / "FACTS_PREFLIGHT.json", HERE / "private/smoke/RESULT.json", HERE / "private/smoke_facts/RESULT.json", HERE / "private/smoke/QUALITY_REGRESSION.json", HERE / "private/smoke/VERIFY_QUALITY_SMOKE.json") if path.exists()],
        detailed_costs=identity(HERE / "private/costs/FULL_COSTS.json"),
        cold_reuse="Each Pro session starts from a fresh model copy. Each facts session uses its own version-bound cache. Separate local preflight cold/warm costs are retained; provider token caching follows reported usage.")
    write("COSTS.json", output)
    return output


if __name__ == "__main__":
    result = collect()
    print(result["actual_Pro_sessions"], result["consumer_wall_s"], result["Blender_calls"], result["disk_snapshot"])
