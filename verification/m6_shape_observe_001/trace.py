"""Seven cached, read-only frozen forwards for the six preselected witnesses."""

import time
BOOT_WALL = time.perf_counter()
BOOT_CPU = time.process_time()

import os
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import ctypes
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
OPT = HERE.parent / "m6_shape_opt_001"
TRAIN = HERE.parent / "m6_shape_train_001"
DATA = HERE.parent / "m6_shape_data_001"
sys.path.append(str(TRAIN))
from data_io import cases_at, candidate_from_prediction, forward_arrays, load_sample


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def own_resources():
    spec = importlib.util.spec_from_file_location("_observe_trace_metrics", OPT / "process_runner.py")
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    return monitor.process_metrics(ctypes.windll.kernel32.GetCurrentProcess())


def main():
    started, cpu_started = time.perf_counter(), time.process_time()
    marker = HERE / "TRACE_STARTED.json"
    if marker.exists():
        raise RuntimeError("frozen_trace_already_invoked_inspect_preserved_call_count")
    plan = json.loads((HERE / "EVIDENCE_PLAN.json").read_bytes())
    if not (HERE / "PLAN.json").exists():
        raise RuntimeError("observation_plan_missing")
    identities = sorted({row[key] for row in plan["evidence"]
                         for key in ("case_id", "paired_normal_case_id")})
    if len(identities) > 12:
        raise ValueError("frozen_forward_budget_exceeded")
    marker_state = {"status": "running", "maximum_calls": 12, "attempted_calls": 0,
                    "completed_calls": 0, "case_ids": identities, "failures": []}
    write(marker, marker_state)
    report = {"cycle_id": "M6-SHAPE-OBSERVE-001", "status": "running",
              "evidence_plan_sha256": sha256(HERE / "EVIDENCE_PLAN.json"),
              "plan_sha256": sha256(HERE / "PLAN.json"), "maximum_forward_calls": 12,
              "actual_forward_calls": 0, "unique_cases": len(identities),
              "cache_policy": "one forward per unique observation case; paired controls reuse that case response",
              "training_updates": 0, "gradient_backward_calls": 0, "Bunny_arrays_loaded": 0,
              "threshold_candidates": 0, "cases": [], "evidence": [], "failures": [],
              "timings": {"array_read_wall_s": 0., "forward_tensor_wall_s": 0.,
                          "frozen_forward_wall_s": 0., "frozen_forward_cpu_s": 0.,
                          "save_and_check_wall_s": 0.}}
    model = None
    weight_path = OPT / "private/weights/step_1200.pt"
    normalization = OPT / "private/normalization.npz"
    weights_before, normalization_before = sha256(weight_path), sha256(normalization)
    try:
        before, before_cpu = time.perf_counter(), time.process_time()
        import torch
        spec = importlib.util.spec_from_file_location("_observe_frozen_expert", OPT / "model.py")
        frozen_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(frozen_module)
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        torch.use_deterministic_algorithms(True)
        model = frozen_module.ResidualExpert()
        checkpoint = torch.load(weight_path, map_location="cpu", weights_only=False)
        model.load_state_dict(checkpoint["model"])
        model.eval()
        for parameter in model.parameters():
            parameter.requires_grad_(False)
        assert sum(parameter.numel() for parameter in model.parameters()) == 6339
        with np.load(normalization, allow_pickle=False) as saved:
            stats = {name: saved[name].copy() for name in saved.files}
        report["timings"]["frozen_import_and_load_wall_s"] = time.perf_counter() - before
        report["timings"]["frozen_import_and_load_cpu_s"] = time.process_time() - before_cpu
        report["weights_sha256_before"] = weights_before
        report["normalization_sha256_before"] = normalization_before
        report["torch_version"] = torch.__version__
        cases = {case["id"]: case for case in cases_at(DATA / "DATASET_INDEX.json")
                 + cases_at(TRAIN / "PUBLIC_DATASET_INDEX.json", "validation")}
        previous = json.loads((OPT / "EVAL_FINAL_HARD.json").read_bytes())
        predictions = {case["id"]: case for group in ("development", "validation")
                       for case in previous[group]["cases"]}
        tau = json.loads((OPT / "LOC_CALIBRATION.json").read_bytes())["tau"]
        report["fixed_tau"] = tau
        traced = {}
        for case_id in identities:
            case = cases[case_id]
            before = time.perf_counter()
            root = DATA / "private/patches" if case["purpose"] == "development_train_pool" else TRAIN / "private/public_data/patches"
            sample = load_sample(case, root)
            with np.load(predictions[case_id]["component_path"], allow_pickle=False) as saved:
                old = {name: saved[name].copy() for name in ("u", "z", "p", "prediction_normalized")}
            report["timings"]["array_read_wall_s"] += time.perf_counter() - before
            before = time.perf_counter()
            arrays = forward_arrays(sample, stats)
            values = tuple(torch.from_numpy(np.ascontiguousarray(array)) for array in arrays)
            report["timings"]["forward_tensor_wall_s"] += time.perf_counter() - before
            captured = {}
            iterations = [0]

            def encoder_hook(module, arguments, output):
                captured["h0"] = output.detach().cpu().numpy().copy()

            def layer_hook(module, arguments, output):
                iterations[0] += 1
                if iterations[0] in (4, 8, 12):
                    captured["h" + str(iterations[0])] = output.detach().cpu().numpy().copy()

            hooks = [model.node_encoder.register_forward_hook(encoder_hook),
                     model.layer_norm.register_forward_hook(layer_hook)]
            marker_state["attempted_calls"] += 1
            write(marker, marker_state)
            before, before_cpu = time.perf_counter(), time.process_time()
            try:
                with torch.inference_mode():
                    conditional, logits, scores = model.forward_components(*values)
                    hard = frozen_module.gate_prediction(conditional, scores, values[5], tau)
                    u, z, p, prediction = (value.cpu().numpy().copy()
                                           for value in (conditional, logits, scores, hard))
            finally:
                for hook in hooks:
                    hook.remove()
            wall = time.perf_counter() - before
            cpu = time.process_time() - before_cpu
            report["actual_forward_calls"] += 1
            marker_state["completed_calls"] += 1
            write(marker, marker_state)
            report["timings"]["frozen_forward_wall_s"] += wall
            report["timings"]["frozen_forward_cpu_s"] += cpu
            before = time.perf_counter()
            if iterations[0] != 12 or set(captured) != {"h0", "h4", "h8", "h12"}:
                raise ValueError("unexpected_frozen_hook_call_sequence")
            actual = {"u": u, "z": z, "p": p, "prediction_normalized": prediction}
            comparisons = {name: {"bitwise_equal": bool(np.array_equal(value.view(np.uint32), old[name].view(np.uint32))),
                                   "max_abs_difference": float(np.max(np.abs(value.astype(np.float64) - old[name].astype(np.float64))))}
                           for name, value in actual.items()}
            if not all(record["bitwise_equal"] for record in comparisons.values()):
                raise ValueError("frozen_component_replay_mismatch_" + case_id)
            candidate = candidate_from_prediction(sample, prediction)
            old_candidate = np.load(predictions[case_id]["candidate_path"], allow_pickle=False)
            candidate_equal = bool(np.array_equal(candidate.view(np.uint64), old_candidate.view(np.uint64)))
            if not candidate_equal:
                raise ValueError("frozen_candidate_replay_mismatch_" + case_id)
            folder = HERE / "private/trace" / case["patch_id"]
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / (case["id"].split("/")[1] + ".npz")
            np.savez(path, **captured, u=u, z=z, p=p, prediction_normalized=prediction)
            record = {"case_id": case_id, "source": case["source"],
                      "normal_control": case["normal_control"],
                      "forward_number": report["actual_forward_calls"],
                      "old_component_path": predictions[case_id]["component_path"],
                      "old_component_sha256": sha256(predictions[case_id]["component_path"]),
                      "input_arrays": [{"name": name, "shape": list(array.shape), "dtype": str(array.dtype),
                                        "sha256_bytes": hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()}
                                       for name, array in zip(("node_features", "edge_features", "positions", "normals", "edge_index", "free_mask"), arrays)],
                      "replay": comparisons, "old_binary64_candidate_equal": candidate_equal,
                      "trace_path": str(path), "trace_sha256": sha256(path),
                      "captured_node_counts": {name: int(len(value)) for name, value in captured.items()},
                      "layer_norm_calls": iterations[0], "forward_wall_s": wall, "forward_cpu_s": cpu}
            traced[case_id] = (captured, sample, p, z, u)
            report["cases"].append(record)
            report["timings"]["save_and_check_wall_s"] += time.perf_counter() - before
        for witness in plan["evidence"]:
            case_id, normal_id = witness["case_id"], witness["paired_normal_case_id"]
            states, sample, p, z, u = traced[case_id]
            normal_states, normal_sample, normal_p, normal_z, normal_u = traced[normal_id]
            source_id = witness["source_vertex_id"]
            index = int(np.flatnonzero(sample["mapping"]["context_source_ids"] == source_id)[0])
            normal_index = int(np.flatnonzero(normal_sample["mapping"]["context_source_ids"] == source_id)[0])
            layers = {}
            for name in ("h0", "h4", "h8", "h12"):
                observed_hidden = states[name][index].astype(np.float64)
                normal_hidden = normal_states[name][normal_index].astype(np.float64)
                difference = observed_hidden - normal_hidden
                layers[name] = {"observed": observed_hidden.tolist(), "paired_normal": normal_hidden.tolist(),
                                "difference": difference.tolist(), "difference_l2": float(np.linalg.norm(difference)),
                                "observed_l2": float(np.linalg.norm(observed_hidden)),
                                "paired_normal_l2": float(np.linalg.norm(normal_hidden))}
            report["evidence"].append({"evidence_id": witness["evidence_id"], "case_id": case_id,
                                       "paired_normal_case_id": normal_id, "source_vertex_id": source_id,
                                       "local_index": index, "paired_normal_local_index": normal_index,
                                       "score": float(p[index]), "paired_normal_score": float(normal_p[normal_index]),
                                       "score_difference": float(p[index]) - float(normal_p[normal_index]),
                                       "logit": float(z[index]), "paired_normal_logit": float(normal_z[normal_index]),
                                       "conditional_u": u[index].tolist(), "paired_normal_u": normal_u[normal_index].tolist(),
                                       "layers": layers, "identical_observation_pair": case_id == normal_id})
        report["status"] = "passed_frozen_replay_and_trace"
        marker_state["status"] = "completed"
    except Exception as error:
        failure = {"type": type(error).__name__, "message": str(error),
                   "attempted_calls": marker_state["attempted_calls"],
                   "completed_calls": marker_state["completed_calls"]}
        report["failures"].append(failure)
        marker_state["failures"].append(failure)
        report["status"] = marker_state["status"] = "failed"
        raise
    finally:
        report["weights_sha256_after"] = sha256(weight_path)
        report["normalization_sha256_after"] = sha256(normalization)
        report["weights_and_normalization_preserved"] = (sha256(weight_path) == weights_before and sha256(normalization) == normalization_before)
        report["interpretation_limit"] = "Recorded hidden changes are paired responses. Their norm or layer trend alone does not establish an information-compression pathology."
        report["timings"]["main_wall_s"] = time.perf_counter() - started
        report["timings"]["main_cpu_s"] = time.process_time() - cpu_started
        report["timings"]["bootstrap_to_final_report_wall_s"] = time.perf_counter() - BOOT_WALL
        report["timings"]["bootstrap_to_final_report_cpu_s"] = time.process_time() - BOOT_CPU
        report["own_process_at_end"] = own_resources()
        write(HERE / "FROZEN_TRACE.json", report)
        write(marker, marker_state)
    print(json.dumps({"status": report["status"], "actual_forwards": report["actual_forward_calls"],
                      "weights_preserved": report["weights_and_normalization_preserved"],
                      "main_wall_s": report["timings"]["main_wall_s"]}))


if __name__ == "__main__":
    main()
