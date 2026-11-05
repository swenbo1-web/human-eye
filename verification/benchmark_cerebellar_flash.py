"""Run CF's frozen stages in serial native and portable workers."""

from argparse import ArgumentParser
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns
from zipfile import ZIP_DEFLATED, ZipFile


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from verification.cf_fixtures import SEEDS, manifest_document


PYTHON = Path(r"D:\human eye\venv\Scripts\python.exe")
BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
THREADS = {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
           "BLIS_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1",
           "PYTHONDONTWRITEBYTECODE": "1"}
SOURCE_ROOTS = ("human_eye_fast",)
SOURCES = (
    "docs/CF_ACCEPTANCE_PROTOCOL.md", "docs/CF_WORK_ORDER.md", "docs/CF_PREFLIGHT_REVIEW.md",
    "docs/radical_acceptance_cf_preflight.json", "verification/benchmark_cerebellar_flash.py",
    "verification/test_cerebellar_flash.py", "verification/test_bc_acceptance.py",
    "verification/test_blender_control.py", "verification/test_fast_affordance_out.py",
    "verification/test_raycast_saccade_gpu.py", "verification/vg_acceptance.py", "verification/vg_fixtures.py",
)
FROZEN = (
    "docs/CF_ACCEPTANCE_PROTOCOL.md", "verification/cf_fixtures.py", "verification/cf_baselines.py",
)


def _json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8", newline="\n")


def _load(path):
    return json.loads(path.read_bytes())


def _identity(data):
    return {"sha256": sha256(data).hexdigest(), "bytes": len(data)}


def _file_identity(path):
    from hashlib import file_digest
    with path.open("rb") as handle:
        digest = file_digest(handle, "sha256").hexdigest()
    return {"sha256": digest, "bytes": path.stat().st_size}


def _contents():
    paths = {ROOT / name for name in SOURCES}
    paths.update((ROOT / "verification").glob("cf_*.py"))
    paths.update((ROOT / "verification").glob("test_cf_*.py"))
    for name in SOURCE_ROOTS:
        paths.update((ROOT / name).glob("*.py"))
    return {path.relative_to(ROOT).as_posix(): path.read_bytes() for path in sorted(paths)}


def _check_frozen(contents):
    acceptance = json.loads(contents["docs/radical_acceptance_cf_preflight.json"])
    expected = {name: acceptance["frozen"][name] for name in FROZEN}
    expected.update(acceptance["dependencies"])
    for name, item in expected.items():
        if _identity(contents[name])["sha256"] != item["sha256"]:
            raise ValueError(f"Frozen protocol or dependency differs: {name}")


def _snapshot(out):
    contents = _contents()
    _check_frozen(contents)
    source_identity = {name: _identity(data) for name, data in contents.items()}
    with ZipFile(out / "source.zip", "w", compression=ZIP_DEFLATED) as archive:
        for name, data in contents.items():
            archive.writestr(name, data)
    _json(out / "source.json", source_identity)
    return source_identity


def _run(out, cmd, inputs=()):
    out.mkdir(parents=True, exist_ok=False)
    sources = _snapshot(out)
    cmd = [os.fspath(value) for value in cmd]
    expected = {str(path.resolve()): _identity(path.read_bytes()) for path in inputs}
    _json(out / "launch.json", {"argv": cmd, "cwd": str(ROOT), "file_whitelist": expected,
                               "threads": THREADS})
    print(f"CF {out.parent.name}/{out.name}", flush=True)
    start = perf_counter_ns()
    environment = {**os.environ, **THREADS}
    with (out / "worker.log").open("wb") as stream:
        result = subprocess.run(cmd, cwd=ROOT, env=environment, stdout=stream,
                                stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    elapsed = perf_counter_ns() - start
    stable_sources = sources == {name: _identity(data) for name, data in _contents().items()}
    stable_inputs = expected == {str(path.resolve()): _identity(path.read_bytes()) for path in inputs}
    artifacts = {path.relative_to(out).as_posix(): _file_identity(path)
                 for path in sorted(out.rglob("*")) if path.is_file()}
    _json(out / "process.json", {"exit_code": result.returncode, "elapsed_ns": elapsed,
                                "sources_stable": stable_sources, "inputs_stable": stable_inputs,
                                "outputs": artifacts})
    if result.returncode or not stable_sources or not stable_inputs:
        raise RuntimeError(f"CF worker failed or source/inputs changed: {out / 'worker.log'}")


def _manifest(folder, seed, split):
    path = folder / f"manifest-{split}.json"
    folder.mkdir(parents=True, exist_ok=True)
    current = manifest_document(seed=seed, split=split)
    if path.exists():
        if json.loads(json.dumps(current)) != _load(path):
            raise ValueError(f"Manifest changed: {path}")
    else:
        _json(path, current)
    return path


def _native(args, folder, seed, stage, split, manifest, *, model=None, feedback=None,
            control=None, diagnostic=None, original_receipt=None, original_records=None):
    cmd = [args.blender, "--background", "--factory-startup", "--disable-autoexec", "--threads", "1",
           "--python-exit-code", "1", "--python", Path(__file__).resolve(), "--", "native",
           "--stage", stage, "--split", split, "--out", folder, "--manifest", manifest,
           "--seed", str(seed), "--python", args.python]
    inputs = [manifest]
    for flag, path in (("model", model), ("feedback", feedback), ("control", control),
                       ("diagnostic", diagnostic), ("original-receipt", original_receipt),
                       ("original-records", original_records)):
        if path is not None:
            cmd.extend((f"--{flag}", path))
            inputs.append(path)
    if model is not None and stage in ("evaluate", "evaluation-completion", "performance"):
        inputs.append(model.with_suffix(".json"))
    _run(folder, cmd, inputs)
    complete = _load(folder / "run-complete.json")
    assert (complete["stage"], complete["seed"], complete["split"]) == (stage, seed, split)
    reads = [json.loads(line) for line in (folder / "reads.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {entry["path"] for entry in reads} == {str(path.resolve()) for path in inputs}


def _train(args, root, seed):
    folder = root / str(seed)
    specs = folder / "specs"
    training = folder / "train"
    validation = folder / "validation-labels"
    selection = folder / "validation-arms"
    train_manifest = _manifest(specs, seed, "train")
    validation_manifest = _manifest(specs, seed, "validation")
    _native(args, training, seed, "collect", "train", train_manifest)
    _native(args, validation, seed, "collect", "validation", validation_manifest)
    train_data = (training / "view.npz", training / "action.npz")
    fit = folder / "fit"
    candidates = fit / "candidates.npz"
    _run(fit, (args.python, "-B", "-m", "verification.cf_training", "fit", *train_data, candidates),
         train_data)
    _native(args, selection, seed, "validate", "validation", validation_manifest, model=candidates)
    seal = folder / "seal"
    frozen = seal / "frozen.npz"
    select_data = (selection / "views.json", validation / "action.npz")
    provenance = training / "provenance.json"
    _run(seal, (args.python, "-B", "-m", "verification.cf_training", "seal", str(seed),
                candidates, *select_data, *train_data, frozen, "--provenance", provenance),
         (candidates, candidates.with_suffix(".json"), *select_data, *train_data, provenance))
    _sealed(root, seed)


def _sealed(root, seed):
    snapshot = root / str(seed) / "seal" / "frozen.npz"
    receipt = _load(snapshot.with_suffix(".json"))
    assert receipt["seed"] == seed
    assert _identity(snapshot.read_bytes())["sha256"] == receipt["snapshot_sha256"]
    assert all(f"-{seed}-train-" in value for rows in receipt["train_bank_rows"].values()
               for value in rows)
    return snapshot


def _evaluate(args, root, seed, *, complete_control_transport=False):
    snapshot = _sealed(root, seed)
    folder = root / str(seed)
    specs = folder / "specs"
    manifest = _manifest(specs, seed, "evaluation")
    control = _manifest(specs, seed, "control")
    diagnostic = _manifest(specs, seed, "diagnostic")
    previous = folder / "evaluation"
    if complete_control_transport and previous.exists():
        if (previous / "run-complete.json").exists():
            return
        log = (previous / "worker.log").read_text(encoding="utf-8")
        if "Object of type bool is not JSON serializable" not in log or "_control_view" not in log:
            raise ValueError("The only recoverable stage is the recorded zero-gap control transport error")
        _native(args, folder / "evaluation-completion", seed, "evaluation-completion", "evaluation",
                manifest, model=snapshot, control=control, diagnostic=diagnostic,
                original_receipt=previous / "process.json", original_records=previous / "records.jsonl.gz")
    else:
        _native(args, previous, seed, "evaluate", "evaluation", manifest, model=snapshot,
                control=control, diagnostic=diagnostic)


def _performance(args, root, seed):
    snapshot = _sealed(root, seed)
    folder = root / str(seed)
    feedback = folder / "evaluation" / "summary.json"
    if not feedback.is_file():
        feedback = folder / "evaluation-completion" / "summary.json"
    manifest = _manifest(folder / "specs", seed, "evaluation")
    _native(args, folder / "performance", seed, "performance", "evaluation", manifest,
            model=snapshot, feedback=feedback)


def _memory(args, root, seed):
    snapshot = _sealed(root, seed)
    out = root / str(seed) / "memory"
    _run(out, (args.python, "-B", "-m", "verification.cf_memory", snapshot, out / "memory.json"),
         (snapshot, snapshot.with_suffix(".json")))


def _native_main(argv):
    parser = ArgumentParser()
    parser.add_argument("--stage", choices=("smoke", "collect", "validate", "evaluate",
                                            "evaluation-completion", "performance"),
                        required=True)
    parser.add_argument("--split", required=True)
    parser.add_argument("--seed", type=int, required=True)
    for name in ("out", "manifest", "python", "model", "feedback", "control", "diagnostic",
                 "original-receipt", "original-records"):
        parser.add_argument(f"--{name}", type=Path)
    from verification.cf_experiment import run
    run(parser.parse_args(argv))


def main(argv):
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("all", "smoke", "train", "evaluation",
                                            "complete-evaluation", "performance", "memory", "report"),
                        default="all")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--python", type=Path, default=PYTHON)
    parser.add_argument("--blender", type=Path, default=BLENDER)
    args = parser.parse_args(argv)
    root = args.out.resolve()
    if not root.is_relative_to(ROOT / "artifacts" / "cf") or root.name == "preflight_001":
        raise ValueError("Use a dedicated CF formal artifact directory")
    root.mkdir(parents=True, exist_ok=True)
    if args.phase == "smoke":
        seed = SEEDS[0]
        manifest = _manifest(root / "smoke-specs", seed, "train")
        _native(args, root / "smoke", seed, "smoke", "train", manifest)
        return
    if args.phase in ("train", "all"):
        for seed in SEEDS:
            _train(args, root, seed)
    if args.phase in ("evaluation", "complete-evaluation", "performance", "memory", "all"):
        for seed in SEEDS:
            _sealed(root, seed)
    if args.phase in ("evaluation", "complete-evaluation", "all"):
        for seed in SEEDS:
            _evaluate(args, root, seed, complete_control_transport=(args.phase == "complete-evaluation"))
    if args.phase in ("performance", "all"):
        for seed in SEEDS:
            _performance(args, root, seed)
    if args.phase in ("memory", "all"):
        for seed in SEEDS:
            _memory(args, root, seed)
    if args.phase in ("report", "all"):
        from verification.cf_report import summarize
        _json(root / "summary.json", summarize(root))


if __name__ == "__main__":
    if "--" in sys.argv and sys.argv[sys.argv.index("--") + 1] == "native":
        _native_main(sys.argv[sys.argv.index("--") + 2:])
    else:
        main(sys.argv[1:])
