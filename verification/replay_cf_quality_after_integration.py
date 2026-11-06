"""Replay frozen CF quality serially after the control seam changes."""

from argparse import ArgumentParser, Namespace
from hashlib import file_digest, sha256
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(__file__).resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from verification.benchmark_cerebellar_flash import BLENDER, PYTHON, SEEDS, THREADS


DESTINATION = ROOT / "artifacts/integration/production_functional_001"
ORIGINAL = ROOT / "artifacts/cf/formal_001"
ENV_KEYS = tuple(sorted({
    *THREADS, "OMP_DYNAMIC", "OMP_PROC_BIND", "OMP_PLACES", "MKL_DYNAMIC",
    "MKL_CBWR", "OPENBLAS_CORETYPE", "CUDA_VISIBLE_DEVICES", "CUDA_DEVICE_ORDER",
    "HIP_VISIBLE_DEVICES", "ONEAPI_DEVICE_SELECTOR", "BLENDER_GPU_BACKEND",
    "CYCLES_DEVICE", "PYTHONHASHSEED", "PYTHONNOUSERSITE", "PYTHONPATH",
    "PYTHONPYCACHEPREFIX",
}))
INCIDENTAL_DURATION_FIELDS = ("score_ns", "elapsed_ns")


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
                    encoding="utf-8", newline="\n")


def read_json(path):
    return json.loads(path.read_bytes())


def file_identity(path):
    with path.open("rb") as stream:
        return {"bytes": path.stat().st_size, "sha256": file_digest(stream, "sha256").hexdigest()}


def byte_identity(payload):
    return {"bytes": len(payload), "sha256": sha256(payload).hexdigest()}


def executable_identity(path):
    path = Path(path).resolve(strict=True)
    return {"path": str(path), **file_identity(path)}


def effective_env(environment):
    return {key: environment.get(key) for key in ENV_KEYS}


def module_info(name):
    module = sys.modules.get(name)
    if module is None:
        return None
    return {"version": getattr(module, "__version__", None), "path": getattr(module, "__file__", None)}


def observed_project_modules():
    files = {}
    for module in tuple(sys.modules.values()):
        filename = getattr(module, "__file__", None)
        if not filename:
            continue
        path = Path(filename).resolve()
        if path.is_relative_to(ROOT) and path.is_file():
            files[path.relative_to(ROOT).as_posix()] = file_identity(path)
    return dict(sorted(files.items()))


def runtime(out, name):
    result = {
        "scope": "actual worker runtime and observed project modules",
        "pid": os.getpid(),
        "argv": sys.argv,
        "python_version": sys.version,
        "python_executable": executable_identity(sys.executable),
        "numpy": module_info("numpy"),
        "pillow": module_info("PIL"),
        "pillow_image": module_info("PIL.Image"),
        "environment": effective_env(os.environ),
        "observed_project_modules": observed_project_modules(),
    }
    if name == "native":
        import bpy
        import gpu

        result.update(
            blender_version=bpy.app.version_string,
            blender_build=bpy.app.build_hash.decode(),
            blender_executable=executable_identity(bpy.app.binary_path),
            gpu={"renderer": gpu.platform.renderer_get(), "vendor": gpu.platform.vendor_get(),
                 "backend": gpu.platform.backend_type_get(), "version": gpu.platform.version_get()},
        )
    write_json(out / f"runtime-{name}.json", result)


def native(args):
    from verification import cf_experiment

    class FingerprintedPillowWorker(cf_experiment.PillowWorker):
        def __enter__(self):
            argv = (self.python_exe, "-B", str(SCRIPT), "--worker", "pillow", "--out", str(args.out))
            self.process = subprocess.Popen(
                argv, cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            return self

    model, manifest, control, diagnostic = evaluation_inputs(args.seed)
    try:
        with patch.object(cf_experiment, "PillowWorker", FingerprintedPillowWorker):
            cf_experiment.run(Namespace(
                stage="evaluate", split="evaluation", seed=args.seed, out=args.out,
                python=args.python, model=model, manifest=manifest, control=control,
                diagnostic=diagnostic,
            ))
    finally:
        runtime(args.out, "native")


def pillow(out):
    from verification.cf_visual_acceptance import _worker

    try:
        _worker()
    finally:
        runtime(out, "pillow")


def evaluation_inputs(seed):
    base = ORIGINAL / str(seed)
    return (base / "seal/frozen.npz",
            *(base / "specs" / f"manifest-{split}.json"
              for split in ("evaluation", "control", "diagnostic")))


def archive_paths(seed):
    base = ORIGINAL / str(seed)
    evaluation = base / "evaluation"
    completed = base / "evaluation-completion"
    return (evaluation, completed) if completed.is_dir() else (evaluation,)


def registered_inputs(seed):
    model, *manifests = evaluation_inputs(seed)
    archives = archive_paths(seed)
    completed = archives[-1]
    reference = [
        completed / "summary.json",
        *(archive / name for archive in archives
          for name in ("source.json", "media.zip", "records.jsonl.gz")),
        completed / "prequential/media.zip", completed / "prequential/records.jsonl.gz",
        *(path for path in (completed / "visual-negatives").rglob("*") if path.is_file()),
    ]
    return sorted((model, model.with_suffix(".json"), *manifests, *reference))


def source_snapshot():
    paths = {SCRIPT, *(ROOT / "docs" / name for name in (
        "CF_ACCEPTANCE_PROTOCOL.md", "CF_IMPLEMENTATION.md",
        "radical_acceptance_cf_preflight.json", "ENGINE_INTEGRATION_API.md",
        "ENGINE_INTEGRATION_REWORK_REVIEW.md", "radical_acceptance_integration_rework.json",
    ))}
    for folder in ("human_eye_fast", "verification"):
        paths.update((ROOT / folder).rglob("*.py"))
    return {path.relative_to(ROOT).as_posix(): path.read_bytes() for path in sorted(paths)}


def archive_members(paths):
    members = {}
    for path in paths:
        with ZipFile(path) as archive:
            for item in archive.infolist():
                identity = byte_identity(archive.read(item))
                previous = members.setdefault(item.filename, identity)
                if previous != identity:
                    raise ValueError(f"Conflicting archived media member {item.filename}")
    return members


def compare_identities(expected, actual):
    return {
        "expected_count": len(expected), "actual_count": len(actual),
        "missing": sorted(expected.keys() - actual.keys()),
        "extra": sorted(actual.keys() - expected.keys()),
        "changed": {name: {"expected": expected[name], "actual": actual[name]}
                    for name in sorted(expected.keys() & actual.keys())
                    if expected[name] != actual[name]},
    }


def same_identities(report):
    return not any(report[key] for key in ("missing", "extra", "changed"))


def normalize(value):
    if isinstance(value, dict):
        return {key: normalize(item) for key, item in value.items()
                if key not in INCIDENTAL_DURATION_FIELDS}
    if isinstance(value, list):
        return [normalize(item) for item in value]
    return value


def canonical(value):
    return json.dumps(normalize(value), sort_keys=True, ensure_ascii=False,
                      allow_nan=False, separators=(",", ":")).encode()


def record_identities(paths):
    rows = {}
    for path in paths:
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                record = json.loads(line)
                key = f"{len(rows):04d}:{record['id']}:{record.get('arm', 'action')}"
                rows[key] = byte_identity(canonical(record))
    return rows


def tree_identities(folder):
    return {path.relative_to(folder).as_posix(): file_identity(path)
            for path in sorted(folder.rglob("*")) if path.is_file()}


def compare_quality(out, seed):
    from verification.cf_report import _action_report, _quality_checks, _view_report

    original = archive_paths(seed)
    complete = original[-1]
    expected, actual = (read_json(path / "summary.json") for path in (complete, out))
    summaries = compare_identities(
        {key: byte_identity(canonical(value)) for key, value in expected.items() if key != "environment"},
        {key: byte_identity(canonical(value)) for key, value in actual.items() if key != "environment"},
    )
    top_media = compare_identities(archive_members([path / "media.zip" for path in original]),
                                   archive_members([out / "media.zip"]))
    top_records = compare_identities(record_identities([path / "records.jsonl.gz" for path in original]),
                                     record_identities([out / "records.jsonl.gz"]))
    pre_media = compare_identities(archive_members([complete / "prequential/media.zip"]),
                                   archive_members([out / "prequential/media.zip"]))
    pre_records = compare_identities(record_identities([complete / "prequential/records.jsonl.gz"]),
                                     record_identities([out / "prequential/records.jsonl.gz"]))
    negatives = compare_identities(tree_identities(complete / "visual-negatives"),
                                   tree_identities(out / "visual-negatives"))

    views, _, _ = _view_report(actual["views"])
    actions, _, _ = _action_report(actual["actions"])
    checks = _quality_checks(actual)
    expected_r_failure = seed == 20261105
    r_match = views["R"]["passed"] is (not expected_r_failure)
    gates_match = (views["L"]["passed"] and actions["passed"] and r_match
                   and all(check["passed"] for check in checks.values()))
    comparisons = {"summary_sections": summaries, "media": top_media, "records": top_records,
                   "prequential_media": pre_media, "prequential_records": pre_records,
                   "visual_negative_files": negatives}
    return {
        "matches": bool(gates_match and all(map(same_identities, comparisons.values()))),
        "comparisons": comparisons, "view_rows": {key: len(rows) for key, rows in actual["views"].items()},
        "action_rows": len(actual["actions"]), "R": {"expected_ray_gate_failure": expected_r_failure,
                                                      "actual": views["R"]},
        "L": views["L"], "A": actions, "controls": checks,
    }


def worker_command(blender, python, seed, out):
    return [str(blender), "--background", "--factory-startup", "--disable-autoexec", "--threads", "1",
            "--python-exit-code", "1", "--python", str(SCRIPT), "--", "--worker", "native",
            "--seed", str(seed), "--out", str(out), "--python", str(python)]


def run_seed(job, source_ids, executables):
    seed, out = job["seed"], Path(job["out"])
    out.mkdir()
    write_json(out / "launch.json", job)
    environment = {**os.environ, **job["env_overrides"]}
    with (out / "worker.log").open("wb") as log:
        proc = subprocess.run(job["argv"], cwd=ROOT, env=environment, stdout=log,
                              stderr=subprocess.STDOUT, check=False,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    stable_inputs = all(file_identity(Path(path)) == item for path, item in job["inputs"].items())
    stable_sources = {name: byte_identity(data) for name, data in source_snapshot().items()} == source_ids
    receipts = {}
    for kind in ("native", "pillow"):
        path = out / f"runtime-{kind}.json"
        if path.is_file():
            receipts[kind] = read_json(path)
    import_errors = {
        kind: {name: item for name, item in receipt["observed_project_modules"].items()
               if source_ids.get(name) != item}
        for kind, receipt in receipts.items()
    }
    import_errors = {kind: items for kind, items in import_errors.items() if items}
    input_reads = {}
    if (out / "reads.jsonl").is_file():
        for line in (out / "reads.jsonl").read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            input_reads[item.pop("path")] = item
    actual_inputs_match = input_reads == {path: job["inputs"][path] for path in job["worker_inputs"]}
    runtime_complete = (
        set(receipts) == {"native", "pillow"}
        and not import_errors
        and receipts["native"]["blender_executable"] == executables["blender"]
        and receipts["pillow"]["python_executable"] == executables["pillow_python"]
        and all(receipt["environment"] == job["effective_env"] for receipt in receipts.values())
        and receipts["native"]["numpy"] is not None
        and receipts["pillow"]["pillow_image"] is not None
    )
    try:
        quality = compare_quality(out, seed)
    except (OSError, ValueError, KeyError, TypeError, AssertionError, BadZipFile) as error:
        quality = {"matches": False, "comparison_error": f"{type(error).__name__}: {error}"}
    old_sources = read_json(archive_paths(seed)[-1] / "source.json")
    source_changes = {name: {"archived": prior, "current": source_ids.get(name)}
                      for name, prior in old_sources.items() if source_ids.get(name) != prior}
    result = {
        "seed": seed, "exit_code": proc.returncode, "stable_inputs": stable_inputs,
        "stable_sources": stable_sources, "actual_input_reads_match": actual_inputs_match,
        "runtime_complete": runtime_complete, "observed_import_mismatches": import_errors,
        "project_source_changes_since_original_quality": source_changes,
        "quality": quality, "output_files": tree_identities(out),
    }
    result["matches"] = bool(proc.returncode == 0 and stable_inputs and stable_sources
                             and actual_inputs_match and runtime_complete and quality["matches"])
    write_json(out / "comparison.json", result)
    print(f"CF quality {seed} {'MATCH' if result['matches'] else 'DIFFERENCE'}", flush=True)
    return result


def launch(args):
    out = args.out
    if not out.is_relative_to(DESTINATION) or out == DESTINATION:
        raise ValueError("Use a fresh directory inside production_functional_001")
    out.mkdir(parents=True, exist_ok=False)
    sources = source_snapshot()
    source_ids = {name: byte_identity(data) for name, data in sources.items()}
    executables = {"blender": executable_identity(args.blender),
                   "pillow_python": executable_identity(args.python)}
    jobs = []
    for seed in SEEDS:
        seed_out = out / str(seed)
        model, *specs = evaluation_inputs(seed)
        seal = model.with_suffix(".json")
        expected = read_json(seal)
        assert expected["seed"] == seed and file_identity(model)["sha256"] == expected["snapshot_sha256"]
        overrides = {**THREADS, "PYTHONPYCACHEPREFIX": str(seed_out / "empty-pycache")}
        jobs.append({
            "seed": seed, "out": str(seed_out), "cwd": str(ROOT),
            "argv": worker_command(executables["blender"]["path"],
                                   executables["pillow_python"]["path"], seed, seed_out),
            "env_overrides": overrides, "effective_env": effective_env({**os.environ, **overrides}),
            "worker_inputs": [str(path.resolve()) for path in (model, seal, *specs)],
            "inputs": {str(path.resolve()): file_identity(path) for path in registered_inputs(seed)},
        })
    with ZipFile(out / "sources.zip", "w", compression=ZIP_DEFLATED) as archive:
        for name, data in sources.items():
            archive.writestr(name, data)
    write_json(out / "manifest.json", {
        "scope": "Old CF functional quality replay after integration; serial frozen evaluate stages.",
        "incidental_durations": {"excluded_from_content_comparison": list(INCIDENTAL_DURATION_FIELDS),
                                  "run_complete_wall_ns": "existing process provenance only"},
        "executables": executables,
        "source_files": source_ids, "jobs": jobs,
    })
    results = []
    for job in jobs:
        print(f"CF quality {job['seed']} starting", flush=True)
        try:
            result = run_seed(job, source_ids, executables)
        except (OSError, ValueError, KeyError, TypeError, AssertionError, BadZipFile) as error:
            seed_out = Path(job["out"])
            result = {"seed": job["seed"], "matches": False,
                      "error": f"{type(error).__name__}: {error}",
                      "output_files": tree_identities(seed_out)}
            write_json(seed_out / "comparison.json", result)
            print(f"CF quality {job['seed']} ERROR {error}", flush=True)
        results.append(result)
    passed = all(result["matches"] for result in results)
    write_json(out / "summary.json", {
        "matches": passed, "scope": "quality and evidence replay", "performance_measured": False,
        "seeds": [{"seed": result["seed"], "matches": result["matches"],
                   "report": f"{result['seed']}/comparison.json"} for result in results],
    })
    return 0 if passed else 1


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--worker", choices=("native", "pillow"))
    parser.add_argument("--seed", choices=SEEDS, type=int)
    parser.add_argument("--out", type=Path, default=DESTINATION / "old_cf_quality")
    parser.add_argument("--blender", type=Path, default=BLENDER)
    parser.add_argument("--python", type=Path, default=PYTHON)
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else None
    args = parser.parse_args(argv)
    args.out = args.out.resolve()
    if args.worker == "native":
        native(args)
    elif args.worker == "pillow":
        pillow(args.out)
    else:
        return launch(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
