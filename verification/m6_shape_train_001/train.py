"""One fixed first-round CPU training run, with fixed-step validation."""
import os
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import random
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from data_io import batch_samples, cases_at, fit_standardization, load_sample
from process_runner import process_metrics


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def own_resources():
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    return process_metrics(ctypes.windll.kernel32.GetCurrentProcess())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, default=HERE.parent / "m6_shape_data_001")
    parser.add_argument("--public-root", type=Path, default=HERE)
    args = parser.parse_args()
    full_started, full_cpu = time.perf_counter(), time.process_time()
    marker = HERE / "TRAIN_STARTED.json"
    if marker.exists():
        raise RuntimeError("first_round_already_started_inspect_existing_state")
    before = time.perf_counter()
    import torch
    from model import ResidualExpert, graph_loss
    from evaluate import evaluate_model
    torch_import_s = time.perf_counter() - before
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    random.seed(1729)
    np.random.seed(1729)
    torch.manual_seed(1729)
    public_selection = json.loads((args.public_root / "PUBLIC_PATCH_SELECTION.json").read_bytes())
    for source in ("Stanford_Armadillo", "Stanford_Bunny"):
        assert sum(patch["source"] == source for patch in public_selection["patches"]) >= 3
    train_cases = cases_at(args.input_root / "DATASET_INDEX.json")
    val_cases = cases_at(args.public_root / "PUBLIC_DATASET_INDEX.json", "validation")
    assert len(train_cases) == 231 and len(val_cases) == 117
    assert all(case["purpose"] == "development_train_pool" for case in train_cases)
    assert all(case["source"] == "Stanford_Armadillo" for case in val_cases)
    train_patch_root = args.input_root / "private/patches"
    val_patch_root = args.public_root / "private/public_data/patches"
    before = time.perf_counter()
    samples = {case["id"]: load_sample(case, train_patch_root) for case in train_cases}
    load_s = time.perf_counter() - before
    before = time.perf_counter()
    stats = fit_standardization(list(samples.values()))
    stats_s = time.perf_counter() - before
    private = HERE / "private"
    weights = private / "weights"
    weights.mkdir(exist_ok=True)
    np.savez(private / "normalization.npz", **stats)
    write(HERE / "NORMALIZATION.json", {"source": "231 training observations only", "train_case_ids": [case["id"] for case in train_cases],
                                        "values": {name: value.tolist() for name, value in stats.items()}, "persisted_scalars": 18})
    roles = ["Yanyite", "Richie", "Chipow", "Yunhex"]
    patches = {source: list(dict.fromkeys(case["patch_id"] for case in train_cases if case["source"] == source)) for source in roles}
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
    model = ResidualExpert()
    assert sum(parameter.numel() for parameter in model.parameters()) == 6290
    optimizer = torch.optim.AdamW(model.parameters(), lr=.001, betas=(.9, .999), eps=1e-8,
                                 weight_decay=1e-5, foreach=False, fused=False)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=1200, eta_min=.0001)
    train_probe = [case for source in roles for case in train_cases if case["source"] == source and case["patch_id"] == patches[source][0] and case["id"].endswith(("sample_00", "sample_06"))]
    log = {"cycle_id": "M6-SHAPE-TRAIN-001", "status": "running", "seed": 1729, "steps_completed": 0,
           "requested_steps": 1200, "training_runs": 1, "Bunny_model_scores": 0,
           "torch_version": torch.__version__, "numpy_version": np.__version__, "torch_import_wall_s": torch_import_s,
           "train_array_load_wall_s": load_s, "normalization_wall_s": stats_s,
           "timings": {"batch_build_s": 0., "forward_s": 0., "loss_s": 0., "backward_s": 0., "optimizer_s": 0., "checkpoint_s": 0., "evaluation_s": 0.},
           "steps": [], "evaluations": [], "failures": []}
    write(marker, {"seed": 1729, "steps": 1200, "status": "started", "model_parameters": 6290, "Bunny_scoring": False})
    budget_started = time.perf_counter()
    def save_checkpoint(step):
        before = time.perf_counter()
        path = weights / f"step_{step:04d}.pt"
        torch.save({"model": model.state_dict(), "step": step, "seed": 1729, "parameters": 6290,
                    "optimizer": optimizer.state_dict(), "scheduler": scheduler.state_dict(), "rng": torch.get_rng_state()}, path)
        log["timings"]["checkpoint_s"] += time.perf_counter() - before
        return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size, "step": step}
    def evaluate_step(step):
        before = time.perf_counter()
        probe = train_cases if step == 1200 else train_probe
        dev = evaluate_model(model, probe, train_patch_root, stats, private / "predictions" / f"step_{step:04d}_development")
        val = evaluate_model(model, val_cases, val_patch_root, stats, private / "predictions" / f"step_{step:04d}_validation")
        path = HERE / f"EVAL_STEP_{step:04d}.json"
        write(path, {"step": step, "development": dev, "validation": val, "reserved_test_scores": 0})
        log["evaluations"].append({"step": step, "path": str(path), "development_cases": len(probe), "validation_cases": len(val_cases)})
        log["timings"]["evaluation_s"] += time.perf_counter() - before
    try:
        log["initial_checkpoint"] = save_checkpoint(0)
        evaluate_step(0)
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
            prediction = model(*forward)
            log["timings"]["forward_s"] += time.perf_counter() - before
            before = time.perf_counter()
            loss, components = graph_loss(prediction, **supervision)
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
            log["steps"].append({"step": step + 1, "cases": ids, "loss": float(loss.detach()), "gradient_norm_before_clip": float(gradient),
                                 "lr_after_step": optimizer.param_groups[0]["lr"], "components": components})
            if (step + 1) % 100 == 0:
                print(json.dumps({"step": step + 1, "loss": float(loss.detach()), "elapsed_s": time.perf_counter() - budget_started}), flush=True)
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
        log["failures"].append({"type": type(error).__name__, "message": str(error), "completed_steps": log["steps_completed"]})
        log["partial_checkpoint"] = save_checkpoint(log["steps_completed"])
        raise
    finally:
        log["budget_elapsed_s_including_evaluations"] = time.perf_counter() - budget_started
        log["main_wall_s"] = time.perf_counter() - full_started
        log["main_cpu_s"] = time.process_time() - full_cpu
        log["actual_python_process_metrics_at_end"] = own_resources()
        log["Bunny_model_scores"] = 0
        write(HERE / "TRAIN_LOG.json", log)


if __name__ == "__main__":
    main()
