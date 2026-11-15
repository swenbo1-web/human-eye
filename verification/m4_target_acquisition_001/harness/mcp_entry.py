"""Normal installed MCP server with byte-forwarding I/O timing and budget audit."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from budget import Budget, encoded


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AuditStreams:
    def __init__(self, incoming, outgoing, directory, audit_path, budget, phase):
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
        params = request.get("params")
        args = params.get("arguments", {}) if isinstance(params, dict) else {}
        query = args.get("query", {}) if isinstance(args, dict) else {}
        active_image = (request.get("method") == "tools/call"
                        and isinstance(query, dict) and query.get("mode") == "active_observation"
                        and args.get("include_image", True) is True)
        token = self.budget.reserve("raster_request", str(request.get("id")),
                                    self.phase, 6) if active_image else None
        self.pending = {"id": request.get("id"), "method": request.get("method"),
                        "sequence": self.sequence, "request_received_ns": received,
                        "TX_bytes": len(raw), "TX_sha256": hashlib.sha256(raw).hexdigest(),
                        "raster_reservation": token,
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
        row.update(reply_completed_ns=completed, RX_bytes=len(raw),
                   RX_sha256=hashlib.sha256(raw).hexdigest(), response_id=response.get("id"))
        if "request_received_ns" in row:
            row["request_to_reply_ns"] = completed - row["request_received_ns"]
        token = row.get("raster_reservation")
        if token is not None:
            # record_event writes each render-attempt event before construction.
            # Successful output has returned from the finite six-view loop.
            tail = b""
            if self.audit_path.exists():
                with self.audit_path.open("rb") as stream:
                    stream.seek(row["audit_start_bytes"])
                    tail = stream.read()
            events = [json.loads(line) for line in tail.splitlines() if line.strip()]
            attempts = [event for event in events if event.get("event") == "active_observation_render_attempt"]
            successful = "error" not in response and response.get("result", {}).get("isError") is False
            # A completed product error also finishes the synchronous invocation,
            # but retain the full upper bound if the audit cannot prove its end.
            completed_error = any(event.get("event") == "active_observation_failed" for event in events)
            exact = len(attempts) if successful or completed_error else None
            self.budget.settle_rasters(token, actual=exact, lower_bound=len(attempts),
                evidence={"audit_path": str(self.audit_path), "tail_start_bytes": row["audit_start_bytes"],
                          "tail_bytes": len(tail), "tail_sha256": hashlib.sha256(tail).hexdigest(),
                          "render_attempt_events": attempts},
                outcome="completed_success" if successful else "completed_product_error" if completed_error else "unknown")
            row.update(raster_actual=exact, raster_confirmed_lower_bound=len(attempts))
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
    args = parser.parse_args()
    binding = json.loads(args.binding.read_bytes())
    if binding.get("dependency_root"):
        sys.path.insert(0, binding["dependency_root"])
    helper = load_module("_target_verified_bootstrap", Path(__file__).parent / "reused/verified_bootstrap.py")
    guard = helper.bootstrap(binding)
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.live_spatial_mcp import _configure_utf8_stdio, run_stdio_mcp_server
    _configure_utf8_stdio()
    service = LiveSpatialService(str(args.config), production_mode=True)
    config = json.loads(args.config.read_bytes())
    streams = AuditStreams(sys.stdin, sys.stdout, args.evidence, config["audit_file"],
                           Budget(args.ledger), args.phase)
    runtime = {"pid": os.getpid(), "parent_pid": os.getppid(),
               "entry": str(Path(__file__).resolve()),
               "entry_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "binding_sha256": hashlib.sha256(args.binding.read_bytes()).hexdigest(),
               "python": sys.executable, "python_version": sys.version,
               "dependency_root": binding.get("dependency_root"), "source_sha256": binding["source_sha256"],
               "implementation": "installed LiveSpatialService and standard run_stdio_mcp_server",
               "algorithm_monkeypatches": 0, "stream_audit": "original bytes forwarded; timing and bounded reservation only"}
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
