"""Default production launcher: trusted live configuration, explicit demo opt-in."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


def resolve_config(explicit: str | None = None, *, environ=None, cwd=None) -> Path:
    """Select an operator-controlled path without walking to unrelated projects."""
    environment = os.environ if environ is None else environ
    working_directory = Path.cwd() if cwd is None else Path(cwd)
    configured = explicit if explicit is not None else environment.get("HUMAN_EYE_CONFIG")
    if configured is not None:
        if not isinstance(configured, str) or not configured.strip():
            raise ValueError("The live configuration path must not be empty")
        candidate = Path(configured).expanduser()
        if not candidate.is_absolute():
            candidate = working_directory / candidate
    else:
        candidate = working_directory / ".human-eye" / "live-connector.json"
    candidate = candidate.resolve()
    if not candidate.is_file():
        raise FileNotFoundError("Live configuration not found: " + str(candidate)
            + ". Set --config or HUMAN_EYE_CONFIG; demo requires explicit --demo.")
    return candidate


def run_demo_stdio(input_stream=None, output_stream=None) -> None:
    """Expose the frozen demonstration with an explicit, truthful mode handshake.

    Legacy dispatch and its tools remain untouched. This wrapper never runs from
    the default production branch, including after a live configuration error.
    """
    from . import mcp_server as legacy
    from .runtime_identity import runtime_identity
    incoming = sys.stdin if input_stream is None else input_stream
    outgoing = sys.stdout if output_stream is None else output_stream
    for raw_line in incoming:
        if not raw_line.strip():
            continue
        try:
            request = json.loads(raw_line)
            # All JSON-RPC notifications are silent, including mutating calls.
            if isinstance(request, dict) and "id" not in request:
                continue
            response = legacy.handle_jsonrpc_message(request)
            if (isinstance(request, dict) and request.get("method") == "initialize"
                    and isinstance(response, dict) and isinstance(response.get("result"), dict)):
                identity = runtime_identity(mode="demo")
                identity["source_file_count"] = len(identity.pop("source_files", []))
                identity["production_mode"] = False
                identity["scene_source"] = "legacy_synthetic_demonstration"
                response["result"].setdefault("_meta", {})["human_eye"] = identity
        except Exception as exc:
            response = {"jsonrpc": "2.0", "id": None,
                        "error": {"code": -32700, "message": "Demo request error: " + str(exc)}}
        if response is not None:
            outgoing.write(json.dumps(response, ensure_ascii=False, allow_nan=False) + "\n")
            outgoing.flush()


def construct_live_service(config):
    """Construct once and best-effort time only the service constructor call.

    Interpreter startup, package/module imports, argument parsing, configuration
    path selection and host connection are excluded. The audit writer is also
    excluded from the trace duration. No host connection is made by construction.
    """
    from .live_service import LiveSpatialService
    from .auto_router import _trace_span
    from .runtime_identity import IMPLEMENTATION_REVISION
    from .telemetry import best_effort_trace
    holder = {}
    def write(record):
        service = holder.get("service")
        if service is None:
            return False
        return service.record_event("request_trace", measurement_scope="service_constructor_only",
            excluded_stages=["interpreter_startup", "module_imports", "argument_parsing",
                             "config_path_selection", "host_connection", "audit_writer"],
            trace=record)
    with best_effort_trace("startup.service_construct", writer=write,
            implementation_revision=IMPLEMENTATION_REVISION) as trace:
        with _trace_span("startup.service_construct", kind="startup", source_name="service_constructor"):
            service = LiveSpatialService(config, production_mode=True)
        holder["service"] = service
        if trace is not None:
            try:
                trace.annotate(request_origin="production_launcher", source_name="service_constructor_only")
                trace.record_usage(source="unavailable")
                trace.set_outcome("configured")
            except Exception:
                pass
    return service


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(
        "Human Eye production MCP: requires trusted live configuration; "
        "use --demo only for the legacy synthetic demonstration."))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--config", help="Trusted local live-service configuration JSON")
    mode.add_argument("--demo", action="store_true", help="Explicit legacy synthetic-scene demonstration")
    args = parser.parse_args(argv)
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    if args.demo:
        run_demo_stdio()
        return 0
    try:
        config = resolve_config(args.config)
        # Importing or constructing the live service does not connect to Blender.
        # Connection failures on actual reads/writes remain live errors; there is
        # deliberately no error handler that falls back to a synthetic scene.
        service = construct_live_service(config)
    except Exception as exc:
        print("Unable to configure Human Eye production service: " + str(exc), file=sys.stderr)
        return 2
    from .live_spatial_mcp import run_stdio_mcp_server
    run_stdio_mcp_server(service)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
