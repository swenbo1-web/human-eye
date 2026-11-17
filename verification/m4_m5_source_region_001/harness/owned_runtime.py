"""Fixed B, direct root-held qualification runtime, without model consumers."""

import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import traceback


HERE = Path(__file__).resolve().parent
NAMESPACE = HERE.parent
sys.path.insert(0, str(HERE))
from budget import Budget, save
EXTERNAL = Path('D:/he_m4_m5_source_region_001')
ASSET = EXTERNAL / 'fixture/main.blend'
ASSET_SHA256 = json.loads((NAMESPACE/'fixture/ASSET_BINDING.json').read_bytes())['asset_sha256']


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read(path):
    return json.loads(Path(path).read_bytes())

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

def append(path, value):
    with Path(path).open("ab") as stream:
        stream.write((json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n").encode())
        stream.flush()

def correlate_archive(before, after, started_ns, closed_ns, is_error, archive_root):
    """Bind one actual producer append to this synchronous public request."""
    if not after.startswith(before):
        raise ValueError('same_producer_archive_prefix_changed')
    if (before and not before.endswith(b'\n')) or (after and not after.endswith(b'\n')):
        raise ValueError('same_producer_archive_incomplete_index')
    old = [json.loads(line) for line in before.splitlines() if line.strip()]
    records = [json.loads(line) for line in after.splitlines() if line.strip()]
    previous = 0
    for record in records:
        if type(record) is not dict:
            raise ValueError('same_producer_archive_invalid_entry')
        index = record.get('index')
        if type(index) is not int or index <= previous:
            raise ValueError('same_producer_archive_duplicate_or_unordered_index')
        previous = index
    added = records[len(old):]
    if len(added) > 1:
        raise ValueError('same_producer_archive_multiple_new_entries')
    if not added:
        if is_error:
            return None
        raise ValueError('same_producer_archive_missing')
    record = added[0]
    begin, returned = record.get('started_ns'), record.get('producer_returned_ns')
    if (type(begin) is not int or type(returned) is not int
            or not started_ns <= begin <= returned <= closed_ns):
        raise ValueError('same_producer_archive_cross_request_window')
    expected = Path(archive_root).resolve() / ('call_' + str(record['index']).zfill(3)) / 'SERVICE_RESULT.json'
    path = Path(record['path']).resolve()
    if path != expected:
        raise ValueError('same_producer_archive_cross_slot_path')
    if digest(path) != record.get('sha256'):
        raise ValueError('same_producer_archive_content_changed')
    return record

class RootRuntime:
    @classmethod
    def start(cls, runroot, phase, label, group, deadline_ns=None, budget=None):
        self = cls()
        self.started_ns = time.perf_counter_ns()
        self.deadline_ns = self.started_ns + 600_000_000_000 if deadline_ns is None else deadline_ns
        if (group not in ("R0", "R1")
                or not self.started_ns < self.deadline_ns <= self.started_ns + 600_000_000_000):
            raise ValueError("fixed_owned_phase_group_and_original_deadline")
        self.consumer_deadline_ns = self.deadline_ns
        self.runroot = Path(runroot).resolve()
        if not self.runroot.is_relative_to(EXTERNAL.resolve()):
            raise ValueError("owned_runtime_outside_registered_batch")
        self.runroot.mkdir(parents=True, exist_ok=True)
        self.phase, self.label, self.group = phase, label, group
        self.budget = Budget(EXTERNAL / "budget") if budget is None else budget
        self.native = self.client = self.runtime_handle = None
        self.stages, self.native_calls, self.public_requests, self.source_reads = [], [], [], []
        self.buffers, self.by_ref, self.by_view = {}, {}, {}
        self._scene_cache = None
        self._meshes = self._face_ids = None
        self._native_frames = 0
        self._product_calls = 0
        self.errors = []
        self.poisoned = False
        self.closed = False
        self.claim = None
        try:
            self.binding_path = NAMESPACE / (group + "_RUN_BINDING.json")
            self.binding = read(self.binding_path)
            if len(self.binding["source_manifest"]) < 143:
                raise ValueError("fixed_product141_required")
            for row in self.binding["source_manifest"]:
                if digest(Path(self.binding["install_root"]) / row["path"]) != row["sha256"]:
                    raise ValueError("installed_product_source_changed")
            if digest(ASSET) != ASSET_SHA256:
                raise ValueError("original_task_asset_changed")
            self.device = {"source": "existing_product_scope_fitted_six_cameras", "external_camera_override": False}
            bootstrap = module("_consume_verified_bootstrap", HERE / "reused/verified_bootstrap.py")
            self.guard = bootstrap.bootstrap(self.binding)
            self.np = __import__("numpy")
            from PIL import Image
            self.Image = Image
            self.proof_module = module("_consume_process_proof", HERE / "reused/process_proof.py")
            helper = module("_consume_owned_native", HERE / ("state_owned_native.py" if label == "state" else "reused/owned_native.py"))
            self.claim = self.budget.reserve("Blender_start", label, phase, 1)
            self.native = helper.NativeSession.start(blender="D:/Tools/blender5.2/blender.exe", asset=ASSET,
                workspace=self.runroot / "native", deadline_ns=self.deadline_ns, condition="P",
                expected_asset_sha256=ASSET_SHA256, max_calls=128)
            self._start_mcp()
            self.ready_ns = time.perf_counter_ns()
            save(self.runroot / "RUNTIME_START.json", self.snapshot())
            return self
        except BaseException:
            self.errors.append({"stage": "startup", "traceback": traceback.format_exc()})
            self.close()
            raise

    def set_consumer_deadline(self, deadline_ns):
        if type(deadline_ns) is not int or deadline_ns > self.consumer_deadline_ns or deadline_ns > self.deadline_ns:
            raise ValueError("consumer_deadline_cannot_be_renewed")
        self.consumer_deadline_ns = deadline_ns

    def check(self):
        if time.perf_counter_ns() >= self.consumer_deadline_ns:
            raise TimeoutError("original_600_second_recovery_deadline")
        if self.poisoned or self.native is not None and (self.native.workspace / "POISONED.json").exists():
            raise RuntimeError("current_owned_scene_poisoned")

    def _start_mcp(self):
        config = {"schema_version": "1.0", "enabled": True, "observe_on_prompt": False,
                  "project_root": self.binding["install_root"], "state_file": str(self.runroot / "product_state.json"),
                  "audit_file": str(self.runroot / "product_audit.jsonl"),
                  "expected_identity": {"source_sha256": self.binding["source_sha256"]}, "request_budget_s": 30,
                  "blender": {"host": self.native.host, "port": self.native.port, "timeout_s": 30}}
        save(self.runroot / "PRODUCT_CONFIG.json", config)
        transport = module("_consume_stdio", HERE / "reused/stdio_checks.py")
        command = [sys.executable, "-I", "-B", "-X", "utf8", str(HERE / "mcp_entry.py"),
                   "--binding", str(self.binding_path),
                   "--config", str(self.runroot / "PRODUCT_CONFIG.json"), "--ledger", str(self.budget.root),
                   "--evidence", str(self.runroot / "mcp_io"), "--phase", self.phase, "--label", self.label,
                   "--archive", str(self.runroot / "product_full")]
        self.client = transport.StdioClient(command, self.runroot, self.runroot / "mcp", self.consumer_deadline_ns)
        response = self.client.call({"jsonrpc": "2.0", "id": "initialize", "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                       "clientInfo": {"name": "live-target-task-consumer", "version": "001"}}})
        save(self.runroot / "INITIALIZE.json", response)
        identity = response["result"]["_meta"]["human_eye"]
        if identity["source_sha256"] != self.binding["source_sha256"] or identity["source_kind"] != "installed_distribution":
            raise ValueError("actual_MCP_public_source_changed")
        proof, self.runtime_handle = self.proof_module._windows_runtime_proof(self.client.process, self.client.process.pid,
                                                                            self.deadline_ns)
        save(self.runroot / "MCP_RUNTIME_PROOF.json", proof)
        if proof["confirmed"] is not True:
            raise ValueError("actual_MCP_retained_runtime_not_proved")
        self.client.call({"jsonrpc": "2.0", "method": "notifications/initialized"})
        tools = self.client.call({"jsonrpc": "2.0", "id": "tools", "method": "tools/list"})
        save(self.runroot / "MCP_TOOLS.json", tools)
        self.product_tools = copy.deepcopy(tools["result"]["tools"])
        actual = next(row for row in self.product_tools if row["name"] == "human_eye_scene_observe")
        expected = read(NAMESPACE / "public_schema" / (self.group + "_scene_observe.json"))
        if actual != expected:
            raise ValueError("actual_installed_public_tool_schema_changed")

    def _native_call(self, code, *, trusted, timeout_s=30):
        self.check()
        started = time.perf_counter_ns()
        timeout = min(30, float(timeout_s), max(.001, (self.consumer_deadline_ns - started) / 1e9))
        result = self.native.run(code, timeout_s=timeout)
        response = result["response"]
        if response.get("poisoned") is True:
            self.poisoned = True
        error = None if response.get("status") == "success" else response.get("error")
        value = {"stdout": response.get("result", {}).get("result", response.get("stdout", "")),
                 "stderr": response.get("stderr", ""), "error": error}
        row = {"index": len(self.native_calls) + 1, "trusted_fixture_operation": trusted,
               "started_ns": started, "closed_ns": time.perf_counter_ns(), "timeout_s": timeout,
               "code_sha256": hashlib.sha256(code.encode()).hexdigest(), "response": value,
               "helper_response": result}
        self.native_calls.append(row)
        append(self.runroot / "NATIVE_CALLS.jsonl", row)
        self.check()
        return value

    def scene_data(self, selectors=None):
        self.check()
        if selectors is not None:
            if type(selectors) is not list:
                raise ValueError("raw_selector_list_required")
            names = [value if type(value) is str else value.get("name") if type(value) is dict and set(value) == {"name"} else None
                     for value in selectors]
            if any(type(name) is not str for name in names):
                raise ValueError("raw_exact_object_names_required")
        else:
            names = None
        if names is None and self._scene_cache is not None:
            return copy.deepcopy(self._scene_cache)
        code = """
import json as _raw_json
import hashlib as _raw_hashlib
import os as _raw_os
import uuid as _raw_uuid
_raw_names = _raw_json.loads(""" + repr(json.dumps(names)) + """ )
if '_raw_document_instance' not in globals():
    _raw_document_instance = _raw_uuid.uuid4().hex
_raw_dg = bpy.context.evaluated_depsgraph_get()
_raw_scale = float(bpy.context.scene.unit_settings.scale_length)
_raw_objects = []
for _raw_obj in bpy.data.objects:
    if _raw_obj.type != 'MESH' or (_raw_names is not None and _raw_obj.name not in _raw_names):
        continue
    _raw_id = 'blender:' + _raw_hashlib.sha256(_raw_json.dumps(['',_raw_obj.name],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    _raw_eval = _raw_obj.evaluated_get(_raw_dg)
    _raw_mesh = _raw_eval.to_mesh()
    try:
        _raw_mesh.calc_loop_triangles()
        _raw_vertices = [[float(value)*_raw_scale for value in (_raw_eval.matrix_world @ vertex.co)] for vertex in _raw_mesh.vertices]
        _raw_faces = [list(triangle.vertices) for triangle in _raw_mesh.loop_triangles]
        _raw_objects.append({'name':_raw_obj.name,'object_id':_raw_id,'instance_id':str(_raw_obj.session_uid),
            'vertices':_raw_vertices,'triangles':_raw_faces})
    finally:
        _raw_eval.to_mesh_clear()
_raw_packet = {'objects':sorted(_raw_objects,key=lambda row:row['object_id']),
    'source':{'kind':'actual_owned_Blender_evaluated_mesh','instance_id':_raw_document_instance,
        'pid':_raw_os.getpid(),'frame':bpy.context.scene.frame_current,
        'subframe':bpy.context.scene.frame_subframe,'scale_length':_raw_scale}}
print('CURRENT_RAW_SCENE:' + _raw_json.dumps(_raw_packet,separators=(',',':'),allow_nan=False))
"""
        result = self._native_call(code, trusted=True)
        if result["error"] is not None:
            raise RuntimeError("actual_raw_scene_read_failed:" + str(result["error"]))
        marked = [line for line in result["stdout"].splitlines() if line.startswith("CURRENT_RAW_SCENE:")]
        if len(marked) != 1:
            raise ValueError("actual_raw_scene_marker_count")
        value = json.loads(marked[0].split(":", 1)[1])
        if names is not None and {row["name"] for row in value["objects"]} != set(names):
            raise ValueError("raw_selected_object_missing")
        value["source"]["asset_sha256"] = ASSET_SHA256
        ordinal = len(self.source_reads) + 1
        value["source_ref"] = "live-source-" + str(ordinal).zfill(3)
        folder = self.runroot / "raw_sources"
        folder.mkdir(exist_ok=True)
        path = folder / (value["source_ref"] + ".json")
        save(path, value)
        self.source_reads.append({"source_ref": value["source_ref"], "path": str(path), "sha256": digest(path),
                                  "native_call_index": len(self.native_calls), "object_names": [row["name"] for row in value["objects"]]})
        if names is None:
            self._scene_cache = copy.deepcopy(value)
        return value

    def _register(self, *, ref, view, png, npz, arrays, object_names, source_face_offsets, source_ref, origin, extra=None):
        if ref in self.by_ref:
            return self.by_ref[ref]
        for value in arrays.values():
            value.setflags(write=False)
        row = {"ref": ref, "view": view, "view_name": view, "PNG": str(png), "NPZ": str(npz),
               "PNG_sha256": digest(png), "NPZ_sha256": digest(npz), "source_ref": source_ref,
               "object_names": object_names, "source_face_offsets": source_face_offsets,
               "triangle_id_scope": "zero_based_global_source_triangles_in_this_frame_object_order",
               "size_px": [512, 512], "origin": origin,
               "buffer_handle": ref, "status": "completed"}
        if extra:
            row.update(extra)
        self.by_ref[ref] = row
        self.by_view[view] = row
        self.buffers[ref] = arrays
        self.buffers[view] = arrays
        return row

    def public_request(self, arguments):
        self.check()
        if type(arguments) is not dict:
            raise ValueError("original_product_arguments_object_required")
        self._product_calls += 1
        message = {"jsonrpc": "2.0", "id": "observe-" + str(self._product_calls), "method": "tools/call",
                   "params": {"name": "human_eye_scene_observe", "arguments": copy.deepcopy(arguments)}}
        call = self.runroot / 'product_calls' / ('call_' + str(self._product_calls).zfill(3))
        call.mkdir(parents=True)
        save(call / 'REQUEST.json', message)
        index_path = self.runroot / 'product_full/INDEX.jsonl'
        before = index_path.read_bytes() if index_path.exists() else b''
        (call / 'ARCHIVE_BEFORE.bin').write_bytes(before)
        started = time.perf_counter_ns()
        response = self.client.call(message)
        closed = time.perf_counter_ns()
        receipt = self.client.records[-1]
        after = index_path.read_bytes() if index_path.exists() else b''
        (call / 'ARCHIVE_AFTER.bin').write_bytes(after)
        save(call / 'RESPONSE.json', response)
        save(call / 'RECEIPT.json', dict(receipt))
        rpc = self.runroot / 'mcp' / ('rpc_' + str(receipt['index']).zfill(2))
        row = {"id": message["id"], "request": message, "started_ns": started, "closed_ns": closed,
            "complete_client_call_ns": closed - started,
            "client_flush_to_received_ns": receipt["received_complete_ns"] - receipt["stdin_flushed_ns"],
            "client_internal_pre_receipt_ns": receipt["closed_ns"] - receipt["started_ns"],
            "receipt": dict(receipt), "response": response,
            "internal_public_call_index": self._product_calls, "producer_archive_index": None,
            "producer_index_path": str(index_path),
            "request_path": str(call / 'REQUEST.json'), "request_sha256": digest(call / 'REQUEST.json'),
            "response_path": str(call / 'RESPONSE.json'), "response_sha256": digest(call / 'RESPONSE.json'),
            "actual_TX_path": str(rpc / 'TX.bin'), "actual_TX_sha256": digest(rpc / 'TX.bin'),
            "actual_RX_path": str(rpc / 'RX.bin'), "actual_RX_sha256": digest(rpc / 'RX.bin'),
            "archive_before_sha256": hashlib.sha256(before).hexdigest(),
            "archive_after_sha256": hashlib.sha256(after).hexdigest()}
        self.public_requests.append(row)
        try:
            entry = correlate_archive(before, after, started, closed,
                'error' in response or response.get('result', {}).get('isError') is True,
                self.runroot / 'product_full')
            if entry is not None:
                row['producer_archive_index'] = entry['index']
                row['producer_archive'] = copy.deepcopy(entry)
                raw = read(entry['path'])
                frames = raw.get('frames', [])
                names = []
                if frames:
                    names = [item['object_name'] for item in sorted(raw['binding']['objects'], key=lambda item: item['object_index'])]
                for frame in frames:
                    png, npz = Path(frame['image_path']), Path(frame['arrays_path'])
                    if not png.resolve().is_relative_to(self.runroot) or not npz.resolve().is_relative_to(self.runroot):
                        raise ValueError('producer_frame_outside_current_slot')
                    if digest(png) != frame['image_sha256'] or digest(npz) != frame['arrays_sha256']:
                        raise ValueError('same_producer_frame_hash_mismatch')
                    with self.np.load(npz, allow_pickle=False) as archive:
                        arrays = {key: archive[key] for key in ('color', 'depth', 'owners', 'triangle_ids')}
                        offsets = archive['face_patch_offsets'].tolist()
                    self._register(ref=frame['image_ref'], view=frame['view_name'], png=png, npz=npz, arrays=arrays,
                        object_names=names, source_face_offsets=offsets,
                        source_ref='product-binding:' + frame['host_binding_sha256'], origin='product',
                        extra={'producer': copy.deepcopy(frame), 'full_result': entry})
            self._save_evidence()
            self.check()
            return response
        except BaseException as error:
            row['post_reply_binding_error'] = {'type': type(error).__name__, 'message': str(error)}
            raise
        finally:
            append(self.runroot / 'PUBLIC_REQUESTS.jsonl', row)

    def _save_evidence(self):
        value = {"schema": "live-target-task-saved-evidence-v1", "label": self.label, "group": self.group,
                 "product_source_sha256": getattr(self, "binding", {}).get("source_sha256"), "asset_sha256": ASSET_SHA256,
                 "device": getattr(self, "device", None), "sources": self.source_reads,
                 "frames": [copy.deepcopy(row) for row in self.by_ref.values()],
                 "native_wire": str(self.runroot / "native/WIRE"),
                 "product_full_index": str(self.runroot / "product_full/INDEX.jsonl")}
        path = self.runroot / "SAVED_EVIDENCE.json"
        path.write_text(json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n", encoding="utf-8", newline="\n")

    def snapshot(self):
        return {"schema": "target-consumption-owned-runtime-v1", "group": self.group, "label": self.label, "phase": self.phase,
                "started_ns": self.started_ns, "owned_deadline_ns": self.deadline_ns,
                "consumer_deadline_ns": self.consumer_deadline_ns, "closed": self.closed,
                "product_source_sha256": getattr(self, "binding", {}).get("source_sha256"), "asset_sha256": ASSET_SHA256,
                "device": getattr(self, "device", None), "stages": self.stages, "native_calls": self.native_calls,
                "public_requests": self.public_requests, "sources": self.source_reads,
                "frames": list(self.by_ref.values()), "errors": self.errors,
                "native_pid": None if self.native is None else self.native.config["pid"],
                "MCP_pid": None if self.client is None else self.client.process.pid,
                "native_spawn_receipt": str(self.runroot / "native/SPAWN.json"),
                "MCP_spawn_receipt": str(self.runroot / "mcp/SPAWN.json"),
                "budget": self.budget.snapshot(),
                "wrapper_work": {"actual_loop_visits": None,
                    "source_derived_scope": "NativeSession terminal guards traverse the whole scene before and after each RPC and again at closure. Their elapsed work is included, separate from selected raw source returns and selective product counters."}}

    def close(self):
        if self.closed:
            return read(self.runroot / "RUNTIME_CLOSE.json")
        started = time.perf_counter_ns()
        result = {"started_ns": started, "errors": []}
        if self.client is not None:
            try:
                result["MCP_stdio_close"] = self.client.finish()
                if self.runtime_handle is not None:
                    result["MCP_retained_exit"] = self.proof_module._runtime_exit(self.runtime_handle)
                    self.runtime_handle = None
                else:
                    result["MCP_retained_exit"] = {"confirmed": None, "reason": "retained_handle_not_acquired"}
                if (result["MCP_stdio_close"].get("confirmed") is not True
                        or result["MCP_stdio_close"].get("exit_code") != 0
                        or result["MCP_retained_exit"].get("confirmed") is False):
                    raise RuntimeError("MCP_held_cleanup_unconfirmed")
            except BaseException as error:
                result["errors"].append({"stage": "MCP_close", "type": type(error).__name__, "message": str(error)})
        if self.native is not None:
            try:
                result["Blender_close"] = self.native.close()
                result["Blender_status"] = self.native.status()
                closed = result["Blender_status"]["closed"]
                if (result["Blender_close"].get("exit_code") != 0 or not result["Blender_close"].get("process_reaped")
                        or closed is None or closed.get("poisoned")
                        or closed["initial_geometry_fingerprint"] != closed["final_geometry_fingerprint"]):
                    raise RuntimeError("owned_Blender_close_or_source_changed")
            except BaseException as error:
                result["errors"].append({"stage": "Blender_close", "type": type(error).__name__, "message": str(error)})
        if hasattr(self, "guard"):
            try:
                self.guard.verify_loaded()
            except BaseException as error:
                result["errors"].append({"stage": "source_guard_close", "type": type(error).__name__, "message": str(error)})
        if self.claim is not None:
            self.budget.settle_start(self.claim, pid=None if self.native is None else self.native.config["pid"],
                spawn_status="unknown" if self.native is None else "spawned", outcome="failed" if self.errors or result["errors"] else "completed")
        self.closed = True
        self._save_evidence()
        result["closed_ns"] = time.perf_counter_ns()
        result["elapsed_ns"] = result["closed_ns"] - started
        result["runtime"] = self.snapshot()
        result["complete_actor_runtime_ns"] = result["closed_ns"] - self.started_ns
        result["scope"] = "Root slot parent independently records earlier checks through final result publication. Actor/runtime/consumer clocks are nested, never summed."
        save(self.runroot / "RUNTIME_CLOSE.json", result)
        return result
