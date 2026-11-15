"""Read closed six-slot evidence and write this namespace's runtime review only."""

import ast
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import zlib


HERE = Path(__file__).resolve().parent
RUNTIME = Path("D:/he_m4_camera_001")
LABELS = [variant + "_" + asset for asset in ("extreme", "origin", "peripheral")
          for variant in ("OLD", "NEW")]
NUMERIC_REASON = "active_observation_target_camera_numeric_insufficient"
EXPECTED_LIMITS = {"Blender_start_attempts": 10, "qualification_rasters": 36,
                   "formal_rasters": 0, "all_rasters": 36}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


class Review:
    def __init__(self):
        self.pins = {}
        self.checks = []
        self.costs = []
        self.bindings = {}
        self.original_runtime = []

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

    def source(self, binding_path):
        binding = read(binding_path)
        self.pin(binding_path, "actual per-slot installation binding")
        source_sha = binding["source_sha256"]
        if source_sha in self.bindings:
            return binding
        manifest = binding["source_manifest"]
        root = Path(binding["install_root"])
        for row in manifest:
            actual = self.pin(root / row["path"], "installed product source")
            self.check(source_sha[:8] + "/source/" + row["path"], actual["sha256"] == row["sha256"])
        identity = {key: binding[key] for key in ("base_version", "implementation_revision")}
        identity["files"] = manifest
        actual_sha = digest(json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode())
        self.check(source_sha[:8] + "/aggregate", actual_sha == source_sha and len(manifest) == 141)
        self.bindings[source_sha] = binding
        return binding

    def slot(self, label):
        root = RUNTIME / "controls" / label
        result = read(root / "RESULT.json")
        binding = self.source(result["binding_file"])
        self.check(label + "/operational_result", result["passed"] is True and result["errors"] == [])
        self.check(label + "/source_binding", result["source_sha256"] == binding["source_sha256"]
                   and result["binding_sha256"] == self.pin(result["binding_file"], "binding")['sha256'])
        self.check(label + "/deadlines", result["public_request_budget_s"] == 30
                   and result["blender_timeout_s"] == 30
                   and result["original_lifecycle_deadline_ns"] - result["started_ns"] == 600_000_000_000)
        requested = result["requests"]
        self.check(label + "/fixed_four_calls", [row["id"] for row in requested] ==
                   ["target_observation", "after_active_ping", "source_readback", "after_readback_ping"])
        self.check(label + "/two_post_main_pings", all(row["ping_success"] is True for row in requested if row["result_kind"] == "ping"))
        active_request = read(root / "REQUEST_01.json")
        readback_request = read(root / "REQUEST_03.json")
        selector = {"name": result["asset"]["target"]}
        self.check(label + "/fixed_active_request", active_request["params"]["arguments"] == {
            "session_id": "m4-target-camera-reliability-001", "include_image": True,
            "response_detail": "full", "query": {"mode": "active_observation", "objects": [selector]}})
        self.check(label + "/fixed_later_readback", readback_request["params"]["arguments"] == {
            "session_id": "m4-target-camera-reliability-001", "include_image": False,
            "query": {"mode": "task", "objects": [selector], "requested_facts": ["aabb"]}})
        stdio = {}
        for folder in sorted((root / "stdio").glob("rpc_*")):
            tx = folder / "TX.bin"
            if not tx.exists():
                continue
            request = read(tx)
            if "id" in request:
                rx = folder / "RX.bin"
                stdio[request["id"]] = (request, read(rx), tx.read_bytes(), rx.read_bytes())
        io_by_id = {row["id"]: row for row in result["io_audit"]}
        for name, row in io_by_id.items():
            request, response, tx, rx = stdio[name]
            logical = rx[:-2] + b"\n" if rx.endswith(b"\r\n") else rx
            self.check(label + "/wire/" + name,
                       row["TX_bytes"] == len(tx) and row["TX_sha256"] == digest(tx)
                       and row["RX_text_UTF8_LF_bytes"] == len(logical)
                       and row["RX_text_UTF8_LF_sha256"] == digest(logical)
                       and row["request_to_reply_ns"] == row["reply_completed_ns"] - row["request_received_ns"])
        for index, record in enumerate(requested, 1):
            request, actual_response, tx, rx = stdio[record["id"]]
            self.check(label + "/original_reply/" + record["id"], actual_response == read(root / f"RESPONSE_{index:02}.json")
                       and record["raw_RX_bytes"] == len(rx))
        main = read(root / "PUBLIC_01.json")
        main_response = stdio["target_observation"][1]
        full_text = [row["text"] for row in main_response["result"]["content"] if row["type"] == "text"]
        self.check(label + "/main_full_original", len(full_text) == 1 and json.loads(full_text[0]) == main)
        self.check(label + "/readback_reply", read(root / "PUBLIC_03.json").get("result_kind") == "task_query"
                   and read(root / "RESPONSE_03.json")["result"]["isError"] is False)
        numeric = label == "NEW_extreme"
        if numeric:
            self.check(label + "/typed_numeric_unknown", main_response["result"]["isError"] is True
                       and main.get("status") == "unknown" and main.get("reason") == NUMERIC_REASON
                       and main.get("observation_status") == "numeric_insufficient"
                       and main.get("automatic_retry") is False)
            self.check(label + "/no_main_producer_frames", not main.get("frames")
                       and not result.get("producer_frames") and result["main_outcome"] == "numeric_insufficient_unknown")
        else:
            self.check(label + "/actual_full_observation", main_response["result"]["isError"] is False
                       and main.get("result_kind") == "active_observation" and isinstance(main.get("frames"), list))
        frames = main.get("frames", [])
        delivered = [base64.b64decode(row["data"], validate=True) for row in main_response["result"]["content"] if row["type"] == "image"]
        self.check(label + "/frame_delivery_count", len(delivered) == len(frames) == len(result.get("producer_frames", [])))
        for index, frame in enumerate(frames):
            png = Path(frame["image_path"])
            npz = Path(frame["arrays_path"])
            self.check(label + "/producer_hashes/" + str(index),
                       self.pin(png, "actual producer PNG")['sha256'] == frame["image_sha256"]
                       and self.pin(npz, "actual producer NPZ")['sha256'] == frame["arrays_sha256"]
                       and png.read_bytes() == delivered[index]
                       and png.stat().st_size == frame["PNG_bytes"]
                       and npz.stat().st_size == frame["compressed_array_file_bytes"]
                       and struct.unpack(">II", delivered[index][16:24]) == (512, 512))
            self.check(label + "/frame_binding/" + str(index),
                       frame["host_binding_sha256"] == main["binding"]["binding_sha256"]
                       and frame["source_revision"] == main["binding"]["scene_revision"]
                       and frame["scene_identity"] == main["binding"]["geometry_identity"]
                       and frame["candidate_identity"] == main["binding"]["camera_identity"])
        owner = read(root / "OWNER_BINDING.json")
        captures = owner["captures"]
        roles = Counter(row["role"] for row in captures)
        self.check(label + "/main_vs_later_capture_roles", roles["main_target_capture"] == (0 if numeric else 1)
                   and roles["post_main_source_readback"] == 1)
        for cap in captures:
            packet = read(cap["capture"])
            self.check(label + "/capture_original/" + cap["role"],
                       self.pin(cap["capture"], "actual decoded capture or later source readback")['sha256'] == cap["capture_sha256"])
            self.check(label + "/capture_instance_map/" + cap["role"],
                       all(row["instance_id"] == packet["host_identity"]["object_instances"][row["object_id"]] for row in cap["mapping"]))
        if not numeric:
            original = next(read(row["capture"]) for row in captures if row["role"] == "main_target_capture")
            later = next(read(row["capture"]) for row in captures if row["role"] == "post_main_source_readback")
            main_target = next(mesh for mesh in original["meshes"] if mesh["name"] == result["asset"]["target"])
            self.check(label + "/same_host_later_source", original["capture_state"]["instance_id"] == later["capture_state"]["instance_id"]
                       and original["host_identity"]["document_epoch"] == later["host_identity"]["document_epoch"]
                       and main_target["vertices"] == later["meshes"][0]["vertices"] and main_target["faces"] == later["meshes"][0]["faces"])
        runtime = read(root / "io_audit/RUNTIME.json")
        proof = read(root / "RUNTIME_PROOF.json")
        close = result["stdio_close"]
        held = result["MCP_runtime_exit"]
        self.check(label + "/held_MCP_process_and_handles", runtime["pid"] == proof["runtime_pid"] == close["pid"]
                   and proof["confirmed"] is True and close["confirmed"] is True and close["exit_code"] == 0
                   and close["process_handle_closed"] is True and close["reader_stopped"] is True
                   and all(close["pipes_closed"].values()) and held["confirmed"] is True
                   and held["exit_code"] == 0 and held["handle_closed"] is True)
        self.check(label + "/controlled_entry_pin", runtime["entry_sha256"] == self.pin(HERE / "harness/mcp_entry.py", "frozen entry")['sha256']
                   and runtime["binding_sha256"] == result["binding_sha256"])
        native = result["native_close"]
        closed = result["native_final"]["closed"]
        self.check(label + "/owned_Blender_exit_reaped", native["exit_code"] == 0 and native["process_reaped"] is True and native["error"] is None)
        self.check(label + "/owned_Blender_readonly", native["source_file_unchanged"] is True and native["protected_files_unchanged"] is True
                   and closed["poisoned"] is False and closed["initial_geometry_fingerprint"] == closed["final_geometry_fingerprint"])
        wire = read(root / "native/WIRE/INDEX.json")
        commands = []
        payloads = []
        remote_numeric = []
        for item in wire:
            folder = root / "native/WIRE" / f"{item['sequence']:03}"
            tx = (folder / "REQUEST.bin").read_bytes()
            rx = (folder / "RESPONSE.bin").read_bytes()
            self.check(label + "/host_wire/" + str(item["sequence"]), len(tx) == item["request_bytes"]
                       and len(rx) == item["response_attempted_bytes"] and item["response_sendall_completed"] is True)
            request = json.loads(tx)
            commands.append(request["type"])
            if request["type"] != "execute_code":
                continue
            for node in ast.walk(ast.parse(request["params"]["code"])):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "compile" and len(node.args) >= 2):
                    continue
                expression = node.args[0]
                if not (isinstance(expression, ast.Call) and isinstance(expression.func, ast.Attribute) and expression.func.attr == "decompress"):
                    continue
                blob = zlib.decompress(base64.b64decode(ast.literal_eval(expression.args[0].args[0]), validate=True))
                path = Path(ast.literal_eval(node.args[1]))
                payloads.append(digest(blob) == self.pin(path, "actual host bootstrap source")['sha256'])
            stdout = json.loads(rx).get("result", {}).get("result", "")
            for line in stdout.splitlines():
                if line.startswith("HUMAN_EYE_BLENDER_MCP:"):
                    inner = json.loads(line.split(":", 1)[1])
                    if "error" in inner:
                        remote_numeric.append(inner["error"])
        self.check(label + "/actual_source_payloads", payloads and all(payloads))
        self.check(label + "/host_step_and_close_count", commands == ["execute_code", "execute_code", "close"])
        if numeric:
            self.check(label + "/actual_typed_host_failure", remote_numeric == [{"type": "BlenderHostError", "message": NUMERIC_REASON, "mutation_uncertain": False}])
        main_io = io_by_id["target_observation"]
        readback_io = io_by_id["source_readback"]
        self.check(label + "/session_clock", result["complete_session_ns"] == result["session_closed_ns"] - result["started_ns"])
        self.check(label + "/postrun_clock", result["postrun_validation_ns"] == result["postrun_closed_ns"] - result["session_closed_ns"])
        self.costs.append({"slot": label, "source_sha256": binding["source_sha256"], "main_outcome": result["main_outcome"],
            "main_request_to_reply_ns": main_io["request_to_reply_ns"],
            "main_client_outer_including_recording_ns": requested[0]["client_outer_including_recording_ns"],
            "readback_request_to_reply_ns": readback_io["request_to_reply_ns"],
            "post_main_pings_ns": [io_by_id[name]["request_to_reply_ns"] for name in ("after_active_ping", "after_readback_ping")],
            "complete_lifecycle_ns": result["complete_session_ns"], "postrun_saved_validation_ns": result["postrun_validation_ns"],
            "main_MCP_TX_bytes": len(stdio["target_observation"][2]), "main_MCP_raw_RX_bytes": len(stdio["target_observation"][3]),
            "main_MCP_audit_LF_text_bytes": main_io["RX_text_UTF8_LF_bytes"],
            "public_text_UTF8_bytes": requested[0]["public_text_UTF8_bytes"],
            "PNG_bytes": sum(len(raw) for raw in delivered), "producer_frame_count": len(frames),
            "main_raster_actual": main_io.get("raster_actual"), "host_TCP_steps": wire,
            "Blender_Win32_handle_closed": None,
            "worker_event_status_not_used_as_exit_evidence": Counter(row.get("status") for row in result["worker_events"])})

    def budget(self):
        root = RUNTIME / "budget"
        limits = read(root / "LIMITS.json")
        claims = [read(path) for path in sorted((root / "claims").glob("*.json"))]
        settlements = {path.stem: read(path) for path in (root / "settlements").glob("*.json")}
        self.check("budget/unchanged_limits", limits == EXPECTED_LIMITS)
        starts = [claim for claim in claims if claim["kind"] == "Blender_start"]
        rasters = [claim for claim in claims if claim["kind"] == "raster_request"]
        self.check("budget/all_claims_settled", all(claim["token"] in settlements for claim in claims))
        actual = lower = upper = released = 0
        for claim in rasters:
            settlement = settlements[claim["token"]]
            proof = settlement["evidence"]
            raw = Path(proof["audit_path"]).read_bytes()
            tail = raw[proof["tail_start_bytes"]:proof["tail_start_bytes"] + proof["tail_bytes"]]
            events = [json.loads(line) for line in tail.splitlines() if line.strip()]
            attempts = [event for event in events if event.get("event") == "active_observation_render_attempt"]
            known = settlement["actual_attempts"]
            confirmed = settlement["confirmed_attempts_lower_bound"]
            self.check("budget/audit_tail/" + claim["token"], digest(tail) == proof["tail_sha256"]
                       and len(attempts) == confirmed and confirmed <= claim["reserved_upper_bound"])
            if known is not None:
                actual += known
                upper += known
                released += settlement["released_proven_unconstructed_reservation"]
                self.check("budget/settlement_arithmetic/" + claim["token"], known == confirmed
                           and known + settlement["released_proven_unconstructed_reservation"] == claim["reserved_upper_bound"])
            else:
                upper += claim["reserved_upper_bound"]
            lower += confirmed
            numeric = proof.get("numeric_pre_render_source_proof")
            if numeric:
                source = Path(numeric["source"])
                tree = ast.parse(source.read_bytes())
                camera = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_observation_target_cameras")
                inside = {id(node) for node in ast.walk(camera)}
                tokens = [node for node in ast.walk(tree) if isinstance(node, ast.Constant) and node.value == NUMERIC_REASON]
                self.check("budget/numeric_pre_render_phase", self.pin(source, "numeric producer phase")['sha256'] == numeric["sha256"]
                           and tokens and all(id(node) in inside for node in tokens)
                           and numeric["only_in_host_camera_function"] is True and known == 0 and not attempts
                           and settlement["outcome"] == "completed_numeric_pre_render")
        self.check("budget/actual_starts_and_rasters", len(starts) == 7 and len(rasters) == 6
                   and actual == lower == upper == 7 and released == 29,
                   {"starts": len(starts), "raster_reservations": len(rasters), "actual": actual, "lower": lower, "upper": upper, "released": released})
        self.check("budget/within_fixed_bounds", len(starts) <= 10 and upper <= 36)
        self.check("budget/no_unrecorded_start_labels", {claim["label"] for claim in starts} == set(LABELS) | {"camera_fixed_asset_builder"})
        self.check("budget/all_started_processes_recorded", all(settlements[claim["token"]]["spawn_status"] == "spawned"
                   and settlements[claim["token"]]["pid"] and settlements[claim["token"]]["outcome"] in ("passed", "completed") for claim in starts))
        return {"limits": limits, "start_attempts": len(starts), "confirmed_spawned": len(starts),
                "raster_request_reservations": len(rasters), "total_reserved_before_settlement": sum(row["reserved_upper_bound"] for row in rasters),
                "confirmed_actual": actual, "confirmed_lower": lower, "final_upper": upper,
                "proven_unconstructed_reservations_released": released, "unsettled_claims": 0,
                "recovery_start_attempts_used": len(starts) - 7,
                "semantics": "Actual construction failures remain counted. Numeric camera exit is zero only with pinned producer phase plus exact completed typed error and zero render-attempt events."}

    def finish(self):
        for path in sorted(p for p in RUNTIME.rglob("*") if p.is_file()):
            self.original_runtime.append(self.pin(path, "closed original runtime evidence"))
        for label in LABELS:
            self.slot(label)
        budget = self.budget()
        builder = read(RUNTIME / "assets_01/PREPARATION.json")
        self.check("builder/one_success", builder["passed"] is True and builder["exit_code"] == 0)
        plan = read(HERE / "fixtures/INPUT_PLAN.json")
        for row in plan["source_pins"]:
            self.check("frozen_input/" + Path(row["path"]).name, self.pin(row["path"], "frozen source input")['sha256'] == row["sha256"])
        assets = read(RUNTIME / "assets_01/ASSETS.json")
        for asset in assets["inputs"]:
            self.check("fixed_asset/" + asset["name"], self.pin(asset["asset"], "fixed owned asset")['sha256'] == asset["asset_sha256"]
                       and self.pin(asset["geometry"], "actual Blender evaluated asset inventory")['sha256'] == asset["geometry_sha256"])
        derivation = read(RUNTIME / "assets_01/DERIVATION.json")
        self.check("origin/actual_quantization_preserved", derivation["source_local_matrix_faces_readback_exact"] is True
                   and derivation["origin_preserves_quantized_world_dimensions"] is True
                   and derivation["world_extents"] == derivation["origin_extents"])
        self.check("source/two_installed_variants", len(self.bindings) == 2)
        mappings = [{row['path']: row['sha256'] for row in binding['source_manifest']} for binding in self.bindings.values()]
        changed = sorted(path for path in mappings[0] if mappings[0][path] != mappings[1][path])
        self.check("source/only_two_product_files_changed", changed == ['human_eye_plugin/blender_host.py', 'human_eye_plugin/live_spatial_mcp.py'], changed)
        history = Path('D:/he_m4_target_001/qualification/A_peripheral_01/RESULT.json')
        old = read(history)
        self.pin(history, "historical first attempt; no replacement proof")
        self.check("history/old_extra_runtime_proof_unknown", old['MCP_runtime_exit']['confirmed'] is None)
        denial = HERE.parent / 'm4_target_acquisition_001/CLEANUP_EVENT.json'
        self.pin(denial, "historical blocked cleanup")
        self.check("history/old_cleanup_denial_retained", read(denial)['tool_reason'] == 'blocked by policy')
        for path in [Path(__file__), HERE/'fixtures/INPUT_PLAN.json', HERE/'harness/CONTROL_SCHEDULE.json',
                     HERE/'harness/STATIC_READY.json', HERE/'harness/run_case.py', HERE/'harness/mcp_entry.py',
                     HERE/'harness/extract_saved.py', HERE/'harness/budget.py']:
            self.pin(path, 'frozen audit or harness source')
        self.check("original_inputs_unchanged_after_review", all(Path(row['path']).stat().st_size == row['bytes']
                   and digest(Path(row['path']).read_bytes()) == row['sha256'] for row in self.pins.values()))
        passed = all(row['passed'] for row in self.checks)
        report = {'schema': 'm4-target-camera-runtime-review-v1', 'passed': passed, 'passed_checked_scope': passed,
                  'scope': 'Saved source, original wire, producer frame receipts, held-process exits, fixed clocks, readback separation and persistent budget. Camera quality is independently reviewed elsewhere.',
                  'reviewer': '/root/m1_binding_tests',
                  'association': 'Reviewer authored this batch harness, asset builder and budget adaptation, and earlier runtime reviews. Root performed all owned executions. This review is associated with its harness implementation.',
                  'executed_slot_count': len(LABELS), 'labels': LABELS, 'cost_table': self.costs,
                  'builder_elapsed_ns': builder['elapsed_ns'], 'budget': budget,
                  'closed_runtime_originals': {'files': len(self.original_runtime), 'bytes': sum(row['bytes'] for row in self.original_runtime)},
                  'source_bindings': [{'source_sha256': binding['source_sha256'], 'install_root': binding['install_root'], 'source_count': len(binding['source_manifest'])} for binding in self.bindings.values()],
                  'producer_receipt': {'full_first_main_result': True, 'original_producer_NPZ_hashes': True, 'producer_frames': sum(row['producer_frame_count'] for row in self.costs), 'no_additional_observation_for_receipt': True, 'frame_pose': 'Not directly projected in full result; independently bind same main capture camera_plan.'},
                  'extreme_outcome': {'NEW': 'explicit_numeric_insufficient', 'restored_as_complete': False, 'main_geometry_delivery': 'none for NEW extreme', 'later_actual_source_readback': True},
                  'historical_state': {'old_A01_extra_runtime_exit': 'unknown', 'old_thin_launcher_exit': old['stdio_close']['exit_code'], 'new_instance_replaces_old_proof': False, 'old_cleanup_denial': 'blocked by policy, retained, no alternate deletion'},
                  'limits_and_unverified': ['Single correctness sample per input/variant. No paired performance admission or model-benefit estimate.', 'NPZ producer byte hashes and saved PNG delivery checked. This runtime audit does not rerasterize depth/owner truth.', 'Separate Blender Win32 handle-closed status is not recorded. Owned Popen exit0/wait-reap is recorded. MCP retained runtime handle closure is recorded.', 'Worker event status fields, including the close event default unknown, are not process cleanup evidence.', 'Main capture and later task/aabb readback remain separate; the latter never fills missing geometry in a failed main request.', 'Output audit fields measure LF text before platform translation. Actual wire size/hash comes from original stdio RX.bin.', 'Temporary bytecode is excluded from harness source dependencies. Historical cleanup refusal is retained without deletion attempts.'],
                  'new_operations_by_review': {'Blender_starts': 0, 'product_calls': 0, 'rasters': 0, 'evaluators': 0, 'model_calls': 0},
                  'check_count': len(self.checks), 'checks': self.checks,
                  'failed_checks': [row for row in self.checks if not row['passed']],
                  'input_pins': sorted(self.pins.values(), key=lambda row: row['path'])}
        with (HERE/'RUNTIME_REVIEW.json').open('x', encoding='utf8', newline='\n') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        lines = ['# 相机可靠性运行证据复核', '',
                 f"`passed_checked_scope={str(passed).lower()}`，{len(self.checks)}项运行检查。覆盖保存来源、真实wire、producer摘要、持有进程退出、预算及成本时界。相机几何与像素质量由独立验收处理。", '',
                 '## 实际执行与退出', '',
                 f"共{budget['start_attempts']}次owned启动，包含1个资产builder和6个旧新控制槽。实际raster为{budget['confirmed_actual']}，最终上界为{budget['final_upper']}，无pending。新增numeric极值明确数值不足，未恢复为完整目标。", '',
                 '六槽均有主观察后的ping、之后独立task/aabb读回及第二次ping。MCP持有进程均exit0，reader、管道及runtime句柄关闭。Blender owned Popen均exit0并完成wait/reap，场景指纹与资产原件保持一致。Blender单独Win32句柄关闭状态未记录。worker事件的unknown状态不用于推断cleanup。', '',
                 '## 成本原窗', '',
                 '| 槽 | 主请求至回复 ms | 完整生命周期 ms | 后续读回 ms | actual raster |',
                 '|---|---:|---:|---:|---:|']
        for row in self.costs:
            lines.append(f"| {row['slot']} | {row['main_request_to_reply_ns']/1e6:.4f} | {row['complete_lifecycle_ns']/1e6:.4f} | {row['readback_request_to_reply_ns']/1e6:.4f} | {row['main_raster_actual']} |")
        lines.extend(['', '主业务仅第一条请求。完整生命周期包含启动、主请求、两个ping、后续读回、预算结算和清理。事后保存证据核查另记，嵌套时钟不相加。这里没有完整任务提速或模型收益结论。', '',
                      '## Producer与来源', '',
                      f"实际{report['producer_receipt']['producer_frames']}份frame直接由同一次主full回复提供producer NPZ摘要和frame身份，逐份与保存文件及交付PNG核对。pose仍从同次真实camera_plan绑定。NEW extreme主捕获缺失，之后READBACK_CAPTURE仅证明后来的同宿主求值，未冒充主请求交付。", '',
                      '旧新141源分别钉安装及真实TCP bootstrap，只有宿主相机与MCP错误映射两文件不同。源/实例和局部面顺序沿实际capture绑定，原资产及origin量化尺寸保持。实际MCP字节取RX.bin，I/O的RX_text_UTF8_LF字段保留文本编码口径。', '',
                      '## 预算与历史状态', '',
                      f"6个主请求共预留{budget['total_reserved_before_settlement']}次，实际{budget['confirmed_actual']}次，释放{budget['proven_unconstructed_reservations_released']}个已证未构造预留。NEW extreme的0次由已钉camera阶段token、精确typed错误完整回包及零render事件共同核对。其他未知应保留上界。", '',
                      '旧A01附加runtime退出仍unknown，原thin launcher退出另列。旧缓存删除拒绝保留，未另行删除。新实例没有补证历史进程。本复核编写者同时是harness/资产/预算作者，实际执行由根完成。', '',
                      '本复核新增Blender、产品、raster、evaluator和模型调用均为0。所有输入SHA、实际wire边界、成本、检查及限制见JSON。'])
        with (HERE/'RUNTIME_REVIEW.md').open('x', encoding='utf8', newline='\n') as stream:
            stream.write('\n'.join(lines)+'\n')
        print(json.dumps({'passed_checked_scope': passed, 'checks': len(self.checks), 'failed_checks': report['failed_checks'],
                          'budget': budget, 'JSON_sha256': digest((HERE/'RUNTIME_REVIEW.json').read_bytes()),
                          'MD_sha256': digest((HERE/'RUNTIME_REVIEW.md').read_bytes())}, ensure_ascii=False))


def main():
    missing = [label for label in LABELS if not (RUNTIME/'controls'/label/'RESULT.json').is_file()
               or not (RUNTIME/'controls'/label/'native/WORKER_CLOSED.json').is_file()
               or not (RUNTIME/'controls'/label/'stdio/CLOSE.json').is_file()]
    if missing:
        raise RuntimeError('closed_six_slot_evidence_required:' + ','.join(missing))
    Review().finish()


if __name__ == '__main__':
    main()
