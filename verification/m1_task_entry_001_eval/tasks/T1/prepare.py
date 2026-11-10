"""Bounded one-shot T1 preparation; no production runtime or model execution."""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
EXPECTED_PRODUCT = "0005ab437c8f330ed277bd49133348389fe7222bda3087f16450dce55ec9c05a"
SPEC_SHA = "b54110358c37dc7be1f47a201ef14b12156923f53729a723874ab902645a4ce2"
PROMPT_SHA = "fd4baf27d33372d05ba23721216b66b1d4061dc88a439e7343f65836cd07aef0"


def need(value, reason):
    if not value:
        raise ValueError("T1_prepare_" + reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def dump(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    need(path.read_bytes() == raw, "persist_readback")


def product_identity():
    # Parse declarations as data; never import or execute any product module.
    tree = ast.parse((ROOT / "human_eye_plugin/runtime_identity.py").read_bytes())
    wanted = {"BASE_VERSION", "IMPLEMENTATION_REVISION", "_ROOT_MODULES"}
    constants = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in wanted}
    names = set(constants["_ROOT_MODULES"]) | {path.relative_to(ROOT).as_posix()
        for package in ("human_eye_plugin", "human_eye_module1_operators") for path in (ROOT / package).glob("*.py")}
    manifest = [{"path": name, "sha256": sha((ROOT / name).read_bytes())} for name in sorted(names)]
    digest = sha(json.dumps({"base_version": constants["BASE_VERSION"], "implementation_revision": constants["IMPLEMENTATION_REVISION"],
                            "files": manifest}, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode())
    need(len(manifest) == 137 and digest == EXPECTED_PRODUCT, "fixed_product_changed")
    return {"source_sha256": digest, "source_file_count": len(manifest), "files": manifest}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--source-freeze-sha256", required=True)
    parser.add_argument("--blender", type=Path, default=Path("D:/Tools/blender5.2/blender.exe"))
    args = parser.parse_args()
    need(Path(args.output).name == args.output and args.output not in (".", ".."), "output_name")
    output = HERE / args.output
    output.mkdir(exist_ok=False)
    started = time.perf_counter_ns()
    deadline = started + 180 * 10**9
    result = {"schema": "T1-preparation-result-v1", "passed": False,
        "started_ns": started, "original_deadline_ns": deadline,
        "processes": [], "errors": [], "production_calls": 0, "model_calls": 0,
        "shared_GUI_access": False, "new_asset_build_only": True,
        "product_commit": "7411ac7aa9338f17355ffe5cdf4df113ce862aed", "product_canonical": EXPECTED_PRODUCT}
    frozen = None
    binary = args.blender.resolve()
    binary_sha = None

    def sources_check():
        need(time.perf_counter_ns() < deadline, "original_deadline")
        need(sha((HERE / "SPEC.FROZEN.json").read_bytes()) == SPEC_SHA
             and sha((HERE / "PROMPT.txt").read_bytes()) == PROMPT_SHA, "task_contract_changed")
        if frozen is not None:
            need(all(sha((HERE / row["path"]).read_bytes()) == row["sha256"] for row in frozen["files"]), "QA_source_changed")
        if binary_sha is not None:
            need(sha(binary.read_bytes()) == binary_sha, "blender_binary_changed")
        return product_identity()

    def publish(name, value):
        sources_check()
        dump(output / name, value)
        sources_check()

    def process(label, command, limit_s):
        sources_check()
        stamp = time.perf_counter_ns()
        phase_deadline = min(deadline, stamp + limit_s * 10**9)
        row = {"label": label, "command": list(map(str, command)), "cwd": str(output),
            "started_ns": stamp, "original_run_deadline_ns": deadline,
            "phase_deadline_ns": phase_deadline, "timeout_s": limit_s,
            "pid": None, "process_reaped": False, "exit_code": None, "error": None}
        environment = os.environ.copy()
        overrides = {"BLENDER_USER_CONFIG": str(output / "isolated_config"),
            "BLENDER_USER_SCRIPTS": str(output / "isolated_scripts"),
            "BLENDER_USER_DATAFILES": str(output / "isolated_data"),
            "BLENDER_USER_EXTENSIONS": str(output / "isolated_extensions"),
            "TEMP": str(output / "tmp"), "TMP": str(output / "tmp"), "TMPDIR": str(output / "tmp")}
        for path in overrides.values():
            Path(path).mkdir(exist_ok=True)
        environment.update(overrides)
        row["environment_overrides"] = overrides
        owner = None
        try:
            with (output / (label + ".stdout.txt")).open("xb") as stdout, (output / (label + ".stderr.txt")).open("xb") as stderr:
                owner = subprocess.Popen(list(map(str, command)), cwd=output, stdin=subprocess.DEVNULL,
                    stdout=stdout, stderr=stderr, shell=False,
                    env=environment,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                row["pid"] = owner.pid
                while owner.poll() is None:
                    need(time.perf_counter_ns() < phase_deadline, "phase_deadline_" + label)
                    need(all((output / (label + suffix)).stat().st_size <= 1048576 for suffix in (".stdout.txt", ".stderr.txt")), "process_log_bytes")
                    time.sleep(.025)
                row["exit_code"] = owner.wait(timeout=5)
                row["process_reaped"] = True
                need(row["exit_code"] == 0, "process_exit_" + label)
                need(time.perf_counter_ns() < phase_deadline, "phase_publication_deadline_" + label)
        except BaseException as exc:
            row["error"] = {"type": type(exc).__name__, "reason": str(exc)}
            raise
        finally:
            if owner is not None:
                if owner.poll() is None:
                    owner.kill()
                row["exit_code"] = owner.wait(timeout=5)
                row["process_reaped"] = True
            row["ended_ns"] = time.perf_counter_ns()
            row["elapsed_ns"] = row["ended_ns"] - stamp
            row["logs"] = [{"path": label + suffix, "bytes": (output / (label + suffix)).stat().st_size,
                            "sha256": sha((output / (label + suffix)).read_bytes())} for suffix in (".stdout.txt", ".stderr.txt") if (output / (label + suffix)).is_file()]
            result["processes"].append(row)
            # Failure records remain evidence of failure even after expiration.
            row["published_before_original_deadline"] = time.perf_counter_ns() < deadline
            dump(output / (label + ".PROCESS.json"), row)
        sources_check()

    try:
        freeze_raw = (HERE / "SOURCE_FREEZE.json").read_bytes()
        need(sha(freeze_raw) == args.source_freeze_sha256, "QA_source_freeze_pin")
        frozen = json.loads(freeze_raw)
        need(frozen["spec_sha256"] == SPEC_SHA and frozen["prompt_sha256"] == PROMPT_SHA, "QA_source_task_pins")
        need(binary.is_file(), "blender_binary")
        binary_sha = sha(binary.read_bytes())
        identity = sources_check()
        publish("RUN_START.json", {"source_freeze_sha256": sha(freeze_raw), "frozen": frozen,
            "product_identity": identity, "blender": str(binary), "blender_sha256": binary_sha,
            "coordinator_python": sys.executable, "coordinator_python_version": sys.version,
            "coordinator_python_sha256": sha(Path(sys.executable).read_bytes()),
            "started_ns": started, "original_deadline_ns": deadline,
            "asset_policy": "one new owned background build; one fresh background read; no product or model execution"})
        process("01_BUILD", [binary, "--factory-startup", "--disable-autoexec", "--background",
            "--python-exit-code", "1", "--python", HERE / "generate_asset.py", "--", "--output", output], 60)
        asset = output / "scene.blend"
        need(asset.is_file() and asset.stat().st_size <= 4194304, "asset_bytes")
        asset_sha = sha(asset.read_bytes())
        process("02_READ", [binary, "--factory-startup", "--disable-autoexec", "--background", asset,
            "--python-exit-code", "1", "--python", HERE / "read_snapshot.py", "--", "--output", output,
            "--asset-sha256", asset_sha], 60)
        need((output / "SNAPSHOT.json").stat().st_size <= 131072, "snapshot_bytes")
        for stage, extra in (("03_ORACLE", []), ("04_REPLAY", ["--replay"])):
            child_deadline = min(deadline, time.perf_counter_ns() + 30 * 10**9)
            process(stage, [sys.executable, "-B", HERE / "oracle.py", "--output", output,
                "--deadline-ns", str(child_deadline), *extra], 30)
        replay = json.loads((output / "ORACLE_REPLAY.json").read_bytes())
        need(replay["passed"] is True and sha(asset.read_bytes()) == asset_sha, "final_replay_or_asset_binding")
        result.update(passed=True, asset=str(asset), asset_sha256=asset_sha,
            snapshot_sha256=sha((output / "SNAPSHOT.json").read_bytes()),
            truth_sha256=sha((output / "TRUTH.json").read_bytes()),
            oracle_sha256=sha((output / "ORACLE.json").read_bytes()),
            independent_replay_passed=True, prompt_sha256=PROMPT_SHA,
            statistics=json.loads((output / "ORACLE.json").read_bytes())["statistics"],
            final_product_identity=sources_check())
    except BaseException as exc:
        result["passed"] = False
        result["errors"].append({"type": type(exc).__name__, "reason": str(exc), "traceback": traceback.format_exc()})
    finally:
        try:
            sources_check()
            result["sources_unchanged"] = True
        except BaseException as exc:
            result["sources_unchanged"] = False
            result["passed"] = False
            result["errors"].append({"type": type(exc).__name__, "reason": str(exc)})
        result["ended_ns"] = time.perf_counter_ns()
        result["elapsed_ns"] = result["ended_ns"] - started
        result["published_before_original_deadline"] = result["ended_ns"] < deadline
        result["passed"] = result["passed"] and result["published_before_original_deadline"]
        result["artifacts"] = [{"path": path.name, "bytes": path.stat().st_size, "sha256": sha(path.read_bytes())}
            for path in sorted(output.iterdir()) if path.is_file()]
        dump(output / "PREPARATION_RESULT.json", result)
        if time.perf_counter_ns() >= deadline:
            raise TimeoutError("T1_prepare_result_publication_crossed_original_deadline")
    print(json.dumps({"output": str(output), "passed": result["passed"], "elapsed_s": result["elapsed_ns"] / 1e9}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main())
