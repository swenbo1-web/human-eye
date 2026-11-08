"""Model-neutral persistent JSON-lines worker (not the legacy MCP server)."""
from __future__ import annotations

import argparse
import json
import sys

from .auto_router import HumanEyeAutoRouter


def run_stdio_router() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("auto", "off", "force_3d"), default="auto")
    parser.add_argument("--quad-size", type=int, default=128)
    parser.add_argument("--readback-atol-m", type=float, default=1e-9,
                        help="Trusted host readback comparison tolerance; max 1e-5 metres")
    args = parser.parse_args()
    router = HumanEyeAutoRouter(mode=args.mode, quad_size=args.quad_size,
                               readback_atol_m=args.readback_atol_m)
    for line in sys.stdin:
        request_id = None
        try:
            if len(line) > 32 * 1024 * 1024:
                raise ValueError("Request exceeds 32 MiB")
            def reject_constant(value):
                raise ValueError("Non-finite JSON number: " + value)
            request = json.loads(line, parse_constant=reject_constant)
            if not isinstance(request, dict):
                raise ValueError("Request must be a JSON object")
            candidate_id = request.get("id")
            if candidate_id is not None and type(candidate_id) not in (str, int):
                raise ValueError("Request id must be a string or integer")
            request_id = candidate_id
            # A request/response envelope is convenient for non-Python agents.
            event = request.get("payload", request)
            response = {"id": request_id, "result": router.handle_event(event)}
        except Exception as exc:
            response = {"id": request_id, "error": {"type": type(exc).__name__, "message": str(exc)}}
        sys.stdout.write(json.dumps(response, ensure_ascii=True, allow_nan=False) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(run_stdio_router())
