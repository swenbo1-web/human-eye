"""Synthetic structural and one-update gradient QA for the fixed M6 expert.

No public validation or reserved-test observation is loaded. Exactly one
optimizer update tests gradient propagation through zero-initialized heads.
This synthetic gradient QA is separate from the single authorized training run.
"""

import argparse
import json
import math
import sys
import time
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model import ResidualExpert, graph_loss


def _mesh(side):
    vertices = []
    triangles = []
    for row in range(side):
        for column in range(side):
            x = (column - (side - 1) / 2) * 0.31
            y = (row - (side - 1) / 2) * 0.29
            z = 0.13 * math.sin(1.2 * x) * math.cos(0.7 * y) + 0.03 * x * y
            vertices.append((x, y, z))
            if row < side - 1 and column < side - 1:
                first = row * side + column
                triangles.extend(((first, first + 1, first + side + 1),
                                  (first, first + side + 1, first + side)))
    allowed = torch.tensor(
        [0 < row < side - 1 and 0 < column < side - 1
         for row in range(side) for column in range(side)], dtype=torch.bool
    )
    free = torch.tensor(
        [1 < row < side - 2 and 1 < column < side - 2
         for row in range(side) for column in range(side)], dtype=torch.bool
    )
    faces = torch.tensor(triangles, dtype=torch.long)
    edges = set()
    for triangle in triangles:
        for first, second in ((0, 1), (1, 2), (2, 0)):
            edges.add(tuple(sorted((triangle[first], triangle[second]))))
    undirected = torch.tensor(sorted(edges), dtype=torch.long).T
    directed = torch.cat((undirected, undirected.flip(0)), dim=1)
    return torch.tensor(vertices, dtype=torch.float64), faces, directed, allowed, free


def _observe(vertices, faces, edge_index, allowed, free, statistics=None):
    origin, neighbor = edge_index
    normal_sum = torch.zeros_like(vertices)
    face_normals = torch.linalg.cross(
        vertices[faces[:, 1]] - vertices[faces[:, 0]],
        vertices[faces[:, 2]] - vertices[faces[:, 0]], dim=1,
    )
    for corner in range(3):
        normal_sum.index_add_(0, faces[:, corner], face_normals)
    normals = normal_sum / normal_sum.norm(dim=1, keepdim=True).clamp_min(1e-15)
    center = vertices[~free].mean(dim=0)
    scale = torch.quantile((vertices[neighbor] - vertices[origin]).norm(dim=1), 0.5)
    positions = (vertices - center) / scale
    relative = positions[neighbor] - positions[origin]
    degree = torch.bincount(origin, minlength=len(vertices)).to(torch.float64)
    laplacian = torch.zeros_like(vertices)
    laplacian.index_add_(0, origin, relative)
    lengths = torch.zeros(len(vertices), dtype=torch.float64)
    lengths.index_add_(0, origin, relative.norm(dim=1))
    dot = (normals[origin] * normals[neighbor]).sum(dim=1).clamp(-1, 1)
    variation = torch.zeros_like(lengths)
    variation.index_add_(0, origin, 1 - dot)
    node_features = torch.column_stack(
        (positions.norm(dim=1), (normals * laplacian / degree[:, None]).sum(dim=1),
         variation / degree, lengths / degree, torch.log1p(degree), allowed, ~free)
    )
    edge_features = torch.column_stack(
        (relative.square().sum(dim=1), dot,
         (normals[origin] * relative).sum(dim=1),
         (normals[neighbor] * relative).sum(dim=1))
    )
    if statistics is None:
        statistics = {
            "node_mean": node_features[:, :5].mean(dim=0),
            "node_std": node_features[:, :5].std(dim=0, correction=0).clamp_min(1e-6),
            "edge_mean": edge_features.mean(dim=0),
            "edge_std": edge_features.std(dim=0, correction=0).clamp_min(1e-6),
        }
    node_features[:, :5] = (
        node_features[:, :5] - statistics["node_mean"]
    ) / statistics["node_std"]
    edge_features = (edge_features - statistics["edge_mean"]) / statistics["edge_std"]
    return {
        "node_features": node_features.float(),
        "edge_features": edge_features.float(),
        "positions": positions.float(),
        "normals": normals.float(),
        "edge_index": edge_index,
        "free_mask": free,
    }, statistics, float(scale)


def _rotation(axis, angle):
    axis = torch.tensor(axis, dtype=torch.float64)
    axis = axis / axis.norm()
    x, y, z = axis.tolist()
    skew = torch.tensor(((0, -z, y), (z, 0, -x), (-y, x, 0)), dtype=torch.float64)
    return (torch.eye(3, dtype=torch.float64) * math.cos(angle)
            + (1 - math.cos(angle)) * torch.outer(axis, axis)
            + math.sin(angle) * skew)


def _maximum_error(actual, expected, tolerance=5e-6):
    error = float((actual - expected).abs().max())
    assert math.isfinite(error) and error <= tolerance, (error, tolerance)
    return error


def _gradient_norms(model):
    return {
        name: float(parameter.grad.norm()) if parameter.grad is not None else 0.0
        for name, parameter in model.named_parameters()
    }


def _loss_checks():
    prediction = torch.tensor(((1., 0., 0.), (2., 0., 0.), (0., 0., 0.),
                               (3., 0., 0.), (0., 0., 0.)), requires_grad=True)
    allowed = torch.tensor((True, True, False, True, True))
    damaged = torch.tensor((True, False, False, False, False))
    normal_free = torch.tensor((False, True, False, True, False))
    edges = torch.tensor(((0, 1, 1, 2, 3, 4), (1, 0, 2, 1, 4, 3)))
    graph_ids = torch.tensor((0, 0, 0, 1, 1))
    loss, records = graph_loss(
        prediction, torch.zeros_like(prediction), allowed, damaged, normal_free, edges, graph_ids
    )
    _maximum_error(loss.detach(), torch.tensor(3.7875), 1e-6)
    assert records[0]["denominators"] == {
        "A": 2, "S": 1, "normal_allowed": 1, "normal_free": 1,
        "fixed": 1, "directed_edges": 4,
    }
    assert records[1]["normal_control"] and records[1]["mse"]["S"] is None
    loss.backward()
    assert prediction.grad is not None and torch.isfinite(prediction.grad).all()

    empty_edges = torch.empty((2, 0), dtype=torch.long)
    one = torch.tensor(((1., 0., 0.),), requires_grad=True)
    active = torch.tensor((True,))
    inactive = torch.tensor((False,))
    single_graph = torch.tensor((0,))
    empty_term_loss, empty_term_records = graph_loss(
        one, torch.zeros_like(one), active, active, inactive, empty_edges, single_graph
    )
    _maximum_error(empty_term_loss.detach(), torch.tensor(1.0), 1e-6)
    assert empty_term_records[0]["mse"]["normal_free"] is None
    zero_loss, zero_records = graph_loss(
        one * 0, torch.zeros_like(one), inactive, inactive, inactive, empty_edges, single_graph
    )
    assert float(zero_loss.detach()) == 0 and zero_records[0]["mse"]["A"] is None

    cross_edge_rejected = False
    try:
        graph_loss(prediction, torch.zeros_like(prediction), allowed, damaged, normal_free,
                   torch.tensor(((0,), (3,))), graph_ids)
    except ValueError as error:
        cross_edge_rejected = "cross-graph" in str(error)
    assert cross_edge_rejected
    return {
        "unequal_graph_sizes_equal_graph_mean": float(loss.detach()),
        "expected_equal_graph_mean": 3.7875,
        "per_graph": records,
        "empty_term_renormalized_loss": float(empty_term_loss.detach()),
        "empty_allowed_loss": float(zero_loss.detach()),
        "cross_graph_edge_rejected": cross_edge_rejected,
    }


def run_qa():
    started = time.perf_counter()
    torch.set_num_threads(1)
    torch.manual_seed(4099)
    torch.use_deterministic_algorithms(True)
    vertices, faces, edges, allowed, free = _mesh(6)
    inputs, statistics, original_scale = _observe(vertices, faces, edges, allowed, free)
    model = ResidualExpert()
    parameter_modules = {
        name: sum(parameter.numel() for parameter in module.parameters())
        for name, module in model.named_children()
    }
    expected_modules = {
        "node_encoder": 792, "edge_mlp": 1872, "node_update": 2352,
        "layer_norm": 48, "alpha_head": 1201, "beta_head": 25,
    }
    assert parameter_modules == expected_modules
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    assert parameter_count == 6290 and model.message_steps == 12
    with torch.no_grad():
        initial_prediction = model(**inputs)
    assert torch.count_nonzero(initial_prediction) == 0

    # A separate nonzero-head instance makes geometric QA nontrivial.
    geometric_model = ResidualExpert().eval()
    with torch.no_grad():
        geometric_model.alpha_head[-1].weight.normal_(0, 0.03)
        geometric_model.alpha_head[-1].bias.fill_(0.007)
        geometric_model.beta_head.weight.normal_(0, 0.03)
        geometric_model.beta_head.bias.fill_(-0.012)
        reference_prediction = geometric_model(**inputs)
    assert float(reference_prediction[free].norm()) > 1e-4
    assert torch.count_nonzero(reference_prediction[~free]) == 0

    permutation = torch.randperm(len(vertices))
    inverse = torch.empty_like(permutation)
    inverse[permutation] = torch.arange(len(vertices))
    edge_permutation = torch.randperm(edges.shape[1])
    permuted = {
        name: value[permutation]
        for name, value in inputs.items()
        if name not in ("edge_index", "edge_features")
    }
    permuted["edge_index"] = inverse[edges[:, edge_permutation]]
    permuted["edge_features"] = inputs["edge_features"][edge_permutation]
    with torch.no_grad():
        permutation_error = _maximum_error(
            geometric_model(**permuted), reference_prediction[permutation]
        )

    transform_records = []
    transformations = (
        ((1.2, -2.3, 0.7), 0.812, 3.7),
        ((0.4, 0.8, -1.7), -1.63, 0.037),
        ((0.2, -0.9, 0.3), 2.3, 100.0),
    )
    for axis, angle, scale_factor in transformations:
        rotation = _rotation(axis, angle)
        translated = scale_factor * vertices @ rotation.T + torch.tensor((0.71, -1.2, 0.39))
        transformed, _, transformed_scale = _observe(
            translated, faces, edges, allowed, free, statistics
        )
        with torch.no_grad():
            transformed_prediction = geometric_model(**transformed)
        expected_prediction = reference_prediction @ rotation.float().T
        transform_records.append({
            "axis": list(axis), "angle_radians": angle, "scale_factor": scale_factor,
            "rotation_determinant": float(torch.linalg.det(rotation)),
            "node_scalar_max_error": _maximum_error(
                transformed["node_features"], inputs["node_features"]
            ),
            "edge_scalar_max_error": _maximum_error(
                transformed["edge_features"], inputs["edge_features"]
            ),
            "normalized_prediction_max_error": _maximum_error(
                transformed_prediction, expected_prediction
            ),
            "world_correction_max_error": _maximum_error(
                transformed_prediction * transformed_scale,
                scale_factor * original_scale * expected_prediction, tolerance=5e-5
            ),
        })

    second_vertices, second_faces, second_edges, second_allowed, second_free = _mesh(7)
    second, _, _ = _observe(
        second_vertices, second_faces, second_edges, second_allowed, second_free, statistics
    )
    batch = {
        name: torch.cat((inputs[name], second[name]), dim=0)
        for name in inputs if name != "edge_index"
    }
    batch["edge_index"] = torch.cat((edges, second_edges + len(vertices)), dim=1)
    graph_ids = torch.cat((torch.zeros(len(vertices), dtype=torch.long),
                           torch.ones(len(second_vertices), dtype=torch.long)))
    batch_origin, batch_neighbor = batch["edge_index"]
    assert torch.all(graph_ids[batch_origin] == graph_ids[batch_neighbor])
    with torch.no_grad():
        batch_prediction = geometric_model(**batch)
        second_prediction = geometric_model(**second)
    batch_error = _maximum_error(
        batch_prediction, torch.cat((reference_prediction, second_prediction), dim=0)
    )
    perturbed_batch = dict(batch)
    perturbed_batch["node_features"] = batch["node_features"].clone()
    perturbed_batch["node_features"][len(vertices):, :5] += 0.713
    with torch.no_grad():
        isolation_error = _maximum_error(
            geometric_model(**perturbed_batch)[:len(vertices)], batch_prediction[:len(vertices)]
        )

    # Exactly one synthetic optimizer update, followed by a second backward.
    gradient_model = ResidualExpert()
    damaged = torch.zeros_like(free)
    damaged[torch.where(free)[0][:2]] = True
    normal_free = free & ~damaged
    target = torch.zeros_like(inputs["positions"])
    target[damaged] = (
        -0.12 * inputs["normals"][damaged] + 0.03 * inputs["positions"][damaged]
    )
    optimizer = torch.optim.SGD(gradient_model.parameters(), lr=0.01)
    first_loss, first_records = graph_loss(
        gradient_model(**inputs), target, allowed, damaged, normal_free, edges,
        torch.zeros(len(vertices), dtype=torch.long),
    )
    first_loss.backward()
    first_gradients = _gradient_norms(gradient_model)
    active_heads = ("alpha_head.2.weight", "alpha_head.2.bias", "beta_head.weight", "beta_head.bias")
    assert all(first_gradients[name] > 0 for name in active_heads)
    assert all(value == 0 for name, value in first_gradients.items() if name not in active_heads)
    optimizer.step()
    optimizer.zero_grad(set_to_none=True)
    second_loss, second_records = graph_loss(
        gradient_model(**inputs), target, allowed, damaged, normal_free, edges,
        torch.zeros(len(vertices), dtype=torch.long),
    )
    second_loss.backward()
    second_gradients = _gradient_norms(gradient_model)
    assert all(math.isfinite(value) for value in second_gradients.values())
    for module_name in expected_modules:
        assert any(value > 0 for name, value in second_gradients.items()
                   if name.startswith(module_name + ".")), module_name

    return {
        "cycle_id": "M6-SHAPE-TRAIN-001",
        "qa_scope": "synthetic structural and gradient QA",
        "passed": True,
        "public_validation_observations_loaded": 0,
        "reserved_test_observations_loaded": 0,
        "formal_training_runs": 0,
        "synthetic_optimizer_updates": 1,
        "synthetic_gradient_backward_passes": 2,
        "torch_version": torch.__version__,
        "torch_threads": torch.get_num_threads(),
        "parameter_count": parameter_count,
        "parameters_by_module": parameter_modules,
        "message_steps": model.message_steps,
        "initial_noop_nonzero_values": int(torch.count_nonzero(initial_prediction)),
        "nonzero_head_prediction_norm": float(reference_prediction[free].norm()),
        "fixed_nonzero_values": int(torch.count_nonzero(reference_prediction[~free])),
        "node_and_edge_permutation_max_error": permutation_error,
        "SO3_translation_scale_checks": transform_records,
        "batch_graph_nodes": [len(vertices), len(second_vertices)],
        "batch_directed_edges": [edges.shape[1], second_edges.shape[1]],
        "cross_graph_edge_count": 0,
        "batch_vs_single_max_error": batch_error,
        "other_graph_feature_perturbation_max_error": isolation_error,
        "first_backward_parameter_gradient_norms": first_gradients,
        "after_one_update_parameter_gradient_norms": second_gradients,
        "first_synthetic_loss": float(first_loss.detach()),
        "after_one_update_synthetic_loss": float(second_loss.detach()),
        "first_synthetic_graph_records": first_records,
        "after_one_update_synthetic_graph_records": second_records,
        "loss_checks": _loss_checks(),
        "wall_seconds": time.perf_counter() - started,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("MODEL_QA.json"))
    args = parser.parse_args()
    result = run_qa()
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "parameter_count": result["parameter_count"],
                      "synthetic_optimizer_updates": result["synthetic_optimizer_updates"],
                      "wall_seconds": result["wall_seconds"], "output": str(args.output)}))
