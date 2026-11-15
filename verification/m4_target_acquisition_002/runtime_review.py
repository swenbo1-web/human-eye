"""Audit closed M4 target002 original evidence, without live product operations."""

import ast
import base64
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import re
import statistics
import struct
import zlib


HERE = Path(__file__).resolve().parent
RUNTIME = Path("D:/he_m4_target_002")
QUALIFICATION = ["A_main", "A_target_only", "B_main", "B_target_only"]
CACHE = RUNTIME / "controls/B_cache_move_restore"
LIMITS = {"Blender_start_attempts": 24, "qualification_rasters": 48,
          "formal_rasters": 72, "all_rasters": 120}
REQUEST_IDS = ["target_observation", "after_active_ping", "source_readback", "after_readback_ping"]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def lines(path):
    return [json.loads(line) for line in Path(path).read_bytes().splitlines() if line.strip()]


def forward(points, matrix, scale):
    return [[(((matrix[axis][0] * point[0] + matrix[axis][1] * point[1])
                + matrix[axis][2] * point[2]) + matrix[axis][3]) * scale
             for axis in range(3)] for point in points]


class Review:
    def __init__(self):
        self.pins = {}
        self.checks = []
        self.costs = []
        self.bindings = {}
        self.sessions = []
        self.runtime_files = []
        self.transfers = []
        self.scope_rows = []
        self.formal_metrics = {}
        self.requests = []

    def pin(self, path, role):
        path = Path(path).resolve()
        key = str(path)
        if key not in self.pins:
            raw = path.read_bytes()
            self.pins[key] = {"path": key, "bytes": len(raw), "sha256": digest(raw), "roles": []}
        if role not in self.pins[key]["roles"]:
            self.pins[key]["roles"].append(role)
        return self.pins[key]

    def check(self, name, flag, actual=None):
        row = {"name": name, "passed": bool(flag)}
        if actual is not None:
            row["actual"] = actual
        self.checks.append(row)

    def source(self, path):
        binding = read(path)
        self.pin(path, "actual installation binding")
        key = binding["source_sha256"]
        if key in self.bindings:
            return binding
        manifest = binding["source_manifest"]
        root = Path(binding["install_root"])
        for row in manifest:
            self.check(key[:8] + "/installed/" + row["path"],
                       self.pin(root / row["path"], "installed product source")["sha256"] == row["sha256"])
        identity = {name: binding[name] for name in ("base_version", "implementation_revision")}
        identity["files"] = manifest
        actual = digest(json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode())
        self.check(key[:8] + "/source141", actual == key and len(manifest) == 141)
        self.bindings[key] = binding
        return binding

    def wire(self, root, binding, label, cache=False):
        """Decode original bytes, and reconstruct only actually returned captures."""
        index = read(root / "native/WIRE/INDEX.json")
        manifest = {row["path"]: row["sha256"] for row in binding["source_manifest"]}
        install = Path(binding["install_root"])
        resources = {}
        captures = {}
        commands = []
        payloads = []
        setups = []
        for item in index:
            folder = root / "native/WIRE" / f"{item['sequence']:03}"
            tx = (folder / "REQUEST.bin").read_bytes()
            rx = (folder / "RESPONSE.bin").read_bytes()
            request, response = json.loads(tx), json.loads(rx)
            self.check(label + "/TCP/" + str(item["sequence"]),
                       len(tx) == item["request_bytes"] and len(rx) == item["response_attempted_bytes"]
                       and item["response_sendall_completed"] is True
                       and item["request_response_attempted_bytes"] == len(tx) + len(rx))
            row = {"session": label, "sequence": item["sequence"], "request_bytes": len(tx),
                   "response_bytes": len(rx), "request_type": request["type"],
                   "request_sha256": digest(tx), "response_sha256": digest(rx)}
            commands.append(request["type"])
            if request["type"] in ("qa_far11_move", "qa_far11_restore"):
                self.check(label + "/fixed_setup_command/" + str(item["sequence"]),
                           cache and request == {"type": request["type"], "params": {}}
                           and response.get("status") == "success")
                setups.append({"sequence": item["sequence"], "request": request, "response": response})
                self.transfers.append(row)
                continue
            if request["type"] != "execute_code":
                self.transfers.append(row)
                continue
            code = request["params"]["code"]
            for node in ast.walk(ast.parse(code)):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == "compile" and len(node.args) >= 2):
                    continue
                expression = node.args[0]
                if not (isinstance(expression, ast.Call) and isinstance(expression.func, ast.Attribute)
                        and expression.func.attr == "decompress"):
                    continue
                blob = zlib.decompress(base64.b64decode(ast.literal_eval(expression.args[0].args[0]), validate=True))
                loaded = Path(ast.literal_eval(node.args[1]))
                relative = loaded.relative_to(install).as_posix()
                actual_sha = digest(blob)
                self.check(label + "/executed_source/" + relative,
                           actual_sha == manifest[relative]
                           and self.pin(loaded, "source loaded through actual TCP bootstrap")["sha256"] == actual_sha)
                payloads.append({"path": relative, "sha256": actual_sha, "bytes": len(blob)})
            match = re.search(r"_request = _json.loads\((.+)\)\n", code)
            if match is None:
                self.check(label + "/known_host_command/" + str(item["sequence"]), False)
                self.transfers.append(row)
                continue
            command = json.loads(ast.literal_eval(match.group(1)))
            row["host_command"] = command["command"]
            self.check(label + "/read_only_host_command/" + str(item["sequence"]),
                       command["command"] in ("capture_active_observation", "capture_task"))
            self.check(label + "/completed_host_response/" + str(item["sequence"]), response.get("status") == "success")
            stdout = response.get("result", {}).get("result", "")
            marked = [line for line in stdout.splitlines() if line.startswith("HUMAN_EYE_BLENDER_MCP:")]
            self.check(label + "/single_host_marker/" + str(item["sequence"]), len(marked) == 1)
            if len(marked) == 1:
                inner = json.loads(marked[0].split(":", 1)[1])
                self.check(label + "/no_host_error/" + str(item["sequence"]), "error" not in inner)
                packet = inner.get("result", {})
                row["marked_result_UTF8_bytes"] = len(marked[0].encode("utf-8"))
                row["stdout_UTF8_bytes"] = len(stdout.encode("utf-8"))
                if isinstance(packet, dict):
                    row["returned_resource_count"] = len(packet.get("resources", []))
                    row["returned_resource_vertices"] = sum(len(value.get("vertices_local", [])) for value in packet.get("resources", []))
                    row["returned_resource_faces"] = sum(len(value.get("faces", [])) for value in packet.get("resources", []))
                    for resource in packet.get("resources", []):
                        resources[(resource["id"], resource["revision"])] = resource
                    capture = copy.deepcopy(packet.get("capture", packet))
                    if isinstance(capture, dict) and capture.get("meshes"):
                        for mesh in capture["meshes"]:
                            reference = mesh.pop("_scene_resource", None)
                            if reference is not None:
                                resource = resources[(reference["id"], reference["revision"])]
                                mesh.update(vertices=forward(resource["vertices_local"], reference["matrix"], reference["scale"]),
                                            faces=resource["faces"], edges=resource["edges"])
                        captures[item["sequence"]] = {"capture": capture, "command": command}
                        row["capture_meshes"] = len(capture["meshes"])
                        row["capture_vertices"] = sum(len(mesh["vertices"]) for mesh in capture["meshes"])
                        row["capture_faces"] = sum(len(mesh["faces"]) for mesh in capture["meshes"])
                        row["actual_target_work"] = capture.get("observation_target", {}).get("work")
            self.transfers.append(row)
        expected = ["execute_code", "execute_code", "close"]
        if cache:
            expected = ["execute_code", "execute_code", "qa_far11_move", "execute_code", "execute_code",
                        "qa_far11_restore", "execute_code", "execute_code", "close"]
        self.check(label + "/actual_host_step_order", commands == expected, commands)
        self.check(label + "/actual_host_source_present", any(row["path"] == "human_eye_plugin/blender_host.py" for row in payloads))
        return captures, setups

    def public_phase(self, root, folder, result, state, binding, decoded, label):
        requested = state["requests"]
        self.check(label + "/fixed_four_calls", [row["id"] for row in requested] == REQUEST_IDS)
        self.check(label + "/post_main_pings", all(row["ping_success"] is True for row in requested if row.get("result_kind") == "ping"))
        original = []
        for rpc in sorted((root / "stdio").glob("rpc_*")):
            if not (rpc / "TX.bin").is_file() or not (rpc / "RX.bin").is_file():
                continue
            receipt = read(rpc / "RECEIPT.json")
            original.append({"folder": rpc, "receipt": receipt,
                             "request": read(rpc / "TX.bin"), "response": read(rpc / "RX.bin")})
        audit = lines(root / "io_audit/MCP_IO.jsonl")
        matched = {}
        for index, request in enumerate(requested, 1):
            name = request["id"]
            begin, end = request["client_call_started_ns"], request["client_call_completed_ns"]
            candidates = [row for row in original if row["request"].get("id") == name
                          and begin <= row["receipt"]["started_ns"] <= row["receipt"]["closed_ns"] <= end]
            self.check(label + "/single_original_receipt/" + name, len(candidates) == 1)
            if len(candidates) != 1:
                continue
            item = candidates[0]
            receipt = item["receipt"]
            tx = (item["folder"] / "TX.bin").read_bytes()
            rx = (item["folder"] / "RX.bin").read_bytes()
            logical = rx[:-2] + b"\n" if rx.endswith(b"\r\n") else rx
            io = [row for row in audit if row["id"] == name and begin <= row["request_received_ns"] <= end]
            self.check(label + "/single_server_receipt/" + name, len(io) == 1)
            if len(io) != 1:
                continue
            io = io[0]
            self.check(label + "/original_request_reply/" + name,
                       item["request"] == read(folder / f"REQUEST_{index:02}.json")
                       and item["response"] == read(folder / f"RESPONSE_{index:02}.json")
                       and request["response_json_sha256"] == self.pin(folder / f"RESPONSE_{index:02}.json", "original public reply")["sha256"])
            self.check(label + "/wire_and_LF_boundary/" + name,
                       len(tx) == io["TX_bytes"] and digest(tx) == io["TX_sha256"]
                       and len(rx) == request["raw_RX_bytes"]
                       and len(logical) == io["RX_text_UTF8_LF_bytes"]
                       and digest(logical) == io["RX_text_UTF8_LF_sha256"])
            server = io["reply_completed_ns"] - io["request_received_ns"]
            transport = receipt["received_complete_ns"] - receipt["stdin_flushed_ns"]
            complete_call = end - begin
            inner = receipt["closed_ns"] - receipt["started_ns"]
            outer_field = request.get("client_outer_including_recording_ns", request.get("complete_client_call_ns"))
            self.check(label + "/three_request_clocks/" + name,
                       server == io["request_to_reply_ns"] == request["server_request_to_reply_ns"]
                       and transport == request["client_flush_to_received_ns"]
                       and complete_call == outer_field and inner <= complete_call
                       and request["client_stdin_flushed_ns"] == receipt["stdin_flushed_ns"]
                       and request["client_received_complete_ns"] == receipt["received_complete_ns"])
            matched[name] = {"request": item["request"], "response": item["response"], "io": io,
                             "TX": tx, "RX": rx, "receipt": receipt,
                             "server_ns": server, "transport_ns": transport,
                             "complete_call_ns": complete_call, "internal_pre_receipt_ns": inner}
            self.requests.append({"label": label, "request_id": name, "main": index == 1,
                                  "server_ns": server, "transport_ns": transport,
                                  "complete_call_ns": complete_call, "internal_pre_receipt_ns": inner,
                                  "TX_bytes": len(tx), "raw_RX_bytes": len(rx),
                                  "LF_text_RX_bytes": len(logical), "stdio_rpc": str(item["folder"])})
        selector = {"name": result["asset"]["target"]}
        active = read(folder / "REQUEST_01.json")
        later = read(folder / "REQUEST_03.json")
        self.check(label + "/fixed_public_arguments", active["params"]["arguments"] == {
            "session_id": "m4-target-acquisition-002", "include_image": True, "response_detail": "full",
            "query": {"mode": "active_observation", "objects": [selector]}}
            and later["params"]["arguments"] == {"session_id": "m4-target-acquisition-002", "include_image": False,
                "query": {"mode": "task", "objects": [selector], "requested_facts": ["aabb"]}})
        main = read(folder / "PUBLIC_01.json")
        response = matched["target_observation"]["response"]
        texts = [block["text"] for block in response["result"]["content"] if block["type"] == "text"]
        self.check(label + "/original_full_main", len(texts) == 1 and json.loads(texts[0]) == main
                   and response["result"]["isError"] is False and main.get("result_kind") == "active_observation")
        self.check(label + "/independent_task_readback", matched["source_readback"]["response"]["result"]["isError"] is False
                   and read(folder / "PUBLIC_03.json").get("result_kind") == "task_query")
        frames = main["frames"]
        pngs = [base64.b64decode(block["data"], validate=True) for block in response["result"]["content"] if block["type"] == "image"]
        receipts = state.get("producer_frames", [])
        self.check(label + "/same_result_producer_count", len(frames) == len(pngs) == len(receipts))
        for index, frame in enumerate(frames):
            png, npz = Path(frame["image_path"]), Path(frame["arrays_path"])
            self.check(label + "/same_result_producer/" + str(index), png.read_bytes() == pngs[index]
                       and self.pin(png, "same original full result PNG")["sha256"] == frame["image_sha256"]
                       and self.pin(npz, "same original full result NPZ")["sha256"] == frame["arrays_sha256"]
                       and png.stat().st_size == frame["PNG_bytes"]
                       and npz.stat().st_size == frame["compressed_array_file_bytes"]
                       and struct.unpack(">II", pngs[index][16:24]) == (512, 512)
                       and receipts[index]["producer_arrays_sha256"] == frame["arrays_sha256"]
                       and receipts[index]["producer_image_sha256"] == frame["image_sha256"])
            self.check(label + "/producer_binding/" + str(index),
                       frame["host_binding_sha256"] == main["binding"]["binding_sha256"]
                       and frame["source_revision"] == main["binding"]["scene_revision"]
                       and frame["scene_identity"] == main["binding"]["geometry_identity"]
                       and frame["candidate_identity"] == main["binding"]["camera_identity"])
        owner = read(folder / "OWNER_BINDING.json")
        self.check(label + "/owner_source", owner["source_proof"]["expected_source_sha256"] == binding["source_sha256"]
                   and owner["source_proof"]["actual_runtime_identity"]["source_sha256"] == binding["source_sha256"]
                   and owner["source_proof"]["actual_runtime_identity"]["source_kind"] == "installed_distribution")
        roles = Counter(row["role"] for row in owner["captures"])
        self.check(label + "/main_readback_roles", roles == {"main_target_capture": 1, "post_main_source_readback": 1})
        for cap in owner["captures"]:
            sequence = int(Path(cap["wire_request"]).parent.name)
            actual = read(cap["capture"])
            self.check(label + "/actual_capture/" + cap["role"], sequence in decoded
                       and decoded[sequence]["capture"] == actual
                       and self.pin(cap["capture"], "actual decoded host capture")["sha256"] == cap["capture_sha256"]
                       and self.pin(cap["wire_request"], "original native request")["sha256"] == cap["wire_request_sha256"]
                       and self.pin(cap["wire_response"], "original native response")["sha256"] == cap["wire_response_sha256"])
            self.check(label + "/capture_instance/" + cap["role"],
                       all(mapping["instance_id"] == actual["host_identity"]["object_instances"][mapping["object_id"]]
                           for mapping in cap["mapping"]))
        main_capture = next(read(cap["capture"]) for cap in owner["captures"] if cap["role"] == "main_target_capture")
        readback = next(read(cap["capture"]) for cap in owner["captures"] if cap["role"] == "post_main_source_readback")
        target = next(mesh for mesh in main_capture["meshes"] if mesh["name"] == result["asset"]["target"])
        self.check(label + "/same_host_actual_later_readback", main_capture["capture_state"]["instance_id"] == readback["capture_state"]["instance_id"]
                   and target["vertices"] == readback["meshes"][0]["vertices"] and target["faces"] == readback["meshes"][0]["faces"])
        observation_target = main_capture.get("observation_target", {})
        self.scope_rows.append({"label": label, "source_sha256": binding["source_sha256"],
                                "actual_mesh_count": len(main_capture["meshes"]),
                                "actual_vertices": sum(len(mesh["vertices"]) for mesh in main_capture["meshes"]),
                                "actual_faces": sum(len(mesh["faces"]) for mesh in main_capture["meshes"]),
                                "target_work": observation_target.get("work"),
                                "scene_directory": observation_target.get("scene_directory"),
                                "full_scene_identity": observation_target.get("full_scene_identity"),
                                "retained_object_ids": observation_target.get("retained_object_ids"),
                                "excluded_object_ids": observation_target.get("excluded_object_ids"),
                                "source_frame": observation_target.get("source_frame"),
                                "public_work": main.get("work"), "generation_work": main.get("generation_work"),
                                "generation_stages": main.get("generation_stages"), "public_stages": main.get("stages"),
                                "missing_fields": "unexposed values remain null, never inferred from source-derived loops"})
        main_io = matched["target_observation"]["io"]
        cost = {"label": label, "source_sha256": binding["source_sha256"],
                "server_request_to_reply_ns": matched["target_observation"]["server_ns"],
                "client_flush_to_received_ns": matched["target_observation"]["transport_ns"],
                "complete_client_call_ns": matched["target_observation"]["complete_call_ns"],
                "internal_pre_receipt_span_ns": matched["target_observation"]["internal_pre_receipt_ns"],
                "complete_session_ns": result["complete_session_ns"],
                "session_scope": "shared single session for all three cache phases" if root == CACHE else "one fresh owned session",
                "postrun_saved_validation_ns": result["postrun_validation_ns"],
                "main_MCP_TX_bytes": len(matched["target_observation"]["TX"]),
                "main_MCP_raw_RX_bytes": len(matched["target_observation"]["RX"]),
                "main_MCP_LF_text_RX_bytes": main_io["RX_text_UTF8_LF_bytes"],
                "main_public_text_UTF8_bytes": sum(len(text.encode("utf-8")) for text in texts),
                "producer_frames": len(frames), "PNG_bytes": sum(len(png) for png in pngs),
                "main_raster_actual": main_io.get("raster_actual"),
                "readback_server_ns": matched["source_readback"]["server_ns"],
                "post_main_pings_server_ns": [matched[name]["server_ns"] for name in ("after_active_ping", "after_readback_ping")]}
        self.costs.append(cost)
        return cost, owner

    def session(self, root, label, formal=False, cache=False):
        result = read(root / "RESULT.json")
        binding = self.source(result["binding_file"])
        self.check(label + "/operational_result", result["passed"] is True and result["errors"] == [])
        self.check(label + "/actual_source_binding", result["source_sha256"] == binding["source_sha256"]
                   and result["binding_sha256"] == self.pin(result["binding_file"], "current source binding")["sha256"])
        A_source = read(HERE / "A_RUN_BINDING.json")["source_sha256"]
        expected_manifest = read(HERE / "SOURCE_FREEZE_B.json")["runtime_manifest"]
        self.check(label + "/variant_matches_actual_source",
                   binding["source_sha256"] == A_source if label.startswith("A")
                   else binding["source_sha256"] != A_source and binding["source_manifest"] == expected_manifest)
        self.check(label + "/original_deadlines", result["public_request_budget_s"] == 30
                   and result["blender_timeout_s"] == 30
                   and result["original_lifecycle_deadline_ns"] - result["started_ns"] == 600_000_000_000)
        runtime = read(root / "io_audit/RUNTIME.json")
        proof = read(root / "RUNTIME_PROOF.json")
        close, held = result["stdio_close"], result["MCP_runtime_exit"]
        self.check(label + "/held_MCP_exit_and_handles", runtime["pid"] == proof["runtime_pid"] == close["pid"]
                   and proof["confirmed"] is True and close["confirmed"] is True and close["exit_code"] == 0
                   and close["process_handle_closed"] is True and close["reader_stopped"] is True
                   and all(close["pipes_closed"].values()) and held["confirmed"] is True
                   and held["exit_code"] == 0 and held["handle_closed"] is True)
        self.check(label + "/controlled_entry_source", runtime["entry_sha256"] == self.pin(HERE / "harness/mcp_entry.py", "frozen standard entry")["sha256"]
                   and runtime["binding_sha256"] == result["binding_sha256"] and runtime["source_sha256"] == binding["source_sha256"])
        initialized = read(root / "INITIALIZE.json")["result"]["_meta"]["human_eye"]
        self.check(label + "/public_initialize_source", initialized["source_sha256"] == binding["source_sha256"]
                   and initialized["source_kind"] == "installed_distribution")
        native, closed = result["native_close"], result["native_final"]["closed"]
        self.check(label + "/owned_Blender_wait_reap", native["exit_code"] == 0 and native["process_reaped"] is True and native["error"] is None)
        self.check(label + "/terminal_restore_and_files", native["source_file_unchanged"] is True and native["protected_files_unchanged"] is True
                   and closed["poisoned"] is False and closed["initial_geometry_fingerprint"] == closed["final_geometry_fingerprint"])
        self.check(label + "/fourth_session_clock", result["complete_session_ns"] == result["session_closed_ns"] - result["started_ns"]
                   and result["postrun_validation_ns"] == result["postrun_closed_ns"] - result["session_closed_ns"])
        self.check(label + "/asset_original_hash", self.pin(result["asset"]["asset"], "unchanged owned source asset")["sha256"] == result["asset"]["asset_sha256"])
        decoded, setups = self.wire(root, binding, label, cache=cache)
        owners = []
        if cache:
            self.check(label + "/three_cache_phases", [row["phase"] for row in result["phases"]] == ["baseline", "moved", "restored"])
            for state in result["phases"]:
                self.check(label + "/phase_operational/" + state["phase"], state["passed_operationally"] is True and state["errors"] == [])
                cost, owner = self.public_phase(root, Path(state["output"]), result, state, binding, decoded, label + "/" + state["phase"])
                owners.append(owner)
            patch_path = HERE / "fixtures/CACHE_VERTEX_PATCH.json"
            patch = read(patch_path)
            self.pin(patch_path, "fixed cache vertex fixture")
            self.check(label + "/two_setup_steps578assignments", len(setups) == 2
                       and [row["response"]["result"]["operation"] for row in setups] == ["qa_far11_move", "qa_far11_restore"]
                       and sum(row["response"]["result"]["vertices_written"] for row in setups) == 578
                       and all(row["response"]["result"]["fixture_sha256"] == self.pin(patch_path, "fixed vertex patch")["sha256"] for row in setups)
                       and all(row["response"]["result"]["matrix_after"] == patch["matrix_world"] for row in setups)
                       and result["fixture_final_stage"] == closed["cache_fixture_stage"] == 2)
            main_caps = [next(read(row["capture"]) for row in owner["captures"] if row["role"] == "main_target_capture") for owner in owners]
            far = [[mesh for mesh in cap["meshes"] if mesh["name"] == "M4_Far_11"] for cap in main_caps]
            self.check(label + "/Far11_scope_changed_then_restored", len(far[0]) == 0 and len(far[1]) == 1 and len(far[2]) == 0)
            if far[1]:
                self.check(label + "/actual_moved_points_faces", far[1][0]["vertices"] == patch["moved_vertices"]
                           and far[1][0]["faces"] == patch["source_triangles"])
            self.check(label + "/actual_setup_fingerprint_chain", setups[0]["response"]["result"]["before_fingerprint"] == closed["initial_geometry_fingerprint"]
                       and setups[0]["response"]["result"]["after_fingerprint"] == setups[1]["response"]["result"]["before_fingerprint"]
                       and setups[1]["response"]["result"]["after_fingerprint"] == closed["final_geometry_fingerprint"])
        else:
            cost, owner = self.public_phase(root, root, result, result, binding, decoded, label)
            if formal:
                self.formal_metrics[label] = cost
        events = lines(root / "native/WORKER_EVENTS.jsonl")
        product_events = [row for row in events if row.get("script_sha256")]
        self.check(label + "/terminal_product_guards", len(product_events) == (6 if cache else 2)
                   and all(row.get("terminal_geometry_and_file_checks_passed") is True and row.get("script_error") is None for row in product_events))
        self.sessions.append({"label": label, "source_sha256": binding["source_sha256"], "runtime_pid": runtime["pid"],
                              "Blender_pid": result["native_final"]["config"]["pid"],
                              "owned_workspace": result["native_final"]["config"]["workspace"],
                              "capture_instance": next(iter(decoded.values()))["capture"]["capture_state"]["instance_id"],
                              "complete_session_ns": result["complete_session_ns"],
                              "postrun_validation_ns": result["postrun_validation_ns"],
                              "MCP_retained_handle_exit": held, "owned_Blender_close": native,
                              "Blender_separate_Win32_handle_closed": None,
                              "product_setter_commands": 0, "fixture_vertex_assignments": 578 if cache else 0,
                              "worker_events": events,
                              "worker_default_unknown_status_used_as_cleanup_proof": False})

    def budget(self):
        root = RUNTIME / "budget"
        limits = read(root / "LIMITS.json")
        claims = [read(path) for path in sorted((root / "claims").glob("*.json"))]
        settlements = {path.stem: read(path) for path in (root / "settlements").glob("*.json")}
        self.check("budget/frozen_limits", limits == LIMITS)
        self.check("budget/every_claim_settled", all(claim["token"] in settlements for claim in claims))
        starts = [claim for claim in claims if claim["kind"] == "Blender_start"]
        rasters = [claim for claim in claims if claim["kind"] == "raster_request"]
        counts = {phase: {"actual": 0, "lower": 0, "upper": 0, "reserved": 0, "released": 0, "requests": 0}
                  for phase in ("qualification", "formal")}
        for claim in claims:
            settlement = settlements.get(claim["token"])
            if settlement is None:
                continue
            self.check("budget/claim_binding/" + claim["token"],
                       self.pin(root / "claims" / (claim["token"] + ".json"), "persistent budget claim")["sha256"] == settlement["claim_sha256"])
            if claim["kind"] == "Blender_start":
                self.check("budget/actual_start/" + claim["label"], settlement.get("pid")
                           and settlement.get("spawn_status") == "spawned" and settlement.get("outcome") in ("passed", "completed"))
                continue
            proof = settlement["evidence"]
            raw = Path(proof["audit_path"]).read_bytes()
            tail = raw[proof["tail_start_bytes"]:proof["tail_start_bytes"] + proof["tail_bytes"]]
            events = [json.loads(line) for line in tail.splitlines() if line.strip()]
            attempts = [event for event in events if event.get("event") == "active_observation_render_attempt"]
            actual, lower = settlement["actual_attempts"], settlement["confirmed_attempts_lower_bound"]
            self.check("budget/actual_attempt_tail/" + claim["token"], digest(tail) == proof["tail_sha256"]
                       and len(attempts) == lower and lower <= claim["reserved_upper_bound"])
            count = counts[claim["phase"]]
            count["requests"] += 1
            count["reserved"] += claim["reserved_upper_bound"]
            count["lower"] += lower
            count["actual"] += lower if actual is None else actual
            count["upper"] += claim["reserved_upper_bound"] if actual is None else actual
            if actual is not None:
                released = settlement["released_proven_unconstructed_reservation"]
                count["released"] += released
                self.check("budget/reservation_release/" + claim["token"], actual == lower
                           and actual + released == claim["reserved_upper_bound"])
        self.check("budget/actual_starts19", len(starts) == 19, len(starts))
        self.check("budget/actual_qualification10", counts["qualification"]["actual"] == counts["qualification"]["lower"] == counts["qualification"]["upper"] == 10)
        self.check("budget/actual_formal18", counts["formal"]["actual"] == counts["formal"]["lower"] == counts["formal"]["upper"] == 18)
        self.check("budget/request_denominators", counts["qualification"]["requests"] == 8 and counts["formal"]["requests"] == 12)
        self.check("budget/within_all_limits", len(starts) <= 24 and counts["qualification"]["upper"] <= 48
                   and counts["formal"]["upper"] <= 72 and sum(row["upper"] for row in counts.values()) <= 120)
        expected_labels = set(QUALIFICATION + ["B_legacy_peripheral", "B_cache_move_restore"])
        expected_labels.update(row["label"] for row in read(HERE / "PREREGISTRATION.json")["formal_schedule"])
        builder_token = read(RUNTIME / "assets_01/PREPARATION.json")["budget_start_claim"]
        builder_claim = next(claim for claim in starts if claim["token"] == builder_token)
        expected_labels.add(builder_claim["label"])
        actual_labels = {claim["label"] for claim in starts}
        self.check("budget/session_and_builder_labels", actual_labels == expected_labels and len(actual_labels) == 19, sorted(actual_labels))
        return {"limits": limits, "start_attempts": len(starts), "raster_request_reservations": len(rasters),
                "phases": counts, "actual_rasters": sum(row["actual"] for row in counts.values()),
                "final_raster_upper": sum(row["upper"] for row in counts.values()),
                "unsettled_claims": sum(claim["token"] not in settlements for claim in claims),
                "recovery_starts_used": len(starts) - 19,
                "semantics": "Reservations are upper bounds, actual failures count, unknown retains its full bound."}

    def paired_gates(self):
        prereg = read(HERE / "PREREGISTRATION.json")
        formal = read(RUNTIME / "formal/RESULT.json")
        marker = read(RUNTIME / "FORMAL_ONCE.json")
        self.check("formal/once_only_order", len(formal["results"]) == len(formal["dispatches"]) == 12
                   and formal["remaining_not_dispatched"] == [] and formal["replacement_samples"] == formal["retries"] == 0
                   and [row["label"] for row in formal["results"]] == [row["label"] for row in prereg["formal_schedule"]]
                   and marker["formal_schedule"] == prereg["formal_schedule"])
        gates = {}
        for input_name in ("main", "target_only"):
            pairs = []
            for index in (1, 2, 3):
                slots = {row["variant"]: row["label"] for row in prereg["formal_schedule"]
                         if row["input"] == input_name and row["pair"] == index}
                A, B = self.formal_metrics[slots["A"]], self.formal_metrics[slots["B"]]
                metrics = ("server_request_to_reply_ns", "client_flush_to_received_ns", "complete_client_call_ns", "complete_session_ns")
                pairs.append({"pair": index, "A": slots["A"], "B": slots["B"],
                              "ratios_B_over_A": {key: B[key] / A[key] for key in metrics}})
            server = [row["ratios_B_over_A"]["server_request_to_reply_ns"] for row in pairs]
            lifecycle = [row["ratios_B_over_A"]["complete_session_ns"] for row in pairs]
            limit = .90 if input_name == "main" else 1.05
            faster = sum(value < 1 for value in server)
            passed = statistics.median(server) <= limit and (input_name != "main" or faster >= 2 and statistics.median(lifecycle) <= 1)
            gates[input_name] = {"pairs": pairs, "server_paired_median": statistics.median(server),
                                 "session_paired_median": statistics.median(lifecycle), "server_B_faster_pairs": faster,
                                 "server_limit": limit, "timing_gate_passed": passed,
                                 "median_semantics": "median of three paired B/A ratios, never ratio of group medians"}
            stored = formal["timing_gates"][input_name]
            self.check("formal/recomputed_gate/" + input_name, stored["server_paired_median"] == statistics.median(server)
                       and stored["session_paired_median"] == statistics.median(lifecycle)
                       and stored["server_B_faster_pairs"] == faster and stored["timing_gate_passed"] == passed)
        for row in formal["results"]:
            actual = self.formal_metrics[row["label"]]
            self.check("formal/recomputed_slot_clocks/" + row["label"], all(row["metrics"][key] == actual[key]
                       for key in ("server_request_to_reply_ns", "client_flush_to_received_ns", "complete_client_call_ns", "complete_session_ns")))
        return gates

    def history_and_sources(self):
        baseline = read(HERE / "BASELINE.json")
        for path, expected in baseline["protected_old_pins"].items():
            self.check("history/protected/" + Path(path).name + "/" + expected[:8], self.pin(path, "protected historical seal")["sha256"] == expected)
        self.check("history/protected20", len(baseline["protected_old_pins"]) == 20)
        for path, expected in baseline["references"].items():
            self.check("reference/" + Path(path).name, self.pin(path, "original plan or analytical reference")["sha256"] == expected)
        freeze = read(HERE / "SOURCE_FREEZE_B.json")
        B = next(binding for key, binding in self.bindings.items() if key != baseline["A_source141_sha256"])
        self.check("source/B_frozen_install_manifest", freeze["runtime_manifest"] == B["source_manifest"])
        for row in freeze["runtime_manifest"]:
            self.check("source/current_candidate/" + row["path"], self.pin(HERE.parent.parent / row["path"], "current frozen candidate source")["sha256"] == row["sha256"])
        A = self.bindings[baseline["A_source141_sha256"]]
        left = {row["path"]: row["sha256"] for row in A["source_manifest"]}
        right = {row["path"]: row["sha256"] for row in B["source_manifest"]}
        changed = sorted(path for path in left if left[path] != right[path])
        self.check("source/one_unique_product_direction", changed == ["human_eye_plugin/blender_host.py"], changed)
        failure = read(HERE / "harness/pre_clarification/PREPARATION_FAILURE.json")
        old_matrix = read(HERE / "harness/unexecuted_matrix_prepare/PREPARATION.json")
        self.check("history/static_failure_retained", failure["error"] == "AssertionError"
                   and failure["actual_Blender_starts"] == failure["actual_rasters"] == failure["actual_product_calls"] == 0)
        self.check("history/matrix_prepare_unexecuted", old_matrix["executions"] == old_matrix["Blender_starts"] == old_matrix["rasters"] == 0)
        for pin in old_matrix["pins"]:
            self.check("history/matrix_prepare_pin/" + Path(pin["path"]).name, self.pin(pin["path"], "unexecuted preparatory matrix source")["sha256"] == pin["sha256"])
        clarification = read(HERE / "MEASUREMENT_CLARIFICATION.json")
        self.check("history/measurement_preformal", clarification["clarified_ns"] < read(RUNTIME / "FORMAL_ONCE.json")["started_ns"]
                   and clarification["client_complete_call"]["duration_field"] == "RESULT.requests.client_outer_including_recording_ns")
        old = Path("D:/he_m4_target_001/qualification/A_peripheral_01/RESULT.json")
        old_result = read(old)
        self.pin(old, "historical extra runtime proof remains unknown")
        self.check("history/old_runtime_unknown_separate_from_stdio_exit", old_result["MCP_runtime_exit"]["confirmed"] is None)
        denial = HERE.parent / "m4_target_acquisition_001/CLEANUP_EVENT.json"
        self.pin(denial, "historical automatic cleanup denial")
        self.check("history/no_cleanup_denial_replacement", read(denial)["tool_reason"] == "blocked by policy")
        return {"protected_old_pin_count": len(baseline["protected_old_pins"]), "changed_product_paths": changed,
                "old_A01_extra_runtime_exit": "unknown", "old_A01_held_stdio_exit": old_result["stdio_close"]["exit_code"],
                "old_cleanup": "blocked by policy, original event retained, no alternate deletion",
                "static_CRLF_reconstruction_failure": "retained as preparation failure, zero live attempts",
                "unexecuted_matrix_prepare": "retained bytes, zero actual starts or rasters",
                "measurement_clarification": "published before formal, enclosing call includes original finally receipt persistence"}

    def finish(self):
        for name in QUALIFICATION:
            self.session(RUNTIME / "qualification" / name, name)
        self.session(RUNTIME / "controls/B_legacy_peripheral", "B_legacy_peripheral")
        self.session(CACHE, "B_cache_move_restore", cache=True)
        schedule = read(HERE / "PREREGISTRATION.json")["formal_schedule"]
        for row in schedule:
            self.session(RUNTIME / "formal" / row["label"], row["label"], formal=True)
        gates = self.paired_gates()
        budget = self.budget()
        history = self.history_and_sources()
        builder = read(RUNTIME / "assets_01/PREPARATION.json")
        self.check("builder/one_success_and_clock", builder["passed"] is True and builder["exit_code"] == 0
                   and builder["elapsed_ns"] == builder["closed_ns"] - builder["started_ns"])
        assets = read(RUNTIME / "assets_01/ASSETS.json")
        for asset in assets["inputs"]:
            self.check("assets/" + asset["name"], self.pin(asset["asset"], "fixed original asset")["sha256"] == asset["asset_sha256"]
                       and self.pin(asset["geometry"], "actual builder evaluated geometry")["sha256"] == asset["geometry_sha256"])
        self.check("execution/session_and_request_denominators", len(self.sessions) == 18 and len(self.costs) == 20
                   and len(self.requests) == 80 and sum(row["producer_frames"] for row in self.costs) == 28)
        self.check("execution/fresh_process_sessions", len({row["owned_workspace"] for row in self.sessions}) == 18
                   and len({row["capture_instance"] for row in self.sessions}) == 18)
        for path in sorted(path for path in RUNTIME.rglob("*") if path.is_file()):
            self.runtime_files.append(self.pin(path, "closed original batch runtime evidence"))
        self.pin(Path(__file__), "runtime review source")
        for path in (HERE / "BASELINE.json", HERE / "SOURCE_FREEZE_B.json", HERE / "PREREGISTRATION.json",
                     HERE / "MEASUREMENT_CLARIFICATION.json", HERE / "harness/CONTROL_READY.json"):
            self.pin(path, "frozen batch control")
        self.check("inputs_unchanged_through_review", all(Path(row["path"]).stat().st_size == row["bytes"]
                   and digest(Path(row["path"]).read_bytes()) == row["sha256"] for row in self.pins.values()))
        passed = all(row["passed"] for row in self.checks)
        report = {"schema": "m4-target-acquisition-002-runtime-review-v1", "passed": passed, "passed_checked_scope": passed,
                  "reviewer": "/root/m1_binding_tests",
                  "author_association": "Reviewer authored batch fixtures, owned harness adaptation, budget and static tests. Root alone performed all live executions. This runtime review is associated with its harness author.",
                  "scope": "Actual saved source/TCP/MCP/producer bytes, four timing windows, paired timing arithmetic, held process exits, fixture setter separation, original assets and persistent budget. Independent geometry and pixel quality are reviewed separately.",
                  "cost_table": self.costs, "all_request_clocks": self.requests,
                  "session_table": self.sessions, "actual_native_transfers": self.transfers,
                  "actual_scope_and_work": self.scope_rows, "budget": budget, "paired_timing_gates": gates,
                  "builder_elapsed_ns": builder["elapsed_ns"], "historical_state": history,
                  "source_bindings": [{"source_sha256": value["source_sha256"], "install_root": value["install_root"],
                                      "source_count": len(value["source_manifest"])} for value in self.bindings.values()],
                  "closed_runtime_originals": {"files": len(self.runtime_files), "bytes": sum(row["bytes"] for row in self.runtime_files)},
                  "time_semantics": {"server": "actual request received through stdout flush completion",
                     "client_transport": "stdin flush through existing reader received_complete after raw response recording",
                     "complete_client_call": "outer original call including its finally RECEIPT.json persistence",
                     "internal_pre_receipt_span": "original receipt closed-start, separately retained",
                     "complete_session": "startup, source checks, fixed calls, settlement and owned cleanup",
                     "postrun": "saved validation after complete session, separately retained",
                     "nesting": "intervals are nested, not added; the cache session occurs once across its three main request rows"},
                  "setter_accounting": {"product_mutation_commands": 0, "test_fixture_vertex_assignments": 578,
                     "test_fixture_steps": 2, "source_asset_saves": 0,
                     "evidence_scope": "actual fixed command responses, full terminal scene readback and pinned producer source; unrestricted Python is not a security sandbox"},
                  "limitations": ["Twelve once-only finite engineering slots, with quality acceptance delegated to independent source and image checks.",
                     "Paired timing pass does not establish complete AI task benefit or broad asset coverage.",
                     "Stage/counter values that the source does not expose remain null. Source-derived possible loop visits are not actual measured visits.",
                     "Producer NPZ byte hashes and delivered PNG identity checked without new rasterization.",
                     "Separate Blender Win32 handle closure is unrecorded. Owned Popen exit and wait/reap are recorded. MCP retained runtime handle closure is recorded.",
                     "A worker close event's default unknown field is not process exit evidence.",
                     "Root owns the later archive receipt. This review does not create or validate an archive.",
                     "Experimental model/paid API use is zero. Coordinator/reviewer cost and unrepeated preparation cost are separate and not priced here."],
                  "new_operations_by_review": {"Blender_starts": 0, "product_calls": 0, "rasters": 0, "evaluators": 0, "models": 0},
                  "check_count": len(self.checks), "checks": self.checks,
                  "failed_checks": [row for row in self.checks if not row["passed"]],
                  "input_pins": sorted(self.pins.values(), key=lambda row: row["path"])}
        json_path = HERE / "RUNTIME_REVIEW.json"
        with json_path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        md = ["# M4 目标采集第二批运行复核", "",
              f"`passed_checked_scope={str(passed).lower()}`，共{len(self.checks)}项证据检查。独立质量验收另行判定。", "",
              f"实际{budget['start_attempts']}次owned启动，包含1个builder和18个产品宿主会话。20次主观察包括缓存会话内的3个阶段。raster实际{budget['actual_rasters']}次，最终上界{budget['final_raster_upper']}次。", "",
              "## 四个成本时界", "",
              "| 观察 | 服务端 ms | 客户端传输 ms | 完整调用 ms | 完整会话 ms | raster |",
              "|---|---:|---:|---:|---:|---:|"]
        for row in self.costs:
            md.append(f"| {row['label']} | {row['server_request_to_reply_ns']/1e6:.4f} | {row['client_flush_to_received_ns']/1e6:.4f} | {row['complete_client_call_ns']/1e6:.4f} | {row['complete_session_ns']/1e6:.4f} | {row['main_raster_actual']} |")
        md.extend(["", "完整调用包含原finally回执保存。内部closed-start另记。完整会话包含启动、固定请求、结算与清理，事后保存校验另列。三个缓存阶段共用一个会话，嵌套成本没有相加。", "",
                   f"builder单独为{builder['elapsed_ns']/1e6:.4f}毫秒。协调和审核成本另计，实验模型与付费API调用为0。", "",
                   "## 三对时界复算", ""])
        for name, row in gates.items():
            md.append(f"- {name} 的服务端配对B/A中位数为{row['server_paired_median']:.6f}，完整会话配对中位数为{row['session_paired_median']:.6f}，时界门限结果为{str(row['timing_gate_passed']).lower()}。")
        md.extend(["", "配对结果由各槽原始时间记录重算，12槽顺序固定，未替换样本。时界结果不代表模型实战收益。", "",
                   "## 来源、进程与缓存控制", "",
                   "A/B分别核对安装141源、当前候选及实际TCP压缩bootstrap。主capture与稍后task/aabb读回保持各自来源。PNG和NPZ producer摘要来自同一次full主结果，实际传输字节按原RX.bin核对，LF文本口径另列。", "",
                   "MCP持有进程均核验exit0、管道和句柄关闭。Blender owned Popen核验exit0与wait/reap，单独Win32句柄关闭状态未记录。worker事件的unknown字段没有用于推断进程退出。", "",
                   "缓存控制实际执行两步固定顶点写入与恢复，共578次fixture顶点赋值。产品变更命令为0，源blend没有保存。完整场景回读、实际Far11进入和退出采集范围及原始回包保留。未知阶段和未暴露计数没有补造。", "",
                   "## 保留记录和关联", "",
                   "历史20个封存摘要、旧A01附加runtime未知及清理自动策略拒绝均保留。一次静态CRLF重建断言失败和未执行矩阵准备继续列为准备记录，其实机计数均为0。完整调用时界澄清发布于正式测试前。", "",
                   "本复核者同时编写了harness、资产和预算适配，实际执行全部由根完成。归档由根单独出具。本次审计新增产品、Blender、raster、评分器和模型调用均为0。所有输入摘要、完整传输、阶段计数及限制见JSON。"])
        md_path = HERE / "RUNTIME_REVIEW.md"
        with md_path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write("\n".join(md) + "\n")
        print(json.dumps({"passed_checked_scope": passed, "checks": len(self.checks), "failed_checks": report["failed_checks"],
                          "budget": budget, "paired_timing_gates": gates,
                          "JSON_sha256": digest(json_path.read_bytes()), "MD_sha256": digest(md_path.read_bytes())}))


def main():
    if not (RUNTIME / "formal/RESULT.json").is_file():
        raise RuntimeError("formal_twelve_slot_closed_receipt_required")
    schedule = read(HERE / "PREREGISTRATION.json")["formal_schedule"]
    roots = [RUNTIME / "qualification" / name for name in QUALIFICATION]
    roots.extend((RUNTIME / "controls/B_legacy_peripheral", CACHE))
    roots.extend(RUNTIME / "formal" / row["label"] for row in schedule)
    missing = [str(root) for root in roots if not all((root / name).is_file()
               for name in ("RESULT.json", "native/WORKER_CLOSED.json", "stdio/CLOSE.json"))]
    if missing:
        raise RuntimeError("all_owned_sessions_must_be_closed:" + ",".join(missing))
    Review().finish()


if __name__ == "__main__":
    main()
