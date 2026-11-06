"""Run one archived native functional job, with no performance measurement."""

from argparse import ArgumentParser
from hashlib import sha256
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import traceback
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "artifacts/integration/production_functional_001"
RUNTIME_SOURCE = ROOT / "artifacts/integration/method_diagnostic_001/runtime_identity.py"
BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
sys.path.insert(0, str(ROOT))

from artifacts.integration.method_diagnostic_001.runtime_identity import (
    THREAD_ENV, clock_anchor, effective_environment, identity, native_fingerprint, write_json,
)


def _relative(path):
    return path.resolve().relative_to(ROOT).as_posix()


def _observed_project(entry):
    files = {Path(raw).resolve() for module in tuple(sys.modules.values())
             if (raw := getattr(module, "__file__", None))}
    files.update((entry, Path(__file__).resolve()))
    return {_relative(path): identity(path)["sha256"] for path in sorted(files)
            if path.is_relative_to(ROOT) and path.is_file()}


def _fingerprint(anchor):
    try:
        return native_fingerprint(anchor)
    except SystemError as error:
        if "gpu module to be initialized" not in str(error):
            raise
        import gpu

        gpu.init()
        result = native_fingerprint(anchor)
        result["gpu_initialized_only_for_fingerprint"] = True
        return result


def _worker(job_path):
    job = json.loads(job_path.read_bytes())
    directory = job_path.parent
    entry = ROOT / job["entry"]
    sys.dont_write_bytecode = True
    sys.pycache_prefix = os.environ["PYTHONPYCACHEPREFIX"]
    sys.argv = [str(entry), "--", *job["arguments"]]
    anchor = clock_anchor()
    try:
        runpy.run_path(str(entry), run_name="__main__")
    finally:
        write_json(directory / "observed-project-imports.json",
                   {"scope": "Project imports observed at exit and explicit entry",
                    "paths": _observed_project(entry)})
        try:
            write_json(directory / "runtime.json", _fingerprint(anchor))
        except Exception:
            (directory / "runtime-error.txt").write_text(traceback.format_exc(), encoding="utf-8")


def _sources(entry, extra_sources):
    tracked = subprocess.check_output(["git", "ls-files", "-z", "--", "verification"], cwd=ROOT)
    paths = {ROOT / name for name in tracked.decode("utf-8").split("\x00")
             if name.endswith(".py") and (ROOT / name).is_file()}
    paths.update(ROOT.glob("human_eye_fast/**/*.py"))
    paths.update((Path(__file__), entry, RUNTIME_SOURCE))
    paths.update(extra_sources)
    return {_relative(path): path.read_bytes() for path in sorted(paths)}


def _portable_runtime(environment):
    code = """
import json
import sys
import numpy
import PIL
print(json.dumps({"python_version": sys.version, "python_executable": sys.executable,
                  "numpy": {"version": numpy.__version__, "path": numpy.__file__},
                  "pillow": {"version": PIL.__version__, "path": PIL.__file__}}))
"""
    argv = [sys.executable, "-B", "-c", code]
    info = json.loads(subprocess.check_output(argv, cwd=ROOT, env=environment))
    info["python_executable"] = identity(info["python_executable"])
    info["argv"] = argv
    return info


def launch(directory, entry, arguments, inputs, extra_sources):
    directory = directory.resolve()
    entry = entry.resolve(strict=True)
    if directory == OUTPUT_ROOT or not directory.is_relative_to(OUTPUT_ROOT):
        raise ValueError("Use a fresh job directory under production_functional_001")
    directory.mkdir(parents=True)
    registration = directory / "launch.json"
    overrides = {**THREAD_ENV, "PYTHONDONTWRITEBYTECODE": "1",
                 "PYTHONPYCACHEPREFIX": str(directory / "isolated-pycache")}
    environment = {**os.environ, **overrides}
    sources = _sources(entry, extra_sources)
    input_rows = [identity(path) for path in inputs]
    argv = [str(BLENDER), "--background", "--factory-startup", "--disable-autoexec", "--threads",
            "1", "--python-exit-code", "1", "--python", str(Path(__file__).resolve()), "--",
            "--registered-job", str(registration)]
    source_hashes = {name: sha256(data).hexdigest() for name, data in sources.items()}
    record = {"argv": argv, "entry": _relative(entry), "arguments": arguments,
              "blender_executable": identity(BLENDER), "environment_overrides": overrides,
              "environment_effective": effective_environment(environment),
              "portable_python": _portable_runtime(environment),
              "input_files": input_rows, "source_superset": source_hashes}
    with ZipFile(directory / "sources.zip", "x", compression=ZIP_DEFLATED) as archive:
        for name, data in sources.items():
            archive.writestr(name, data)
    write_json(registration, record)
    print(f"Registered {directory}", flush=True)
    with (directory / "worker.log").open("wb") as output:
        completed = subprocess.run(argv, cwd=ROOT, env=environment, stdout=output,
                                   stderr=subprocess.STDOUT, check=False)
    receipt = directory / "observed-project-imports.json"
    observed = json.loads(receipt.read_bytes())["paths"] if receipt.exists() else {}
    diff = [name for name, digest in observed.items() if source_hashes.get(name) != digest]
    runtime_path = directory / "runtime.json"
    runtime = json.loads(runtime_path.read_bytes()) if runtime_path.exists() else None
    summary = {"exit_code": completed.returncode, "stable_sources": sources == _sources(entry, extra_sources),
               "stable_inputs": input_rows == [identity(path) for path in inputs],
               "observed_project_files": len(observed), "observed_source_mismatches": diff,
               "stable_runtime_environment": bool(runtime and runtime["environment"] == record["environment_effective"])}
    write_json(directory / "process.json", summary)
    print(json.dumps(summary), flush=True)
    return 0 if (completed.returncode == 0 and observed and not diff and summary["stable_sources"]
                 and summary["stable_inputs"] and summary["stable_runtime_environment"]) else 1


def main():
    if "--registered-job" in sys.argv:
        _worker(Path(sys.argv[sys.argv.index("--registered-job") + 1]))
        return 0
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--entry", type=Path, required=True)
    parser.add_argument("--input", type=Path, action="append", default=[])
    parser.add_argument("--source", type=Path, action="append", default=[])
    start = sys.argv.index("--") if "--" in sys.argv else len(sys.argv)
    args = parser.parse_args(sys.argv[1:start])
    return launch(args.directory, args.entry, sys.argv[start + 1:], args.input, args.source)


if __name__ == "__main__":
    result = main()
    if result:
        raise SystemExit(result)
