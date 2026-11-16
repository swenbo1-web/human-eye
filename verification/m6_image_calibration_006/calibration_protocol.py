"""Local JSON-lines protocol for the owned deterministic calibration service."""

import json
from contextlib import redirect_stdout
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import calibrator


def dispatch(message):
    if message.get("jsonrpc") != "2.0" or message.get("method") not in ("calibrate", "status"):
        raise ValueError("supported_calibration_JSONRPC_request_required")
    request = message.get("params")
    if not isinstance(request, dict):
        raise ValueError("calibration_request_parameters_required")
    if request.get("stage") == "v2":
        from calibration_batch import calibrate, status
        return calibrate(request) if message["method"] == "calibrate" else status(request)
    return calibrator.calibrate(request) if message["method"] == "calibrate" else calibrator.status(request)


def main():
    for raw in sys.stdin.buffer:
        message = None
        try:
            message = json.loads(raw)
            with redirect_stdout(sys.stderr):
                result = dispatch(message)
            response = dict(jsonrpc="2.0", id=message.get("id"), result=result)
        except Exception as error:
            response = dict(jsonrpc="2.0", id=message.get("id") if isinstance(message, dict) else None,
                error=dict(code=-32000, type=type(error).__name__, message=str(error)))
        sys.stdout.write(json.dumps(response, allow_nan=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
