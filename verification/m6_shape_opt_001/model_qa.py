"""Synthetic structural, loss and gradient QA for the single optimization.

One synthetic SGD update checks gradient propagation through zero heads. It is
independent of the authorized 1200-step training and uses no public observation.
"""

import argparse
import hashlib
import importlib.util
import inspect
import json
import math
from pathlib import Path
import sys
import time

import torch
from torch.nn import functional as F


HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / "m6_shape_train_001"
sys.path.insert(0, str(HERE))
from model import ResidualExpert, gate_prediction, graph_loss, optimization_loss


# Reuse the frozen synthetic mesh, observation and transform constructions.
_saved_search_path = list(sys.path)
_qa_spec = importlib.util.spec_from_file_location("_m6_prior_shape_qa", PRIOR / "model_qa.py")
_prior_qa = importlib.util.module_from_spec(_qa_spec)
_qa_spec.loader.exec_module(_prior_qa)
sys.path[:] = _saved_search_path
_mesh = _prior_qa._mesh
_observe = _prior_qa._observe
_rotation = _prior_qa._rotation
_maximum_error = _prior_qa._maximum_error
_gradient_norms = _prior_qa._gradient_norms


def _loss_checks():
    conditional = torch.tensor(((1., 0., 0.), (2., 0., 0.), (0., 0., 0.),
                                (3., 0., 0.), (0., 0., 0.)), requires_grad=True)
    logits = torch.tensor((0., 0.6, -0.3, -0.8, 0.1), requires_grad=True)
    scores = logits.sigmoid()
    allowed = torch.tensor((True, True, False, True, True))
    damaged = torch.tensor((True, False, False, False, False))
    normal_free = torch.tensor((False, True, False, True, False))
    edges = torch.tensor(((0, 1, 1, 2, 3, 4), (1, 0, 2, 1, 4, 3)))
    graph_ids = torch.tensor((0, 0, 0, 1, 1))
    target = torch.zeros_like(conditional)
    base, _ = graph_loss(scores[:, None] * conditional, target, allowed, damaged,
                         normal_free, edges, graph_ids)
    actual, records = optimization_loss(conditional, logits, scores, target, allowed,
                                        damaged, normal_free, edges, graph_ids)
    first_loc = 0.5 * F.softplus(-logits[0]) + 0.5 * F.softplus(logits[1])
    second_loc = F.softplus(logits[3])
    expected = base + (0.4 + 0.05 * first_loc + 0.05 * second_loc) / 2
    error = _maximum_error(actual.detach(), expected.detach(), 1e-6)
    assert records[0]["localization_denominators"] == {"S": 1, "N_F": 1, "F": 2}
    assert records[0]["localization_group_weights"] == {"S": 0.5, "N_F": 0.5}
    assert records[1]["localization_denominators"] == {"S": 0, "N_F": 1, "F": 1}
    assert records[1]["localization_group_weights"] == {"F": 1.0}
    assert records[1]["conditional_support_mse"] is None
    actual.backward()
    assert torch.isfinite(conditional.grad).all() and torch.isfinite(logits.grad).all()

    one = torch.tensor(((1., 0., 0.),), requires_grad=True)
    z = torch.zeros(1, requires_grad=True)
    active, inactive = torch.tensor((True,)), torch.tensor((False,))
    empty_edges, graph = torch.empty((2, 0), dtype=torch.long), torch.tensor((0,))
    support_only, support_records = optimization_loss(
        one, z, z.sigmoid(), torch.zeros_like(one), active, active, inactive,
        empty_edges, graph,
    )
    expected_support = 0.25 + 0.4 + 0.05 * math.log(2)
    _maximum_error(support_only.detach(), torch.tensor(expected_support), 1e-6)
    assert support_records[0]["localization_means"]["N_F_negative"] is None
    assert support_records[0]["localization_group_weights"] == {"S": 1.0, "N_F": 0.0}
    empty, empty_records = optimization_loss(
        one * 0, z, z.sigmoid(), torch.zeros_like(one), inactive, inactive, inactive,
        empty_edges, graph,
    )
    assert float(empty.detach()) == 0
    assert empty_records[0]["localization_denominators"] == {"S": 0, "N_F": 0, "F": 0}
    assert empty_records[0]["localization_means"]["F_control_negative"] is None
    assert empty_records[0]["localization_group_weights"] == {"F": 0.0}
    return {
        "unequal_graph_sizes_equal_graph_mean": float(actual.detach()),
        "independent_formula": float(expected.detach()),
        "independent_formula_max_error": error,
        "per_graph": records,
        "empty_normal_free_renormalized_loss": float(support_only.detach()),
        "empty_groups_loss": float(empty.detach()),
        "original_loss_qa": _prior_qa._loss_checks(),
    }


def _initialization_check():
    checkpoint_path = PRIOR / "private/weights/step_0000.pt"
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    assert checkpoint["step"] == 0 and checkpoint["seed"] == 1729
    torch.manual_seed(1729)
    expert = ResidualExpert()
    old_state = checkpoint["model"]
    new_state = expert.state_dict()
    additional = set(new_state) - set(old_state)
    assert additional == {"localization_head.weight", "localization_head.bias"}
    assert all(torch.equal(new_state[name], value) for name, value in old_state.items())
    assert all(torch.count_nonzero(new_state[name]) == 0 for name in additional)
    expected_names = ["node_features", "edge_features", "positions", "normals", "edge_index", "free_mask"]
    forward_arguments = list(inspect.signature(expert.forward).parameters)
    component_arguments = list(inspect.signature(expert.forward_components).parameters)
    assert forward_arguments == component_arguments == expected_names
    return expert, {
        "checkpoint": str(checkpoint_path),
        "checkpoint_sha256": hashlib.sha256(checkpoint_path.read_bytes()).hexdigest(),
        "old_state_tensors_equal": len(old_state),
        "old_parameters_equal": sum(value.numel() for value in old_state.values()),
        "added_state_names": sorted(additional),
        "forward_arguments": forward_arguments,
        "component_arguments": component_arguments,
        "labels_or_metadata_forward_arguments": 0,
    }


def _gating_checks():
    conditional = torch.ones((4, 3))
    scores = torch.tensor((0.49, 0.5, 0.5001, 0.9))
    free = torch.tensor((True, True, True, False))
    gated = gate_prediction(conditional, scores, free, 0.5)
    assert torch.equal(gated, torch.tensor(((0., 0., 0.), (0., 0., 0.),
                                          (1., 1., 1.), (0., 0., 0.))))
    high_score = float(scores[2])
    low_score = float(torch.nextafter(scores[2], torch.tensor(float("-inf"))))
    threshold_between = (3 * high_score + low_score) / 4
    # Float32 casting would round this threshold up to the selected score.
    assert float(torch.tensor(threshold_between)) == high_score
    precise = gate_prediction(conditional, scores, free, threshold_between)
    assert torch.equal(precise, gated)
    return {
        "strict_threshold_equal_is_unselected": bool(torch.count_nonzero(gated[1]) == 0),
        "fixed_above_threshold_is_zero": bool(torch.count_nonzero(gated[3]) == 0),
        "float64_frozen_threshold": threshold_between,
        "float32_score_above_threshold": high_score,
        "threshold_scalar_rounding_avoided": True,
    }


def run_qa():
    started, cpu_started = time.perf_counter(), time.process_time()
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    model, initialization = _initialization_check()
    torch.manual_seed(4099)
    vertices, faces, edges, allowed, free = _mesh(6)
    inputs, statistics, original_scale = _observe(vertices, faces, edges, allowed, free)
    expected_modules = {
        "node_encoder": 792, "edge_mlp": 1872, "node_update": 2352,
        "layer_norm": 48, "alpha_head": 1201, "beta_head": 25,
        "localization_head": 49,
    }
    parameter_modules = {
        name: sum(parameter.numel() for parameter in module.parameters())
        for name, module in model.named_children()
    }
    assert parameter_modules == expected_modules
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    assert parameter_count == 6339 and model.message_steps == 12
    with torch.no_grad():
        conditional, logits, scores = model.forward_components(**inputs)
        initial_prediction = model(**inputs)
    assert torch.count_nonzero(initial_prediction) == torch.count_nonzero(conditional) == 0
    assert torch.count_nonzero(logits) == 0 and torch.all(scores == 0.5)
    assert tuple(logits.shape) == tuple(scores.shape) == (len(vertices),)

    geometric_model = ResidualExpert().eval()
    with torch.no_grad():
        geometric_model.alpha_head[-1].weight.normal_(0, 0.03)
        geometric_model.alpha_head[-1].bias.fill_(0.007)
        geometric_model.beta_head.weight.normal_(0, 0.03)
        geometric_model.beta_head.bias.fill_(-0.012)
        geometric_model.localization_head.weight.normal_(0, 0.03)
        geometric_model.localization_head.bias.fill_(0.023)
        reference_u, reference_z, reference_p = geometric_model.forward_components(**inputs)
        reference_prediction = geometric_model(**inputs)
        reference_hard = geometric_model.hard_prediction(**inputs, tau=0.5)
    assert float(reference_prediction[free].norm()) > 1e-4
    assert torch.count_nonzero(reference_prediction[~free]) == 0
    assert torch.equal(reference_prediction, reference_p[:, None] * reference_u)
    assert torch.equal(reference_hard, gate_prediction(reference_u, reference_p, free, 0.5))

    permutation = torch.randperm(len(vertices))
    inverse = torch.empty_like(permutation)
    inverse[permutation] = torch.arange(len(vertices))
    edge_permutation = torch.randperm(edges.shape[1])
    permuted = {name: value[permutation] for name, value in inputs.items()
                if name not in ("edge_index", "edge_features")}
    permuted["edge_index"] = inverse[edges[:, edge_permutation]]
    permuted["edge_features"] = inputs["edge_features"][edge_permutation]
    with torch.no_grad():
        permutation_error = _maximum_error(geometric_model(**permuted), reference_prediction[permutation])
        permuted_u, permuted_z, permuted_p = geometric_model.forward_components(**permuted)
    component_permutation_errors = {
        "u": _maximum_error(permuted_u, reference_u[permutation]),
        "z": _maximum_error(permuted_z, reference_z[permutation]),
        "p": _maximum_error(permuted_p, reference_p[permutation]),
    }

    transform_records = []
    for axis, angle, scale_factor in (
        ((1.2, -2.3, 0.7), 0.812, 3.7),
        ((0.4, 0.8, -1.7), -1.63, 0.037),
        ((0.2, -0.9, 0.3), 2.3, 100.0),
    ):
        rotation = _rotation(axis, angle)
        translated = scale_factor * vertices @ rotation.T + torch.tensor((0.71, -1.2, 0.39))
        transformed, _, transformed_scale = _observe(translated, faces, edges, allowed, free, statistics)
        with torch.no_grad():
            transformed_u, transformed_z, transformed_p = geometric_model.forward_components(**transformed)
            transformed_prediction = geometric_model(**transformed)
        expected_prediction = reference_prediction @ rotation.float().T
        transform_records.append({
            "axis": list(axis), "angle_radians": angle, "scale_factor": scale_factor,
            "rotation_determinant": float(torch.linalg.det(rotation)),
            "node_scalar_max_error": _maximum_error(transformed["node_features"], inputs["node_features"]),
            "edge_scalar_max_error": _maximum_error(transformed["edge_features"], inputs["edge_features"]),
            "conditional_vector_rotation_max_error": _maximum_error(transformed_u, reference_u @ rotation.float().T),
            "logit_scalar_max_error": _maximum_error(transformed_z, reference_z),
            "score_scalar_max_error": _maximum_error(transformed_p, reference_p),
            "normalized_prediction_max_error": _maximum_error(transformed_prediction, expected_prediction),
            "native_correction_max_error": _maximum_error(
                transformed_prediction * transformed_scale,
                scale_factor * original_scale * expected_prediction, tolerance=5e-5),
        })

    second_vertices, second_faces, second_edges, second_allowed, second_free = _mesh(7)
    second, _, _ = _observe(second_vertices, second_faces, second_edges, second_allowed, second_free, statistics)
    batch = {name: torch.cat((inputs[name], second[name]), dim=0)
             for name in inputs if name != "edge_index"}
    batch["edge_index"] = torch.cat((edges, second_edges + len(vertices)), dim=1)
    with torch.no_grad():
        batch_prediction = geometric_model(**batch)
        second_prediction = geometric_model(**second)
    batch_error = _maximum_error(batch_prediction, torch.cat((reference_prediction, second_prediction)))
    perturbed = dict(batch)
    perturbed["node_features"] = batch["node_features"].clone()
    perturbed["node_features"][len(vertices):, :5] += 0.713
    with torch.no_grad():
        isolation_error = _maximum_error(geometric_model(**perturbed)[:len(vertices)], batch_prediction[:len(vertices)])

    gradient_model = ResidualExpert()
    damaged = torch.zeros_like(free)
    damaged[torch.where(free)[0][:2]] = True
    normal_free = free & ~damaged
    target = torch.zeros_like(inputs["positions"])
    target[damaged] = -0.12 * inputs["normals"][damaged] + 0.03 * inputs["positions"][damaged]
    graph_ids = torch.zeros(len(vertices), dtype=torch.long)
    supervision = (target, allowed, damaged, normal_free, edges, graph_ids)
    optimizer = torch.optim.SGD(gradient_model.parameters(), lr=0.01)
    first_loss, first_records = optimization_loss(*gradient_model.forward_components(**inputs), *supervision)
    first_loss.backward()
    first_gradients = _gradient_norms(gradient_model)
    assert all(first_gradients[name] > 0 for name in (
        "alpha_head.2.weight", "alpha_head.2.bias", "beta_head.weight", "beta_head.bias",
        "localization_head.weight",
    ))
    assert all(value == 0 for name, value in first_gradients.items()
               if not name.startswith(("alpha_head.2.", "beta_head.", "localization_head.")))
    optimizer.step()
    optimizer.zero_grad(set_to_none=True)
    second_loss, second_records = optimization_loss(*gradient_model.forward_components(**inputs), *supervision)
    second_loss.backward()
    second_gradients = _gradient_norms(gradient_model)
    assert all(math.isfinite(value) for value in second_gradients.values())
    for module_name in expected_modules:
        assert any(value > 0 for name, value in second_gradients.items() if name.startswith(module_name + "."))

    return {
        "cycle_id": "M6-SHAPE-OPT-001", "passed": True,
        "qa_scope": "synthetic structural, old-initialization, loss and one-update gradient QA",
        "public_validation_observations_loaded": 0, "reserved_test_observations_loaded": 0,
        "formal_training_runs": 0, "synthetic_optimizer_updates": 1,
        "synthetic_gradient_backward_passes": 2,
        "torch_version": torch.__version__, "torch_threads": torch.get_num_threads(),
        "parameter_count": parameter_count, "parameters_by_module": parameter_modules,
        "message_steps": model.message_steps, "initialization": initialization,
        "initial_noop_nonzero_values": int(torch.count_nonzero(initial_prediction)),
        "initial_scores_all_half": bool(torch.all(scores == 0.5)),
        "nonzero_head_prediction_norm": float(reference_prediction[free].norm()),
        "fixed_nonzero_values": int(torch.count_nonzero(reference_prediction[~free])),
        "node_and_edge_permutation_max_error": permutation_error,
        "component_permutation_max_errors": component_permutation_errors,
        "SO3_translation_scale_checks": transform_records,
        "batch_graph_nodes": [len(vertices), len(second_vertices)],
        "batch_directed_edges": [edges.shape[1], second_edges.shape[1]],
        "batch_vs_single_max_error": batch_error,
        "other_graph_feature_perturbation_max_error": isolation_error,
        "first_backward_parameter_gradient_norms": first_gradients,
        "after_one_update_parameter_gradient_norms": second_gradients,
        "first_synthetic_loss": float(first_loss.detach()),
        "after_one_update_synthetic_loss": float(second_loss.detach()),
        "first_synthetic_graph_records": first_records,
        "after_one_update_synthetic_graph_records": second_records,
        "loss_checks": _loss_checks(), "gating_checks": _gating_checks(),
        "wall_seconds": time.perf_counter() - started,
        "cpu_seconds": time.process_time() - cpu_started,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=HERE / "MODEL_QA.json")
    args = parser.parse_args()
    result = run_qa()
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("passed", "parameter_count", "synthetic_optimizer_updates", "wall_seconds", "cpu_seconds")}))
