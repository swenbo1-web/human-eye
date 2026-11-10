"""Read-only M1 entry equivalence on two existing, independently owned scenes.

Run once, after reviewing this file, with the project's existing Python:
  <python> verification/m1_task_entry_001/run_blender_equivalence.py \
    --expected-source-sha256 <reviewed candidate canonical hash> \
    --output blender_equivalence_01

This is source-checkout qualification, not wheel/installation qualification or
a model A/B test. The only engine copy is an exact 137-file byte snapshot plus
the checkout's original pyproject marker. It creates no environment or assets.
Instrumentation preserves arguments, responses, deadlines and operator budgets;
its I/O costs mean these records must not be used as a speed benchmark.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import time
import traceback
import types
from types import MappingProxyType


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PRODUCT_BASE = "df016079b0265ee327f884c90dd4815c392016b6"
REFERENCE_BASE = "d341bb68a4747d1076d5e332789bee1d5f217cd7"
ALLOWED_PRODUCT_EDITS = frozenset((
    "human_eye_plugin/live_spatial_mcp.py", "human_eye_plugin/production_server.py"))
SOURCE_COUNT = 137
CASE_WINDOW_NS = 570 * 10**9
RPC_TIMEOUT_S = 30
MAX_CALLS = 128
SESSION_ID = "m1-entry-equivalence-current-scene"
NATIVE_HELPER = "verification/native_plugin_complex_003/reused/accepted_native.py"
ASSEMBLY_ASSET = "verification/native_plugin_complex_003/scene.blend"
ASSEMBLY_TRUTH = "verification/native_plugin_complex_003/private/TRUTH.json"
ASSEMBLY_SNAPSHOT = "verification/native_plugin_complex_003/private/author_mesh_snapshots.json"
D48_ASSET = "verification/scale_diag_001/fixtures/D48.blend"
D48_SNAPSHOT = "verification/scale_diag_001/fixtures/D48.json"
D48_ORACLE = "verification/scale_diag_001/ORACLE.json"
D48_REPLAY = "verification/scale_diag_001/ORACLE_REPLAY.json"
REFERENCE_FILES = (NATIVE_HELPER, ASSEMBLY_ASSET, ASSEMBLY_TRUTH, ASSEMBLY_SNAPSHOT,
                   D48_ASSET, D48_SNAPSHOT, D48_ORACLE, D48_REPLAY,
                   "verification/native_plugin_complex_003/FREEZE.json",
                   "verification/scale_diag_001/FREEZE.json")

# Literal read-only observation from 003/actor.py; do not import that actor.
SNAPSHOT = """import json as _j
print(_j.dumps({'unit_scale_m':bpy.context.scene.unit_settings.scale_length,'objects':[{'name':o.name,
'vertices_local':[list(v.co) for v in o.data.vertices],'matrix_world':[list(r) for r in o.matrix_world],
'faces':[list(p.vertices) for p in o.data.polygons]} for o in sorted(bpy.context.scene.objects,key=lambda x:x.name) if o.type=='MESH']},allow_nan=False))"""


def need(condition, reason):
    if not condition:
        raise ValueError("m1_equivalence_" + reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                       indent=2) + "\n").encode("utf8")


def error_record(exc):
    return {"type": type(exc).__name__, "reason": str(exc),
            "traceback": "".join(traceback.format_exception(exc))}


def deadline_check(deadline_ns):
    need(type(deadline_ns) is int and time.perf_counter_ns() < deadline_ns,
         "original_deadline_expired")


def git_bytes(*arguments):
    result = subprocess.run(["git", "-C", str(ROOT), *arguments], check=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=30, shell=False)
    return result.stdout


def archive_bytes(revision, names):
    names = sorted(names)
    raw = git_bytes("archive", "--format=tar", revision, "--", *names)
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        members = [member for member in archive.getmembers() if member.isfile()]
        need({member.name for member in members} == set(names), "git_archive_members")
        result = {}
        for member in members:
            stream = archive.extractfile(member)
            need(stream is not None, "git_archive_member_missing")
            result[member.name] = stream.read()
    return result


def identity_constants(raw):
    wanted = {"BASE_VERSION", "IMPLEMENTATION_REVISION", "_ROOT_MODULES"}
    tree = ast.parse(raw)
    result = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
              if isinstance(node, ast.Assign) and len(node.targets) == 1
              and isinstance(node.targets[0], ast.Name) and node.targets[0].id in wanted}
    need(set(result) == wanted, "runtime_identity_constants")
    return result


def source_names(constants, paths):
    names = set(constants["_ROOT_MODULES"])
    for relative in paths:
        parts = PurePosixPath(relative).parts
        if len(parts) == 2 and parts[0] in ("human_eye_plugin", "human_eye_module1_operators") and relative.endswith(".py"):
            names.add(relative)
    return sorted(names)


def manifest_for(blobs):
    return [{"path": name, "sha256": sha(raw)} for name, raw in sorted(blobs.items())]


def canonical(constants, manifest):
    return sha(json.dumps({"base_version": constants["BASE_VERSION"],
                           "implementation_revision": constants["IMPLEMENTATION_REVISION"],
                           "files": manifest}, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True).encode("utf8"))


class Evidence:
    """Exclusive outputs; late/error artifacts are explicitly invalid evidence."""

    def __init__(self, output, run_deadline_ns):
        self.output = output
        self.run_deadline_ns = run_deadline_ns
        self.check_sources = lambda: True

    def checks(self, deadline_ns=None):
        result = {"checked_at_ns": time.perf_counter_ns(), "deadline_ns": deadline_ns,
                  "run_deadline_ns": self.run_deadline_ns, "source_ok": False,
                  "deadline_ok": False, "errors": []}
        try:
            deadline_check(self.run_deadline_ns)
            if deadline_ns is not None:
                deadline_check(deadline_ns)
            result["deadline_ok"] = True
        except BaseException as exc:
            result["errors"].append(error_record(exc))
        try:
            self.check_sources()
            result["source_ok"] = True
        except BaseException as exc:
            result["errors"].append(error_record(exc))
        return result

    def write(self, relative, value, *, deadline_ns=None, failure=False):
        checks = self.checks(deadline_ns)
        if not failure:
            need(checks["deadline_ok"] and checks["source_ok"], "publication_checks_" + relative)
        path = self.output / relative
        need(path.resolve().is_relative_to(self.output), "output_escape")
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = encoded(value)
        with path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        need(path.read_bytes() == raw, "publication_readback")
        # A successful write is not a disk-persistence claim. Check after it as
        # well, so a report crossing its original deadline cannot count as pass.
        after = self.checks(deadline_ns)
        receipt = {"path": str(path), "sha256": sha(raw), "bytes": len(raw),
                   "before": checks, "after": after,
                   "valid_current_evidence": (not failure and checks["deadline_ok"]
                       and checks["source_ok"] and after["deadline_ok"] and after["source_ok"])}
        receipt_path = path.with_name(path.name + ".publication.json")
        with receipt_path.open("xb") as stream:
            stream.write(encoded(receipt))
            stream.flush()
            os.fsync(stream.fileno())
        if not failure:
            need(receipt["valid_current_evidence"], "late_or_changed_publication_" + relative)
        return receipt


def prepare_snapshot(output, expected_sha256, evidence):
    entry_bytes = Path(__file__).read_bytes()
    constants = identity_constants((ROOT / "human_eye_plugin/runtime_identity.py").read_bytes())
    names = source_names(constants, (path.relative_to(ROOT).as_posix()
                         for package in ("human_eye_plugin", "human_eye_module1_operators")
                         for path in (ROOT / package).glob("*.py")))
    baseline_constants = identity_constants(git_bytes("show", PRODUCT_BASE + ":human_eye_plugin/runtime_identity.py"))
    baseline_paths = git_bytes("ls-tree", "-r", "--name-only", PRODUCT_BASE).decode("utf8").splitlines()
    baseline_names = source_names(baseline_constants, baseline_paths)
    need(names == baseline_names and len(names) == SOURCE_COUNT, "runtime_membership_not_137_baseline")
    need(constants == baseline_constants, "runtime_version_contract_changed")
    blobs = {name: (ROOT / name).read_bytes() for name in names}
    baseline = archive_bytes(PRODUCT_BASE, names)
    differences = sorted(name for name in names if blobs[name] != baseline[name])
    need(set(differences) == ALLOWED_PRODUCT_EDITS, "changes_outside_two_M1_files")
    manifest = manifest_for(blobs)
    digest = canonical(constants, manifest)
    need(digest == expected_sha256, "candidate_canonical_pin")
    references = archive_bytes(REFERENCE_BASE, REFERENCE_FILES)
    need(all((ROOT / name).read_bytes() == raw for name, raw in references.items()), "historical_reference_changed")
    marker = (ROOT / "pyproject.toml").read_bytes()
    need(marker == git_bytes("show", PRODUCT_BASE + ":pyproject.toml"), "pyproject_marker_changed")
    runtime = output / "runtime"
    runtime.mkdir(exist_ok=False)
    for name, raw in {**blobs, "pyproject.toml": marker}.items():
        path = runtime / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(raw)
        need(path.read_bytes() == raw, "snapshot_copy_changed")

    def check_sources():
        current_names = source_names(constants, (path.relative_to(ROOT).as_posix()
            for package in ("human_eye_plugin", "human_eye_module1_operators")
            for path in (ROOT / package).glob("*.py")))
        need(current_names == names, "checkout_membership_changed")
        snapshot_names = source_names(constants, (path.relative_to(runtime).as_posix()
            for package in ("human_eye_plugin", "human_eye_module1_operators")
            for path in (runtime / package).glob("*.py")))
        need(snapshot_names == names, "snapshot_membership_changed")
        need(all((ROOT / name).read_bytes() == raw and (runtime / name).read_bytes() == raw
                 for name, raw in blobs.items()), "runtime_source_changed")
        need((ROOT / "pyproject.toml").read_bytes() == marker
             and (runtime / "pyproject.toml").read_bytes() == marker, "marker_changed")
        need(all((ROOT / name).read_bytes() == raw for name, raw in references.items()), "reference_changed")
        need(Path(__file__).read_bytes() == entry_bytes, "runner_source_changed")
        return True

    evidence.check_sources = check_sources
    evidence.write("SOURCE_MANIFEST.json", {
        "schema": "m1-entry-source-snapshot-v1", "checkout_root": str(ROOT),
        "runtime_root": str(runtime), "source_kind": "source_checkout",
        "not_installation_qualification": True, "candidate_source_sha256": digest,
        "source_file_count": len(manifest), "files": manifest,
        "product_base": PRODUCT_BASE, "baseline_source_sha256": canonical(baseline_constants, manifest_for(baseline)),
        "runtime_diff_paths": differences,
        "runtime_diff": [{"path": name, "old_sha256": sha(baseline[name]), "new_sha256": sha(blobs[name])} for name in differences],
        "pyproject_sha256": sha(marker), "reference_base": REFERENCE_BASE,
        "reference_files": manifest_for(references), "runner_sha256": sha(entry_bytes),
        "python": sys.executable, "python_version": sys.version,
        "head": git_bytes("rev-parse", "HEAD").decode("ascii").strip(),
        "scope": "entry and fact equivalence only; no model or speed benefit claim"})
    return runtime, blobs, manifest, digest, references


def load_product(runtime, blobs, manifest, digest, evidence):
    loader_relative = "human_eye_plugin/verified_source_loader.py"
    path = runtime / loader_relative
    helper = types.ModuleType("_m1_equivalence_verified_source_bootstrap")
    helper.__file__ = str(path)
    sys.modules[helper.__name__] = helper
    exec(compile(blobs[loader_relative], str(path), "exec", dont_inherit=True), helper.__dict__)
    guard = helper.install(runtime.resolve(), manifest, sources=MappingProxyType(blobs), bootstrap_module=helper)
    package = types.ModuleType("human_eye_plugin")
    package.__path__ = [str(runtime / "human_eye_plugin")]
    guard.allow_namespace(package)
    sys.modules[package.__name__] = package
    sys.path.insert(0, str(runtime))
    from human_eye_plugin.blender_mcp_host import BlenderMCPHost
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer, _project_spatial_relations
    from human_eye_plugin.runtime_identity import runtime_identity
    identity = runtime_identity(mode="live")
    need(identity["source_sha256"] == digest and identity["source_kind"] == "source_checkout", "loaded_runtime_identity")
    need(identity["source_files"] == manifest, "loaded_runtime_manifest")
    original_check = evidence.check_sources

    def check_sources():
        original_check()
        need(guard.verify_loaded() is True, "verified_loaded_witnesses")
        need(dict(guard.sources) == blobs, "guard_frozen_bytes")
        return True

    evidence.check_sources = check_sources
    return types.SimpleNamespace(guard=guard, identity=identity, BlenderMCPHost=BlenderMCPHost,
        LiveSpatialService=LiveSpatialService, LiveSpatialMCPServer=LiveSpatialMCPServer,
        project=_project_spatial_relations)


def load_native(references):
    path = ROOT / NATIVE_HELPER
    need(path.read_bytes() == references[NATIVE_HELPER], "native_helper_source")
    spec = importlib.util.spec_from_file_location("_m1_equivalence_accepted_native", path)
    need(spec is not None and spec.loader is not None, "native_helper_spec")
    helper = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = helper
    spec.loader.exec_module(helper)
    return helper


def without_trace(value):
    # Only the top-level request trace is correlation, not geometry/binding.
    # Preserve every nested field, including unknown/partial/source states.
    need(type(value) is dict, "fact_object")
    return {key: item for key, item in value.items() if key != "trace_id"}


def fact_from_rpc(response):
    need(type(response) is dict and "error" not in response, "rpc_envelope_error")
    result = response.get("result")
    need(type(result) is dict and result.get("isError") is False, "tool_error")
    content = result.get("content")
    need(type(content) is list and len(content) == 1 and set(content[0]) == {"type", "text"}
         and content[0]["type"] == "text", "unexpected_image_or_content")
    return json.loads(content[0]["text"])


def expected_snapshot(value):
    rows = [{"name": row["name"], "vertices_local": row["vertices_local"],
             "matrix_world": row["matrix_world"], "faces": row.get("faces", row.get("triangles"))}
            for row in value["objects"]]
    return {"unit_scale_m": value["unit_scale_m"], "objects": sorted(rows, key=lambda row: row["name"])}


def check_assembly(value, initial, references):
    truth = json.loads(references[ASSEMBLY_TRUTH])
    expected = json.loads(references[ASSEMBLY_SNAPSHOT])["initial"]
    need(initial == expected_snapshot(expected), "assembly_complete_snapshot_binding")
    state = truth["states"]["initial"]
    need(value["schema_version"] == "task-query-set-v1" and value["status"] == "observed", "assembly_status")
    need(value["execution_authority"] is False, "assembly_execution_authority")
    rows = value["binding"]["objects"]
    need([row["name"] for row in rows] == [state["target"], *state["probes"]], "assembly_selection")
    need(len(value["pairs"]) == len(state["probes"]) == 3, "assembly_pair_coverage")
    checks = []
    penetrating = []
    for index, (name, expected_pair) in enumerate(state["probes"].items()):
        pair = value["pairs"][index]
        need(pair["candidate_index"] == index and pair["object_id"] == rows[index + 1]["object_id"], "assembly_pair_identity")
        relation = pair["facts"]["closed_solid_relation"]
        need(relation["status"] == "measured" and relation["value"] == expected_pair["relation"], "assembly_relation_" + name)
        need(pair["facts"]["surface_proximity"]["status"] == "measured", "assembly_surface_fact_" + name)
        row = {"candidate": name, "relation": relation["value"], "passed": True}
        if expected_pair["relation"] == "separated":
            gap = pair["separation_gap"]
            need(gap["status"] == "measured" and type(gap["value"]) in (int, float)
                 and math.isfinite(gap["value"]), "assembly_gap_status_" + name)
            bound = abs(gap["value"] - expected_pair["minimum_gap_m"]) + expected_pair["distance_error_bound_m"]
            need(bound <= 1e-6, "assembly_independent_gap_" + name)
            surface_distance = pair["facts"]["surface_proximity"]["value"]["distance_m"]
            need(surface_distance == gap["value"], "assembly_surface_gap_" + name)
            row.update(distance_m=gap["value"], outward_error_bound_m=bound, tolerance_m=1e-6)
        else:
            penetrating.append(pair["object_id"])
            need(pair["separation_gap"]["status"] == "not_applicable"
                 and pair["separation_gap"]["value"] is None, "assembly_penetration_is_not_gap")
        checks.append(row)
    summary = value["summary"]
    winner = next(row["object_id"] for row in rows if row["name"] == state["nearest_separated_probe"])
    need(summary["penetration_set_complete"] is True and summary["penetrating_ids"] == penetrating
         and summary["known_penetrating_ids"] == penetrating, "assembly_penetrating_set")
    need(summary["nearest_separated_complete"] is True and summary["nearest_separated_ids"] == [winner]
         and summary["best_known_separated_ids"] == [winner], "assembly_nearest_separated_set")
    winner_gap = next(pair["separation_gap"]["value"] for pair in value["pairs"] if pair["object_id"] == winner)
    need(summary["distance_m"] == winner_gap and summary["best_known_distance_m"] == winner_gap,
         "assembly_nearest_separated_distance")
    need(summary["unresolved_relations"] == [] and summary["unresolved_distances"] == {}, "assembly_unresolved")
    need(value["coverage"] == {"requested_candidates": 3, "resolved_candidates": 3,
        "classified_candidates": 3, "unresolved_candidates": 0}, "assembly_coverage")
    return {"independent_truth_sha256": sha(references[ASSEMBLY_TRUTH]),
            "full_input_snapshot_matches": True, "checks": checks,
            "penetrating_set_correct": True, "nearest_separated_set_correct": True,
            "scope": "these three selected candidates, not global nearest"}


def check_d48(value, initial, references):
    snapshot = json.loads(references[D48_SNAPSHOT])
    need(initial == expected_snapshot(snapshot), "D48_complete_snapshot_binding")
    oracle = json.loads(references[D48_ORACLE])
    replay = json.loads(references[D48_REPLAY])
    need(replay["oracle_sha256"] == sha(references[D48_ORACLE])
         and all(row["passed"] is True for row in replay["checks"]), "D48_independent_replay_binding")
    truth = next(row for row in oracle["snapshots"] if row["id"] == "D48")
    expected = truth["global_nearest_unsigned"]
    names = {row["logical_id"]: row["name"] for row in snapshot["objects"]}
    need(expected["complete"] is True and truth["candidate_count"] == truth["qualified_surface_pairs"] == 47
         and truth["directory_count"] == 48 and len(truth["pairs"]) == 47, "D48_oracle_coverage")
    need(value["result_kind"] == "surface_nearest" and value["status"] == "complete"
         and value["execution_authority"] is False, "D48_status")
    need(value["focal"]["name"] == names[snapshot["target_id"]], "D48_target")
    need([row["name"] for row in value["nearest_objects"]] == [names[logical] for logical in expected["nearest_ids"]], "D48_winner")
    need(value["best_known_objects"] == value["nearest_objects"]
         and value["best_known_distance_m"] == value["distance_m"], "D48_best_known")
    distance = value["distance_m"]
    need(type(distance) in (int, float) and math.isfinite(distance), "D48_distance_finite")
    # The entire independently certified interval must satisfy the tolerance;
    # no midpoint substitution or production solver is used as the answer.
    bound = max(abs(distance - expected[key]) for key in ("distance_lower_m", "distance_upper_m"))
    need(bound <= 1e-6, "D48_independent_distance")
    coverage = value["coverage"]
    need(coverage["targets_excluding_focal"] == 47 and coverage["unresolved"] == 0
         and value["unresolved"] == []
         and coverage["distance_valid"] + coverage["strictly_excluded"] + coverage["unresolved"] == 47,
         "D48_all_47_covered")
    return {"independent_oracle_sha256": sha(references[D48_ORACLE]),
            "independent_replay_sha256": sha(references[D48_REPLAY]),
            "full_input_snapshot_matches": True, "winner": value["nearest_objects"],
            "distance_m": distance, "certified_interval_m": [expected["distance_lower_m"], expected["distance_upper_m"]],
            "outward_error_bound_m": bound, "tolerance_m": 1e-6,
            "coverage": coverage, "scope": "global unsigned surface distance, not nearest separated"}


def observe_state_files(folder):
    return {name: {"exists": (folder / name).exists(),
                   "sha256": sha((folder / name).read_bytes()) if (folder / name).exists() else None}
            for name in ("state.json", "state.json.lock")}


def run_case(case, *, output, runtime, digest, references, product, helper, blender, evidence):
    folder = output / case
    folder.mkdir(exist_ok=False)
    deadline_ns = time.perf_counter_ns() + CASE_WINDOW_NS
    native = host = None
    initial = final = None
    result = {"case": case, "passed": False, "original_deadline_ns": deadline_ns,
              "errors": [], "zero_product_setters_required": True,
              "zero_save_required": True, "default_session_id": SESSION_ID}
    native_rpc_count = host_rpc_count = host_wire_count = 0
    capture_bindings = []
    host_script_hashes = []

    def write(name, value, *, failure=False):
        return evidence.write(case + "/" + name, value, deadline_ns=deadline_ns, failure=failure)

    def logged_call(kind, ordinal, request, call):
        started = time.perf_counter_ns()
        write(kind + "/" + str(ordinal).zfill(3) + "_REQUEST.json", request)
        try:
            response = call()
        except BaseException as exc:
            write(kind + "/" + str(ordinal).zfill(3) + "_ERROR.json",
                  {"error": error_record(exc), "elapsed_ns": time.perf_counter_ns() - started}, failure=True)
            raise
        write(kind + "/" + str(ordinal).zfill(3) + "_RESPONSE.json",
              {"response": response, "elapsed_ns": time.perf_counter_ns() - started})
        return response

    def snapshot(name):
        receipt = native.run(SNAPSHOT, timeout_s=RPC_TIMEOUT_S)
        write(name + "_RECEIPT.json", receipt)
        need(receipt["source_file_unchanged"] is True and receipt["protected_files_unchanged"] is True, "snapshot_protected_files")
        response = receipt["response"]
        need(response["status"] == "success" and response["result"]["executed"] is True, "snapshot_rpc")
        value = json.loads(response["result"]["result"])
        write(name + ".json", value)
        return value

    try:
        asset = ASSEMBLY_ASSET if case == "assembly" else D48_ASSET
        write("CONTRACT.json", {"asset": asset, "asset_sha256": sha(references[asset]),
            "worker_lifetime_s": 570, "rpc_timeout_s": RPC_TIMEOUT_S, "max_calls": MAX_CALLS,
            "runtime_source_sha256": digest, "production_mode": True,
            "source_kind": "source_checkout", "model_calls": 0,
            "owned_background_only": True, "setter_calls_authorized": 0,
            "save_calls_authorized": 0, "operator_budget_changes": False})
        native = helper.NativeSession.start(blender=blender, asset=ROOT / asset,
            workspace=folder / "native", deadline_ns=deadline_ns, condition="P",
            expected_asset_sha256=sha(references[asset]), max_calls=MAX_CALLS)
        original_native_exchange = native._exchange

        def native_exchange(request, timeout_s):
            nonlocal native_rpc_count
            native_rpc_count += 1
            return logged_call("native_rpc", native_rpc_count,
                {"request": copy.deepcopy(request), "timeout_s": timeout_s},
                lambda: original_native_exchange(request, timeout_s))

        native._exchange = native_exchange
        initial = snapshot("INITIAL_SNAPSHOT")
        host = product.BlenderMCPHost(runtime, native.host, native.port, timeout_s=RPC_TIMEOUT_S)
        original_host_request = host._request
        original_host_exchange = host._exchange

        def host_exchange(payload):
            nonlocal host_wire_count
            host_wire_count += 1
            request = json.loads(payload)
            need(request["type"] == "execute_code", "host_wire_request_type")
            host_script_hashes.append(sha(request["params"]["code"].encode("utf8")))
            return logged_call("host_wire", host_wire_count,
                {"payload_utf8": payload.decode("utf8"), "payload_sha256": sha(payload), "bytes": len(payload)},
                lambda: original_host_exchange(payload))

        def host_request(command, params):
            nonlocal host_rpc_count
            host_rpc_count += 1
            need(command in {"capture_task", "capture_nearest_candidates"}, "unexpected_nonreadonly_host_command_" + command)
            response = logged_call("host_rpc", host_rpc_count,
                {"command": command, "params": copy.deepcopy(params)},
                lambda: original_host_request(command, params))
            capture = response["capture"] if command == "capture_nearest_candidates" else response
            token = capture.get("capture_state")
            need(type(token) is dict and set(token) == {"instance_id", "epoch", "revision", "selection_key"}
                 and type(token["instance_id"]) is str and type(token["selection_key"]) is str
                 and type(token["epoch"]) is int and type(token["revision"]) is int,
                 "missing_capture_source_epoch_revision_selection")
            capture_bindings.append(copy.deepcopy({"command": command, "capture_state": token,
                "source": capture["source"], "scene_revision": capture["revision"],
                "host_identity": capture.get("host_identity"), "capture_scope": capture.get("capture_scope"),
                "task_selection": capture.get("task_selection"),
                "nearest_binding": response.get("binding")}))
            return response

        host._exchange = host_exchange
        host._request = host_request
        config = {"schema_version": "1.0", "enabled": True, "observe_on_prompt": False,
            "project_root": str(runtime), "state_file": str(folder / "state.json"),
            "audit_file": str(folder / "audit.jsonl"), "quad_size": 128,
            "request_budget_s": 30., "max_sessions": 4,
            "expected_identity": {"source_sha256": digest, "source_kind": "source_checkout"},
            "blender": {"host": native.host, "port": native.port, "timeout_s": 30.}}
        write("PRODUCT_CONFIG.json", config)
        service = product.LiveSpatialService(folder / "PRODUCT_CONFIG.json", host=host, production_mode=True)
        ordinary = product.LiveSpatialMCPServer(service, default_session_id=SESSION_ID)
        simple = product.LiveSpatialMCPServer(service, default_session_id=SESSION_ID, spatial_task_only=True)
        state_before = observe_state_files(folder)
        write("ACTION_STATE_BEFORE.json", state_before)
        directory = {"jsonrpc": "2.0", "id": "directory", "method": "tools/list", "params": {}}
        for label, server in (("ordinary", ordinary), ("S", simple)):
            write(label + "_DIRECTORY_REQUEST.json", directory)
            response = server.handle_jsonrpc_message(copy.deepcopy(directory))
            write(label + "_DIRECTORY_RESPONSE.json", response)
            names = [tool["name"] for tool in response["result"]["tools"]]
            if label == "S":
                need(names == ["human_eye_spatial_relations", "human_eye_surface_nearest"], "S_directory")
            else:
                need("human_eye_scene_observe" in names and not {"human_eye_spatial_relations", "human_eye_surface_nearest"}.intersection(names),
                     "ordinary_directory")
        if case == "assembly":
            truth = json.loads(references[ASSEMBLY_TRUTH])["states"]["initial"]
            target = {"name": truth["target"]}
            candidates = [{"name": name} for name in truth["probes"]]
            ordinary_args = {"session_id": SESSION_ID, "include_image": False,
                "query": {"mode": "task", "target": target, "candidates": candidates,
                          "requested_facts": ["closed_solid_relation", "surface_proximity", "aabb"]}}
            simple_name = "human_eye_spatial_relations"
            simple_args = {"target": target, "candidates": candidates, "include_aabb": True}
        else:
            ordinary_args = {"session_id": SESSION_ID, "include_image": False,
                "query": {"mode": "surface_nearest", "objects": [{"name": "Target"}]}}
            simple_name = "human_eye_surface_nearest"
            simple_args = {"target": {"name": "Target"}}
        facts = []
        for label, server, name, arguments in (("ordinary", ordinary, "human_eye_scene_observe", ordinary_args),
                                                ("S", simple, simple_name, simple_args)):
            request = {"jsonrpc": "2.0", "id": case + "-" + label, "method": "tools/call",
                       "params": {"name": name, "arguments": arguments}}
            write(label + "_REQUEST.json", request)
            response = server.handle_jsonrpc_message(copy.deepcopy(request))
            write(label + "_RESPONSE.json", response)
            facts.append(fact_from_rpc(response))
            write(label + "_FACT.json", facts[-1])
        expected = product.project(copy.deepcopy(facts[0])) if case == "assembly" else facts[0]
        need(without_trace(expected) == without_trace(facts[1]), case + "_full_fact_equivalence")
        need(len(capture_bindings) == 2 and capture_bindings[0] == capture_bindings[1],
             case + "_source_epoch_revision_selection_equivalence")
        need(facts[0]["binding"]["runtime_source_sha256"] == digest, "ordinary_fact_runtime_source_binding")
        simple_binding = facts[1]["context"] if case == "assembly" else facts[1]["binding"]
        need(simple_binding["runtime_source_sha256"] == digest, "S_fact_runtime_source_binding")
        write("CAPTURE_BINDING_EQUIVALENCE.json", {"equal": True, "captures": capture_bindings,
            "runtime_source_sha256": digest,
            "scope": "source, instance, epoch, revision, selection, document identity and acquisition binding"})
        independent = (check_assembly if case == "assembly" else check_d48)(facts[0], initial, references)
        write("INDEPENDENT_TRUTH_CHECKS.json", independent)
        state_after = observe_state_files(folder)
        need(state_after == state_before, "read_entry_changed_action_state")
        write("ACTION_STATE_AFTER.json", state_after)
        # Retain capture source/instance/epoch/revision/selection proof in full
        # host RPC responses, and separately expose the exact equality criterion.
        result.update(facts_equivalent=True, ignored_fields=["top-level trace_id only"],
            independent_truth=independent, action_state_unchanged=True,
            comparison="existing relations projection" if case == "assembly" else "full unprojected nearest fact",
            binding_fields_preserved=True, unknown_and_partial_fields_preserved=True)
    except BaseException as exc:
        result["errors"].append(error_record(exc))
    finally:
        if native is not None:
            try:
                final = snapshot("FINAL_SNAPSHOT")
                need(initial is not None and final == initial, "terminal_scene_changed")
                result["initial_final_snapshot_equal"] = True
            except BaseException as exc:
                result["errors"].append(error_record(exc))
        # Close the product connector first, then the owned worker regardless of
        # any capture/publication error. No user GUI process is involved.
        if host is not None:
            try:
                host.close()
                need(host.is_alive is False, "product_host_close")
                write("PRODUCT_HOST_CLOSE.json", {"closed": True, "at_ns": time.perf_counter_ns()})
            except BaseException as exc:
                result["errors"].append(error_record(exc))
        if native is not None:
            try:
                closed = native.close()
                result["native_close"] = closed
                need(closed["process_reaped"] is True and closed["exit_code"] == 0
                     and closed["error"] is None and closed["source_file_unchanged"] is True
                     and closed["protected_files_unchanged"] is True, "native_close_failure")
                status = native.status()
                write("NATIVE_FINAL_STATUS.json", status)
                terminal = status["closed"]
                need(terminal is not None and terminal["poisoned"] is False
                     and terminal["initial_geometry_fingerprint"] == terminal["final_geometry_fingerprint"], "native_terminal_geometry")
                events = [json.loads(line) for line in (folder / "native/WORKER_EVENTS.jsonl").read_bytes().splitlines()]
                scripts = [event for event in events if "script_sha256" in event]
                need(len(scripts) == host_wire_count + 2 and len(scripts) <= MAX_CALLS,
                     "all_native_executions_accounted")
                need(all(event["status"] == "completed" and event["terminal_geometry_and_file_checks_passed"] is True
                         and event["changed_or_new_PNG_files"] == [] and event["render_events_after"] == 0
                         for event in scripts), "native_execution_terminal_checks")
                need([event["script_sha256"] for event in scripts] == [sha(SNAPSHOT.encode("utf8")), *host_script_hashes, sha(SNAPSHOT.encode("utf8"))],
                     "native_scripts_match_logged_requests")
                write("RPC_ACCOUNTING.json", {"worker_events": events,
                    "script_count": len(scripts), "host_scripts": host_script_hashes,
                    "native_snapshot_scripts": 2, "product_setter_commands": 0,
                    "product_save_commands": 0, "new_images": 0,
                    "protection_scope": "fixed readonly commands, complete script audit and terminal geometry/file checks; no Python sandbox or reverted-transient-mutation claim",
                    "worker_artifacts": [{"path": path.relative_to(output).as_posix(), "sha256": sha(path.read_bytes())}
                        for path in sorted((folder / "native").rglob("*")) if path.is_file()]})
            except BaseException as exc:
                result["errors"].append(error_record(exc))
        result.update(native_client_rpc_count=native_rpc_count, host_rpc_count=host_rpc_count,
                      host_wire_count=host_wire_count, ended_ns=time.perf_counter_ns())
        checks = evidence.checks(deadline_ns)
        result["publication_checks"] = checks
        result["passed"] = (not result["errors"] and checks["deadline_ok"] and checks["source_ok"]
                            and result.get("facts_equivalent") is True
                            and result.get("initial_final_snapshot_equal") is True)
        write("RESULT.json", result, failure=not result["passed"])
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-source-sha256", required=True)
    parser.add_argument("--output", required=True, help="Fresh immediate child directory of this runner's directory")
    parser.add_argument("--blender", type=Path, default=Path("D:/Tools/blender5.2/blender.exe"))
    args = parser.parse_args(argv)
    need(len(args.expected_source_sha256) == 64 and all(c in "0123456789abcdef" for c in args.expected_source_sha256), "expected_canonical_format")
    need(Path(args.output).name == args.output and args.output not in (".", ".."), "output_name")
    output = (HERE / args.output).resolve()
    need(output.parent == HERE and not output.exists(), "exclusive_output")
    output.mkdir(exist_ok=False)
    sys.dont_write_bytecode = True
    started = time.perf_counter_ns()
    evidence = Evidence(output, started + 2 * CASE_WINDOW_NS)
    results = []
    summary = {"schema": "m1-entry-blender-equivalence-v1", "passed": False,
        "started_ns": started, "cases": results, "errors": [], "model_calls": 0,
        "source_kind": "source_checkout", "installation_qualification": False,
        "speed_benefit_qualification": False, "shared_GUI_touched": False}
    try:
        runtime, blobs, manifest, digest, references = prepare_snapshot(output, args.expected_source_sha256, evidence)
        product = load_product(runtime, blobs, manifest, digest, evidence)
        helper = load_native(references)
        blender = args.blender.resolve()
        need(blender.is_file(), "blender_binary_missing")
        binary_sha = sha(blender.read_bytes())
        original_check = evidence.check_sources

        def check_sources():
            original_check()
            need(sha(blender.read_bytes()) == binary_sha, "blender_binary_changed")
            return True

        evidence.check_sources = check_sources
        evidence.write("EXECUTION_IDENTITY_INITIAL.json", {"identity": product.identity,
            "blender": str(blender), "blender_sha256": binary_sha,
            "guard_verify_loaded": product.guard.verify_loaded(),
            "helper_sha256": sha(references[NATIVE_HELPER]), "root": str(runtime)})
        for case in ("assembly", "D48"):
            result = run_case(case, output=output, runtime=runtime, digest=digest,
                references=references, product=product, helper=helper, blender=blender, evidence=evidence)
            results.append(result)
            if not result["passed"]:
                break  # Fail closed; no replacement, retry or partial success.
        for result in results:
            deadline_check(result["original_deadline_ns"])
        witnesses = {name: product.guard._executed[id(module)][1] for name, module in list(sys.modules.items())
            if id(module) in product.guard._executed}
        evidence.write("EXECUTION_IDENTITY_FINAL.json", {"identity": product.identity,
            "source_file_count": len(manifest), "guard_verify_loaded": product.guard.verify_loaded(),
            "loaded_product_witnesses": witnesses, "source_and_reference_checks": evidence.checks(),
            "runtime_manifest": manifest})
        summary["passed"] = len(results) == 2 and all(result["passed"] for result in results)
    except BaseException as exc:
        summary["errors"].append(error_record(exc))
    finally:
        summary["ended_ns"] = time.perf_counter_ns()
        checks = evidence.checks()
        summary["publication_checks"] = checks
        summary["passed"] = summary["passed"] and not summary["errors"] and checks["deadline_ok"] and checks["source_ok"]
        evidence.write("SUMMARY.json", summary, failure=not summary["passed"])
    print(json.dumps({"output": str(output), "passed": summary["passed"],
                      "cases": [{"case": row["case"], "passed": row["passed"]} for row in results]}))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
