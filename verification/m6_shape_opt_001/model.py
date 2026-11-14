"""The fixed 6339-parameter locating and conditional-correction mesh expert."""

import importlib.util
from pathlib import Path

import torch
from torch import nn
from torch.nn import functional as F


_PRIOR_MODEL_PATH = Path(__file__).resolve().parent.parent / "m6_shape_train_001/model.py"
_prior_spec = importlib.util.spec_from_file_location("_m6_shape_train_001_model", _PRIOR_MODEL_PATH)
_prior_model = importlib.util.module_from_spec(_prior_spec)
_prior_spec.loader.exec_module(_prior_model)
graph_loss = _prior_model.graph_loss


def gate_prediction(conditional, scores, free_mask, tau):
    """Apply the frozen strict score threshold and the existing free domain."""
    selected = (scores.to(dtype=torch.float64) > tau) & free_mask
    return conditional.masked_fill(~selected.unsqueeze(1), 0.0)


class ResidualExpert(_prior_model.ResidualExpert):
    """Reuse the original module initialization before adding 49 zero parameters."""

    def __init__(self):
        super().__init__()
        self.localization_head = nn.Linear(48, 1)
        nn.init.zeros_(self.localization_head.weight)
        nn.init.zeros_(self.localization_head.bias)

    def forward_components(
        self, node_features, edge_features, positions, normals, edge_index, free_mask
    ):
        """Return conditional vectors u, logits z and scores p through six inputs.

        The shared cell and vector equations match the frozen first-round
        implementation. Localization uses the existing final and initial state.
        Labels, reference geometry and source metadata stay outside this call.
        """
        origin, neighbor = edge_index
        node_count = node_features.shape[0]
        degree = torch.bincount(origin, minlength=node_count).clamp_min(1)
        divisor = degree.to(dtype=node_features.dtype).unsqueeze(1)
        initial = self.node_encoder(node_features)
        hidden = initial
        for _ in range(self.message_steps):
            message = self.edge_mlp(
                torch.cat((hidden[origin], hidden[neighbor], edge_features), dim=1)
            )
            aggregate = hidden.new_zeros((node_count, self.width))
            aggregate.index_add_(0, origin, message)
            aggregate = aggregate / divisor
            update = self.node_update(torch.cat((hidden, aggregate, initial), dim=1))
            hidden = self.layer_norm(hidden + 0.1 * update)

        final_and_initial = torch.cat((hidden, initial), dim=1)
        alpha = self.alpha_head(final_and_initial)
        beta = self.beta_head(message)
        relative = positions[neighbor] - positions[origin]
        vector_aggregate = positions.new_zeros((node_count, 3))
        vector_aggregate.index_add_(0, origin, beta * relative)
        conditional = alpha * normals + vector_aggregate / divisor
        conditional = conditional.masked_fill(~free_mask.unsqueeze(1), 0.0)
        logits = self.localization_head(final_and_initial).squeeze(1)
        scores = torch.sigmoid(logits)
        return conditional, logits, scores

    def forward(
        self, node_features, edge_features, positions, normals, edge_index, free_mask
    ):
        conditional, _, scores = self.forward_components(
            node_features, edge_features, positions, normals, edge_index, free_mask
        )
        return scores.unsqueeze(1) * conditional

    def hard_prediction(
        self, node_features, edge_features, positions, normals, edge_index, free_mask,
        *, tau,
    ):
        conditional, _, scores = self.forward_components(
            node_features, edge_features, positions, normals, edge_index, free_mask
        )
        return gate_prediction(conditional, scores, free_mask, tau)


def optimization_loss(
    conditional,
    logits,
    scores,
    target,
    allowed_mask,
    damaged_mask,
    normal_free_mask,
    edge_index,
    graph_index,
):
    """Equal-graph original soft loss plus the two fixed supervised terms.

    Original graph-loss records retain their denominators and component values.
    New denominator records distinguish support, normal-free and control-free
    groups. Empty reported means are None and their differentiable terms are 0.
    """
    node_count = conditional.shape[0]
    if logits.shape != (node_count,) or scores.shape != (node_count,):
        raise ValueError("localization logits and scores must have shape [N]")
    soft = scores.unsqueeze(1) * conditional
    original_loss, records = graph_loss(
        soft, target, allowed_mask, damaged_mask, normal_free_mask,
        edge_index, graph_index,
    )
    conditional_errors = (conditional - target).square().sum(dim=1)
    positive_errors = F.softplus(-logits)
    negative_errors = F.softplus(logits)
    free_mask = damaged_mask | normal_free_mask
    additional_losses = []
    for graph_id, record in zip(torch.unique(graph_index, sorted=True), records):
        in_graph = graph_index == graph_id
        support = in_graph & damaged_mask
        normal_free = in_graph & normal_free_mask
        free = in_graph & free_mask
        denominators = {
            "S": int(support.sum()),
            "N_F": int(normal_free.sum()),
            "F": int(free.sum()),
        }
        zero = conditional_errors[in_graph].sum() * 0.0 + logits[in_graph].sum() * 0.0
        conditional_mean = conditional_errors[support].mean() if denominators["S"] else zero
        positive_mean = positive_errors[support].mean() if denominators["S"] else zero
        normal_mean = negative_errors[normal_free].mean() if denominators["N_F"] else zero
        control_mean = negative_errors[free].mean() if denominators["F"] else zero
        if record["normal_control"]:
            localization_mean = control_mean
            group_weights = {"F": 1.0 if denominators["F"] else 0.0}
        else:
            active_groups = int(denominators["S"] > 0) + int(denominators["N_F"] > 0)
            localization_mean = (positive_mean + normal_mean) / active_groups
            group_weights = {
                "S": 1.0 / active_groups,
                "N_F": 1.0 / active_groups if denominators["N_F"] else 0.0,
            }
        conditional_loss = 0.4 * conditional_mean
        localization_loss = 0.05 * localization_mean
        additional_losses.append(conditional_loss + localization_loss)
        record.update(
            base_total_loss=record["total_loss"],
            conditional_support_denominator=denominators["S"],
            conditional_support_mse=float(conditional_mean.detach()) if denominators["S"] else None,
            conditional_loss=float(conditional_loss.detach()),
            localization_denominators=denominators,
            localization_means={
                "S_positive": float(positive_mean.detach()) if denominators["S"] else None,
                "N_F_negative": float(normal_mean.detach()) if denominators["N_F"] else None,
                "F_control_negative": float(control_mean.detach()) if record["normal_control"] and denominators["F"] else None,
            },
            localization_group_weights=group_weights,
            localization_loss_unweighted=float(localization_mean.detach()),
            localization_loss=float(localization_loss.detach()),
        )
        record["total_loss"] = record["base_total_loss"] + record["conditional_loss"] + record["localization_loss"]
    return original_loss + torch.stack(additional_losses).mean(), records
