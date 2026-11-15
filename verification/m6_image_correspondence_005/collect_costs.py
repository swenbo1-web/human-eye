"""Collect the four correspondence consumers and retained preparation/execution costs."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time


HERE = Path(__file__).resolve().parent
TASK_STARTED_EPOCH = 1794783059.259194
ORDER = (("v1", "native"), ("v1", "facts"), ("v2", "facts"), ("v2", "native"))
TASK_ID = "repair"
TERMINAL_STATUSES = ("completed", "failed")
TOOL_METRICS = (
    "wall_s", "public_text_UTF8_bytes", "complete_text_UTF8_bytes",
    "stdio_response_UTF8_bytes", "public_image_count", "public_image_bytes", "image_base64_bytes",
)
PROCESS_FIELDS = (
    "label", "pid", "status", "returncode", "command", "stdout", "stderr", "full_process_wall_s", "full_process_cpu_s",
    "peak_working_set_bytes", "tree_cpu_s", "tree_sampled_peak_working_set_bytes", "memory_samples",
    "memory_scope", "tree_scope", "process_tree", "final_memory_query",
)


def read(path, default=None):
    path = Path(path)
    return json.loads(path.read_bytes()) if path.exists() else default


def identity(path):
    path = Path(path).resolve()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return dict(path=path.relative_to(HERE).as_posix() if path.is_relative_to(HERE) else str(path),
                bytes=path.stat().st_size, sha256=digest.hexdigest())


def identities(paths):
    unique = {str(Path(path).resolve()).casefold(): Path(path).resolve() for path in paths}
    return [identity(path) for path in sorted(unique.values()) if path.is_file()]


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def summed(rows, field):
    values = [row[field] for row in rows if number(row.get(field))]
    return sum(values) if values else None


def maximum(rows, field):
    values = [row[field] for row in rows if number(row.get(field))]
    return max(values) if values else None


def timing_observations(value, prefix=""):
    result = {}
    if isinstance(value, dict):
        for key, item in value.items():
            name = prefix + "." + key if prefix else key
            if number(item) and any(part in key.lower() for part in ("wall", "cpu", "rss", "peak", "bytes", "epoch", "unix")):
                result[name] = item
            elif isinstance(item, (dict, list)):
                result.update(timing_observations(item, name))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            result.update(timing_observations(item, prefix + "[" + str(index) + "]"))
    return result


def process_fields(record):
    return {key: record[key] for key in PROCESS_FIELDS if key in record}


def process_summary(rows):
    return dict(launches=len(rows), statuses=dict(Counter(row.get("status", "unknown") for row in rows)),
        wall_s_sum_nonexclusive=summed(rows, "full_process_wall_s"),
        parent_process_CPU_s_sum=summed(rows, "full_process_cpu_s"),
        tree_CPU_s_sum=summed(rows, "tree_cpu_s"),
        maximum_process_peak_RSS_bytes=maximum(rows, "peak_working_set_bytes"),
        maximum_sampled_tree_peak_RSS_bytes=maximum(rows, "tree_sampled_peak_working_set_bytes"),
        tree_CPU_measurements=sum(number(row.get("tree_cpu_s")) for row in rows),
        tree_RSS_measurements=sum(number(row.get("tree_sampled_peak_working_set_bytes")) for row in rows))


def phase_for(command, label=""):
    words = [str(word) for word in command]
    names = {Path(word).name for word in words}
    if "consumer_runner.py" in names:
        stage = words[words.index("--stage") + 1] if "--stage" in words else "unknown"
        return "consumer_" + stage
    if any(name in names for name in ("prepare_case.py", "prepare_inputs.py", "bind_consumer_images.py")):
        return "preparation"
    if "api_preflight.py" in names:
        return "actual_control_preflight"
    if "diagnostics.py" in names:
        return "frozen_program_diagnostics"
    if "construction_quality.py" in names:
        return "construction_geometry_QA"
    if any("preflight" in name for name in names):
        return "local_preflight"
    if "render_results.py" in names:
        return "result_rendering"
    if "independent_verify.py" in names:
        return "saved_result_verification"
    if "analyze_consumers.py" in names:
        return "consumer_analysis"
    return "other_support"


def collect_python(path):
    record = read(path, {})
    worker = record.get("worker") or {}
    request = read(path.parent / "REQUEST.json", {})
    return dict(record=identity(path), status=record.get("status"), returncode=record.get("returncode"),
        executor={key: record[key] for key in ("wall_s", "JSON_encode_wall_s", "JSON_encode_CPU_s", "input_JSON_bytes",
            "input_transport", "observed_version", "timeout_s", "public_truncated", "error") if key in record},
        worker_wall_s=worker.get("worker_wall_s_before_write"), worker_process=worker.get("process", {}),
        transport=worker.get("transport", {}), access_policy=worker.get("access_policy"),
        image_pixel_reads=worker.get("image_pixel_reads", []), created_fit_diagnostics=worker.get("created_fit_diagnostics", []),
        array_packet=request.get("array_packet"), delivered_reference_packets=request.get("read_only_packets", []),
        error=worker.get("error", record.get("error")),
        evidence=identities(path.parent / name for name in ("REQUEST.json", "CODE.py", "FILE_ACCESS.json", "STDOUT.bin", "STDERR.bin", "COMPLETE_RESULT.json")))


def python_summary(rows):
    transports = [row["transport"] for row in rows]
    executors = [row["executor"] for row in rows]
    processes = [row["worker_process"] for row in rows]
    image_reads = [item for row in rows for item in row.get("image_pixel_reads", [])]
    return dict(executions=len(rows), statuses=dict(Counter(row.get("status", "unknown") for row in rows)),
        executor_wall_s=summed(executors, "wall_s"),
        JSON_encode_wall_s=summed(executors, "JSON_encode_wall_s"),
        JSON_encode_CPU_s=summed(executors, "JSON_encode_CPU_s"), input_JSON_bytes=summed(executors, "input_JSON_bytes"),
        worker_wall_s=summed(rows, "worker_wall_s"), worker_CPU_s=summed(processes, "CPU_s"),
        maximum_worker_peak_RSS_bytes=maximum(processes, "peak_working_set_bytes"),
        shared_image_pixels=dict(calls=len(image_reads), cold_decodes=sum(item.get("cache_hit") is False for item in image_reads),
            per_worker_cache_hits=sum(item.get("cache_hit") is True for item in image_reads),
            wall_s=summed(image_reads, "wall_s"), CPU_s=summed(image_reads, "CPU_s"),
            cold_PNG_bytes=sum(item.get("PNG_bytes", 0) for item in image_reads if item.get("cache_hit") is False),
            cold_decoded_array_bytes=sum(item.get("decoded_array_bytes", 0) for item in image_reads if item.get("cache_hit") is False),
            scope="Model-requested image pixel reads in Python. Decode/cache costs nest in worker/executor timers and are separate from MCP image delivery and component raster preparation."),
        created_fit_diagnostic_count=sum(len(row.get("created_fit_diagnostics", [])) for row in rows),
        transport_totals={key: sum(row.get(key, 0) for row in transports if number(row.get(key)))
            for key in sorted({key for row in transports for key, value in row.items() if number(value)})},
        timing_scope="Executor encloses packet validation and worker execution. Worker CPU/RSS are individual-process observations.")


def collect_tools(paths):
    rows = []
    for path in sorted(set(paths)):
        cost = read(path, {})
        request = read(path.parent / "REQUEST.json", {})
        name = cost.get("name", request.get("name", "unknown"))
        row = dict(record=identity(path), name=name, index=cost.get("index"), status=cost.get("status"),
            truncated=cost.get("truncated"), metrics={key: cost.get(key, 0) for key in TOOL_METRICS},
            snapshot=cost.get("snapshot"), preview=cost.get("preview"),
            image_delivery_kind=cost.get("image_delivery_kind"), image_version=cost.get("image_version"),
            error=read(path.parent / "PRIVATE_ERROR.json"),
            evidence=identities(path.parent / filename for filename in
                ("REQUEST.json", "RESPONSE.json", "COMPLETE_RESULT.json", "PRIVATE_RESULT.json", "PRIVATE_ERROR.json")))
        if name in ("focus", "resolve_ref"):
            complete = read(path.parent / "COMPLETE_RESULT.json", {})
            row["facts"] = complete.get("cost", {})
            component = complete.get("image_correspondence")
            if isinstance(component, dict):
                row["correspondence"] = {key: component[key] for key in ("cost", "binding_sha256",
                    "candidate_points", "core_budget", "positive_attention_full_mesh_points", "localized_support") if key in component}
        rows.append(row)
    return rows


def tool_summary(rows):
    snapshots = [row["snapshot"] for row in rows if isinstance(row.get("snapshot"), dict)]
    previews = [row["preview"] for row in rows if isinstance(row.get("preview"), dict)]
    facts = [row["facts"] for row in rows if "facts" in row]
    correspondence = [row["correspondence"]["cost"] for row in rows if row.get("correspondence", {}).get("cost")]
    return dict(calls=len(rows), by_name=dict(Counter(row["name"] for row in rows)),
        statuses=dict(Counter(row.get("status", "unknown") for row in rows)),
        totals={key: summed([row["metrics"] for row in rows], key) for key in TOOL_METRICS},
        packet_snapshots=dict(calls=len(snapshots), warm_hits=sum(row.get("cache_hit") is True for row in snapshots),
            cold_creations=sum(row.get("cache_hit") is False for row in snapshots),
            totals={key: sum(row.get(key, 0) for row in snapshots if number(row.get(key)))
                for key in sorted({key for row in snapshots for key, value in row.items() if number(value)})}),
        facts=dict(calls=len(facts), measured={key: sum(row.get(key, 0) for row in facts if number(row.get(key)))
            for key in sorted({key for row in facts for key, value in row.items() if number(value)})}),
        correspondence=dict(calls=len(correspondence), cold_computations=sum(row.get("cache_hit") is False for row in correspondence),
            cache_hits=sum(row.get("cache_hit") is True for row in correspondence), request_wall_s=summed(correspondence, "wall_s"),
            request_CPU_s=summed(correspondence, "CPU_s"), maximum_in_memory_array_bytes=maximum(correspondence, "in_memory_array_bytes"),
            scope="Component request timers are nested in facts and tools. Per-view original computation stages and local-support diagnostics are retained separately."),
        image_deliveries=dict(by_kind=dict(Counter(row["image_delivery_kind"] for row in rows if row.get("image_delivery_kind"))),
            preview_observations=len(previews), cache_hits=sum(row.get("cache_hit") is True for row in previews),
            render_invocations=sum(row.get("render_invoked") is True for row in previews),
            unique_render_job_labels=sorted({row["render_job_label"] for row in previews if row.get("render_job_label")}),
            observations=previews),
        timing_scope="Tools, snapshot creation, facts, Python executors and Blender jobs are nested under the calling session or preflight.")


def collect_session(stage, route):
    folder = HERE / "private/consumers" / stage / TASK_ID / route
    path = folder / "CONSUMER.json"
    record = read(path, {})
    claim = read(folder / "CLAIM.json", {})
    bridge_path = folder / "bridge/BRIDGE_RESULT.json"
    bridge = read(bridge_path, {})
    tools = collect_tools((folder / "bridge").glob("tool_*/COST.json"))
    python = [collect_python(path) for path in sorted((folder / "bridge").glob("tool_*/python/EXECUTION.json"))]
    retained_fields = ("status", "wall_s", "prompt_to_final_s", "pre_session_prepare_wall_s", "model", "reasoning_effort",
        "requested_service_tier", "resolved_model_settings", "usage", "usage_rows", "fees", "provider_requests",
        "provider_retry_observations", "input_prompt_UTF8_bytes", "output_text_UTF8_bytes", "initial_image_count",
        "initial_image_bytes", "public_image_count", "public_image_bytes", "MCP_image_count", "MCP_image_bytes",
        "actual_image_delivery_verified", "valid_completion", "process_cleanup", "readers_stopped", "safe_to_continue",
        "tool_count", "errors", "CLI_identity", "helper_identity", "started_ns", "final_received_ns")
    state_path = HERE / "private/sessions" / (stage + "_" + TASK_ID + "_" + route) / "session.json"
    state = read(state_path, {})
    return dict(stage=stage, task_id=TASK_ID, route=route, **{key: record[key] for key in retained_fields if key in record},
        transport_status=record.get("status", "not_started"), claim=claim,
        artifacts=identities(folder / name for name in ("CONSUMER.json", "CLAIM.json", "PROMPT.txt", "events.jsonl",
            "stdout.raw.bin", "stderr.raw.bin", "PUBLIC_FINAL.txt", "final.txt", "malformed_stdout.bin")),
        bridge=dict(record=identity(bridge_path) if bridge_path.exists() else None, closed=bridge.get("closed"),
            process_id=bridge.get("process_id"), process_metrics=bridge.get("process_metrics") or {}, wall_s=bridge.get("wall_s")),
        actual_saved_session=dict(record=identity(state_path) if state_path.exists() else None,
            version=state.get("version"), operation_count=len(state.get("operations", [])),
            pending=state.get("pending"), operations=state.get("operations", [])),
        delivery=tool_summary(tools), tools=tools, python=python_summary(python), python_executions=python)


def observed_launch_interval(record):
    wall = record.get("full_process_wall_s")
    stdout = record.get("stdout")
    if not number(wall) or wall < 0 or not stdout:
        return None
    path = Path(stdout)
    if not path.is_absolute():
        path = HERE / path
    if not path.is_file():
        return None
    observed = path.stat()
    started = getattr(observed, "st_birthtime", observed.st_ctime)
    return dict(start_epoch=started, end_epoch=started + wall,
        source="Original stdout Windows creation time (st_birthtime, fallback st_ctime) plus monitor full_process_wall_s",
        stdout_path=str(path), observed_wall_s=wall)


def collect_roots():
    # run_measured retains the same monitor record in measured and processes.
    launches = {}
    paths = sorted((HERE / "private/measured").glob("*.json")) + sorted((HERE / "private/processes").glob("*.json"))
    for path in paths:
        record = read(path, {})
        command = record.get("command") or []
        if not command or Path(str(command[0])).name.casefold() == "blender.exe":
            continue
        key = (record.get("pid"), record.get("label", path.stem), tuple(command))
        if key in launches:
            launches[key]["aliases"].append(identity(path))
            continue
        launches[key] = dict(record=identity(path), aliases=[], **process_fields(record),
            phase=phase_for(record["command"], record.get("label", path.stem)))
    rows = list(launches.values())
    for row in rows:
        row["observed_launch_interval"] = observed_launch_interval(row)
    for row in rows:
        child_interval = row["observed_launch_interval"]
        row["enclosing_monitored_launches"] = [parent["record"]["path"] for parent in rows if parent is not row
            and row.get("pid") is not None and parent.get("pid") != row["pid"]
            and row["pid"] in {process.get("pid") for process in parent.get("process_tree", [])}
            and child_interval is not None and parent["observed_launch_interval"] is not None
            and parent["observed_launch_interval"]["start_epoch"] <= child_interval["start_epoch"]
            and child_interval["end_epoch"] <= parent["observed_launch_interval"]["end_epoch"]]
    outer = [row for row in rows if not row["enclosing_monitored_launches"]]
    phases = {phase: process_summary([row for row in outer if row["phase"] == phase]) for phase in sorted({row["phase"] for row in outer})}
    return dict(unique_launches=rows, outer_root_totals=process_summary(outer), phase_totals=phases,
        accounting="Duplicate monitor copies share one launch. An enclosing monitored launch requires distinct root PIDs, child PID membership in the parent's observed process tree, and complete containment of the stdout-creation-plus-wall observation interval. Unknown intervals retain the launch in outer totals. Descendant monitored launches remain listed. Root trees include their nested Blender, CLI, bridge and Python children. Phase wall sums can overlap.")


def job_scope(job, script, label):
    paths = [str(value) for value in job.values() if isinstance(value, str)]
    components = {part.casefold() for value in paths for part in Path(value).parts}
    formal = next((stage + "_" + TASK_ID + "_" + route for stage, route in ORDER
        if (stage + "_" + TASK_ID + "_" + route).casefold() in components), None)
    script_name = Path(script.get("path", "")).name
    if label in ("construct_fixed_normal", "read_fixed_normal", "construct_fixed_current", "read_fixed_current"):
        return "fixed_saved_input_read", formal
    if label in ("input_normal_render", "input_current_render"):
        return "initial_rendering", formal
    control = any("control" in part for part in components)
    if control:
        return ("actual_preview_control" if script_name == "blender_render.py" else "actual_restore_control"), formal
    if formal:
        if "final_verify" in components:
            return "final_independent_read", formal
        if "results" in components and script_name == "blender_render.py":
            return "final_saved_render", formal
        if "previews" in components:
            return "formal_saved_preview", formal
        return ("formal_edit" if script_name == "blender_edit.py" else "formal_readback"), formal
    return "other_actual_job", formal


def collect_jobs():
    jobs_root = (HERE / "private/jobs").resolve()
    directories = {str(path.parent.resolve()).casefold(): path.parent.resolve()
        for path in jobs_root.glob("*/job.json")}
    process_records = {}
    for path in sorted((HERE / "private/processes").glob("*.json")):
        process = read(path, {})
        command = process.get("command") or []
        if not command or Path(str(command[0])).name.casefold() != "blender.exe" or "--job" not in command:
            continue
        folder = Path(command[command.index("--job") + 1]).resolve().parent
        if not folder.is_relative_to(jobs_root):
            continue
        key = str(folder).casefold()
        directories[key] = folder
        process_records.setdefault(key, []).append((path, process))
    rows = []
    for key, folder in sorted(directories.items()):
        run_path = folder / "run.json"
        run = read(run_path, {})
        aliases = process_records.get(key, [])
        process = aliases[0][1] if aliases else run.get("process", {})
        job = read(folder / "job.json", {})
        receipt_path = folder / "receipt.json"
        receipt = read(receipt_path, run.get("receipt", {}))
        command = process.get("command", [])
        script = run.get("script", {})
        if not script and "--python" in command:
            script = dict(path=command[command.index("--python") + 1])
        scope, formal = job_scope(job, script, folder.name)
        rows.append(dict(label=folder.name, actual_launch_started=process.get("pid") is not None,
            record=identity(run_path) if run_path.exists() else None,
            process_record=identity(aliases[0][0]) if aliases else None,
            process_records=identities(path for path, _ in aliases), script=script, scope=scope,
            operation=job.get("operation", "edit" if Path(script.get("path", "")).name == "blender_edit.py" else None),
            formal_consumer=formal, wall_s=run.get("wall_s", process.get("full_process_wall_s")),
            process=process_fields(process), receipt_status=receipt.get("status"),
            receipt_execution=receipt.get("execution"),
            evidence=identities([folder / "job.json", receipt_path, *folder.glob("*.py")])))
    launched = [row for row in rows if row["actual_launch_started"]]
    processes = [row["process"] for row in launched]
    return dict(calls=len(launched), retained_job_directories=len(rows),
        by_script=dict(Counter(Path(row["script"].get("path", "unknown")).name for row in launched)),
        by_scope={scope: dict(calls=sum(row["scope"] == scope for row in launched),
            nested_wall_s=summed([row for row in launched if row["scope"] == scope], "wall_s"),
            process_totals=process_summary([row["process"] for row in launched if row["scope"] == scope]))
            for scope in sorted({row["scope"] for row in launched})},
        formal_consumer_jobs=sum(row["formal_consumer"] is not None for row in launched),
        formal_consumer_edit_jobs=sum(row["formal_consumer"] is not None and Path(row["script"].get("path", "")).name == "blender_edit.py" for row in launched),
        nested_job_wall_s=summed(launched, "wall_s"), process_totals=process_summary(processes), jobs=rows,
        accounting="Each resolved owned job directory is counted once. Its run receipt and matching Blender --job process receipts are aliases. Failed/incomplete launches are retained. Software correspondence, ray and in-memory fitting audits have zero actual Blender jobs. Nested job costs remain within their enclosing roots.")


def collect_local_delivery():
    paths = [path for path in (HERE / "private").rglob("COST.json") if "consumers" not in path.relative_to(HERE / "private").parts]
    executions = [path for path in (HERE / "private").rglob("EXECUTION.json") if "consumers" not in path.relative_to(HERE / "private").parts]
    scopes = sorted({path.relative_to(HERE / "private").parts[0] for path in paths + executions})
    rows = []
    for scope in scopes:
        tools = collect_tools(path for path in paths if path.relative_to(HERE / "private").parts[0] == scope)
        workers = [collect_python(path) for path in sorted(executions) if path.relative_to(HERE / "private").parts[0] == scope]
        rows.append(dict(scope=scope, delivery=tool_summary(tools), tools=tools,
            python=python_summary(workers), python_executions=workers))
    return rows


def collect_evidence():
    paths = {path for path in HERE.glob("*.json") if path.name not in ("COSTS.json", "MANIFEST.json", "HANDOFF.json")}
    for pattern in ("private/analysis/**/*.json", "private/*preflight/**/RESULT.json",
                    "private/*preflight/**/RUNS.json", "private/*preflight/**/FAIL*.json",
                    "private/*preflight/**/METADATA*.json", "private/results/*SUMMARY*.json",
                    "private/results/*VERIFICATION*.json", "private/construction_quality/*SUMMARY*.json",
                    "private/diagnostics/PREPARATION.json", "private/diagnostics/UNSCORED_EXECUTION.json",
                    "private/diagnostics/FAILED_*.json", "private/*COST*.json", "private/*AUDIT*.json"):
        paths.update(HERE.glob(pattern))
    rows = []
    for path in sorted(paths):
        record = read(path, {})
        row = dict(record=identity(path), timings=timing_observations(record), observation=record)
        if isinstance(record, dict):
            row["status"] = record.get("status")
            row["attempt_statuses"] = [item.get("status") for item in record.get("attempts", []) if isinstance(item, dict)]
            row["stage_metadata"] = {key: record[key] for key in ("stage_costs", "consumer_changes",
                "first_stage_failure", "dominant_failure", "selection", "additional_costs") if key in record}
        rows.append(row)
    return rows


def collect_preflight_artifacts():
    private = HERE / "private"
    scopes = [path for path in private.iterdir() if path.is_dir()
        and ("preflight" in path.name or path.name == "control")]
    scopes.extend(path for path in (private / "sessions").glob("*") if path.is_dir()
        and any(label in path.name for label in ("preflight", "protocol", "control")))
    artifacts = identities(path for scope in scopes for path in scope.rglob("*") if path.is_file())
    return dict(scopes=[path.relative_to(HERE).as_posix() for path in sorted(scopes)],
        retained_files=len(artifacts), retained_file_bytes=sum(row["bytes"] for row in artifacts),
        artifacts=artifacts,
        cached_packet_artifacts=[row for row in artifacts if "/snapshots/" in row["path"] or "/references/" in row["path"]],
        accounting="Exact retained preflight and control file byte counts and SHA256 include raw protocol replies, errors, source, access records and caches. Tool/executor receipts carry the full byte and cache measurements. Artifact identities are evidence references and add no execution calls.")


def collect_component_evidence():
    paths = []
    for pattern in ("*CORRESPONDENCE*.json", "*RAY*.json", "*FIT*.json", "*OPTIMIZATION*.json",
                    "private/correspondence_baseline/**/*", "private/correspondence_scores/**/*",
                    "private/fit_audits/**/*", "private/f/**/correspondence/SUMMARY.json",
                    "private/f/**/correspondence/BINDING.json", "private/f/**/correspondence/ARRAYS.npz",
                    "private/f/**/LOCAL_SUPPORT.json"):
        paths.extend(path for path in HERE.glob(pattern) if path.is_file())
    computation_records = []
    for path in sorted(set(paths)):
        if path.name in ("SUMMARY.json", "LOCAL_SUPPORT.json"):
            record = read(path)
            computation_records.append(dict(record=identity(path), timings=timing_observations(record), observation=record))
    return dict(artifacts=identities(paths), computation_records=computation_records,
        accounting="Component, ray and fitting evidence has separate local receipts. Hidden-label scores execute after the derived correspondence or consumer stage is frozen. Component preparation and cache costs are nested within facts/tool or preflight scopes.")


def collect_freezes():
    rows = []
    for name in ("PLAN.json", "PLAN_FREEZE.json", "TOOL_FREEZE_v1.json", "TOOL_FREEZE_v2.json", "OPTIMIZATION_BINDING.json"):
        path = HERE / name
        if path.exists():
            record = read(path)
            rows.append(dict(record=identity(path), frozen=record))
    return rows


def collect(allow_partial=False):
    started, cpu = time.perf_counter(), time.process_time()
    sessions = [collect_session(stage, route) for stage, route in ORDER]
    incomplete = [dict(stage=row["stage"], route=row["route"], status=row["transport_status"]) for row in sessions
        if row["transport_status"] not in TERMINAL_STATUSES]
    if incomplete and not allow_partial:
        raise RuntimeError("four_terminal_consumers_required_" + json.dumps(incomplete))
    usage = Counter()
    for row in sessions:
        usage.update({key: value for key, value in (row.get("usage") or {}).items() if number(value)})
    all_tools = [call for row in sessions for call in row["tools"]]
    all_python = [execution for row in sessions for execution in row["python_executions"]]
    roots = collect_roots()
    now = time.time()
    stages = {}
    for stage in ("v1", "v2"):
        selected = [row for row in sessions if row["stage"] == stage]
        stages[stage] = dict(terminal=sum(row["transport_status"] in TERMINAL_STATUSES for row in selected),
            consumer_wall_s=summed(selected, "wall_s"),
            usage=dict(sum((Counter(row.get("usage") or {}) for row in selected), Counter())),
            delivery=tool_summary([tool for row in selected for tool in row["tools"]]),
            python=python_summary([execution for row in selected for execution in row["python_executions"]]),
            monitored_roots=roots["phase_totals"].get("consumer_" + stage))
    result = dict(cycle_id="M6-IMAGE-CORRESPONDENCE-005", source_cycle_id="M6-IMAGE-CORRESPONDENCE-005", partial=bool(incomplete), incomplete=incomplete,
        snapshot_UTC=datetime.fromtimestamp(now, timezone.utc).isoformat(),
        end_to_end=dict(start_epoch=TASK_STARTED_EPOCH, start_source="AL task registration write_version 47",
            snapshot_epoch=now, elapsed_through_this_cost_snapshot_s=now - TASK_STARTED_EPOCH,
            scope="Fixed saved-input reuse and fresh QA, correspondence/ray/fitting preflights, four consumers, independent scoring/rendering, optimization, authoring and waits through this snapshot. Subsequent commit/callback time is separately observed. Whole-task CPU/RSS remain unmeasured."),
        actual_Pro=dict(started=sum(row["claim"].get("launch_state") in ("launching", "launched") for row in sessions),
            terminal=len(sessions) - len(incomplete), completed=sum(row["transport_status"] == "completed" for row in sessions),
            failed=sum(row["transport_status"] == "failed" for row in sessions),
            requested_model="gpt-6.1-sol", requested_reasoning_effort="medium", wall_s=summed(sessions, "wall_s"),
            usage=dict(usage), usage_accounting="Cached-input/cache-write counters are reported usage subsets and are not added to input. Reasoning counters are output subsets and are not added to output. Usage rows retain provider observations and are not summed again.",
            resolved_provider_settings=None, fees=None, sessions=sessions),
        actual_consumer_delivery=dict(delivery=tool_summary(all_tools), python=python_summary(all_python),
            bridge_CPU_s=summed([row["bridge"]["process_metrics"] for row in sessions], "CPU_s"),
            maximum_bridge_peak_RSS_bytes=maximum([row["bridge"]["process_metrics"] for row in sessions], "peak_working_set_bytes"),
            image_scope="Server-to-active-CLI MCP ImageContent PNG/base64/stdio counts come from each unique tool receipt. Initial CLI image counters are separate observations. Provider image preprocessing and encoding are unmeasured."),
        actual_Blender=collect_jobs(), monitored_numerical_roots=roots, phase_costs=stages,
        local_preflight_delivery=collect_local_delivery(), metered_evidence=collect_evidence(),
        preflight_artifacts=collect_preflight_artifacts(), correspondence_evidence=collect_component_evidence(),

        exact_frozen_sources=collect_freezes(), full_current_source_identities=identities(HERE.glob("*.py")),
        additional_analysis_source_identities=identities([HERE.parent / "m6_refine_001/analyze_consumers.py"]),
        accounting=[
            "There is no additive grand total across nested timers. Pro session wall includes tools and their Python, facts and Blender work.",
            "Monitor-copy identities are retained. Each unique root launch and each unique Blender job is counted once within its own scope.",
            "Process-tree CPU is the monitor's tree_cpu_s. Process CPU is separately reported. RSS totals always use maxima. Short unsampled descendants remain unmeasured.",
            "The v1/v2 consumer phase and other phase root totals cover their named scopes. Root CPU/RSS include children and cannot be added to Python, bridge or Blender subsets.",
            "Preflight evidence retains all recorded attempts, including failures and rejected-access tests. Latest pass files do not replace earlier raw execution receipts.",
            "Evidence timing paths preserve cumulative and per-attempt observations without summing these representations together.",
        ],
        unmeasured=dict(provider_fees=None, resolved_provider_settings=None, provider_requests_and_hidden_retries=None,
            provider_image_encoding_and_preprocessing=None, root_model_usage_and_fees=None, collaboration_model_usage_and_fees=None,
            whole_task_CPU_and_RSS=None,
            explanation="Preparation/agent cost metadata is preserved verbatim where recorded. The collector does not infer model charges or unrecorded usage from wall time."),
        training=0, Google_API_calls=0, paid_API_calls=0,
        collector_wall_s=time.perf_counter() - started, collector_parent_CPU_s=time.process_time() - cpu)
    snapshot_epoch = time.time()
    result["snapshot_UTC"] = datetime.fromtimestamp(snapshot_epoch, timezone.utc).isoformat()
    result["end_to_end"].update(snapshot_epoch=snapshot_epoch,
        elapsed_through_this_cost_snapshot_s=snapshot_epoch - TASK_STARTED_EPOCH)
    result["collector_wall_s"] = time.perf_counter() - started
    result["collector_parent_CPU_s"] = time.process_time() - cpu
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-partial", action="store_true", help="Print a read-only diagnostic snapshot without writing COSTS.json")
    args = parser.parse_args()
    result = collect(args.allow_partial)
    if args.allow_partial:
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return
    destination = HERE / "COSTS.json"
    temporary = destination.with_suffix(".json.next")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")
    temporary.replace(destination)
    print(json.dumps(dict(Pro=result["actual_Pro"]["started"], terminal=result["actual_Pro"]["terminal"],
        consumer_wall_s=result["actual_Pro"]["wall_s"], Blender=result["actual_Blender"]["calls"],
        elapsed_s=result["end_to_end"]["elapsed_through_this_cost_snapshot_s"])))


if __name__ == "__main__":
    main()
