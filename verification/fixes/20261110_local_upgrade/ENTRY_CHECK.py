"""Read-only owned-fixture acceptance through the installed default MCP entry.

G_low/G60_D12 and D_mid/D48: one cold and two warm observations each.
This measures a separate MCP process, not SCALE-OPT's in-process benchmark.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import traceback
import types


HERE = Path(__file__).resolve().parent
BUILD = "3fc2651e108ad7ac252394871d78e1abaee1200c92a018125984b2fc240193bd"
COMMIT = "df016079b0265ee327f884c90dd4815c392016b6"
RELEASE = "9.7.2+20261110.scale.opt.r1"
ENTRY_SHA = "e8f710dd283be03acf01a29f3b811a41ef767fd12b2fb6372fa8b628269617d2"
HELPER_SHA = "d636da8ad4d6e052792bb26163ac46dabc006db93635548e027003d4a9cd5ece"
SCORER_SHA = "5f9193ffda1bc341f0e47f56fef4e629ba4f305c162fb0ebc7bbab047314f77e"
ORACLE_SHA = "4c6d45ddc087e2c9c38864890a4f99333e3c6cda40c6f36397b1768791509720"
DEFAULT_DIAG = Path("C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/scale_diag_001")
DEFAULT_PYTHON = Path("D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe")
DEFAULT_ENTRY = Path("D:/hefe/.human-eye/releases") / RELEASE / "admin/target_runtime_entry.py"
BLENDER = Path("D:/Tools/blender5.2/blender.exe")


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_bytes())


def save(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")


def fixed_module(name, path, expected_sha):
    require(sha(path) == expected_sha, "Frozen helper changed: " + str(path))
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(Path(path).read_bytes(), str(path), "exec", dont_inherit=True), module.__dict__)
    return module


def check_identity(value):
    count = len(value["source_files"]) if "source_files" in value else value.get("source_file_count")
    require(value.get("source_sha256") == BUILD and count == 137
            and value.get("source_kind") == "installed_distribution"
            and value.get("distribution_version") == RELEASE, "Actual runtime identity differs")


class MCP:
    def __init__(self, python, entry, config, folder):
        self.folder = folder
        folder.mkdir()
        self.responses = queue.Queue()
        self.sequence = 0
        self.calls = []
        self.started_ns = time.perf_counter_ns()
        self.stderr = (folder / "STDERR.txt").open("xb")
        self.process = subprocess.Popen([str(python), "-I", "-B", str(entry),
            "serve", "--config", str(config)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self.stderr, cwd=str(folder), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

        def read():
            try:
                while True:
                    raw = self.process.stdout.readline(64 * 1024 * 1024 + 1)
                    if not raw:
                        break
                    self.responses.put((raw, time.perf_counter_ns()))
            finally:
                self.responses.put((None, time.perf_counter_ns()))

        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()

    def call(self, method, params=None, label=None):
        self.sequence += 1
        request = dict(jsonrpc="2.0", id=self.sequence, method=method, params=params or {})
        name = "%02d_%s" % (self.sequence, label or method.replace("/", "_"))
        save(self.folder / (name + "_REQUEST.json"), request)
        raw_request = json.dumps(request, separators=(",", ":"), allow_nan=False).encode() + b"\n"
        started = time.perf_counter_ns()
        row = dict(id=self.sequence, method=method, label=label, request_bytes=len(raw_request))
        self.calls.append(row)
        try:
            self.process.stdin.write(raw_request)
            self.process.stdin.flush()
            raw, arrived = self.responses.get(timeout=45)
            require(raw is not None and len(raw) <= 64 * 1024 * 1024, "MCP exit or oversized response")
            (self.folder / (name + "_RESPONSE.json")).write_bytes(raw)
            value = json.loads(raw)
            require(value.get("jsonrpc") == "2.0" and value.get("id") == self.sequence
                    and "error" not in value, "MCP correlation or protocol error")
            row.update(rtt_ns=arrived-started, response_bytes=len(raw), arrived_ns=arrived,
                       response_parsed_and_archived_ns=time.perf_counter_ns()-started)
            return value, row
        except BaseException as exc:
            row.update(error=dict(type=type(exc).__name__, message=str(exc)), elapsed_ns=time.perf_counter_ns()-started)
            raise

    def close(self):
        started = time.perf_counter_ns()
        forced = False
        try:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                forced = True
                self.process.kill()
                self.process.wait(timeout=5)
        finally:
            self.reader.join(timeout=2)
            self.stderr.close()
            self.process.stdout.close()
        return dict(pid=self.process.pid, exit_code=self.process.returncode,
            process_reaped=self.process.poll() is not None, forced_kill=forced,
            reader_joined=not self.reader.is_alive(), close_ns=time.perf_counter_ns()-started)


def metadata(value):
    envelope = value["result"]
    texts = [row["text"] for row in envelope["content"] if row["type"] == "text"]
    require(len(texts) == 1 and not envelope.get("isError"), "Tool result is an error or lacks one text payload")
    return json.loads(texts[0])


def score_input(response, mode):
    """Adapt the normal task-set wire shape for the frozen scalar scorer.

    The dedicated spatial tool had candidates/context. Normal scene_observe
    publishes the same measured values as pairs/binding; raw output is retained.
    """
    if mode != "G":
        return response
    payload = metadata(response)
    require(payload.get("schema_version") == "task-query-set-v1", "Unexpected normal task-set schema")
    objects = {obj["object_id"]: obj["name"] for obj in payload["binding"]["objects"]}
    pairs = payload["pairs"]
    require(len(pairs) == 1 and pairs[0]["candidate_index"] == 0, "One ordered candidate required")
    candidate = pairs[0]
    projection = dict(status=payload["status"], context=payload["binding"], candidates=[
        dict(name=objects[candidate["object_id"]], **candidate["facts"])])
    return dict(jsonrpc=response["jsonrpc"], id=response["id"], result=dict(
        content=[dict(type="text", text=json.dumps(projection, allow_nan=False))],
        isError=response["result"].get("isError", False)))


def lane(args, cell, scene, mode, helper, scorer, snapshot, freeze, oracle):
    folder = args.output / cell
    folder.mkdir()
    begun = time.perf_counter_ns()
    native = mcp = None
    result = dict(cell=cell, scene=scene, mode=mode, status="failed", expected_observations=3, observations=[],
                  runtime_source_sha256=BUILD, fixed_commit=COMMIT, default_mcp_mode=True)
    fixture = load(args.diag / "fixtures" / (scene + ".json"))
    asset = args.diag / "fixtures" / (scene + ".blend")
    try:
        native = helper.NativeSession.start(blender=BLENDER, asset=asset, workspace=folder / "native",
            deadline_ns=begun+570*10**9, condition="P", expected_asset_sha256=freeze["files"]["fixtures/"+scene+".blend"], max_calls=128)
        initial_receipt = native.run(snapshot, timeout_s=30)
        save(folder / "INITIAL_RECEIPT.json", initial_receipt)
        initial = scorer.receipt_payload(initial_receipt)
        save(folder / "INITIAL.json", initial)
        require(initial == {key: fixture[key] for key in ("unit_scale_m", "objects")}, "Initial worldmesh differs from frozen fixture")
        config = dict(schema_version="1.0", enabled=True, observe_on_prompt=False,
            project_root=str(args.entry.parent.parent / "site-packages"),
            state_file=str(folder / "state.json"), audit_file=str(folder / "audit.jsonl"),
            quad_size=128, request_budget_s=30.0, max_sessions=4,
            expected_identity={"source_sha256": BUILD},
            blender=dict(host=native.host, port=native.port, timeout_s=30.0))
        config_path = folder / "CONFIG.json"
        save(config_path, config)
        mcp = MCP(args.python, args.entry, config_path, folder / "mcp")
        response, timing = mcp.call("initialize", dict(protocolVersion="2025-03-26", capabilities={},
            clientInfo=dict(name="human-eye-local-upgrade-check", version="1")))
        check_identity(response["result"]["_meta"]["human_eye"])
        result["mcp_spawn_to_initialized_ns"] = timing["arrived_ns"]-mcp.started_ns
        mcp.call("ping")
        response, _ = mcp.call("tools/list")
        tools = {tool["name"]: tool for tool in response["result"]["tools"]}
        require({"human_eye_scene_observe", "human_eye_transform", "human_eye_clearance_segment",
                 "human_eye_connection_status", "human_eye_arm_twist_observe"} <= set(tools)
                and "human_eye_spatial_relations" not in tools, "Default MCP tool exposure differs")
        modes = tools["human_eye_scene_observe"]["inputSchema"]["properties"]["query"]["properties"]["mode"]["enum"]
        require("task" in modes and "surface_nearest" in modes, "Default scene_observe lacks new query modes")
        response, _ = mcp.call("tools/call", dict(name="human_eye_connection_status", arguments={}), "status_before")
        check_identity(metadata(response)["runtime_identity"])
        result["normal_tools_verified"] = sorted(tools)
        for repeat in range(3):
            query = (dict(mode="task", target=dict(name="Target"), candidates=[dict(name="Peer_000")],
                requested_facts=["closed_solid_relation", "surface_proximity"]) if mode == "G" else
                dict(mode="surface_nearest", objects=[dict(name="Target")]))
            arguments = dict(session_id="scale-entry-task", include_image=False, query=query)
            response, timing = mcp.call("tools/call", dict(name="human_eye_scene_observe", arguments=arguments), "observe_%d" % repeat)
            row = dict(repeat=repeat, cold=repeat == 0, rtt_ns=timing["rtt_ns"],
                response_bytes=timing["response_bytes"], score=dict(task_success=False, outcome="scoring_not_completed"))
            result["observations"].append(row)
            projected = score_input(response, mode)
            if mode == "G":
                save(folder / ("SCORER_INPUT_%d.json" % repeat), projected)
            row["score"] = scorer.answer_score(dict(result=projected, exception=None), "P", mode, fixture,
                oracle[scene], dict(source_canonical=BUILD, accuracy_m=freeze["accuracy_m"]))
            save(folder / ("SCORE_%d.json" % repeat), row)
            if repeat == 0:
                result["mcp_spawn_to_first_answer_ns"] = timing["arrived_ns"]-mcp.started_ns
                result["owned_chain_start_to_first_answer_ns"] = timing["arrived_ns"]-begun
        mcp.call("ping", label="ping_after")
        response, _ = mcp.call("tools/call", dict(name="human_eye_connection_status", arguments={}), "status_after")
        final_status = metadata(response)
        check_identity(final_status["runtime_identity"])
        require(not final_status.get("inflight_operation") and not final_status.get("quarantined"), "Unexpected pending runtime state")
        final_receipt = native.run(snapshot, timeout_s=30)
        save(folder / "FINAL_RECEIPT.json", final_receipt)
        final = scorer.receipt_payload(final_receipt)
        save(folder / "FINAL.json", final)
        require(final == initial, "Read-only observations changed source scene")
        result["initial_and_final_worldmesh_equal"] = True
        result["status"] = "passed" if all(row["score"]["task_success"] for row in result["observations"]) else "failed"
    except BaseException as exc:
        result["error"] = dict(type=type(exc).__name__, message=str(exc), traceback=traceback.format_exc())
    finally:
        for name, obj in (("mcp", mcp), ("blender", native)):
            if obj is not None:
                try:
                    result[name+"_close"] = obj.close()
                    if name == "mcp":
                        result["protocol_calls"] = obj.calls
                    else:
                        status = obj.status()
                        save(folder / "WORKER_STATUS.json", status)
                        closed = status.get("closed") or {}
                        require(status["source_file_unchanged"] and status["protected_files_unchanged"]
                            and not closed.get("poisoned", True)
                            and closed.get("initial_geometry_fingerprint") == closed.get("final_geometry_fingerprint"), "Owned worker final source check failed")
                    close = result[name+"_close"]
                    require(close["process_reaped"] and close["exit_code"] == 0 and not close.get("forced_kill")
                            and not close.get("error"), name+" failed normal close/reap")
                except BaseException as exc:
                    result["status"] = "failed"
                    result.setdefault("cleanup_errors", []).append(dict(process=name, type=type(exc).__name__, message=str(exc)))
        result["whole_owned_chain_ns"] = time.perf_counter_ns()-begun
        result["unattempted_observations"] = 3-len(result["observations"])
        save(folder / "RESULT.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entry", type=Path, default=DEFAULT_ENTRY)
    parser.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    parser.add_argument("--diag", type=Path, default=DEFAULT_DIAG)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cells", nargs="+", choices=("G_low", "D_mid"), default=["G_low", "D_mid"])
    args = parser.parse_args()
    for key in ("entry", "python", "diag", "output"):
        setattr(args, key, getattr(args, key).resolve())
    require(sha(args.entry) == ENTRY_SHA, "Installed entry differs from fixed installation")
    freeze = load(args.diag / "FREEZE.json")
    needed = ["driver.py", "session.py", "ORACLE.json"] + ["fixtures/"+scene+suffix
        for scene in ("G60_D12", "D48") for suffix in (".blend", ".json")]
    for relative in needed:
        require(sha(args.diag / relative) == freeze["files"][relative], "Frozen test input changed: " + relative)
    require(sha(args.diag / "ORACLE.json") == ORACLE_SHA, "Oracle differs")
    helper = fixed_module("upgrade_owned_session", args.diag / "session.py", HELPER_SHA)
    scorer = fixed_module("upgrade_pure_scorer", args.diag / "quality_review.py", SCORER_SHA)
    tree = ast.parse((args.diag / "driver.py").read_bytes())
    snapshot = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "SNAPSHOT" for target in node.targets))
    oracle = {value["id"]: value for value in load(args.diag / "ORACLE.json")["snapshots"]}
    args.output.mkdir(parents=True, exist_ok=False)
    save(args.output / "CONTRACT.json", dict(commit=COMMIT, build=BUILD, entry=str(args.entry), entry_sha256=ENTRY_SHA,
        source_count=137, python=str(args.python), diag=str(args.diag), script_sha256=sha(__file__),
        input_sha256={relative:sha(args.diag / relative) for relative in needed}, scorer_sha256=SCORER_SHA,
        logical_observations=3*len(args.cells), cells=args.cells, per_fixture="one cold, two warm", request_budget_s=30,
        timing="rtt: stdin write through complete stdout response arrival; MCP spawn through initialized and first-answer separately; whole owned chain includes fixture start, proof readbacks and close/reap",
        comparison="separate-process default MCP acceptance; not comparable as a speed delta to prior in-process SCALE-OPT samples",
        model_calls=0, hooks="not_run", default_configuration_changed=False))
    rows = []
    for cell, scene, mode in (("G_low", "G60_D12", "G"), ("D_mid", "D48", "D")):
        if cell not in args.cells:
            continue
        result = lane(args, cell, scene, mode, helper, scorer, snapshot, freeze, oracle)
        rows.append(result)
        print(json.dumps(dict(cell=cell, status=result["status"], observations=len(result["observations"]),
            rtt_ms=[row["rtt_ns"]/1e6 for row in result["observations"]]), ensure_ascii=False), flush=True)
    summary = dict(status="passed" if all(row["status"] == "passed" for row in rows) else "failed",
        logical_denominator=3*len(args.cells), correct=sum(observation["score"]["task_success"] for row in rows for observation in row["observations"]),
        unattempted=sum(row["unattempted_observations"] for row in rows), lanes=rows,
        default_configuration_changed=False, model_calls=0, real_host_hook="not_run")
    save(args.output / "SUMMARY.json", summary)
    return 0 if summary["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
