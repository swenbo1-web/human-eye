"""Actual subprocess client for calibration requests with retained raw transport."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import PYTHON, identity, write
from calibrator import request_for


def call(method, request, *, output=None):
    started, cpu = time.perf_counter(), time.process_time()
    directory = Path(output).resolve() if output else HERE / "private/protocol" / uuid.uuid4().hex[:12]
    if not directory.is_relative_to(HERE / "private"):
        raise ValueError("protocol_evidence_output_must_belong_to_current_batch")
    directory.mkdir(parents=True, exist_ok=False)
    message = dict(jsonrpc="2.0", id="calibration_client", method=method, params=request)
    raw = (json.dumps(message, allow_nan=False) + "\n").encode()
    (directory / "REQUEST.json").write_bytes(raw)
    command = [str(PYTHON), "-I", "-B", "-X", "utf8", str(HERE / "calibration_protocol.py")]
    process = subprocess.run(command, input=raw, capture_output=True, timeout=1200, cwd=HERE,
        creationflags=subprocess.CREATE_NO_WINDOW)
    (directory / "STDOUT.bin").write_bytes(process.stdout)
    (directory / "STDERR.bin").write_bytes(process.stderr)
    lines = process.stdout.splitlines()
    response = json.loads(lines[-1]) if lines else dict(error=dict(message="protocol_process_returned_no_response"))
    record = dict(protocol_client=True, actual_Pro_calls=0, method=method, request=message, response=response,
        process_returncode=process.returncode, wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu,
        command=command, client_source=identity(Path(__file__)), service_source=identity(HERE / "calibration_protocol.py"),
        request_identity=identity(directory / "REQUEST.json"), stdout_identity=identity(directory / "STDOUT.bin"),
        stderr_identity=identity(directory / "STDERR.bin"))
    write(directory / "RESULT.json", record)
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("v1", "v2"), default="v1")
    parser.add_argument("--proposal", choices=("v1_native", "v2_facts"), required=True)
    parser.add_argument("--method", choices=("calibrate", "status"), default="calibrate")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = call(args.method, request_for(args.proposal, args.stage), output=args.output)
    response = result["response"]
    value = response.get("result", {})
    print(json.dumps(dict(protocol_client=True, method=args.method, stage=args.stage, proposal=args.proposal,
        process_returncode=result["process_returncode"], error=response.get("error"), reused=value.get("reused"),
        selected_alpha=value.get("result", {}).get("selected_alpha"), result_reference=value.get("result_reference"),
        wall_s=result["wall_s"])))
    if result["process_returncode"] or "error" in response:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
