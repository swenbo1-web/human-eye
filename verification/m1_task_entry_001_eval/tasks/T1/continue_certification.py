"""One bounded QA correction over the unchanged first T1 asset/snapshot.

No Blender process, asset generation, product call or model call is performed.
The rejected exact-matrix assumption and all first-run evidence are preserved.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent


def need(condition, reason):
    if not condition:
        raise ValueError("T1_certification_" + reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    with path.open("xb") as stream:
        stream.write((json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-freeze-sha256", required=True)
    args = parser.parse_args()
    output = HERE / "run_01"
    started = time.perf_counter_ns()
    deadline = started + 120 * 10**9
    result = {"schema": "T1-actual-affine-certification-result-v1", "passed": False,
        "started_ns": started, "original_deadline_ns": deadline, "processes": [], "errors": [],
        "new_Blender_processes": 0, "asset_regenerations": 0, "production_calls": 0, "model_calls": 0,
        "original_preparation_failure_preserved": True, "same_first_asset_and_snapshot": True}
    freeze = None

    def check():
        need(time.perf_counter_ns() < deadline, "original_deadline")
        if freeze is not None:
            need(all(sha((HERE / row["path"]).read_bytes()) == row["sha256"] for row in freeze["files"]), "frozen_source_or_input_changed")
        return original.product_identity()

    original = None
    try:
        raw = (HERE / "CERTIFICATION_SOURCE_FREEZE.json").read_bytes()
        need(sha(raw) == args.source_freeze_sha256, "freeze_pin")
        freeze = json.loads(raw)
        need(all(sha((HERE / row["path"]).read_bytes()) == row["sha256"] for row in freeze["files"]), "source_input_pin")
        loader = importlib.util.spec_from_file_location("T1_frozen_preparation_data_helpers", HERE / "prepare.py")
        original = importlib.util.module_from_spec(loader)
        loader.loader.exec_module(original)
        identity = check()
        save(output / "CERTIFICATION_START.json", {"source_freeze_sha256": sha(raw), "freeze": freeze,
            "product_identity": identity, "original_deadline_ns": deadline,
            "python": sys.executable, "python_sha256": sha(Path(sys.executable).read_bytes())})
        for label, replay in (("05_INTERVAL_ORACLE", False), ("06_INTERVAL_REPLAY", True)):
            check()
            phase_started = time.perf_counter_ns()
            phase_deadline = min(deadline, phase_started + 30 * 10**9)
            command = [sys.executable, "-B", str(HERE / "oracle_interval.py"), "--output", str(output),
                       "--deadline-ns", str(phase_deadline)] + (["--replay"] if replay else [])
            row = {"label": label, "command": command, "started_ns": phase_started,
                "phase_deadline_ns": phase_deadline, "original_deadline_ns": deadline,
                "pid": None, "exit_code": None, "process_reaped": False, "error": None}
            owner = None
            try:
                with (output / (label + ".stdout.txt")).open("xb") as stdout, (output / (label + ".stderr.txt")).open("xb") as stderr:
                    owner = subprocess.Popen(command, cwd=output, stdin=subprocess.DEVNULL, stdout=stdout,
                        stderr=stderr, shell=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    row["pid"] = owner.pid
                    while owner.poll() is None:
                        need(time.perf_counter_ns() < phase_deadline, "phase_deadline")
                        need(all((output / (label + suffix)).stat().st_size <= 1048576 for suffix in (".stdout.txt", ".stderr.txt")), "log_bytes")
                        time.sleep(.025)
                    row["exit_code"] = owner.wait(timeout=5)
                    need(row["exit_code"] == 0 and time.perf_counter_ns() < phase_deadline, "oracle_phase_failed")
            except BaseException as exc:
                row["error"] = {"type": type(exc).__name__, "reason": str(exc)}
                raise
            finally:
                if owner is not None:
                    if owner.poll() is None:
                        owner.kill()
                    row["exit_code"] = owner.wait(timeout=5)
                    row["process_reaped"] = True
                row["elapsed_ns"] = time.perf_counter_ns() - phase_started
                row["logs"] = [{"path": label + suffix, "bytes": (output / (label + suffix)).stat().st_size,
                    "sha256": sha((output / (label + suffix)).read_bytes())} for suffix in (".stdout.txt", ".stderr.txt") if (output / (label + suffix)).exists()]
                result["processes"].append(row)
                save(output / (label + ".PROCESS.json"), row)
            check()
        replay = json.loads((output / "ORACLE_REPLAY.json").read_bytes())
        need(replay["passed"] is True, "replay_pass")
        result.update(passed=True, final_product_identity=check(), oracle_replayed=True,
            truth_sha256=sha((output / "TRUTH.json").read_bytes()),
            oracle_sha256=sha((output / "ORACLE.json").read_bytes()),
            snapshot_sha256=sha((output / "SNAPSHOT.json").read_bytes()),
            asset_sha256=sha((output / "scene.blend").read_bytes()))
    except BaseException as exc:
        result["passed"] = False
        result["errors"].append({"type": type(exc).__name__, "reason": str(exc), "traceback": traceback.format_exc()})
    finally:
        try:
            check()
            result["sources_and_inputs_unchanged"] = True
        except BaseException as exc:
            result["passed"] = False
            result["sources_and_inputs_unchanged"] = False
            result["errors"].append({"type": type(exc).__name__, "reason": str(exc)})
        result["elapsed_ns"] = time.perf_counter_ns() - started
        result["published_utc"] = datetime.now(timezone.utc).isoformat()
        spec_freeze = json.loads((HERE / "SPEC_FREEZE.json").read_bytes())
        frozen_at = datetime.fromisoformat(spec_freeze["frozen_at_utc"].replace("Z", "+00:00"))
        result["wallclock_seconds_since_spec_freeze_including_QA_development"] = (datetime.now(timezone.utc) - frozen_at).total_seconds()
        result["original_failed_preparation_elapsed_ns"] = json.loads((output / "PREPARATION_RESULT.json").read_bytes())["elapsed_ns"]
        result["published_before_original_deadline"] = time.perf_counter_ns() < deadline
        result["passed"] = result["passed"] and result["published_before_original_deadline"]
        save(output / "CERTIFICATION_RESULT.json", result)
        need(time.perf_counter_ns() < deadline, "publication_crossed_original_deadline")
    print(json.dumps({"passed": result["passed"], "elapsed_s": result["elapsed_ns"] / 1e9}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main())
