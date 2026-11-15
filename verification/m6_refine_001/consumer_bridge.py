"""Stdio tools for actual consumer edits and independent saved-mesh readback."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "m6_shape_pretrain_001/private/deps"))
import numpy as np
from python_executor import execute


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")


def tool(name, description, properties, required=()):
    return dict(name=name, description=description, inputSchema=dict(type="object", properties=properties,
        required=list(required), additionalProperties=False))


def json_value(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    raise TypeError("unsupported_tool_JSON_value_" + type(value).__name__)


def file_identity(path):
    path = path.resolve()
    data = path.read_bytes()
    return dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def binding_digest(binding):
    return hashlib.sha256(json.dumps(binding, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf8")).hexdigest()


class Bridge:
    def __init__(self, options):
        self.options = options
        self.case, self.session, self.audit = options.case.resolve(), options.session.resolve(), options.audit.resolve()
        self.audit.mkdir(parents=True, exist_ok=True)
        self.started, self.calls, self.api = time.perf_counter(), [], None
        self.task = json.loads((self.case / "task.json").read_bytes())
        self.input_hashes = {name: hashlib.sha256((self.case / name).read_bytes()).hexdigest() for name in ("task.json", "input.npz")}
        self.tools = [
            tool("execute_python", "Run ordinary Python in a fresh bounded local interpreter. NumPy/SciPy/standard-library imports work. "
                 "V/current/vertices are current world coordinates [N,3], V0 initial world coordinates, faces full source triangles, "
                 "F_ids/I_ids/C_ids/B0_ids/B1_ids source IDs, n0 initial smoothed normal field [N,3], h,ell,center,version,task are available. "
                 "Use your own geometry algorithm. save_edit(ids, values, mode='positions_world'|'displacements_world') stores your computed finite "
                 "sparse edit and returns payload_id plus observed_version. Displacements are relative to the current snapshot. "
                 "Only submit_edit changes the isolated Blender model. Each Python invocation is fresh; print compact evidence.",
                 dict(code=dict(type="string")), ("code",)),
            tool("submit_edit", "Apply your saved sparse payload to this independent Blender copy and save a new blend. "
                 "Provide the observed snapshot version and a unique operation_id. Same operation_id supports receipt recovery. "
                 "Only I vertices are editable. Values are applied as computed. If a receipt is uncertain, query state before retrying.",
                 dict(payload_id=dict(type="string"), expected_version=dict(type="integer"), operation_id=dict(type="string")),
                 ("payload_id", "expected_version", "operation_id")),
            tool("state", "Read the current isolated-copy version, operation records and saved artifact identities.", {}),
            tool("save_readback", "Save/read the current isolated model through a new independent Blender process and report actual geometry quality.", {}),
        ]
        if options.route == "facts":
            self.tools += [tool("focus", "Read current target/background/protection geometry facts and versioned references.", {}),
                tool("resolve_ref", "Resolve a returned current-region reference to precise current geometry.",
                     dict(reference=dict(type="string")), ("reference",))]

    def load_api(self):
        if self.api is None:
            spec = importlib.util.spec_from_file_location("_refine_session_api", HERE / "session_api.py")
            self.api = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = self.api
            spec.loader.exec_module(self.api)
        return self.api

    def state(self):
        return self.load_api().load_state(self.session)

    def path(self, value):
        path = Path(value)
        return path if path.is_absolute() else self.session / path

    def snapshot_fields(self, state):
        with np.load(self.path(state["current_npz"]), allow_pickle=False) as current:
            vertices = current["vertices_world"] if "vertices_world" in current else current["vertices"]
            faces = current["faces"]
            source_ids = current["source_ids"] if "source_ids" in current else np.arange(len(vertices), dtype=np.int64)
        with np.load(self.path(state["initial_npz"]), allow_pickle=False) as initial:
            first = initial["vertices_world"] if "vertices_world" in initial else initial["vertices"]
            fields = dict(vertices=vertices, initial_vertices=first, faces=faces, source_ids=source_ids,
                F_ids=initial["F_source_ids"] if "F_source_ids" in initial else initial["F_ids"],
                I_ids=initial["I_ids"], C_ids=initial["C_ids"], B0_ids=initial["B0_ids"], B1_ids=initial["B1_ids"], n0=initial["n0"])
        if fields["n0"].shape != vertices.shape or not np.array_equal(source_ids, np.arange(len(vertices))):
            raise ValueError("full_source_ID_indexed_geometry_and_n0_required")
        floating = ("vertices", "initial_vertices", "n0")
        return {key: np.asarray(value, dtype=np.float64 if key in floating else np.int64) for key, value in fields.items()}

    def snapshot(self):
        started, cpu = time.perf_counter(), time.process_time()
        state = self.state()
        current_path, initial_path = self.path(state["current_npz"]).resolve(), self.path(state["initial_npz"]).resolve()
        current_identity = file_identity(current_path)
        initial_identity = current_identity if current_path == initial_path else file_identity(initial_path)
        sources = dict(current_npz=current_identity, initial_npz=initial_identity)
        session_key = hashlib.sha256(str(self.session).casefold().encode("utf8")).hexdigest()
        folder = self.session / "snapshots" / ("v" + str(state["version"]))
        manifest_path = folder / "snapshot.json"
        manifest = json.loads(manifest_path.read_bytes()) if manifest_path.exists() else None
        cache_hit = bool(manifest and manifest["binding"]["sources"] == sources
            and manifest["binding"]["version"] == state["version"] and manifest["binding"]["session_key"] == session_key)
        creation_wall = creation_cpu = 0.
        if cache_hit:
            if binding_digest(manifest["binding"]) != manifest["cache_key"]:
                raise ValueError("snapshot_cache_binding_changed")
            packet_path = folder / manifest["filename"]
            if packet_path.parent.resolve() != folder.resolve() or file_identity(packet_path)["sha256"] != manifest["sha256"]:
                raise ValueError("snapshot_cache_packet_changed")
        else:
            creation_started, creation_cpu_started = time.perf_counter(), time.process_time()
            fields = self.snapshot_fields(state)
            if file_identity(current_path) != current_identity or file_identity(initial_path) != initial_identity:
                raise ValueError("snapshot_source_changed_during_packet_creation")
            schema = {key: dict(dtype=str(value.dtype), shape=list(value.shape)) for key, value in fields.items()}
            binding = dict(session_key=session_key, version=state["version"], sources=sources, schema=schema)
            cache_key = binding_digest(binding)
            folder.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=folder, suffix=".npz", delete=False) as stream:
                temporary = Path(stream.name)
                np.savez(stream, **fields)
            try:
                packet_identity = file_identity(temporary)
                packet_path = folder / ("s" + packet_identity["sha256"][:16] + ".npz")
                if packet_path.exists() and file_identity(packet_path)["sha256"] != packet_identity["sha256"]:
                    raise ValueError("snapshot_packet_filename_collision")
                os.replace(temporary, packet_path)
            finally:
                temporary.unlink(missing_ok=True)
            manifest = dict(binding=binding, cache_key=cache_key, filename=packet_path.name,
                sha256=packet_identity["sha256"], bytes=packet_identity["bytes"])
            with tempfile.NamedTemporaryFile(dir=folder, suffix=".json", delete=False) as stream:
                temporary_manifest = Path(stream.name)
            write(temporary_manifest, manifest)
            os.replace(temporary_manifest, manifest_path)
            creation_wall, creation_cpu = time.perf_counter()-creation_started, time.process_time()-creation_cpu_started
        specification = state["source_spec"]
        if not isinstance(specification, dict):
            specification = json.loads(self.path(specification).read_bytes())
        task = dict(self.task)
        for name, aliases in (("h", ("h", "h_m")), ("ell", ("ell", "ell_m")), ("center_source_id", ("center_source_id", "center"))):
            task[name] = next(specification[key] for key in aliases if key in specification)
        packet = dict(path=str(packet_path), sha256=manifest["sha256"], bytes=manifest["bytes"],
            cache_key=manifest["cache_key"], binding=manifest["binding"])
        cost = dict(cache_hit=cache_hit, wall_s=time.perf_counter()-started, CPU_s=time.process_time()-cpu,
            creation_wall_s=creation_wall, creation_CPU_s=creation_cpu, packet_bytes=manifest["bytes"],
            cache_key=manifest["cache_key"], source_identity_validation="current and initial NPZ SHA256 checked per snapshot",
            timing_scope="Packet creation is nested within snapshot wall and CPU.")
        return dict(version=state["version"], array_packet=packet, snapshot_cost=cost), task

    def call(self, params):
        started = time.perf_counter()
        index = len(self.calls) + 1
        folder = self.audit / ("tool_" + str(index).zfill(2))
        folder.mkdir(exist_ok=False)
        write(folder / "REQUEST.json", params)
        name, arguments = params.get("name"), params.get("arguments", {})
        record = dict(index=index, name=name, status="running")
        error = False
        try:
            if index > self.options.max_tool_calls:
                raise RuntimeError("fixed_tool_call_budget_exhausted")
            if name == "execute_python":
                if set(arguments) != {"code"} or type(arguments["code"]) is not str:
                    raise ValueError("execute_python_requires_code_string")
                snapshot, task = self.snapshot()
                record["snapshot"] = snapshot["snapshot_cost"]
                payload, execution = execute(arguments["code"], snapshot, task, self.session / "payloads", folder / "python",
                    timeout_s=self.options.python_timeout_s, output_chars=self.options.python_output_chars)
                record["execution"] = execution
                error = payload["error"] is not None
            elif name == "submit_edit":
                if set(arguments) != {"payload_id", "expected_version", "operation_id"}:
                    raise ValueError("submit_edit_fields_required")
                ident = arguments["payload_id"]
                if not isinstance(ident, str) or not re.fullmatch(r"p[0-9a-f]{32}", ident):
                    raise ValueError("invalid_own_payload_ID")
                metadata = json.loads((self.session / "payloads" / (ident + ".json")).read_bytes())
                if type(arguments["expected_version"]) is not int or metadata["observed_version"] != arguments["expected_version"]:
                    raise ValueError("payload_observed_version_mismatch")
                payload = self.load_api().submit_edit(self.session, self.session / "payloads" / (ident + ".npz"),
                    arguments["expected_version"], arguments["operation_id"])
            elif name in ("state", "save_readback", "focus"):
                if arguments:
                    raise ValueError("tool_requires_empty_arguments")
                if name == "state":
                    payload = self.state()
                    payload = {key: value for key, value in payload.items() if key not in ("case_dir", "source_spec", "initial_npz", "source_original")}
                elif name == "save_readback":
                    payload = self.load_api().save_readback(self.session)
                elif self.options.route == "facts":
                    payload = self.load_api().focus(self.session)
                else:
                    raise ValueError("focus_available_in_facts_route")
            elif name == "resolve_ref" and self.options.route == "facts":
                if set(arguments) != {"reference"} or type(arguments["reference"]) is not str:
                    raise ValueError("reference_string_required")
                payload = self.load_api().resolve_ref(self.session, arguments["reference"])
            else:
                raise ValueError("tool_unavailable_in_route")
            complete = json.dumps(payload, ensure_ascii=True, allow_nan=False, default=json_value)
            payload = json.loads(complete)
            write(folder / "COMPLETE_RESULT.json", payload)
            limit = self.options.fact_output_chars if name != "execute_python" else self.options.python_output_chars * 2 + 2000
            record.update(complete_text_UTF8_bytes=len(complete.encode("utf8")), truncated=len(complete) > limit)
            if record["truncated"]:
                complete = json.dumps(dict(truncated=True, preview=complete[:limit], original_UTF8_bytes=record["complete_text_UTF8_bytes"]), ensure_ascii=True)
            result = dict(content=[dict(type="text", text=complete)], isError=error)
            record["status"] = "tool_error" if error else "completed"
        except BaseException as exception:
            payload = dict(error=type(exception).__name__, message=str(exception))
            write(folder / "PRIVATE_ERROR.json", payload)
            result = dict(content=[dict(type="text", text=json.dumps(payload, ensure_ascii=True))], isError=True)
            record["status"] = "failed"
        record.update(wall_s=time.perf_counter() - started,
            public_text_UTF8_bytes=sum(len(block["text"].encode("utf8")) for block in result["content"]))
        self.calls.append(record)
        write(folder / "RESPONSE.json", result)
        write(folder / "COST.json", record)
        self.save(False)
        return result

    def save(self, closed):
        after = {name: hashlib.sha256((self.case / name).read_bytes()).hexdigest() for name in self.input_hashes}
        write(self.audit / "BRIDGE_RESULT.json", dict(task_id=self.task["task_id"], route=self.options.route, closed=closed,
            calls=self.calls, initial_input_identities_before=self.input_hashes, initial_input_identities_after=after,
            source_unchanged=self.input_hashes == after, wall_s=time.perf_counter() - self.started,
            execution_scope="ordinary Python in a fresh local process, asset writes confined by the isolated session edit API; no OS sandbox certification"))

    def serve(self):
        try:
            for raw in sys.stdin.buffer:
                request = json.loads(raw)
                method, ident = request.get("method"), request.get("id")
                if ident is None:
                    continue
                if method == "initialize":
                    result = dict(protocolVersion=request.get("params", {}).get("protocolVersion", "2024-11-05"),
                        capabilities=dict(tools=dict(listChanged=False)), serverInfo=dict(name="task_geometry", version="1"))
                elif method == "tools/list":
                    result = dict(tools=self.tools)
                elif method == "tools/call":
                    result = self.call(request.get("params", {}))
                elif method == "ping":
                    result = {}
                else:
                    reply = dict(jsonrpc="2.0", id=ident, error=dict(code=-32601, message="method_unavailable"))
                    sys.stdout.write(json.dumps(reply) + "\n")
                    sys.stdout.flush()
                    continue
                sys.stdout.write(json.dumps(dict(jsonrpc="2.0", id=ident, result=result), ensure_ascii=True, allow_nan=False) + "\n")
                sys.stdout.flush()
        finally:
            self.save(True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--route", choices=("native", "facts"), required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--max-tool-calls", type=int, default=10)
    parser.add_argument("--python-timeout-s", type=float, default=45)
    parser.add_argument("--python-output-chars", type=int, default=16000)
    parser.add_argument("--fact-output-chars", type=int, default=50000)
    Bridge(parser.parse_args()).serve()


if __name__ == "__main__":
    main()
