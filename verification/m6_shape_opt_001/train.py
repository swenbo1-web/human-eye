"""The single fixed 1200-step M6 localization and conditional repair run."""

import os
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import ctypes
import hashlib
import json
from pathlib import Path
import random
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "m6_shape_train_001"
DATA = HERE.parent / "m6_shape_data_001"
sys.path.insert(0, str(PREVIOUS))
sys.path.insert(0, str(HERE))
from data_io import batch_samples, cases_at, load_sample
from process_runner import process_metrics


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8", newline="\n")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def own_resources():
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    return process_metrics(ctypes.windll.kernel32.GetCurrentProcess())


def main():
    started, cpu_started = time.perf_counter(), time.process_time()
    marker = HERE / "TRAIN_STARTED.json"
    if marker.exists():
        raise RuntimeError("optimization_run_already_invoked_inspect_preserved_evidence")
    freeze = json.loads((HERE / "TRAIN_FREEZE.json").read_bytes())
    for record in freeze["files"]:
        if digest(HERE / record["path"]) != record["sha256"]:
            raise ValueError("pretraining_frozen_file_changed_" + record["path"])
    write(marker, {"cycle_id": "M6-SHAPE-OPT-001", "status": "invoked", "seed": 1729,
                   "requested_steps": 1200, "optimization_training_invocations": 1,
                   "parameters": 6339, "Bunny_model_scores": 0})
    log = {"cycle_id": "M6-SHAPE-OPT-001", "status": "starting", "seed": 1729,
           "steps_completed": 0, "requested_steps": 1200, "training_runs": 1,
           "optimization_training_runs": 1, "initial_training_runs_historical": 1,
           "Bunny_model_scores": 0, "failures": [], "steps": [], "evaluations": [],
           "timings": {name: 0.0 for name in ("batch_build_s", "forward_s", "loss_s",
                                             "backward_s", "optimizer_s", "checkpoint_s", "evaluation_s")}}
    budget_started = None
    model = optimizer = scheduler = None
    try:
        before = time.perf_counter()
        import torch
        from model import ResidualExpert, optimization_loss
        from evaluate import evaluate_model
        log["torch_import_wall_s"] = time.perf_counter() - before
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        torch.use_deterministic_algorithms(True)
        random.seed(1729)
        np.random.seed(1729)
        torch.manual_seed(1729)
        train_cases = cases_at(DATA / "DATASET_INDEX.json")
        validation_cases = cases_at(PREVIOUS / "PUBLIC_DATASET_INDEX.json", "validation")
        assert len(train_cases) == 231 and len(validation_cases) == 117
        assert all(case["purpose"] == "development_train_pool" for case in train_cases)
        assert all(case["source"] == "Stanford_Armadillo" for case in validation_cases)
        train_root = DATA / "private/patches"
        validation_root = PREVIOUS / "private/public_data/patches"
        before = time.perf_counter()
        samples = {case["id"]: load_sample(case, train_root) for case in train_cases}
        log["train_array_load_wall_s"] = time.perf_counter() - before
        stats_path = HERE / "private/normalization.npz"
        assert digest(stats_path) == digest(PREVIOUS / "private/normalization.npz")
        with np.load(stats_path, allow_pickle=False) as saved:
            stats = {name: saved[name].copy() for name in saved.files}
        assert sum(value.size for value in stats.values()) == 18
        log["normalization"] = {"mode": "reuse_exact_training_only_18_scalars",
                                "sha256": digest(stats_path), "fitted_again": False}
        roles = ["Yanyite", "Richie", "Chipow", "Yunhex"]
        patches = {source: list(dict.fromkeys(case["patch_id"] for case in train_cases
                                            if case["source"] == source)) for source in roles}
        previous_log = json.loads((PREVIOUS / "TRAIN_LOG.json").read_bytes())

        def batch_for_step(step):
            ids = []
            normal_role = step % 4
            for offset in range(4):
                role = (normal_role + offset) % 4
                source = roles[role]
                prior_normal = (step + 3 - role) // 4
                if role == normal_role:
                    patch = patches[source][prior_normal % len(patches[source])]
                    ordinal = 0
                else:
                    prior_dented = step - prior_normal
                    patch = patches[source][(prior_dented // 6) % len(patches[source])]
                    ordinal = prior_dented % 6 + 1
                ids.append(patch + f"/sample_{ordinal:02d}")
            return ids

        assert all(batch_for_step(step) == previous_log["steps"][step]["cases"]
                   for step in range(1200))
        log["all_1200_batch_sequences_equal_first_round"] = True
        model = ResidualExpert()
        assert sum(parameter.numel() for parameter in model.parameters()) == 6339
        original_initial = torch.load(PREVIOUS / "private/weights/step_0000.pt",
                                      map_location="cpu", weights_only=False)["model"]
        current = model.state_dict()
        assert all(torch.equal(current[name], value) for name, value in original_initial.items())
        log["old_module_initial_states_bitwise_equal"] = True
        log["old_module_initial_tensor_count"] = len(original_initial)
        optimizer = torch.optim.AdamW(model.parameters(), lr=.001, betas=(.9, .999), eps=1e-8,
                                     weight_decay=1e-5, foreach=False, fused=False)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=1200, eta_min=.0001)
        weights = HERE / "private/weights"
        weights.mkdir(parents=True, exist_ok=True)
        probe = [case for source in roles for case in train_cases
                 if case["source"] == source and case["patch_id"] == patches[source][0]
                 and case["id"].endswith(("sample_00", "sample_06"))]

        def save_checkpoint(step):
            before = time.perf_counter()
            path = weights / f"step_{step:04d}.pt"
            torch.save({"model": model.state_dict(), "step": step, "seed": 1729,
                        "parameters": 6339, "optimizer": optimizer.state_dict(),
                        "scheduler": scheduler.state_dict(), "rng": torch.get_rng_state()}, path)
            log["timings"]["checkpoint_s"] += time.perf_counter() - before
            return {"path": str(path), "sha256": digest(path), "bytes": path.stat().st_size,
                    "step": step}

        def evaluate_step(step):
            before = time.perf_counter()
            development = train_cases if step == 1200 else probe
            output = HERE / "private/predictions" / f"step_{step:04d}_soft"
            dev = evaluate_model(model, development, train_root, stats, output / "development")
            val = evaluate_model(model, validation_cases, validation_root, stats, output / "validation")
            path = HERE / f"EVAL_STEP_{step:04d}.json"
            write(path, {"step": step, "output_mode": "soft_p_times_u", "development": dev,
                         "validation": val, "reserved_test_scores": 0})
            log["evaluations"].append({"step": step, "path": str(path),
                                       "development_cases": len(development),
                                       "validation_cases": len(validation_cases), "mode": "soft"})
            log["timings"]["evaluation_s"] += time.perf_counter() - before

        budget_started = time.perf_counter()
        log["initial_checkpoint"] = save_checkpoint(0)
        evaluate_step(0)
        log["status"] = "running"
        for step in range(1200):
            if time.perf_counter() - budget_started >= 1800:
                log["status"] = "training_time_budget_exhausted"
                break
            if own_resources()["peak_working_set_bytes"] > 2 * 1024 ** 3:
                log["status"] = "training_memory_budget_exhausted"
                break
            ids = batch_for_step(step)
            before = time.perf_counter()
            forward, supervision = batch_samples([samples[index] for index in ids], stats)
            log["timings"]["batch_build_s"] += time.perf_counter() - before
            model.train()
            optimizer.zero_grad(set_to_none=True)
            before = time.perf_counter()
            conditional, logits, scores = model.forward_components(*forward)
            log["timings"]["forward_s"] += time.perf_counter() - before
            before = time.perf_counter()
            loss, components = optimization_loss(conditional, logits, scores, **supervision)
            if not torch.isfinite(loss):
                raise FloatingPointError("nonfinite_training_loss")
            log["timings"]["loss_s"] += time.perf_counter() - before
            before = time.perf_counter()
            loss.backward()
            gradient = torch.nn.utils.clip_grad_norm_(model.parameters(), 1., error_if_nonfinite=True)
            log["timings"]["backward_s"] += time.perf_counter() - before
            before = time.perf_counter()
            optimizer.step()
            scheduler.step()
            log["timings"]["optimizer_s"] += time.perf_counter() - before
            log["steps_completed"] = step + 1
            log["steps"].append({"step": step + 1, "cases": ids, "loss": float(loss.detach()),
                                 "gradient_norm_before_clip": float(gradient),
                                 "lr_after_step": optimizer.param_groups[0]["lr"],
                                 "components": components})
            if (step + 1) % 100 == 0:
                print(json.dumps({"step": step + 1, "loss": float(loss.detach()),
                                  "elapsed_s": time.perf_counter() - budget_started}), flush=True)
                write(HERE / "TRAIN_LOG.json", log)
            if (step + 1) % 400 == 0:
                log["last_checkpoint"] = save_checkpoint(step + 1)
                evaluate_step(step + 1)
        if log["steps_completed"] == 1200:
            log["status"] = "completed_fixed_1200_steps"
            log["final_weights"] = log["last_checkpoint"]
        else:
            log["partial_checkpoint"] = save_checkpoint(log["steps_completed"])
    except Exception as error:
        log["status"] = "implementation_or_training_failure"
        log["failures"].append({"type": type(error).__name__, "message": str(error),
                                "completed_steps": log["steps_completed"]})
        if model is not None and optimizer is not None and scheduler is not None:
            path = HERE / "private/weights/failure_state.pt"
            path.parent.mkdir(parents=True, exist_ok=True)
            torch.save({"model": model.state_dict(), "step": log["steps_completed"],
                        "optimizer": optimizer.state_dict(), "scheduler": scheduler.state_dict()}, path)
            log["failure_checkpoint"] = {"path": str(path), "sha256": digest(path)}
        raise
    finally:
        log["budget_elapsed_s_including_soft_evaluations"] = (
            time.perf_counter() - budget_started if budget_started is not None else None)
        log["main_wall_s"] = time.perf_counter() - started
        log["main_cpu_s"] = time.process_time() - cpu_started
        log["actual_python_process_metrics_at_end"] = own_resources()
        write(HERE / "TRAIN_LOG.json", log)
        write(marker, {"cycle_id": "M6-SHAPE-OPT-001", "status": log["status"], "seed": 1729,
                       "requested_steps": 1200, "steps_completed": log["steps_completed"],
                       "optimization_training_invocations": 1, "parameters": 6339,
                       "Bunny_model_scores": 0, "failures": log["failures"]})


if __name__ == "__main__":
    main()
