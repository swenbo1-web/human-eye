from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import median
import importlib.util
import json
import subprocess
import time


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "startup_verified"
MIGRATION = ROOT / "rollback/run_release_rollback.py"
ORDER = "ABBABAAB"


def load_release_inputs():
    spec = importlib.util.spec_from_file_location("_fixed_release_inputs", MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def endpoint(run_dir, mod, arm):
    command = mod.registered(arm)
    path = run_dir / "connector.json"
    binding = json.loads(Path(command[-1]).with_name("RUNTIME_BINDING.json").read_bytes())
    config = {
        "schema_version": "1.0", "enabled": True,
        "project_root": binding["site_packages"], "state_file": "state.json",
        "audit_file": "audit.jsonl", "quad_size": 64, "max_sessions": 16,
        "readback_atol_m": 1e-6, "blender": {"host": "127.0.0.1", "port": 1, "timeout_s": 0.15},
        "expected_identity": {
            **{k: binding["identity"][k] for k in ("base_version", "implementation_revision", "build_id")},
            "source_kind": "installed_distribution", "protocol_version": "2025-03-26", "mode": "live",
        },
    }
    path.write_text(json.dumps(config), encoding="utf-8")
    request = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
               "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                          "clientInfo": {"name": "startup-only-acceptance", "version": "1"}}}
    start = time.perf_counter_ns()
    with (run_dir / "stderr.txt").open("wb") as stderr:
        with subprocess.Popen(command + ["serve", "--config", str(path)], cwd=run_dir,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr) as proc:
            try:
                proc.stdin.write((json.dumps(request) + "\n").encode())
                proc.stdin.close()
                with ThreadPoolExecutor(max_workers=1) as threads:
                    line_future = threads.submit(proc.stdout.readline)
                    try:
                        line = line_future.result(timeout=20)
                    except TimeoutError:
                        proc.kill()
                        raise
                ready = time.perf_counter_ns()
                proc.wait(timeout=20)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()
            end = time.perf_counter_ns()
            assert proc.returncode == 0
            pid = proc.pid
    (run_dir / "initialize.json").write_bytes(line)
    message = json.loads(line)
    assert message["id"] == 1 and "result" in message and "error" not in message
    assert not (run_dir / "state.json").exists()
    audit = [json.loads(row) for row in (run_dir / "audit.jsonl").read_bytes().splitlines()]
    assert len(audit) == 1
    assert audit[0]["runtime_identity"]["build_id"] == config["expected_identity"]["build_id"]
    return {"arm": arm, "pid": pid, "init_ms": (ready-start)/1e6, "exit_ms": (end-start)/1e6}


def main():
    OUT.mkdir()
    mod = load_release_inputs()
    rows = []
    times = defaultdict(list)
    for index, arm in enumerate(ORDER, 1):
        run_dir = OUT / f"{index:02d}_{arm}"
        run_dir.mkdir()
        row = endpoint(run_dir, mod, arm)
        rows.append(row)
        times[arm].append(row["init_ms"])
    result = {"measure": "fresh MCP process; initialize only, no Blender connection",
              "order": ORDER, "rows": rows,
              "ready_median_ms": {arm: median(values) for arm, values in times.items()}}
    (OUT / "RESULT.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
