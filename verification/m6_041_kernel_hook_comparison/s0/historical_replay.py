"""M6-041 S0 historical replay with exact immutable source/installation pins."""
from __future__ import annotations

import argparse
from fractions import Fraction as Q
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
OLD31 = Path("C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_bvh_work_credit_031")
OLD40 = Path("D:/HumanEye/runs/M3-BVH-DEEP-COMPARE-040")
PIN_DIGEST = "1fc144feb80a051252c47f24d1ff96d10d5e504c28d9669eae489ff254998b93"
SOURCE_DIGEST = {
    "032": "0f9e6336ec54adf9e7b9a5379b02d2c2cab9f6d1f734138c3fde29e08ccee241",
    "r3": "eff6511223646c125ac05cd6080d3bcbe191d1c945a8b3b7293d2c1bc0ff1ee4",
}
CASES = ("zero489", "first_yield", "pair129")


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def canonical(doc):
    return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()


def read(path):
    return json.loads(Path(path).read_bytes())


def save(path, doc):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(doc, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    sys.modules[name] = obj
    spec.loader.exec_module(obj)
    return obj


def verify_history():
    orig = ROOT / "history_031/verification"
    hist_code = [orig / "m6_bvh_work_credit_031/test_controls.py",
                 orig / "m6_bvh_projection_yield_030/test_controls.py",
                 orig / "m6_bvh_witness_projection_029/oracle.py"]
    gate = read(OLD31 / "private/controls/GATE.json")
    assert digest(hist_code[0]) == gate["source"]["sha256"]
    assert digest(hist_code[1]) == "94d2fe425441f8c9ce6d1b03353dcb5fe03c954cadfd0d6dbf76e6e27935ab0a"
    assert digest(hist_code[2]) == gate["old_fraction_oracle"]["sha256"]
    old_manifest = {row["path"]: row for row in read(OLD31 / "private/RAW_EVIDENCE.json")["files"]}

    def verify(rel):
        row = old_manifest[rel]
        path = OLD31 / rel
        assert path.stat().st_size == row["bytes"] and digest(path) == row["sha256"]
        return read(path), row

    input_paths = {label: f"private/controls/attempt_002_AF/{label}_INPUT_PROOF.json"
                   for label in CASES[:2]}
    old_proofs = {key: verify(value) for key, value in input_paths.items()}
    old_runs = {key: verify(f"private/controls/attempt_003_Gmain/{key}_G.json") for key in CASES}
    artifact_paths = {row["path"]: row for row in read(OLD40 / "EVIDENCE.json")}
    for name in ("semantic_controls.py", "semantic_controls.json"):
        ref = artifact_paths[name]
        assert (OLD40 / name).stat().st_size == ref["bytes"] and digest(OLD40 / name) == ref["sha256"]
    return (module("_s0_historical_031", hist_code[0]), module("_s0_historical_040", OLD40 / "semantic_controls.py"),
            old_proofs, old_runs, read(OLD40 / "semantic_controls.json"))


def selected_runtime(arm, installed):
    if installed:
        pins_path = ROOT.parent / "install/PINS.json"
        assert digest(pins_path) == PIN_DIGEST
        pin = read(pins_path)["arms"][arm]
        source = Path(pin["site"]).resolve()
        expected = pin["identity"]["source_sha256"]
        assert digest(pin["binding"]["path"]) == pin["binding"]["sha256"]
    else:
        source = ROOT / ("source_032" if arm == "032" else "source_R3")
        expected = SOURCE_DIGEST[arm]
        pin = None
    sys.path.insert(0, str(source))
    from human_eye_plugin import surface_proximity as kernel, surface_geometry as geometry
    from human_eye_plugin.runtime_identity import runtime_identity

    identity = runtime_identity()
    assert identity["source_sha256"] == expected and len(identity["source_files"]) == 143
    if installed:
        assert identity["distribution_version"] == pin["identity"]["distribution_version"]
        assert identity["source_files"] == pin["source_manifest"]
    for row in identity["source_files"]:
        assert digest(source / row["path"]) == row["sha256"]
    for item in (kernel, geometry):
        assert Path(item.__file__).resolve().is_relative_to(source)
    constants = {
        "MAX_FACES": kernel.MAX_FACES,
        "MAX_WORK_UNITS": kernel.MAX_WORK_UNITS,
        "MAX_NARROW_PHASE_PAIRS": kernel.MAX_NARROW_PHASE_PAIRS,
        "LINEAR_PAIR_LIMIT": kernel.LINEAR_PAIR_LIMIT,
        "CLOSED_SOLID_MAX_WORK": geometry.CLOSED_SOLID_MAX_WORK,
    }
    assert tuple(constants.values()) == (4096, 1179648, 16384, 256, 262144)
    return kernel, geometry, identity, constants


def credit_summary(work):
    keys = ("witness_projection_credit_node_units", "witness_projection_credit_narrow_units",
            "witness_projection_credit_node_prune_units", "witness_projection_credit_spent_units")
    amounts = [work.get(key, 0) for key in keys]
    balance = sum(amounts[:3]) - amounts[3]
    assert balance >= 0
    return dict(zip(keys, amounts, strict=True), reconstructed_balance=balance,
                policy=work.get("witness_projection_mode"),
                reference=work.get("witness_projection_credit_reference"))


def measure(kernel, meshes, *, policy=None, prepaid=0):
    holder = {}
    stages = {}
    implementation = kernel._Work

    def trace(stage):
        stages[stage] = stages.get(stage, 0) + 1

    class Prepaid(implementation):
        def __init__(self, checkpoint, diagnostics):
            super().__init__(checkpoint, diagnostics)
            self.consume(prepaid, "equivalent_prepaid_prior_work")

    kwargs = {"_projection_mode": policy} if policy else {}
    if prepaid:
        kernel._Work = Prepaid
    try:
        value = kernel.measure_surface_proximity(*meshes, trace, retain_exact_rank=True,
                                                 retain_witness_triangles=True, _prepared_holder=holder, **kwargs)
    finally:
        kernel._Work = implementation
    work = value["work"]
    assert work["work_units"] <= 1_179_648 and work["narrow_phase_pairs"] <= 16_384
    if "witness_points" in holder:
        origin, factor = holder["pair"][2:4]
        points = [[str(origin[k] + Q(p[k], factor)) for k in range(3)] for p in holder["witness_points"]]
    else:
        points = None
    return {"result": value, "exact_points_world": points, "prepaid": prepaid,
            "checkpoint_histogram": stages, "credit": credit_summary(work)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("arm", choices=("032", "r3"))
    parser.add_argument("--installed", action="store_true")
    parser.add_argument("--credit-boundaries", action="store_true")
    args = parser.parse_args()
    arm = args.arm
    suffix = f"{'installed' if args.installed else 'source'}_{arm}"
    kernel, geometry, identity, constants = selected_runtime(arm, args.installed)
    old31, old40, old_proofs, old_runs, old_witness = verify_history()
    dir_out = ROOT / ("historical_" + suffix)
    dir_out.mkdir(exist_ok=False)
    save(dir_out / "identity.json", {"identity": identity, "constants": constants, "provenance": "fixed source" if not args.installed else "fixed isolated installed site-packages"})
    for label in CASES:
        meshes = old31.problem(label)
        shape = [mesh.to_dict() for mesh in meshes]
        actual_sha = hashlib.sha256(canonical(shape)).hexdigest()
        archives = {"prior_031_runtime": old_runs[label][1]}
        if label in old_proofs:
            proof, ref = old_proofs[label]
            assert actual_sha == proof["geometry_sha256"]
            archives["frozen_input_proof"] = ref
        save(dir_out / (label + "_geometry.json"), shape)
        row = {"case": label, "input_sha256": actual_sha, "face_counts": [len(m.faces) for m in meshes], "archives": archives}
        row["default"] = measure(kernel, meshes)
        if arm == "r3" and not args.installed:
            row["off_paid_dequeue_ref"] = measure(kernel, meshes, policy="off_paid_dequeue_ref")
            row["off"] = measure(kernel, meshes, policy="off")
        valid = row["default"]["result"]
        truth = [0, 1 if label == "first_yield" else 0]
        row["expected_exact_square"] = "3"
        row["expected_exact_source_pair"] = truth
        if valid["measurement_valid"]:
            n, d, expo = valid["_exact_distance_sq"]
            row["exact_truth_agrees"] = Q(n, d) * Q(2) ** expo == Q(3) and valid["witness_triangle_indices"] == truth
        else:
            row["exact_truth_agrees"] = None
        save(dir_out / (label + ".json"), row)
        print(json.dumps({"case": label, "source": suffix, "modes": {
            mode: (record["result"]["measurement_valid"], record["result"].get("reason"),
                   record["result"]["work"]["work_units"], record["result"]["work"]["narrow_phase_pairs"])
            for mode, record in row.items() if isinstance(record, dict) and "result" in record}}), flush=True)
    old_closed = old40.closed_test(geometry)
    prior032 = old_witness["arms"]["032"]["result"]["closed"]["result"]
    current = old_closed["result"]
    save(dir_out / "crossed-box-040.json", {"same_original_fixture_function": True, "new": old_closed,
         "prior032_source_triangles": prior032["local_evidence"]["triangle_indices"],
         "exact_source_witness_equal": current["local_evidence"] == prior032["local_evidence"]})
    if args.credit_boundaries:
        meshes = old31.problem("zero489")
        for offset in (39, 40, 41, 42, 43):
            row = {"default": measure(kernel, meshes, prepaid=offset)}
            if arm == "r3":
                row["paid_reference"] = measure(kernel, meshes, policy="off_paid_dequeue_ref", prepaid=offset)
            save(dir_out / f"zero489_prepaid_{offset}.json", row)
    print(json.dumps({"done": suffix, "crossed": current["local_evidence"]["triangle_indices"]}), flush=True)


if __name__ == "__main__":
    main()
