"""Normal installed MCP server with byte-forwarding I/O timing and budget audit."""

import argparse
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from budget import Budget, encoded, save


NUMERIC_REASON = "active_observation_target_camera_numeric_insufficient"


def numeric_source_phase(binding):
    path = Path(binding["install_root"]) / "human_eye_plugin/blender_host.py"
    raw = path.read_bytes()
    expected = next(row["sha256"] for row in binding["source_manifest"]
                    if row["path"] == "human_eye_plugin/blender_host.py")
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise ValueError("numeric_phase_host_source_pin_changed")
    tree = ast.parse(raw)
    camera = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                  and node.name == "_observation_target_cameras")
    inside = {id(node) for node in ast.walk(camera)}
    tokens = [node for node in ast.walk(tree) if isinstance(node, ast.Constant) and node.value == NUMERIC_REASON]
    return {"source": str(path), "sha256": actual, "token": NUMERIC_REASON,
            "literal_count": len(tokens),
            "only_in_host_camera_function": bool(tokens) and all(id(node) in inside for node in tokens),
            "phase": "host capture camera construction, before external observe_capture/raster",
            "limits": "A completed exact typed public error plus this pinned producer location and zero render-attempt events establishes zero construction. Other errors retain their reservation upper bound."}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_context_metadata(service):
    context = getattr(service, '_read_context', None)
    if context is None:
        return {'available': False}
    selections = []
    for key, state in context._selections.items():
        normalized = state.get('normalized')
        meshes = [] if normalized is None else normalized[1]
        arrays = []
        for mesh in meshes:
            vertices, faces = mesh.vertices, mesh.faces
            arrays.append(dict(object_id=mesh.object_id, name=mesh.name, mesh_python_id=id(mesh),
                vertices_python_id=id(vertices), faces_python_id=id(faces),
                vertex_shape=list(vertices.shape), face_shape=list(faces.shape),
                vertices_nbytes=int(vertices.nbytes), faces_nbytes=int(faces.nbytes)))
        selections.append(dict(key_repr=repr(key), normalized=normalized is not None,
            fingerprint=None if normalized is None else normalized[2],
            result_count=len(state['results']), mesh_arrays=arrays))
    return dict(available=True, generation_repr=repr(context._generation),
        active_selection_repr=repr(context._capture), selections=selections,
        scope='Passive retained object/array metadata. Actual allocation/copy count is unmeasured.')


class AuditStreams:
    def __init__(self, incoming, outgoing, directory, audit_path, budget, phase, source_phase):
        self.incoming = incoming
        self.outgoing = outgoing
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.audit_path = Path(audit_path)
        self.budget = budget
        self.phase = phase
        self.pending = None
        self.written = ""
        self.sequence = 0
        self.source_phase = source_phase
        # mcp_transport reads .buffer when available. This wrapper is itself
        # the byte input and forwards each received line unchanged.
        self.buffer = self

    def readline(self, size=-1):
        raw = self.incoming.buffer.readline(size)
        received = time.perf_counter_ns()
        if not raw or not raw.strip():
            return raw
        try:
            request = json.loads(raw)
        except (ValueError, UnicodeError):
            # Leave malformed requests to the original public parser.
            self.pending = None
            return raw
        if not isinstance(request, dict):
            self.pending = None
            return raw
        self.sequence += 1
        self.pending = {"id": request.get("id"), "method": request.get("method"),
                        "sequence": self.sequence, "request_received_ns": received,
                        "TX_bytes": len(raw), "TX_sha256": hashlib.sha256(raw).hexdigest(),
                        "raster_reservation": None,
                        "audit_start_bytes": self.audit_path.stat().st_size if self.audit_path.exists() else 0}
        return raw

    def write(self, text):
        self.written += text
        return self.outgoing.write(text)

    def flush(self):
        self.outgoing.flush()
        completed = time.perf_counter_ns()
        if not self.written:
            return
        row = dict(self.pending or {})
        response = json.loads(self.written)
        raw = self.written.encode("utf-8")
        row.update(reply_completed_ns=completed, RX_text_UTF8_LF_bytes=len(raw),
                   RX_text_UTF8_LF_sha256=hashlib.sha256(raw).hexdigest(), response_id=response.get("id"),
                   actual_wire_byte_source="original client stdio RX.bin; platform stdout may translate LF to CRLF")
        if "request_received_ns" in row:
            row["request_to_reply_ns"] = completed - row["request_received_ns"]
        if self.audit_path.exists():
            tail = self.audit_path.read_bytes()[row.get("audit_start_bytes",0):]
            attempts = [json.loads(line) for line in tail.splitlines() if line.strip()]
            row["raster_actual"] = sum(event.get("event") in ("active_observation_render_attempt", "source_region_render_attempt") for event in attempts)
        else:
            row["raster_actual"] = 0
        with (self.directory / "MCP_IO.jsonl").open("ab") as stream:
            stream.write(encoded(row))
            stream.flush()
            os.fsync(stream.fileno())
        self.pending = None
        self.written = ""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--phase", choices=("qualification", "formal"), required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    binding = json.loads(args.binding.read_bytes())
    if binding.get("dependency_root"):
        sys.path.insert(0, binding["dependency_root"])
    helper = load_module("_target_verified_bootstrap", Path(__file__).parent / "reused/verified_bootstrap.py")
    guard = helper.bootstrap(binding)
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.live_spatial_mcp import _configure_utf8_stdio, run_stdio_mcp_server
    _configure_utf8_stdio()
    ledger = Budget(args.ledger)
    args.archive.mkdir(parents=True, exist_ok=False)
    class ObservedService(LiveSpatialService):
        """External observer only. Original product methods and formatter stay intact."""
        def __init__(self, *values, **keywords):
            self._archive_counter = 0
            super().__init__(*values, **keywords)

        def record_event(self, event, **fields):
            if event not in ("active_observation_render_attempt", "source_region_render_attempt"):
                return super().record_event(event, **fields)
            token = ledger.reserve("raster_attempt", args.label, args.phase, 1)
            audit_path = Path(json.loads(args.config.read_bytes())["audit_file"])
            offset = audit_path.stat().st_size if audit_path.exists() else 0
            try:
                value = super().record_event(event, **fields)
            except BaseException:
                # A callback/transport failure keeps the unit upper bound.
                raise
            tail = audit_path.read_bytes()[offset:]
            ledger.settle_rasters(token, actual=1, lower_bound=1,
                evidence={"audit_path":str(audit_path),"tail_start_bytes":offset,"tail_bytes":len(tail),
                    "tail_sha256":hashlib.sha256(tail).hexdigest(),"event":event,
                    "boundary":"producer on_render_attempt before raster construction; failed construction remains counted"},
                outcome="producer_attempt_admitted")
            return value

        def observe(self, *values, **keywords):
            self._archive_counter += 1
            directory = args.archive / ("call_" + str(self._archive_counter).zfill(3))
            directory.mkdir()
            before = read_context_metadata(self)
            began = time.perf_counter_ns()
            raw = super().observe(*values, **keywords)
            produced = time.perf_counter_ns()
            after = read_context_metadata(self)
            path = directory / "SERVICE_RESULT.json"
            save(path, raw)
            save(directory / 'READ_CONTEXT.json', dict(before=before, after=after))
            record={"index":self._archive_counter,"producer_returned_ns":produced,
                "started_ns":began,"saved_ns":time.perf_counter_ns(),"path":str(path),
                "sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
                "read_context":str(directory/'READ_CONTEXT.json'),
                "scope":"same returned producer object before original public formatter; no second observe",
                "new_observations_for_archive":0}
            with (args.archive/"INDEX.jsonl").open("ab") as stream:
                stream.write(encoded(record));stream.flush();os.fsync(stream.fileno())
            return raw

    service = ObservedService(str(args.config), production_mode=True)
    config = json.loads(args.config.read_bytes())
    streams = AuditStreams(sys.stdin, sys.stdout, args.evidence, config["audit_file"],
                           Budget(args.ledger), args.phase, numeric_source_phase(binding))
    runtime = {"pid": os.getpid(), "parent_pid": os.getppid(),
               "entry": str(Path(__file__).resolve()),
               "entry_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "binding_sha256": hashlib.sha256(args.binding.read_bytes()).hexdigest(),
               "python": sys.executable, "python_version": sys.version,
               "dependency_root": binding.get("dependency_root"), "source_sha256": binding["source_sha256"],
               "implementation": "installed LiveSpatialService and standard run_stdio_mcp_server",
               "algorithm_monkeypatches": 0, "external_observer_subclass": True,
               "full_archive": str(args.archive), "per_attempt_budget_label": args.label, "stream_audit": "original output text forwarded; timing and bounded reservation only",
               "numeric_pre_render_source_proof": streams.source_phase}
    for name in ("numpy", "PIL"):
        dependency = sys.modules.get(name)
        runtime[name] = None if dependency is None else {
            "file": getattr(dependency, "__file__", None), "version": getattr(dependency, "__version__", None)}
    with (Path(args.evidence) / "RUNTIME.json").open("xb") as stream:
        stream.write(encoded(runtime))
    try:
        run_stdio_mcp_server(service, input_stream=streams, output_stream=streams)
    finally:
        guard.verify_loaded()


if __name__ == "__main__":
    main()
