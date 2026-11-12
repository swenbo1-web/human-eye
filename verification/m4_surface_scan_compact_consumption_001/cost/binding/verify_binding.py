"""Offline post-seal binding audit. Reads originals and writes only this directory.

Run with --write-report to publish deterministic derived JSON and a Chinese report.
Without that option, independently rechecks all assertions and prints a summary.
No product imports, live RPC, model calls, Blender calls, or Git mutations.
"""
import argparse
import ast
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tomllib
import zipfile


OUT = Path(__file__).resolve().parent
BATCH = OUT.parents[1]
REPO = BATCH.parents[1]
PREFIX = BATCH.relative_to(REPO).as_posix() + "/"
ADMIN_COMMIT = "1f1a23dda3413721d6c71bd1db95f3a40a7c4977"
DELIVERY = "f5cfcf5e4768b1b6c31127b5d4a6c1227b8d7907"
PREPARATION = "3a1ba86c5fce2fe125671cc68a84b14031d318cb"
SEAL_SHA = "c054d8b5ea8ef672a9b3558c9fd33d485e87593fc53c87df6f2ec0ba6a82d9eb"
COST_PLAN_SHA = "ef73d9a91d237141f7c90da4685a8207bdaf99fee82e05c19edd4a1af71193f5"
PUBLIC_SHA = "03c566a5438fad7454b1d9f91157c3627a5fbd3740856972b61a353338fec101"
INITIAL_PUBLIC_SHA = "1b8136e92e8533d6a7b95dddf952165ed58baff206c4551aa473728cbf20b8b2"
R2_ZIP_SHA = "5d2ca81f18285da1fff1a05b9c0c03deb97966f57db86fa022c8ecc0b091f54f"
ORDER = ["N1", "O1", "C1", "O2", "C2", "N2", "C3", "N3", "O3"]
FAILURES = {"N2", "O2"}
PROFILES = {
    "O": {
        "commit": "c1cb2da32034e056a270384e691a2cde8dddbc0d",
        "source": "c4832b1a1ced9438f904e25a431e2327c2d7532e2f4efbb34e34ce58a7ed1943",
        "version": "9.7.2+m4.surface.scan.opt1.r1",
        "wheel": "1ad6cd9ad3eb4ca27b62b49e3fa1e2ad66c00f163a80cf268b033d06b7bb4d79",
    },
    "C": {
        "commit": "452b44d2dcf231d6675bef54e568db0431a29261",
        "source": "4067c864c3db1ba586cd7179e6430db5acc4d71675b5295416d471632851a9f6",
        "version": "9.7.2+m4.surface.scan.compact.r1",
        "wheel": "f71c299926ebb38b1c09a2ca9b26a90416810b2407e3b955a43502ad86a55792",
    },
}
inventory = {}
checks = []


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf8")


def pretty(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf8")


def check(condition, label):
    checks.append({"check": label, "passed": bool(condition)})
    if not condition:
        raise AssertionError(label)


def raw(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    try:
        name = path.relative_to(REPO).as_posix()
    except ValueError:
        name = str(path)
    record = {"path": name, "bytes": len(data), "sha256": digest(data)}
    if name in inventory:
        check(inventory[name] == record, "input stable on repeat read " + name)
    inventory[name] = record
    return data


def obj(path):
    return json.loads(raw(path))


def records(path):
    return [json.loads(line) for line in raw(path).splitlines() if line]


def git_tree(commit):
    result = subprocess.run(
        ["git", "ls-tree", "-rz", commit], cwd=REPO,
        capture_output=True, check=True,
    )
    answer = {}
    for item in result.stdout.split(b"\0"):
        if item:
            metadata, name = item.split(b"\t", 1)
            answer[name.decode("utf8")] = metadata.split()[2].decode("ascii")
    return answer


def verify_git_bytes(data, path, tree, label):
    blob_id = hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()
    check(tree.get(path) == blob_id, label)


def manifest(folder):
    answer = []
    for path in sorted(folder.rglob("*"), key=lambda item: item.relative_to(folder).as_posix()):
        if path.is_file():
            data = raw(path)
            answer.append({"path": path.relative_to(folder).as_posix(), "bytes": len(data), "sha256": digest(data)})
    return answer


def project_request(value):
    answer = {k: copy.deepcopy(v) for k, v in value.items() if k not in ("id", "jsonrpc", "_meta")}
    if isinstance(answer.get("params"), dict):
        answer["params"].pop("_meta", None)
    return answer


def project_response(value):
    return {k: v for k, v in value.items() if k not in ("id", "jsonrpc", "_meta")}


def projected_cli_item(value):
    keys = ("type", "tool", "server", "arguments", "result", "error", "status", "command")
    return {key: value[key] for key in keys if key in value}


def configs(argv):
    return [argv[index + 1] for index, item in enumerate(argv) if item == "-c"]


def path_equal(first, second):
    return Path(first).resolve() == Path(second).resolve()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()
    delivery_tree = git_tree(DELIVERY)
    prepared_tree = git_tree(PREPARATION)
    admin_tree = git_tree(ADMIN_COMMIT)
    seal_bytes = raw(OUT / "inputs/QUALITY_SEAL.json")
    cost_plan_bytes = raw(OUT / "inputs/COST_PLAN.md")
    check(digest(seal_bytes) == SEAL_SHA, "administrator seal exact SHA")
    check(digest(cost_plan_bytes) == COST_PLAN_SHA, "administrator cost plan exact SHA")
    verify_git_bytes(seal_bytes, "verification/fixes/20261113_m4_surface_scan_compact_quality_review/QUALITY_SEAL.json", admin_tree, "seal at administrator commit")
    verify_git_bytes(cost_plan_bytes, "docs/M4_SURFACE_SCAN_COMPACT_CONSUMPTION_001_COST_PLAN.md", admin_tree, "cost plan at administrator commit")
    seal = json.loads(seal_bytes)
    check(seal["delivery_commit"] == DELIVERY and seal["preparation_commit"] == PREPARATION, "seal delivery and preparation")
    check(seal["quality_before_cost"] and not seal["private_mapping_opened"] and not seal["cost_usage_analysis_performed"], "quality precedes private mapping and costs")
    check(seal["primary_counts"] == {"complete_correct": 7, "incomplete": 0, "incorrect": 0, "execution_failure": 2, "not_run": 0}, "sealed strict classification")
    check(seal["content_counts"] == {"complete_correct": 9}, "sealed content classification")
    check(seal["matching_facts_correct"] == seal["matching_facts_required"] == 639, "sealed facts 639 of 639")
    plan_bytes = raw(BATCH / "PLAN.json")
    check(digest(plan_bytes) == "e12e20c08e5801e317c847f14a9eb953179c1f8a7fabc5b4b78e24a860d80322", "frozen plan SHA")
    verify_git_bytes(plan_bytes, PREFIX + "PLAN.json", prepared_tree, "plan at prepared commit")
    plan = json.loads(plan_bytes)
    sequence = obj(BATCH / "SEQUENCE.json")
    mapping = obj(BATCH / "private/ANON_MAP.json")
    check([row["cell"] for row in sequence["sequence"]] == ORDER, "frozen order")
    check(sequence["serial"] and sequence["replacements"] == 0, "serial no replacements")
    check(mapping["created_before_consumers"], "private mapping predates consumers")
    check([{k: v for k, v in row.items() if k != "anonymous_id"} for row in mapping["rows"]] == sequence["sequence"], "mapping to real sequence")
    check(len({row["anonymous_id"] for row in mapping["rows"]}) == 9, "nine unique anonymous IDs")
    seal_answers = {row["anonymous_id"]: row for row in seal["answers"]}
    check(set(seal_answers) == {row["anonymous_id"] for row in mapping["rows"]}, "seal includes exact private anonymous IDs")
    run = obj(BATCH / "RUN_RESULT.json")
    check([row["cell"] for row in run["records"]] == ORDER, "actual run order")
    check(run["stop"] is None and run["started_cells"] == run["maximum_consumers"] == 9, "nine planned consumers and no stop")
    check(run["all_planned_dispatched"] and run["no_replacements"], "all fixed cells dispatched once")
    check(run["batch_wall_ns"] == run["batch_ended_ns"] - run["batch_started_ns"], "batch clock exact arithmetic")
    source = obj(BATCH / "preflight/SOURCE_BINDING.json")
    qualification = obj(BATCH / "QUALIFICATION_SEAL.json")
    check(digest(raw(BATCH / "QUALIFICATION_SEAL.json")) == source["qualification_seal_sha256"], "qualification seal retained")
    baseline_paths = qualification["existing_promises"]
    baseline_path = next(Path(p) for p in baseline_paths if p.endswith("BASE_SNAPSHOT.json"))
    truth_path = next(Path(p) for p in baseline_paths if p.endswith("BASE_TRUTH.json"))
    baseline_bytes = raw(baseline_path)
    check(digest(baseline_bytes) == seal["snapshot_sha256"] == source["snapshot_sha256"], "frozen baseline snapshot")
    check(digest(raw(truth_path)) == seal["truth_sha256"] == source["truth_sha256"], "frozen independent truth")
    baseline = json.loads(baseline_bytes)
    asset_sha = plan["inputs"]["scene_sha256"]
    prompt_sha = plan["inputs"]["prompt_sha256"]
    check(digest(raw(BATCH / "input/scene.blend")) == asset_sha, "same original scene")
    check(digest(raw(BATCH / "input/PROMPT.txt")) == prompt_sha, "same original prompt")
    prior_records = []
    for name, expected_sha in [
        ("preflight/POSTRUN_INTEGRITY.json", "4ddf4a4f1c430332515fd7f379f37e111f5cdb998ff306634e8dd8b7e377e0c0"),
        ("scoring/FORMAL_HANDOFF_CHECK.json", "edf7afcdbcc1da72ae8bf358c628f1169801e3aee97b33cfd578fb13373320c4"),
    ]:
        data = raw(BATCH / name)
        check(digest(data) == expected_sha and json.loads(data)["status"] == "pass", "reuse same-byte accepted record " + name)
        prior_records.append({"path": name, "sha256": expected_sha, "checks": json.loads(data)["checks"]})
    installations = {}
    for group, expected in PROFILES.items():
        ready_bytes = raw(BATCH / f"installations/{group}_READY.json")
        ready = json.loads(ready_bytes)
        binding = source["profiles"][group]
        check(digest(ready_bytes) == binding["installation_ready_sha256"], group + " same-byte installation ready")
        check(ready == plan["installations"][group], group + " frozen installation")
        check(ready["commit"] == binding["product_commit"] == expected["commit"], group + " source commit")
        check(ready["source_sha256"] == binding["source_sha256"] == expected["source"], group + " source hash")
        check(ready["version"] == expected["version"] and ready["wheel_sha256"] == expected["wheel"], group + " version and wheel")
        check(ready["installed_identity_passed"] and binding["commit_wheel_install_equal"], group + " accepted source wheel install equivalence")
        check(ready["source_count"] == binding["source_count"] == len(binding["source_manifest"]) == 138, group + " source count")
        check(digest(raw(Path(binding["previous_actual_tools_list"]))) == binding["previous_actual_tools_list_sha256"], group + " prior actual schema unchanged")
        check(digest(raw(Path(ready["entry"]))) == ready["launcher_sha256"], group + " actual launch entry unchanged")
        installations[group] = ready
    public = BATCH / "quality/public"
    initial_public = BATCH / "runtime/handoff_01/public"
    final_manifest = manifest(public)
    initial_manifest = manifest(initial_public)
    check(len(final_manifest) == len(initial_manifest) == 42, "both public packages contain 42 files")
    check(digest(canonical(final_manifest)) == seal["public_canonical_sha256"] == PUBLIC_SHA, "r2 public canonical")
    check(digest(canonical(initial_manifest)) == INITIAL_PUBLIC_SHA, "initial public canonical kept separately")
    r2_data = raw(BATCH / "quality/SURFACE_SCAN_COMPACT_ANONYMOUS_QUALITY_001_r2.zip")
    check(digest(r2_data) == seal["r2_zip_sha256"] == R2_ZIP_SHA, "r2 ZIP sealed SHA")
    with zipfile.ZipFile(io.BytesIO(r2_data)) as archive:
        check(len(archive.namelist()) == len(set(archive.namelist())) == 42, "r2 ZIP names unique")
        expected_names = {row["path"] for row in final_manifest}
        check(set(archive.namelist()) == expected_names, "r2 ZIP exact file set")
        for name in archive.namelist():
            check(archive.read(name) == raw(public / name), "r2 ZIP exact file " + name)
    redaction = obj(BATCH / "quality/ADMIN_REDACTION.json")
    provenance = obj(BATCH / "runtime/handoff_01/private/PROVENANCE.json")
    check(provenance["fixed_anonymous_map"] == mapping, "initial private provenance exact mapping")
    check(digest(raw(BATCH / "runtime/handoff_01/private/PROVENANCE.json")) == redaction["original_PROVENANCE_sha256"], "initial provenance unchanged")
    check(provenance["public_files_sha256"] == {row["path"]: row["sha256"] for row in initial_manifest}, "initial provenance all public files")
    for name, sha in redaction["historical_zip_sha256_unchanged"].items():
        check(digest(raw(BATCH / "quality" / name)) == sha, "historical original ZIP unchanged")
    original_index_bytes = raw(initial_public / "INDEX.json")
    original_index = json.loads(original_index_bytes)
    final_index_bytes = raw(public / "INDEX.json")
    final_index = json.loads(final_index_bytes)
    restored = copy.deepcopy(final_index)
    check(len(redaction["removals"]) == 2, "exactly two administrative removals")
    expected_pointers = {"$/answers/1/consumer_execution_errors/0/perf_ns", "$/answers/3/consumer_execution_errors/0/perf_ns"}
    check({row["pointer"] for row in redaction["removals"]} == expected_pointers, "only known error envelope timestamps removed")
    for removal in redaction["removals"]:
        index = int(removal["pointer"].split("/")[2])
        original_error = original_index["answers"][index]["consumer_execution_errors"][0]
        target = restored["answers"][index]["consumer_execution_errors"][0]
        check(set(original_error) == {"event", "perf_ns"} and set(target) == {"event"}, "error envelope exact keys")
        check(target["event"] == original_error["event"], "error payload and message preserved")
        check(digest(canonical(original_error["perf_ns"])) == removal["removed_value_canonical_sha256"], "removed timestamp exact original value")
        check(digest(canonical(original_error["event"])) == removal["event_payload_canonical_sha256"], "error payload canonical")
        target["perf_ns"] = original_error["perf_ns"]
    check(restored == original_index and pretty(restored) == original_index_bytes, "reinsertion restores source INDEX exact bytes")
    check(digest(final_index_bytes) == redaction["final_INDEX_sha256"], "final INDEX exact SHA")
    for row in final_manifest:
        if row["path"] != "INDEX.json":
            check(raw(public / row["path"]) == raw(initial_public / row["path"]), "41 business files unchanged " + row["path"])
    public_answers = {row["anonymous_id"]: row for row in final_index["answers"]}
    old_public_answers = {row["anonymous_id"]: row for row in original_index["answers"]}
    provenance_answers = {row["mapping"]["anonymous_id"]: row for row in provenance["answers"]}
    frozen_cli = obj(BATCH / "preflight/CLI_ARGV.json")["argv_by_group"]
    native_schema = obj(BATCH / "schemas/COMMON_NATIVE.json")
    native_source_bytes = raw(Path(source["common_native_source"]))
    check(digest(native_source_bytes) == source["common_native_source_sha256"], "accepted common native source unchanged")
    native_tree = ast.parse(native_source_bytes.decode("utf8"))
    native_literal = next(ast.literal_eval(node.value) for node in native_tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "NATIVE" for target in node.targets))
    check(native_literal == native_schema, "common native literal equals frozen schema")
    native_schema_sha = digest(json.dumps(native_literal, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf8") + b"\n")
    cells = []
    threads = set()
    worker_pids = set()
    runtime_pids = set()
    archive_file_count = 0
    business_count = 0
    cli_business_count = 0
    previous_publication = None
    for map_row, run_row in zip(mapping["rows"], run["records"]):
        cell = map_row["cell"]
        group = map_row["group"]
        label = cell + " "
        internal = "N" if group == "N" else "P"
        cell_dir = BATCH / "cells" / cell
        owner = cell_dir / "owner"
        consumer = obj(cell_dir / "CONSUMER.json")
        config = obj(cell_dir / "ACTOR_CONFIG.json")
        launch = obj(cell_dir / "ACTOR_LAUNCH.json")
        identity = obj(owner / "IDENTITY.json")
        endpoint = obj(cell_dir / "ENDPOINT.json")
        finish = obj(cell_dir / "OWNER_FINISH.json")
        close = obj(owner / "CLOSE.json")
        timing = obj(cell_dir / "CELL_FINAL_TIMING.json")
        publication = obj(cell_dir / "CELL_TIMING_PUBLICATION.json")
        sealed = seal_answers[map_row["anonymous_id"]]
        anonymous = public_answers[map_row["anonymous_id"]]
        original_anonymous = old_public_answers[map_row["anonymous_id"]]
        private = provenance_answers[map_row["anonymous_id"]]
        check(private["mapping"] == map_row and private["issues"] == [], label + "private original provenance mapping")
        check(consumer == run_row["consumer"], label + "batch and private consumer exact agreement")
        check(finish == consumer["owner_finish"] == run_row["finish"], label + "finish receipts identical")
        check(close == finish["close"], label + "close receipts identical")
        check(consumer["cell"] == cell and consumer["group"] == config["group"] == identity["group"] == internal, label + "actual internal arm")
        check(consumer["external_group"] == config["external_group"] == identity["external_group"] == group, label + "actual external arm")
        check(all(consumer[key] == map_row[key] for key in ("round", "slot", "task")), label + "fixed slot round task")
        check(identity["actor_pid"] == endpoint["actor_pid"] == close["actor_pid"], label + "actual owner PID")
        check(identity["actor_parent_pid"] == close["actor_parent_pid"] == launch["pid"] == finish["actor_pid"], label + "owner launcher parent")
        check(config["asset_sha256"] == identity["asset_sha256"] == asset_sha, label + "actual asset identity")
        check(consumer["input_sha256"] == prompt_sha and consumer["input_text_bytes"] == len(raw(BATCH / "input/PROMPT.txt")), label + "same input prompt")
        expected_state = "failed" if cell in FAILURES else "completed"
        expected_primary = "execution_failure" if cell in FAILURES else "complete_correct"
        check(consumer["status"] == sealed["execution_state"] == anonymous["cell_execution_state"] == expected_state, label + "strict execution classification retained")
        check(consumer["valid_completion"] == sealed["consumer_valid_completion"] == anonymous["consumer_valid_completion"] == (cell not in FAILURES), label + "valid completion retained")
        check(sealed["primary_classification"] == expected_primary and sealed["final_content_classification"] == "complete_correct", label + "two quality classifications distinct")
        check(consumer["errors"] == original_anonymous["consumer_execution_errors"], label + "original errors preserved")
        check([{k: v for k, v in row.items() if k != "perf_ns"} for row in consumer["errors"]] == anonymous["consumer_execution_errors"] == sealed["execution_errors"], label + "seal and r2 errors exact payloads")
        check(len(consumer["errors"]) == (1 if cell in FAILURES else 0), label + "retained error count")
        check(consumer["exit_code"] == 0 and consumer["process_reaped"] and consumer["readers_stopped"] and consumer["safe_to_continue"], label + "consumer exit and cleanup")
        events_data = raw(cell_dir / "events.jsonl")
        event_lines = [line for line in events_data.splitlines() if line]
        events = [json.loads(line) for line in event_lines]
        starts = [row for row in events if row["event"].get("type") == "thread.started"]
        turns = [row for row in events if row["event"].get("type") == "turn.completed"]
        check(len(starts) == len(turns) == 1, label + "one fresh CLI thread and terminal turn")
        check(starts[0]["event"]["thread_id"] == consumer["thread_id"] and consumer["thread_id"] not in threads, label + "unique actual fresh thread")
        threads.add(consumer["thread_id"])
        check(turns[0]["perf_ns"] == consumer["turn_completed_ns"], label + "terminal turn timestamp")
        raw_errors = [row for row in events if row["event"].get("type") in ("error", "turn.failed")]
        check(raw_errors == consumer["errors"], label + "CLI errors exact raw records")
        messages = [row for row in events if row["event"].get("type") == "item.completed" and row["event"].get("item", {}).get("type") == "agent_message"]
        projected_messages = [{"perf_ns": row["perf_ns"], "id": row["event"]["item"]["id"], "text": row["event"]["item"]["text"]} for row in messages]
        check(projected_messages == consumer["all_public_messages"], label + "all public messages preserved")
        final_bytes = raw(cell_dir / "final.txt")
        check(final_bytes == raw(cell_dir / "PUBLIC_FINAL.txt") == consumer["final"].encode("utf8") == messages[-1]["event"]["item"]["text"].encode("utf8"), label + "CLI last public message and both private final files")
        check(digest(final_bytes) == sealed["final_sha256"] == anonymous["answer_original_sha256"], label + "sealed final SHA")
        for final_name in ("answer.txt", "cli_output_unconfirmed.txt"):
            check(raw(public / map_row["anonymous_id"] / final_name) == final_bytes, label + "public " + final_name + " exact final")
        check(anonymous["source_provenance"]["consumer_record_sha256"] == digest(raw(cell_dir / "CONSUMER.json")), label + "public consumer original SHA")
        archive_path = BATCH / "runtime/handoff_01/private/raw" / (map_row["anonymous_id"] + ".zip")
        with zipfile.ZipFile(io.BytesIO(raw(archive_path))) as archive:
            names = archive.namelist()
            check(len(names) == len(set(names)), label + "original ZIP unique names")
            check(set(names) == set(private["source_files_sha256"]), label + "original ZIP exact provenance file set")
            for name in names:
                data = raw(cell_dir / name)
                check(archive.read(name) == data and digest(data) == private["source_files_sha256"][name], label + "ZIP raw byte binding " + name)
                archive_file_count += 1
        schemas = obj(BATCH / f"schemas/{group}_CONSUMER_TOOLS.json")
        names = [row["name"] for row in schemas]
        check(names == consumer["expected_tool_names"] == identity["exposed_tool_names"], label + "actual exposed tool names")
        check(schemas[0] == native_schema and identity["common_native_sha256"] == native_schema_sha, label + "common native declaration")
        check(not identity["private_geometry_warmup"] and not identity["product_spatial_task_only"], label + "no private geometry warmup")
        check(config["read_schemas"] == ([] if group == "N" else schemas[1:]), label + "frozen actual read schemas")
        actual_argv = consumer["argv"]
        prototype = frozen_cli[group]
        actual_settings = configs(actual_argv)
        prototype_settings = configs(prototype)
        check([x for x in actual_settings if not x.startswith("mcp_servers.arm_engine=")] == [x for x in prototype_settings if not x.startswith("mcp_servers.arm_engine=")], label + "all actual CLI settings equal frozen prototype")
        check(actual_argv[:actual_argv.index("-C")] == prototype[:prototype.index("-C")], label + "fresh isolated CLI flags")
        check(actual_argv[actual_argv.index("-m") + 1] == consumer["model"] == plan["model"] == "gpt-6.1-sol", label + "requested model")
        check(consumer["requested_effort"] == plan["requested_effort"] == "medium" and consumer["resolved_effort"] is None, label + "requested effort and resolved unknown")
        mcp = tomllib.loads(next(x for x in actual_settings if x.startswith("mcp_servers.arm_engine=")))["mcp_servers"]["arm_engine"]
        frozen_mcp = tomllib.loads(next(x for x in prototype_settings if x.startswith("mcp_servers.arm_engine=")))["mcp_servers"]["arm_engine"]
        check({k: v for k, v in mcp.items() if k not in ("args", "cwd")} == {k: v for k, v in frozen_mcp.items() if k not in ("args", "cwd")}, label + "actual MCP protocol approvals and timeouts")
        check(list(mcp["tools"]) == names, label + "MCP tool allowlist")
        check(path_equal(mcp["cwd"], actual_argv[actual_argv.index("-C") + 1]), label + "MCP cwd equals isolated consumer cwd")
        attach_args = mcp["args"]
        check(attach_args[:3] == frozen_mcp["args"][:3] and attach_args[attach_args.index("--kind") + 1] == "native", label + "same thin attach entry")
        check(path_equal(attach_args[attach_args.index("--endpoint") + 1], cell_dir / "ENDPOINT.json"), label + "thin actual endpoint")
        check(path_equal(attach_args[attach_args.index("--audit") + 1], cell_dir / "attachments"), label + "thin actual audit directory")
        check(path_equal(actual_argv[actual_argv.index("-o") + 1], cell_dir / "final.txt"), label + "CLI output path")
        native = owner / "native"
        native_cfg = obj(native / "CONFIG.json")
        session = obj(native / "SESSION.json")
        ready = obj(native / "READY.json")
        check(all(session[k] == v for k, v in native_cfg.items()), label + "native launch configuration retained")
        check(session["pid"] == ready["pid"] == close["native_close"]["pid"] and session["pid"] not in worker_pids, label + "fresh actual Blender worker")
        worker_pids.add(session["pid"])
        check(session["condition"] == internal and session["asset_sha256"] == asset_sha, label + "worker actual group and asset")
        check(digest(raw(native / "input.blend")) == asset_sha, label + "worker input copy exact scene")
        check(all(session[k] == ready[k] for k in ("deadline_ns", "helper_sha256", "host", "pid", "port")), label + "worker ready and session agree")
        worker_events = records(native / "WORKER_EVENTS.jsonl")
        snapshots = [worker_events[0], worker_events[-2]]
        for snap_name, snap_event in zip(("INITIAL", "FINAL"), snapshots):
            snap_bytes = raw(owner / (snap_name + ".json"))
            snapshot = json.loads(snap_bytes)
            receipt = obj(owner / (snap_name + ".json.receipt.json"))
            snapshot_text = receipt["response"]["result"]["result"]
            check(receipt["response"]["status"] == "success" and receipt["response"]["result"]["executed"], label + snap_name + " actual successful read")
            check(json.loads(snapshot_text) == snapshot, label + snap_name + " snapshot from raw response")
            projected_baseline = {
                "unit_scale_m": baseline["unit_scale_m"],
                "objects": [{key: item[key] for key in ("name", "vertices_local", "matrix_world", "faces")} for item in baseline["objects"]],
            }
            check(snapshot == projected_baseline, label + snap_name + " all vertices faces matrices unit equal baseline")
            call_dir = native / ("call_" + str(snap_event["sequence"]))
            check(raw(call_dir / "stdout.txt").decode("utf8").replace("\r\n", "\n") == snapshot_text, label + snap_name + " actual worker stdout")
            check(digest(raw(call_dir / "SCRIPT.py").replace(b"\r\n", b"\n")) == snap_event["script_sha256"] == "cd3461ff034d608a776a81cfcb750744b2dc303800525671272207a4da2e4e73", label + snap_name + " actual snapshot script")
            check(snap_event["status"] == "completed" and snap_event["terminal_geometry_and_file_checks_passed"], label + snap_name + " worker terminal checks")
            check(receipt["source_file_unchanged"] and receipt["protected_files_unchanged"], label + snap_name + " snapshot protection")
        check(raw(owner / "INITIAL.json") == raw(owner / "FINAL.json"), label + "initial and final full snapshot bytes")
        check(snapshots[0]["started_ns"] + snapshots[0]["elapsed_ns"] <= consumer["started_ns"], label + "QA before consumer")
        check(snapshots[1]["started_ns"] >= consumer["cleanup_end_ns"], label + "final QA after consumer cleanup")
        runtime_pid = None
        product_identity = None
        if group == "N":
            check(identity["runtime_identity"] is None and config.get("source_sha256") is None, label + "native only no product loaded")
            check(not (owner / "plugin").exists() and close["plugin_close"] is None and close["product_runtime_exit"] is None, label + "no plugin process in native arm")
            check(config["dependency_python"] == installations["O"]["dependency_python"], label + "native common dependency Python")
        else:
            expected = PROFILES[group]
            product_identity = identity["runtime_identity"]
            init = obj(owner / "PLUGIN_INITIALIZE.json")
            tools = obj(owner / "PLUGIN_TOOLS.json")
            proof = obj(owner / "PRODUCT_RUNTIME_PROOF.json")
            product_cfg = obj(owner / "product_config.json")
            start = obj(owner / "plugin/START.json")
            rpc = obj(owner / "plugin/RPC.json")
            check(init["result"]["_meta"]["human_eye"] == product_identity, label + "actual initialize identity")
            check(product_identity["source_sha256"] == config["source_sha256"] == expected["source"] and product_identity["source_file_count"] == 138, label + "actual loaded source")
            check(product_identity["distribution_version"] == expected["version"] and product_identity["source_kind"] == "installed_distribution", label + "actual loaded installed version")
            check(product_identity["identity_check"]["compatible"] and product_identity["identity_check"]["pins_requested"], label + "actual identity pins")
            check([tool for tool in tools["result"]["tools"] if tool["name"] == "human_eye_scene_observe"] == config["read_schemas"], label + "actual product tools list declaration")
            check(path_equal(config["entry"], installations[group]["entry"]) and path_equal(config["install_root"], installations[group]["install_root"]), label + "actual launcher and installed roots")
            check(start["command"] == [config["dependency_python"], "-I", "-B", config["entry"], "serve", "--config", str(owner / "product_config.json")], label + "actual product command")
            check(product_cfg["expected_identity"] == {"source_sha256": expected["source"]} and product_cfg["project_root"] == config["install_root"], label + "product actual config source pins")
            check(product_cfg["blender"]["host"] == session["host"] and product_cfg["blender"]["port"] == session["port"], label + "product bound to same native worker")
            check(not product_cfg["observe_on_prompt"] and product_cfg["quad_size"] == 128 and product_cfg["request_budget_s"] == 30.0, label + "actual observation config")
            check(proof["confirmed"] and proof["before_stdin"] is False and proof["before_consumer_business"], label + "runtime proof actual scope")
            check(proof["launcher_pid"] == start["launcher_pid"] and proof["runtime_pid"] not in runtime_pids, label + "fresh owned product runtime")
            runtime_pid = proof["runtime_pid"]
            runtime_pids.add(runtime_pid)
            chain = proof["parent_chain"]
            check(chain[0]["pid"] == runtime_pid and chain[0]["created_filetime"] == proof["runtime_created_filetime"], label + "actual runtime creation identity")
            launcher_index = next(index for index, row in enumerate(chain) if row["pid"] == proof["launcher_pid"])
            check(chain[launcher_index]["created_filetime"] == proof["launcher_created_filetime"] and chain[launcher_index]["parent_pid"] == identity["actor_pid"], label + "runtime launcher creation and parent")
            check(all(first["parent_pid"] == second["pid"] for first, second in zip(chain[:launcher_index], chain[1:launcher_index + 1])), label + "actual complete runtime parent edges")
            check(proof["initial_QA_completed_ns"] <= start["started_ns"] <= proof["metadata_completed_ns"] <= proof["observed_ns"] <= proof["proved_ns"] < consumer["started_ns"], label + "QA metadata proof consumer actual order")
            check([row["method"] for row in rpc["requests"][:4]] == ["initialize", "notifications/initialized", "tools/list", "ping"], label + "only four metadata RPCs before business")
            check(all(row["started_ns"] + row["elapsed_ns"] <= proof["metadata_completed_ns"] for row in rpc["requests"][:4]), label + "metadata ends before proof")
            for rpc_index, row in enumerate(rpc["requests"], 1):
                folder = owner / "plugin" / f"{rpc_index:03d}"
                tx = raw(folder / "TX.bin")
                request = json.loads(tx)
                check(obj(folder / "RECEIPT.json") == row and request["method"] == row["method"] and len(tx) == row["sent_bytes"] and row["send_confirmed"], label + "actual product RPC " + str(rpc_index))
                if "id" in request:
                    rx = raw(folder / "RX.bin")
                    check(json.loads(rx)["id"] == request["id"] and len(rx) == row["received_bytes"], label + "actual product RPC response " + str(rpc_index))
                if rpc_index > 4:
                    check(row["started_ns"] >= consumer["started_ns"], label + "geometry business after consumer start")
            audit = records(owner / "audit.jsonl")
            check({row["pid"] for row in audit if row.get("event") == "request_trace"} == {runtime_pid}, label + "actual runtime audit PID")
            check(close["plugin_close"] == obj(owner / "plugin/CLOSE.json") and close["plugin_close"]["confirmed"] and close["product_runtime_exit"]["confirmed"] and close["product_runtime_exit"]["exited"], label + "owned product closure confirmed")
        bridge_dirs = sorted((cell_dir / "attachments").glob("bridge_*"))
        check(len(bridge_dirs) == 1, label + "one actual thin client")
        bridge = bridge_dirs[0]
        started = obj(bridge / "STARTED.json")
        check(started == consumer["bridge_cleanup"]["instances"][0]["started"], label + "thin start receipt")
        check(not (bridge / "EXIT.json").exists() and consumer["bridge_cleanup"]["receipt_status"] == "unknown" and consumer["bridge_cleanup"]["confirmed"] is None, label + "thin EXIT remains unknown")
        bridge_requests = []
        for folder in sorted(bridge.iterdir()):
            if folder.is_dir():
                request = obj(folder / "TX.bin")
                response = obj(folder / "RX.bin") if (folder / "RX.bin").exists() else None
                bridge_requests.append((request, response))
        check([pair[0]["method"] for pair in bridge_requests[:3]] == ["initialize", "notifications/initialized", "tools/list"], label + "actual thin metadata order")
        check(bridge_requests[2][1]["result"]["tools"] == schemas, label + "actual CLI received exact frozen tools schema")
        calls = bridge_requests[3:]
        ledger = obj(owner / "TOOLS.json")
        check(len(calls) == ledger["attempts"] == ledger["calls"] == len(consumer["tool_calls"]) == len(ledger["tools"]), label + "actual business attempt counts")
        tool_events = [(line, row) for line, row in zip(event_lines, events) if row["event"].get("item", {}).get("type") == "mcp_tool_call" and row["event"]["type"] in ("item.started", "item.completed")]
        cli_events = [{"perf_ns": row["perf_ns"], "type": row["event"]["type"], "item": row["event"]["item"]} for _, row in tool_events]
        check(cli_events == consumer["public_events"], label + "all consumer business events exact raw CLI")
        check([row for row in cli_events if row["type"] == "item.completed"] == consumer["tool_calls"], label + "all completed consumer tool calls")
        evidence = obj(public / map_row["anonymous_id"] / "tool_evidence.json")
        check(len(evidence["owner_attempts"]) == len(calls) and len(evidence["public_tool_events"]) == len(cli_events) == 2 * len(calls), label + "public evidence full attempt and CLI event counts")
        for number, ((line, row), published) in enumerate(zip(tool_events, evidence["public_tool_events"]), 1):
            check(published["order"] == number and published["phase"] == row["event"]["type"] and published["event"] == projected_cli_item(row["event"]["item"]), label + "public event exact projection " + str(number))
            check(published["source_line_sha256"] == digest(line) and published["source_sha256"] == digest(events_data), label + "public event raw line binding " + str(number))
        for number, ((request, response), attempt_log, completed, published) in enumerate(zip(calls, ledger["tools"], consumer["tool_calls"], evidence["owner_attempts"]), 1):
            folder = owner / f"tool_{number:02d}"
            owner_request = obj(folder / "REQUEST.json")
            owner_response = obj(folder / "RESPONSE.json")
            attempt = obj(folder / "ATTEMPT.json")
            check(request == owner_request and response == owner_response and attempt == attempt_log, label + "thin and actual owner attempt " + str(number))
            check(published["order"] == number and published["request"] == project_request(request), label + "public request exact business projection " + str(number))
            check(published["responses"] == [{"kind": "RESPONSE.json", "value": project_response(response)}], label + "public response exact business projection " + str(number))
            check(published["is_error"] == attempt["is_error"] and published["owner_exception"] == attempt["exception"], label + "public attempt status preserved " + str(number))
            for source_file in published["source_files"]:
                check(digest(raw(folder / source_file["kind"])) == source_file["original_sha256"], label + "public attempt source SHA " + str(number))
            item = completed["item"]
            check(item["tool"] == request["params"]["name"] == attempt["name"] and item["arguments"] == request["params"]["arguments"], label + "CLI original request business " + str(number))
            check(item["result"]["content"] == response["result"]["content"] and item["result"].get("structured_content") == response["result"].get("structuredContent"), label + "CLI full original response business " + str(number))
            check(item["status"] == ("failed" if response["result"].get("isError") else "completed"), label + "CLI original response status " + str(number))
            meta = request["params"].get("_meta", {})
            check(meta.get("threadId", consumer["thread_id"]) == consumer["thread_id"] and meta.get("x-codex-turn-metadata", {}).get("thread_id", consumer["thread_id"]) == consumer["thread_id"], label + "actual RPC thread binding " + str(number))
        business_count += len(calls)
        cli_business_count += len(cli_events)
        deadline = timing["cell_started_ns"] + 570_000_000_000
        check(deadline == launch["worker_deadline_ns"] == config["worker_deadline_ns"] == native_cfg["deadline_ns"] == endpoint["chain_deadline_ns"] == close["native_close"]["original_deadline_ns"] == close["worker_closed"]["original_deadline_ns"], label + "same original 570 second deadline")
        check(launch["cell_started_ns"] == timing["cell_started_ns"] == run_row["cell_started_ns"], label + "full clock starts before setup")
        check(launch["actor_startup_deadline_ns"] - launch["prepare_started_ns"] == 40_000_000_000 and consumer["deadline_ns"] - consumer["started_ns"] == 450_000_000_000, label + "original startup and consumer budgets")
        check(timing["full_cell_wall_ns"] == timing["business_receipts_closed_ns"] - timing["cell_started_ns"] <= 570_000_000_000 and timing["within_570s"], label + "full cell clock exact and within budget")
        clock = [timing["cell_started_ns"], launch["prepare_started_ns"], close["started_ns"], consumer["started_ns"], consumer["popen_ns"], consumer["prompt_write_started_ns"], consumer["prompt_submitted_ns"], consumer["final_received_ns"], consumer["turn_completed_ns"], consumer["process_exit_ns"], consumer["cleanup_end_ns"], close["ended_ns"], run_row["cell_ended_ns"], timing["business_receipts_closed_ns"], publication["timing_receipt_publication_started_ns"], publication["timing_receipt_publication_closed_ns"]]
        check(clock == sorted(clock), label + "full causal timing chain")
        check(consumer["wall_ns"] == consumer["cleanup_end_ns"] - consumer["started_ns"], label + "consumer wall accounting")
        check(consumer["total_task_wall_ns"] == run_row["cell_ended_ns"] - timing["cell_started_ns"] < timing["full_cell_wall_ns"], label + "prefix distinct from complete business close")
        check(publication["business_receipts_closed_ns"] == timing["business_receipts_closed_ns"] and publication["timing_receipt_publication_ns"] == publication["timing_receipt_publication_closed_ns"] - publication["timing_receipt_publication_started_ns"], label + "timing publication separately accounted")
        check(previous_publication is None or timing["cell_started_ns"] > previous_publication, label + "next cell starts after previous timing publication")
        previous_publication = publication["timing_receipt_publication_closed_ns"]
        check(timing["owner_cleanup_confirmed"] and finish["confirmed"] and close["confirmed"] and finish["exit_code"] == 0, label + "owned cleanup included")
        check(close["native_close"]["process_reaped"] and close["native_close"]["exit_code"] == 0 and close["native_close"]["response"]["status"] == "closed", label + "actual worker closure")
        check(close["geometry_unchanged"] and close["asset_unchanged"] and not close["worker_closed"]["poisoned"], label + "terminal geometry protection")
        check(consumer["public_image_count"] == consumer["input_image_count"] == 0 and close["zero_new_images_budget_met"], label + "zero images in recorded scope")
        consistency = obj(public / map_row["anonymous_id"] / "source_consistency.json")
        for name, sha in consistency["source_records_sha256"].items():
            check(digest(raw(cell_dir / name)) == sha, label + "public source consistency original " + name)
        cells.append({
            "cell": cell, "anonymous_id": map_row["anonymous_id"], "slot": map_row["slot"],
            "external_group": group, "internal_group": internal, "thread_id": consumer["thread_id"],
            "final_sha256": sealed["final_sha256"], "final_content_classification": sealed["final_content_classification"],
            "primary_classification": sealed["primary_classification"], "execution_state": consumer["status"],
            "valid_completion": consumer["valid_completion"], "error_events": len(consumer["errors"]),
            "terminal_turn_completed": True, "cli_exit_code": consumer["exit_code"],
            "actor_launcher_pid": launch["pid"], "actual_owner_pid": identity["actor_pid"],
            "actual_native_pid": session["pid"], "actual_product_pid": runtime_pid,
            "loaded_source_sha256": None if product_identity is None else product_identity["source_sha256"],
            "loaded_distribution_version": None if product_identity is None else product_identity["distribution_version"],
            "actual_tool_names": names, "actual_tool_schema_canonical_sha256": digest(canonical(schemas)),
            "actual_cli_argv_sha256": digest(canonical(actual_argv)), "business_attempts": len(calls),
            "public_CLI_business_events": len(cli_events), "actual_full_snapshots": 2,
            "cell_started_ns": timing["cell_started_ns"], "business_receipts_closed_ns": timing["business_receipts_closed_ns"],
            "full_cell_wall_ns": timing["full_cell_wall_ns"], "legacy_prefix_wall_ns": consumer["total_task_wall_ns"],
            "timing_receipt_publication_ns": publication["timing_receipt_publication_ns"],
            "owned_cleanup_confirmed": True, "thin_client_EXIT": "unknown",
            "resolved_provider_model": "unknown", "resolved_provider_effort": "unknown",
        })
    check(len(threads) == len(worker_pids) == 9 and len(runtime_pids) == 6, "nine fresh contexts workers and six product runtimes")
    check(business_count == 27 and cli_business_count == 54 and archive_file_count == 807, "nine archives 807 originals 27 attempts 54 CLI events")
    delivery_manifest = obj(BATCH / "DELIVERY_MANIFEST.json")
    delivery_records = {row["path"]: row for row in delivery_manifest["files"]}
    for record in list(inventory.values()):
        path = record["path"]
        if path.startswith(PREFIX) and not path.startswith(PREFIX + "cost/"):
            data = (REPO / path).read_bytes()
            verify_git_bytes(data, path, delivery_tree, "same-byte formal delivery " + path[len(PREFIX):])
            relative = path[len(PREFIX):]
            if relative in delivery_records:
                expected = delivery_records[relative]
                check(expected["bytes"] == record["bytes"] and expected["sha256"] == record["sha256"], "delivery manifest original " + relative)
    history = obj(OUT / "CHECK_HISTORY.json")
    check(len(history["failures"]) == 4 and all(row["original_evidence_changed"] is False for row in history["failures"]), "checker development failures retained separately")
    inventory_rows = sorted(inventory.values(), key=lambda row: row["path"])
    result = {
        "schema": "compact-consumption-post-quality-private-binding-v1", "status": "pass",
        "administrator_commit": ADMIN_COMMIT, "preparation_commit": PREPARATION, "formal_delivery_commit": DELIVERY,
        "quality_seal_sha256": SEAL_SHA, "cost_plan_sha256": COST_PLAN_SHA,
        "r2_zip_sha256": R2_ZIP_SHA, "r2_public_canonical_sha256": PUBLIC_SHA,
        "initial_public_canonical_sha256": INITIAL_PUBLIC_SHA,
        "quality_facts_regraded": False, "seal_unchanged": True, "source_mismatch_affecting_quality": False,
        "primary_counts": seal["primary_counts"], "content_counts": seal["content_counts"],
        "strict_failed_cells_retained": sorted(FAILURES), "quality_prerequisite_3_of_3_by_group": {"N": False, "O": False, "C": True},
        "formal_quality_prerequisite_C_vs_N": False, "formal_quality_prerequisite_C_vs_O": False,
        "native_N_scope": "common native only, O dependency Python, no loaded product",
        "old_O_scope": "old surface scan OPT1 c1cb2da3, not desktop mainline",
        "actual_execution_order": ORDER, "cells": cells,
        "original_cell_archives_verified": 9, "original_archive_files_verified": archive_file_count,
        "actual_initial_final_snapshots_verified": 18, "actual_fresh_CLI_threads": 9,
        "actual_fresh_Blender_workers": 9, "actual_product_runtime_processes": 6,
        "owner_business_attempts_verified": business_count, "consumer_business_events_verified": cli_business_count,
        "administrative_perf_fields_exactly_restored": 2, "other_public_files_exactly_unchanged": 41,
        "reused_same_byte_acceptance_records": prior_records,
        "source_wheel_install_scope": "reuse accepted 138-source/profile matrices bound to unchanged ready/source/proof records, additionally verify actual historical launch commands configs schemas process identity and parent/creation times",
        "new_model_Blender_product_API_runs": 0, "git_mutations": 0,
        "verifier_script_sha256": digest(Path(__file__).read_bytes()),
        "checker_development_failures": history["failures"],
        "AL_binding": {"context_bound": False, "host_epoch": 5, "rebind_required": True, "borrowed_handle": False},
        "limitations": [
            "historical identity/process/config records bind evidence but do not replay past process memory",
            "all nine thin-client EXIT receipts remain unknown, separate from confirmed owned backend closure",
            "snapshot and image checks cover recorded terminal geometry/files/render hooks, transient reverted edits or arbitrary Python effects remain outside attestation",
            "provider-resolved model/version/effort and rendered or truncated model input remain unknown",
            "fsync-level disk persistence, external coordination and provider requests or cash billing remain unmeasured",
            "both strict comparisons lack 3/3 valid complete_correct baselines, nine final content-correct results remain descriptive only",
            "business content can reveal route, anonymity remains finite",
        ],
        "checks": len(checks), "check_results": checks,
        "input_file_count": len(inventory_rows), "input_inventory_canonical_sha256": digest(canonical(inventory_rows)),
        "input_inventory": inventory_rows,
    }
    if args.write_report:
        (OUT / "BINDING_RESULT.json").write_bytes(pretty(result))
        lines = [
            "# 同九格成本解封私有来源绑定复核", "", "2026-11-13。离线复核通过。新增模型、Blender、产品 API 调用均为零。", "",
            f"本次完成 {len(checks)} 项断言，读取 {len(inventory_rows)} 个不同输入文件，含两份管理员原件副本和一份复核器失败历史。源证据按固定交付提交核字节，管理员 seal 与成本合同绑定到独立管理员提交。", "",
            f"准备提交 `{PREPARATION}`，正式交付 `{DELIVERY}`，管理员封存 `{ADMIN_COMMIT}`。", "",
            "## 质量与私有映射", "",
            "根 seal 保留原件。九份最终答案内容均为 complete_correct，匹配 639/639 个事实。严格执行为七份 complete_correct、两份 execution_failure。N2 与 O2 的 reconnect/response decoding 错误保留，随后 turn.completed、CLI exit0、final 文件存在的事实同时保留。", "",
            "N、O 各有两格有效完整正确，C 有三格。C/N 与 C/O 均未满足双方各 3/3 的正式质量前提。内容正确口径可用于同九格描述性成本，正式准入仍受冻结执行合同约束。", "",
            "| 格 | 私有匿名 ID | 内容 | 严格执行 | 加载版本 | 完整墙钟 ns |", "|---|---|---|---|---|---:|",
        ]
        for row in cells:
            version = row["loaded_distribution_version"] or "原生工具"
            lines.append(f"| {row['cell']} | {row['anonymous_id']} | {row['final_content_classification']} | {row['execution_state']} | {version} | {row['full_cell_wall_ns']} |")
        lines += [
            "", "## 原始来源与公开投影", "",
            "私有预建 MAP 与固定九格、根 seal、九 final、CLI 最后一条公开消息、原输出文件、两套匿名公开答案逐字节对应。九原始 ZIP 的 807 项原件分别与磁盘、私有 provenance SHA 对应。27 次业务尝试与 54 条消费者开始/结束事件逐项连接到原始请求、完整返回、公开投影和原行 SHA。", "",
            "r2 的 42 文件 canonical 与 ZIP 均匹配根 seal。行政修正仅删除两处错误信封 perf_ns，恢复原值后 INDEX 原字节完全一致，其他 41 文件保持一致。原始匿名 ZIP 与初始 canonical 分别保留。", "",
            "## 实际进程与时界", "",
            "九个独立实际 CLI thread、九个独立 Blender worker、六个独立产品 runtime 分别核验。每格实际 CLI 隔离设置、请求模型与 effort、MCP 配置、tools/list 声明、读取 schema、产品 source pin、安装版本、父链与创建时间对应。初始 QA、四次元数据握手、runtime 证明、消费者业务的先后关系一致。旧 O 绑定旧扫描 OPT1。", "",
            "18 个初末完整快照与实际 worker stdout、snapshot 脚本、receipt 和冻结基准逐项一致，包含全部顶点、面、矩阵及单位。每格完整计时覆盖输入检查前到最终业务回执关闭及 owned 清理结束，prefix 与计时回执发布分别核算。九格均在原 570 秒时限内，下一格开始晚于前格计时回执发布结束。", "",
            "同字节复用既有 source/wheel/install 验收与两份旧复核记录，本次重点新增历史实际运行来源、配置与事件的对应。", "",
            "## 保留的边界", "",
            "九个 thin-client EXIT 回执均为 unknown，owned 消费者、owner、Blender 与适用产品 runtime 的关闭分别得到记录确认。provider 实际解析型号与 effort、实际渲染或截断后的模型输入、fsync 级落盘、请求总数及真实账单仍未测。终态快照及 render/file 保护保持其记录范围，无法排除所有已恢复的瞬时操作。历史 process 记录无法重放过去进程内存。", "",
            "Agent Learning 本轮绑定仍为 context_bound=false、host_epoch=5、rebind_required=true。未借用其他会话句柄。", "",
            "离线复核器开发时出现四次自身读法失败，涉及 Windows 路径排序、schema 字典编码顺序、TOML 解析及基准额外字段。均已修正并保留在 CHECK_HISTORY.json，原件无改动。", "",
            "## 可重复执行", "",
            "使用依赖 Python 加 `-I -B -X utf8` 执行同目录 verify_binding.py 可只读重核。加 `--write-report` 只写本目录派生 BINDING_RESULT.json 与 REPORT.md。完整断言和输入 SHA 清单见 JSON。", "",
        ]
        (OUT / "REPORT.md").write_text("\n".join(lines), encoding="utf8", newline="\n")
    print(json.dumps({k: result[k] for k in ("status", "checks", "input_file_count", "input_inventory_canonical_sha256", "source_mismatch_affecting_quality", "owner_business_attempts_verified", "consumer_business_events_verified")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
