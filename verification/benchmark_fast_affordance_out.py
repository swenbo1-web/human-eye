"""AO author acceptance: three sequential Blender processes and independent public replay."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
from time import perf_counter_ns

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

WARMUPS = 5
PAIRS = 31
CASES = 20
ACTION_CASES = (19, 20)
ARMS = ("candidate", "baseline")
SUFFIX = {"candidate": "c", "baseline": "b"}
PUBLICATION_ORDER = [
    f"{case:02}-{phase}" for case in range(1, CASES + 1)
    for phase in (("before", "final") if case in ACTION_CASES else ("final",))
]
SOURCES = (
    "docs/AO_ACCEPTANCE_PROTOCOL.md",
    "docs/AO_IMPLEMENTATION.md",
    "human_eye_fast/__init__.py",
    "human_eye_fast/engine.py",
    "human_eye_fast/kernels.py",
    "human_eye_fast/resident_bridge.py",
    "human_eye_fast/blender_resident_bridge.py",
    "human_eye_fast/fast_bvh_clearance.py",
    "human_eye_fast/tensor_deform.py",
    "human_eye_fast/raycast_saccade_gpu.py",
    "human_eye_fast/fast_affordance_out.py",
    "human_eye_fast/control.py",
    "verification/ao_fixtures.py",
    "verification/vg_fixtures.py",
    "verification/test_blender_control.py",
    "verification/test_fast_affordance_out.py",
    "verification/benchmark_fast_affordance_out.py",
)
THREADS = {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
           "BLIS_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1",
           "NUMEXPR_NUM_THREADS": "1", "PYTHONDONTWRITEBYTECODE": "1"}
CHAIN_STAGES = ("rb_ns", "bc_ns", "td_ns", "host_frame_set_ns", "vg_prepare_ns", "vg_observe_ns",
                "action_initial_rb_bc_ns", "action_write_readback_ns")
DELIVERY_STAGES = {"candidate": ("action_delivery_ns", "action_public_select_ns"),
                   "baseline": ("baseline_action_delivery_ns", "baseline_action_public_select_ns")}


def _named(columns, *values):
    return dict(zip(columns, values))


def _baseline_encoder():
    """Bind the same fact projector to descriptive rows before starting timers."""
    from human_eye_fast.fast_affordance_out import _BASELINE, _json_bytes, _project

    def encode_baseline(package):
        return _json_bytes(_project(package, _named, _BASELINE))

    return encode_baseline


def _write(path, record, *, compact=False):
    if compact:
        text = json.dumps(record, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    else:
        text = json.dumps(record, ensure_ascii=False, allow_nan=False, indent=2)
    path.write_bytes(text.encode("utf-8"))


def _load(path):
    return json.loads(path.read_bytes())


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _name(index, arm):
    return f"{index:02}.{SUFFIX[arm]}.json"


def _before_name(index, arm):
    return f"{arm}-before-{index:02}.json"


def _encode_publications(encode, package):
    if package.outcome is None:
        return (encode(package),)
    before = type(package)((package.observations[0],))
    return encode(before), encode(package)


def _encode_batch(encode, packages):
    start = perf_counter_ns()
    result = [_encode_publications(encode, package) for package in packages]
    return perf_counter_ns() - start, result


def _time_final(encode, package):
    start = perf_counter_ns()
    payload = encode(package)
    return perf_counter_ns() - start, payload


def _assert_rb_snapshot(encode):
    """Encode through a borrowed RB view, update in place, then replay saved bytes."""
    import numpy as np

    from human_eye_fast.fast_affordance_out import (
        AffordancePackage, DeformationFact, ObjectFact, ObservationFact, public_schema,
    )
    from human_eye_fast.resident_bridge import ResidentBridge
    from human_eye_fast.tensor_deform import compute_cross_frame_deformation_tensor
    from verification.test_fast_affordance_out import decode_public

    bridge = ResidentBridge()
    reference = np.array([[0., 0., 0.], [3., 0., 0.], [0., 3., 0.]])
    sample = reference + (1., 0., 0.)
    triangles = np.array([[0, 1, 2]], dtype=np.int32)
    mesh = bridge.add("snapshot", sample, triangles, np.eye(4))

    def package(observation_id, frame):
        metrics = compute_cross_frame_deformation_tensor([mesh.world_m], triangles,
                                                         reference_vertices=reference)
        return AffordancePackage([ObservationFact(
            observation_id, frame, [ObjectFact("snapshot", 1)],
            deformation=DeformationFact("snapshot", 7, [frame], metrics,
                                        mesh.triangles, frame, mesh.world_m))])

    old = encode(package("old", 8))
    schema = public_schema()
    parsed_old = decode_public(old, schema)
    bridge.update_full("snapshot", reference + (2., 0., 0.))
    assert mesh.world_m[0, 0] == 2.
    new = encode(package("new", 9))
    assert old != new and parsed_old == decode_public(old, schema)
    return {"old": json.loads(old), "new": json.loads(new)}


def _worker(args):
    import bpy
    import numpy as np

    from human_eye_fast.fast_affordance_out import encode, public_schema
    from verification.ao_fixtures import build_state
    from verification.test_blender_control import run_action_cases

    assert bpy.app.background
    out = args.output_dir
    private = out / "private"
    private.mkdir()
    _write(out / "schema.json", public_schema(), compact=True)
    encode_baseline = _baseline_encoder()
    encoders = {"candidate": encode, "baseline": encode_baseline}
    inputs, references, state_reports = [], [], []
    for state in range(2):
        public = out / f"state-{state}"
        public.mkdir()
        packages, tasks, oracle, costs, environment = build_state(
            state, public, encode_baseline=encode_baseline)
        assert len(packages) == len(tasks) == CASES
        inputs.append(packages)
        reference = {arm: _encode_batch(encoder, packages)[1] for arm, encoder in encoders.items()}
        references.append(reference)
        _write(public / "tasks.json", tasks)
        _write(private / f"state-{state}-oracle.json", oracle)
        for arm, cases in reference.items():
            for index, publications in enumerate(cases, 1):
                assert len(publications) == (2 if index in ACTION_CASES else 1)
                if index in ACTION_CASES:
                    # The fixture persisted the actual publication used to select the action.
                    assert publications[0] == (public / _before_name(index, arm)).read_bytes()
                (public / _name(index, arm)).write_bytes(publications[-1])
        image_paths = {obs.image.path for package in packages for obs in package.observations
                       if obs.image is not None}
        pngs = {path: {"bytes": (public / path).stat().st_size, "sha256": _sha(public / path)}
                for path in sorted(image_paths)}
        state_reports.append({"state": state, "costs_ns": costs, "environment": environment,
                              "png": pngs, "png_bytes": sum(value["bytes"] for value in pngs.values())})

    for old, new in zip(references[0]["candidate"], references[1]["candidate"]):
        assert old != new, "Every task must change across the two measured states"

    warmups, samples = [], []
    for sequence in range(WARMUPS + PAIRS):
        state = sequence % 2
        order = ARMS if (sequence // 2 + args.process_index) % 2 == 0 else ARMS[::-1]
        record = {"sequence": sequence, "state": state, "order": list(order), "elapsed_ns": {},
                  "bytes": {}, "publication_bytes": {}}
        batch_results = {}
        for arm in order:
            elapsed, result = _encode_batch(encoders[arm], inputs[state])
            record["elapsed_ns"][arm] = elapsed
            batch_results[arm] = result
        for arm, result in batch_results.items():
            assert result == references[state][arm], (sequence, state, arm)
            case_lengths = [list(map(len, publications)) for publications in result]
            record["bytes"][arm] = list(map(sum, case_lengths))
            record["publication_bytes"][arm] = [length for case in case_lengths for length in case]
        (warmups if sequence < WARMUPS else samples).append(record)

    # Separately measure one final publication per task, after the paired batch run.
    # Stage sums exclude fixture creation, proof generation, file I/O and scoring.
    for packages, report in zip(inputs, state_reports):
        for package, cost in zip(packages, report["costs_ns"]):
            encode_ns = {arm: _time_final(encoder, package)[0] for arm, encoder in encoders.items()}
            upstream_ns = sum(cost.get(stage, 0) for stage in CHAIN_STAGES)
            cost["publish_encoding_ns"] = encode_ns
            cost["chain_stage_sum_ns"] = {
                arm: upstream_ns + sum(cost.get(stage, 0) for stage in DELIVERY_STAGES[arm]) + encode_ns[arm]
                for arm in ARMS
            }

    _write(out / "worker.json", {
        "pid": os.getpid(), "process_index": args.process_index, "platform": platform.platform(),
        "cpu": platform.processor(), "logical_cpus": os.cpu_count(), "python": sys.version,
        "numpy": np.__version__, "blender": bpy.app.version_string,
        "blender_build_hash": bpy.app.build_hash.decode(), "background": bpy.app.background,
        "thread_environment": {key: os.environ.get(key) for key in THREADS},
        "publication_order": PUBLICATION_ORDER,
        "states": state_reports, "warmups": warmups, "samples": samples,
    })
    _write(private / "rb-snapshot.json", {arm: _assert_rb_snapshot(encoder)
                                           for arm, encoder in encoders.items()})
    if args.process_index == 0:
        actions = run_action_cases()
        assert len(actions) == CASES
        _write(private / "actions.json", actions)


def _score_worker(out):
    from verification.test_fast_affordance_out import decode_public, exercise_negative_controls, score_public

    schema_file = out / "schema.json"
    schema = _load(schema_file)
    record = {"schema_bytes": schema_file.stat().st_size, "states": []}
    for state in range(2):
        public = out / f"state-{state}"
        tasks = _load(public / "tasks.json")
        oracle = _load(out / "private" / f"state-{state}-oracle.json")
        rows = []
        for index, task in enumerate(tasks, 1):
            reports, payloads = {}, {}
            for arm in ARMS:
                payload = (public / _name(index, arm)).read_bytes()
                payloads[arm] = payload
                scoring = score_public(payload, schema, public, task, oracle[index - 1])
                publication_bytes = {"final": len(payload)}
                if index in ACTION_CASES:
                    before_payload = (public / _before_name(index, arm)).read_bytes()
                    before = decode_public(before_payload, schema)
                    final = decode_public(payload, schema)
                    assert before["outcome"] is None and before["object_ids"] == final["object_ids"]
                    assert before["observations"] == final["observations"][:1]
                    publication_bytes = {"before": len(before_payload), **publication_bytes}
                reports[arm] = {"bytes": sum(publication_bytes.values()),
                                "publication_bytes": publication_bytes, "score": scoring}
            candidate, baseline = (reports[arm]["score"] for arm in ARMS)
            row = {"case_id": f"{index:02}", "arms": reports,
                   "candidate_baseline_byte_ratio": reports["candidate"]["bytes"] / reports["baseline"]["bytes"],
                   "same_public_answer": candidate["passed"] and baseline["passed"] and all(
                       candidate[key] == baseline[key] for key in ("answer", "images"))}
            if index in (1, 18):
                row["negative_controls"] = {
                    arm: exercise_negative_controls(payloads[arm], schema, public, task, oracle[index - 1])
                    for arm in ARMS
                }
            rows.append(row)
        lengths = {arm: [row["arms"][arm]["bytes"] for row in rows] for arm in ARMS}
        medians = {arm: statistics.median(lengths[arm]) for arm in ARMS}
        record["states"].append({
            "state": state, "cases": rows, "median_bytes": medians,
            "total_bytes": {arm: sum(lengths[arm]) for arm in ARMS},
            "median_byte_ratio": medians["candidate"] / medians["baseline"],
            "lossless_cases": {arm: sum(row["arms"][arm]["score"]["passed"] for row in rows)
                               for arm in ARMS},
            "equal_answers": sum(row["same_public_answer"] for row in rows),
            "negative_controls_passed": all(
                result["rejected"] for row in rows for controls in row.get("negative_controls", {}).values()
                for result in controls.values()),
        })
    _write(out / "consumption.json", record)
    return record


def _p95(values):
    return statistics.quantiles(values, n=100, method="inclusive")[94]


def _summarize(workers, consumption, actions):
    assert len({worker["pid"] for worker in workers}) == 3
    samples = [sample for worker in workers for sample in worker["samples"]]
    assert len(samples) == 3 * PAIRS
    per_process = []
    for worker, report in zip(workers, consumption, strict=True):
        assert worker["background"] and len(worker["warmups"]) == WARMUPS
        assert worker["publication_order"] == PUBLICATION_ORDER
        measured = worker["samples"]
        assert len(measured) == PAIRS
        assert all(left["state"] != right["state"] for left, right in zip(measured, measured[1:]))
        assert {(item["state"], tuple(item["order"])) for item in measured} == {
            (state, order) for state in (0, 1) for order in (ARMS, ARMS[::-1])
        }
        for sample in worker["warmups"] + measured:
            cases = report["states"][sample["state"]]["cases"]
            for arm in ARMS:
                assert sample["bytes"][arm] == [case["arms"][arm]["bytes"] for case in cases]
                assert sample["publication_bytes"][arm] == [
                    size for case in cases for size in case["arms"][arm]["publication_bytes"].values()
                ]
        per_process.append({
            "pid": worker["pid"],
            "median_ns": {arm: statistics.median(row["elapsed_ns"][arm] for row in measured)
                          for arm in ARMS},
            "p95_ns": {arm: _p95([row["elapsed_ns"][arm] for row in measured]) for arm in ARMS},
        })

    p95 = {arm: _p95([sample["elapsed_ns"][arm] for sample in samples]) for arm in ARMS}
    elapsed_ratio = p95["candidate"] / p95["baseline"]
    states = [state for report in consumption for state in report["states"]]
    gates = {
        "median_bytes": all(state["median_byte_ratio"] <= 0.70 for state in states),
        "p95_encoding": elapsed_ratio <= 1.10,
        "script_consumption": all(state["equal_answers"] == CASES
                                  and all(count == CASES for count in state["lossless_cases"].values())
                                  for state in states),
        "negative_controls": all(state["negative_controls_passed"] for state in states),
        "native_action_matrix": len(actions) == CASES and all(
            row["outcome"]["goal_reached"] and row["terminal_probe_zero_write"] for row in actions),
    }
    return {
        "passed": all(gates.values()), "gates": gates, "paired_sample_count": len(samples),
        "tasks_per_batch": CASES, "publications_per_batch": len(PUBLICATION_ORDER),
        "publication_order": PUBLICATION_ORDER,
        "p95_encoding_batch_ns": p95, "p95_encoding_ratio": elapsed_ratio,
        "median_encoding_batch_ns": {
            arm: statistics.median(item["elapsed_ns"][arm] for item in samples) for arm in ARMS},
        "median_paired_delta_ns": statistics.median(
            sample["elapsed_ns"]["candidate"] - sample["elapsed_ns"]["baseline"] for sample in samples),
        "per_process": per_process,
        "per_process_bytes": [[{key: state[key] for key in (
            "state", "median_bytes", "total_bytes", "median_byte_ratio", "lossless_cases", "equal_answers")}
                               for state in report["states"]] for report in consumption],
        "shared_schema_bytes": consumption[0]["schema_bytes"],
        "png_bytes_by_process_state": [[state["png_bytes"] for state in worker["states"]] for worker in workers],
        "native_action_cases": len(actions),
        "native_action_chain_ns": [row["timing"]["action_chain_ns"] for row in actions],
        "external_model_runs": 0,
    }


def _parent(args):
    args.output_dir.mkdir(parents=True)
    out = args.output_dir
    sources = {}
    for name in SOURCES:
        target = out / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
        sources[name] = _sha(target)
    _write(out / "source-manifest.json", {
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "sha256": sources, "runner_python": sys.version, "runner_platform": platform.platform(),
        "blender_executable": str(args.blender), "thread_environment": THREADS,
        "p95_estimator": "linear interpolation on ordered pooled batches",
    })

    worker_reports, consumption = [], []
    for index in range(3):
        process = out / f"process-{index}"
        process.mkdir()
        command = [str(args.blender), "--background", "--factory-startup", "--disable-autoexec",
                   "--python-exit-code", "1", "--python", str(Path(__file__).resolve()),
                   "--", "--worker", "--process-index", str(index), "--output-dir", str(process)]
        print(f"AO Blender process {index}: {process}", flush=True)
        with (process / "blender.log").open("wb") as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT,
                                    env=os.environ | THREADS, check=False)
        if result.returncode:
            raise RuntimeError(f"Blender returned {result.returncode}; see {process / 'blender.log'}")
        worker_reports.append(_load(process / "worker.json"))
        consumption.append(_score_worker(process))
    assert {name: _sha(ROOT / name) for name in SOURCES} == sources
    actions = _load(out / "process-0" / "private" / "actions.json")
    summary = _summarize(worker_reports, consumption, actions)
    _write(out / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return int(not summary["passed"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", type=lambda value: Path(value).resolve())
    parser.add_argument("--output-dir", type=lambda value: Path(value).resolve(), required=True)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--process-index", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else None)
    if args.worker:
        _worker(args)
        return 0
    if args.blender is None:
        parser.error("--blender is required")
    return _parent(args)


if __name__ == "__main__":
    status = main()
    if status:
        raise SystemExit(status)
