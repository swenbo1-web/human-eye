"""Replay frozen 003 lattice programs against the actual 004 current packet."""

import argparse
import ast
from contextlib import redirect_stderr, redirect_stdout
import ctypes
from ctypes import wintypes
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, write
import numpy as np

OLD = HERE.parent / "m6_matched_refine_003"
PRIVATE = HERE / "private/diagnostics"
BASELINE = "c58e464d454c83b90b3c9baa026478c590e578e6"
CONTRACT = "f974cf88ecdb0ccc3677aa204d7bba02521841ec"
NOISE_SHA = "cd8e84d38618d3de642a7023ea02d3244a61d3353a94582747130fd12118e5fb"
SEED = 2026111604
HALF_WIDTH_M = 1 / 8192
BUDGET_M = 0.006893660855829761
PROGRAMS = {
    "v1_native": dict(stage="v1", route="native", tool="08", prefix_lines=4,
        ids_variable="active", sha256="4f78b35a0fc33c6a41b48b0c7de862afbe89807a5d3a47d172eadbe859017f07"),
    "v1_facts": dict(stage="v1", route="facts", tool="07", prefix_lines=5,
        ids_variable="active", sha256="9fe005a7c7275dfbce9e164be0572c1360ebf7e4167599ee2845cf469a41033f"),
    "v2_facts": dict(stage="v2", route="facts", tool="07", prefix_lines=4,
        ids_variable="ids", sha256="a39e30f039c3d2ed119bc55c36f33c5a55b28ba0cf4021bc689ed94a8ea353a4"),
    "v2_native": dict(stage="v2", route="native", tool="05", prefix_lines=4,
        ids_variable="active", sha256="76d880cb251b8e0779de17a0e7b6c04320b8c8d5a449dadcd754e298073a286b"),
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def relative(path):
    return Path(path).resolve().relative_to(HERE).as_posix()


def resource_snapshot():
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize",
                "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return dict(process_CPU_s=time.process_time(), peak_working_set_bytes=counters.PeakWorkingSetSize,
        working_set_bytes=counters.WorkingSetSize, peak_pagefile_bytes=counters.PeakPagefileUsage)


def git_bytes(commit, path):
    result = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=HERE.parents[1],
        capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf8", errors="replace"))
    return result.stdout


def load_packet(path):
    with np.load(path, allow_pickle=False) as packet:
        return {key: packet[key] for key in packet.files}


def batch_path(row):
    path = Path(row["path"])
    return path if path.is_absolute() else HERE / path


def archive_bytes(name, raw):
    target = PRIVATE / "frozen" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.read_bytes() != raw:
        raise ValueError(f"frozen_archive_changed:{name}")
    target.write_bytes(raw)
    return identity(target)


def prepare():
    started, cpu = time.perf_counter(), time.process_time()
    manifest_raw = git_bytes(BASELINE, "verification/m6_matched_refine_003/MANIFEST.json")
    manifest = {row["path"]: row for row in json.loads(manifest_raw)["files"]}
    provenance = dict(baseline_commit=BASELINE, contract_commit=CONTRACT,
        manifest=archive_bytes("003_MANIFEST.json", manifest_raw), programs={})
    for name, spec in PROGRAMS.items():
        folder = Path("private/consumers") / spec["stage"] / "matched" / spec["route"] / "bridge" / ("tool_" + spec["tool"]) / "python"
        code_path = folder / "CODE.py"
        raw = (OLD / code_path).read_bytes()
        expected = manifest[code_path.as_posix()]
        assert sha(raw) == expected["sha256"] == spec["sha256"]
        assert len(raw) == expected["bytes"]
        request_path = folder / "REQUEST.json"
        request_raw = (OLD / request_path).read_bytes()
        assert sha(request_raw) == manifest[request_path.as_posix()]["sha256"]
        request = json.loads(request_raw)
        assert request["code"].encode("utf8") == raw
        fragment = b"".join(raw.splitlines(keepends=True)[:spec["prefix_lines"]])
        ast.parse(fragment.decode("utf8"))
        provenance["programs"][name] = dict(source_path=code_path.as_posix(),
            code=archive_bytes(name + "_CODE.py", raw),
            request=archive_bytes(name + "_REQUEST.json", request_raw),
            detector=archive_bytes(name + "_detector.py", fragment),
            prefix_lines=spec["prefix_lines"], ids_variable=spec["ids_variable"],
            request_budget=request["task"]["edit_budget"])
    for name in ("review.py", "PEER_REVIEWS.json"):
        raw = git_bytes(CONTRACT, "verification/m6_matched_refine_003_review/" + name)
        provenance[name] = archive_bytes("003_review_" + name, raw)
    for name in ("preflight.py", "PREFLIGHT.json"):
        raw = git_bytes(CONTRACT, "verification/m6_degrid_004_plan/" + name)
        provenance[name] = archive_bytes("004_plan_" + name, raw)
    payload_stem = "private/sessions/v1_matched_native/payloads/p500318f92dc449cc8b9ef6b63208aeb4"
    for extension in ("json", "npz"):
        old_path = payload_stem + "." + extension
        raw = (OLD / old_path).read_bytes()
        assert sha(raw) == manifest[old_path]["sha256"]
        provenance["v1_native_payload_" + extension] = archive_bytes("v1_native_payload." + extension, raw)
    report = git_bytes(BASELINE, "verification/m6_matched_refine_003/REPORT.md")
    assert (OLD / "REPORT.md").read_bytes() == report
    provenance["old_report"] = archive_bytes("003_REPORT.md", report)
    old_binding = json.loads((OLD / "CASE_BINDING.json").read_bytes())
    planning = json.loads((HERE / "PLANNING_PREFLIGHT.json").read_bytes())
    arrays = []
    for row in planning["source_files"]:
        path = Path(row["path"])
        assert identity(path)["sha256"] == row["sha256"]
        arrays.append(np.load(path, allow_pickle=False))
    clean, damaged, faces = arrays
    old_initial = load_packet(OLD / old_binding["public_initial"]["path"])
    F = old_initial["F_source_ids"]
    I = old_initial["I_ids"]
    assert (len(F), len(I)) == (410, 274)
    noise = np.zeros_like(clean)
    noise[F] = np.random.default_rng(SEED).uniform(-HALF_WIDTH_M, HALF_WIDTH_M, size=(len(F), 3))
    assert sha(noise.tobytes()) == NOISE_SHA == planning["noise_array_sha256"]
    assert planning["seed"] == SEED
    support = np.flatnonzero(np.linalg.norm(damaged - clean, axis=1) > 0)
    assert len(support) == 47
    outside_F = np.setdiff1d(np.arange(len(clean)), F)
    assert np.count_nonzero(noise[outside_F]) == 0
    assert np.max(np.abs(((damaged + noise) - (clean + noise)) - (damaged - clean))) < 1e-15
    noise_result = dict(seed=SEED, rule="numpy.default_rng(seed).uniform(-1/8192,+1/8192,size=(410,3)); assignment to zeros_like(clean)[F_source_ids] in original F order",
        numpy_version=np.__version__, clean_dtype=str(clean.dtype), noise_dtype=str(noise.dtype),
        original_F_ids_array_sha256=sha(F.tobytes()), noise_array_sha256=sha(noise.tobytes()),
        expected_noise_array_sha256=NOISE_SHA, source_files=planning["source_files"],
        outside_F_nonzero_coordinates=int(np.count_nonzero(noise[outside_F])),
        maximum_damage_vector_change_m=float(np.max(np.abs(((damaged + noise) - (clean + noise)) - (damaged - clean)))),
        noise_RMS_m=float(np.sqrt(np.mean(np.sum(noise[F] ** 2, axis=1)))),
        noise_maximum_m=float(np.linalg.norm(noise[F], axis=1).max()), verified=True)
    provenance["noise_precheck"] = noise_result
    provenance["cost"] = dict(wall_s=time.perf_counter() - started, cpu_s=time.process_time() - cpu,
        process=resource_snapshot())
    provenance["preparatory_observed_failures"] = [
        dict(action="initial read-only skill lookup", exit_code=1, shell_wall_s=0.1860659,
            reason="mistyped nonexistent skills/.system/../x path; corrected by reading learning-worker/SKILL.md"),
        dict(action="old review/planning path lookup in implementation checkout", shell_exit_code=0,
            shell_wall_s=0.1892687, reason="rg reported absent review, _m6ref3 and plan directories; located fixed files through git show"),
        dict(action="old raw directory lookup", shell_exit_code=0, shell_wall_s=0.2266129,
            reason="rg reported absent private/raw path; actual CODE located under private/consumers"),
        dict(action="session_context without context handle", result="context_bound=false/rebind_required=true",
            corrected="session_context with fixed context_handle bound the assignment; no task mutation")]
    write(relative(PRIVATE / "PREPARATION.json"), provenance)
    erratum = f"""# M6-MATCHED-REFINE-003 勘误

固定作者提交 `{BASELINE}` 的 `verification/m6_matched_refine_003/REPORT.md` 中，消费者方法表将V1 native写为“提交positions”。实际最终程序调用 `save_edit(active, displacements, mode='displacements_world')`，载荷元数据也记录 `displacements_world`。本勘误保存在004新增目录。

- 固定旧报告SHA256为 `{sha(report)}`。
- 旧最终程序路径为 `private/consumers/v1/matched/native/bridge/tool_08/python/CODE.py`，SHA256为 `{PROGRAMS['v1_native']['sha256']}`。
- 旧载荷路径为 `{payload_stem}.npz`，SHA256为 `{provenance['v1_native_payload_npz']['sha256']}`。
- 旧载荷元数据路径为 `{payload_stem}.json`，SHA256为 `{provenance['v1_native_payload_json']['sha256']}`。

CODE和载荷的字节身份逐项匹配固定c58提交的003 MANIFEST，私有副本位于 `private/diagnostics/frozen/`。规划复核提交 `{CONTRACT}` 的 `verification/m6_matched_refine_003_review/PEER_REVIEWS.json` 同时记录了这一勘误，003原报告和证据保持固定字节。
"""
    (HERE / "PREVIOUS_ERRATUM.md").write_text(erratum, encoding="utf8", newline="\n")
    return provenance


def execute_frozen(name, raw, V, I, F, budget, *, detector=False):
    started, cpu = time.perf_counter(), time.process_time()
    stdout, stderr = io.StringIO(), io.StringIO()
    captured = []

    def save_edit(ids, values, mode):
        captured.append(dict(ids=np.array(ids, dtype=np.int64, copy=True),
            values=np.array(values, dtype=np.float64, copy=True), mode=str(mode)))
        return dict(captured_in_memory=True, points=len(ids), mode=mode)

    scope = dict(np=np, V=V.copy(), I_ids=I.copy(), F_ids=F.copy(),
        task=dict(edit_budget=dict(max_operation_displacement_m=budget,
            max_cumulative_displacement_m=budget)), save_edit=save_edit)
    error = None
    with redirect_stdout(stdout), redirect_stderr(stderr):
        try:
            exec(compile(raw, name, "exec"), scope, scope)
        except Exception as exc:
            error = dict(type=type(exc).__name__, message=str(exc), traceback=traceback.format_exc())
    record = dict(name=name, code_sha256=sha(raw), error=error,
        status="program_returned" if error is None else "program_failed", save_edit_calls=len(captured),
        stdout=stdout.getvalue(), stderr=stderr.getvalue(),
        wall_s=time.perf_counter() - started, cpu_s=time.process_time() - cpu,
        process=resource_snapshot(), runtime_inputs=["V", "I_ids", "F_ids", "task.edit_budget", "np", "save_edit_capture"],
        PNG_read=False, facts_read=False, score_target_loaded_during_exec=False,
        blender_calls=0, pro_calls=0, saved_file_created=False)
    if detector:
        ids = np.array(scope[PROGRAMS[name]["ids_variable"]], dtype=np.int64)
        return record, ids
    candidate = None
    if name == "v1_native" and "displacements" in scope:
        candidate = dict(ids=np.array(scope["active"], dtype=np.int64, copy=True),
            values=np.array(scope["displacements"], copy=True), mode="displacements_world")
    return record, captured, candidate


def summarize_vectors(vectors):
    lengths = np.linalg.norm(vectors, axis=1)
    return dict(points=len(lengths), RMSE_m=float(np.sqrt(np.mean(lengths ** 2))),
        p95_m=float(np.quantile(lengths, .95)), maximum_m=float(lengths.max()))


def score_capture(capture, initial, target, groups, budget):
    ids, values, mode = capture["ids"], capture["values"], capture["mode"]
    assert values.shape == (len(ids), 3) and np.isfinite(values).all()
    assert len(np.unique(ids)) == len(ids) and np.isin(ids, target["I_ids"]).all()
    updated = initial.copy()
    if mode == "positions_world":
        updated[ids] = values
    elif mode == "displacements_world":
        updated[ids] += values
    else:
        raise ValueError("unrecognized_captured_mode")
    displacement = updated - initial
    result = dict(mode=mode, captured_points=len(ids), groups={},
        changed_points_above_1e_12_m=int(np.count_nonzero(np.linalg.norm(displacement, axis=1) > 1e-12)),
        maximum_displacement_m=float(np.linalg.norm(displacement, axis=1).max()),
        outside_I_displacement=summarize_vectors(displacement[groups["outside_editable"]]))
    result["operation_budget_satisfied"] = result["maximum_displacement_m"] <= budget
    clean = target["clean_vertices_world"]
    for name in ("support_47", "observation_410", "normal_editable_227", "normal_363"):
        chosen = groups[name]
        before = summarize_vectors((initial - clean)[chosen])
        after = summarize_vectors((updated - clean)[chosen])
        result["groups"][name] = dict(before=before, after=after,
            displacement=summarize_vectors(displacement[chosen]),
            RMSE_reduction_fraction=(before["RMSE_m"] - after["RMSE_m"]) / before["RMSE_m"] if before["RMSE_m"] else None)
    result["quality_checks"] = dict(
        support_RMSE_decreases_at_least_30_percent=result["groups"]["support_47"]["RMSE_reduction_fraction"] >= .3,
        observation_RMSE_decreases=result["groups"]["observation_410"]["after"]["RMSE_m"] < result["groups"]["observation_410"]["before"]["RMSE_m"],
        normal_editable_displacement_RMS_at_most_0_10_mm=result["groups"]["normal_editable_227"]["displacement"]["RMSE_m"] <= .0001)
    return result, updated, displacement


def run_diagnostics():
    started, cpu = time.perf_counter(), time.process_time()
    preparation = json.loads((PRIVATE / "PREPARATION.json").read_bytes())
    binding = json.loads((HERE / "CASE_BINDING.json").read_bytes())
    input_path = batch_path(binding["public_initial"])
    assert identity(input_path)["sha256"] == binding["public_initial"]["sha256"]
    current = load_packet(input_path)
    V, I, F = (current[key] for key in ("vertices_world", "I_ids", "F_source_ids"))
    budget = binding["budget_m"]
    assert budget == BUDGET_M and (len(F), len(I)) == (410, 274)
    detector_runs, detections, inverse_runs, captures, candidates = {}, {}, {}, {}, {}
    for name, spec in PROGRAMS.items():
        row = preparation["programs"][name]
        raw = batch_path(row["detector"]).read_bytes()
        assert sha(raw) == row["detector"]["sha256"]
        record, ids = execute_frozen(name, raw, V, I, F, budget, detector=True)
        detector_runs[name], detections[name] = record, ids
    for name in ("v1_native", "v2_facts"):
        row = preparation["programs"][name]
        raw = batch_path(row["code"]).read_bytes()
        assert sha(raw) == row["code"]["sha256"] == PROGRAMS[name]["sha256"]
        record, captured, candidate = execute_frozen(name, raw, V, I, F, budget)
        inverse_runs[name], captures[name] = record, captured
        candidates[name] = candidate
    unscored_path = PRIVATE / "UNSCORED_EXECUTION.json"
    write(relative(unscored_path), dict(detector_runs=detector_runs, inverse_runs=inverse_runs,
        all_frozen_programs_finished_before_target_read=True))
    target_path = batch_path(binding["private_score_target"])
    assert identity(target_path)["sha256"] == binding["private_score_target"]["sha256"]
    target = load_packet(target_path)
    np.testing.assert_array_equal(target["initial_vertices_world"], V)
    for key in ("I_ids", "F_source_ids", "source_ids"):
        np.testing.assert_array_equal(target[key], current[key])
    support = target["support_ids"]
    assert len(support) == 47
    groups = dict(support_47=support, observation_410=F,
        normal_editable_227=np.setdiff1d(I, support), normal_363=np.setdiff1d(F, support),
        outside_editable=np.setdiff1d(current["source_ids"], I))
    detector_scores = {}
    for name, ids in detections.items():
        TP = np.intersect1d(ids, support)
        FP = np.setdiff1d(ids, support)
        FN = np.setdiff1d(support, ids)
        detector_scores[name] = dict(selected=len(ids), candidate_points=274, support_points=47,
            TP=len(TP), FP=len(FP), FN=len(FN), TN=227 - len(FP),
            precision=len(TP) / len(ids) if len(ids) else None, recall=len(TP) / 47,
            selected_ids=ids.tolist(), false_negative_ids=FN.tolist(),
            source_code=preparation["programs"][name]["code"],
            detector_fragment=preparation["programs"][name]["detector"])
    inverse_scores = {}
    for name in inverse_runs:
        row = dict(execution=inverse_runs[name], captured_submissions=[])
        for index, capture in enumerate(captures[name]):
            scored, updated, displacement = score_capture(capture, V, target, groups, budget)
            artifact = PRIVATE / (name + f"_captured_{index}.npz")
            np.savez_compressed(artifact, source_ids=current["source_ids"], vertices_world=updated,
                displacement_world=displacement, captured_ids=capture["ids"], captured_values=capture["values"])
            scored["point_evidence"] = identity(artifact)
            row["captured_submissions"].append(scored)
        if not captures[name] and candidates[name] is not None:
            scored, updated, displacement = score_capture(candidates[name], V, target, groups, budget)
            artifact = PRIVATE / (name + "_unsubmitted_candidate.npz")
            np.savez_compressed(artifact, source_ids=current["source_ids"], vertices_world=updated,
                displacement_world=displacement, candidate_ids=candidates[name]["ids"], candidate_values=candidates[name]["values"])
            scored["point_evidence"] = identity(artifact)
            scored["status"] = "intermediate_arrays_before_failed_assertion; save_edit_not_reached"
            row["unsubmitted_candidate"] = scored
        inverse_scores[name] = row
    result = dict(cycle_id="M6-DEGRID-004", diagnostic="frozen_003_lattice_transfer",
        status="completed", baseline_commit=BASELINE, contract_commit=CONTRACT,
        inputs=dict(case_binding=identity(HERE / "CASE_BINDING.json"), public_initial=identity(input_path),
            scoring_target=identity(target_path), unscored_execution=identity(unscored_path)),
        preparation=identity(PRIVATE / "PREPARATION.json"), noise_precheck=preparation["noise_precheck"],
        detectors=detector_scores, detector_executions=detector_runs, old_inverse=inverse_scores,
        baseline={name: summarize_vectors((V - target["clean_vertices_world"])[ids])
            for name, ids in groups.items() if name != "outside_editable"},
        isolation=dict(programs_finished_before_scoring_target_read=True, runtime_PNG_read=False,
            runtime_facts_read=False, runtime_clean_geometry_read=False, save_edit="in-memory array capture",
            frozen_program_bytes_unchanged=True, parameters_changed=False, generated_seed_candidates=1),
        interpretation="Frozen old-program transfer diagnosis on current saved-file readback. In-memory output quality and budget checks are separate from actual saved-file consumer scoring.",
        cost=dict(wall_s=time.perf_counter() - started, cpu_s=time.process_time() - cpu,
            process=resource_snapshot(), preparation=preparation["cost"],
            diagnostic_execution_wall_s=sum(row["wall_s"] for row in detector_runs.values()) + sum(row["wall_s"] for row in inverse_runs.values()),
            diagnostic_execution_cpu_s=sum(row["cpu_s"] for row in detector_runs.values()) + sum(row["cpu_s"] for row in inverse_runs.values()),
            preparatory_observed_failures=preparation["preparatory_observed_failures"],
            pro_calls=0, blender_calls=0, external_model_usage=0,
            coordination_model_usage="unmeasured by script", fees="unmeasured"))
    write("DIAGNOSTICS.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("prepare", "run"), required=True)
    args = parser.parse_args()
    PRIVATE.mkdir(parents=True, exist_ok=True)
    started, cpu = time.perf_counter(), time.process_time()
    try:
        result = prepare() if args.stage == "prepare" else run_diagnostics()
    except Exception:
        failure = dict(stage=args.stage, status="failed", traceback=traceback.format_exc(),
            wall_s=time.perf_counter() - started, cpu_s=time.process_time() - cpu,
            process=resource_snapshot())
        write(relative(PRIVATE / ("FAILED_" + args.stage + ".json")), failure)
        raise
    print(json.dumps(dict(stage=args.stage, status="completed", wall_s=time.perf_counter() - started,
        output="private/diagnostics/PREPARATION.json" if args.stage == "prepare" else "DIAGNOSTICS.json")))


if __name__ == "__main__":
    main()
