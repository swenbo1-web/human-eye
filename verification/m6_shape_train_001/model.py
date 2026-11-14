"""The fixed 6290-parameter M6 local mesh residual expert and graph loss.

The caller standardizes the five continuous node and four edge features using
training observations. Positions are observation-scale normalized coordinates.
Labels and supervision masks are used only by ``graph_loss``.
"""

import torch
from torch import nn


def _mlp(input_width, hidden_width, output_width):
    return nn.Sequential(
        nn.Linear(input_width, hidden_width),
        nn.SiLU(),
        nn.Linear(hidden_width, output_width),
    )


class ResidualExpert(nn.Module):
    """Shared width-24 cell unrolled exactly 12 times, with SO(3) vector heads."""

    width = 24
    message_steps = 12

    def __init__(self):
        super().__init__()
        self.node_encoder = _mlp(7, 24, 24)
        self.edge_mlp = _mlp(52, 24, 24)
        self.node_update = _mlp(72, 24, 24)
        self.layer_norm = nn.LayerNorm(24)
        self.alpha_head = _mlp(48, 24, 1)
        self.beta_head = nn.Linear(24, 1)
        nn.init.zeros_(self.alpha_head[-1].weight)
        nn.init.zeros_(self.alpha_head[-1].bias)
        nn.init.zeros_(self.beta_head.weight)
        nn.init.zeros_(self.beta_head.bias)

    def forward(
        self, node_features, edge_features, positions, normals, edge_index, free_mask
    ):
        """Return normalized corrections, with fixed/halo rows exactly zero.

        ``edge_index[0]`` is the receiving origin i and ``edge_index[1]`` is j.
        Directed input edges contain no self edges. Different batch graphs use
        disjoint local index ranges. Scalar features are prestandardized.
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

        alpha = self.alpha_head(torch.cat((hidden, initial), dim=1))
        beta = self.beta_head(message)
        relative = positions[neighbor] - positions[origin]
        vector_aggregate = positions.new_zeros((node_count, 3))
        vector_aggregate.index_add_(0, origin, beta * relative)
        correction = alpha * normals + vector_aggregate / divisor
        return correction.masked_fill(~free_mask.unsqueeze(1), 0.0)


def graph_loss(
    prediction,
    target,
    allowed_mask,
    damaged_mask,
    normal_free_mask,
    edge_index,
    graph_index,
):
    """Return an equal-per-graph scalar loss and detached per-graph records.

    Masks are boolean vectors over context nodes. ``damaged_mask`` is S and
    ``normal_free_mask`` is N_F. Under this contract all damaged nodes are free,
    so the complement of their union is the fixed/halo mask. Graph IDs may be
    any nonnegative integers. Empty reported MSE terms are ``None``.
    """
    node_count = prediction.shape[0]
    if prediction.shape != (node_count, 3) or target.shape != prediction.shape:
        raise ValueError("prediction and target must have shape [N, 3]")
    masks = (allowed_mask, damaged_mask, normal_free_mask)
    if any(mask.shape != (node_count,) or mask.dtype != torch.bool for mask in masks):
        raise ValueError("loss masks must be boolean vectors of length N")
    if graph_index.shape != (node_count,) or graph_index.dtype != torch.long:
        raise ValueError("graph_index must be a long vector of length N")
    if edge_index.ndim != 2 or edge_index.shape[0] != 2 or edge_index.dtype != torch.long:
        raise ValueError("edge_index must have shape [2, E] and dtype long")
    if torch.any(damaged_mask & ~allowed_mask):
        raise ValueError("damaged mask must be within the allowed domain")
    if torch.any(normal_free_mask & (~allowed_mask | damaged_mask)):
        raise ValueError("normal free mask must be within allowed normal nodes")
    if torch.any(graph_index < 0) or node_count == 0:
        raise ValueError("graph_index must contain at least one nonnegative graph ID")
    origin, neighbor = edge_index
    if torch.any(origin == neighbor):
        raise ValueError("directed input edges must exclude self edges")
    if torch.any(graph_index[origin] != graph_index[neighbor]):
        raise ValueError("batch input contains a cross-graph edge")

    node_error = (prediction - target).square().sum(dim=1)
    gradient_error = (
        (prediction[neighbor] - prediction[origin])
        - (target[neighbor] - target[origin])
    ).square().sum(dim=1)
    normal_allowed = allowed_mask & ~damaged_mask
    fixed_mask = ~(damaged_mask | normal_free_mask)
    graph_losses = []
    records = []
    for graph_id in torch.unique(graph_index, sorted=True):
        in_graph = graph_index == graph_id
        selections = {
            "A": in_graph & allowed_mask,
            "S": in_graph & damaged_mask,
            "normal_allowed": in_graph & normal_allowed,
            "normal_free": in_graph & normal_free_mask,
            "fixed": in_graph & fixed_mask,
        }
        denominators = {name: int(mask.sum()) for name, mask in selections.items()}
        means = {
            name: node_error[mask].mean()
            for name, mask in selections.items()
            if denominators[name]
        }
        zero = node_error[in_graph].sum() * 0.0
        normal_control = denominators["S"] == 0
        if normal_control:
            point_loss = means.get("A", zero)
        else:
            weights = {"A": 0.2, "S": 0.4, "normal_free": 0.4}
            active_weights = {name: weight for name, weight in weights.items() if name in means}
            point_loss = sum(means[name] * weight for name, weight in active_weights.items())
            point_loss = point_loss / sum(active_weights.values())

        graph_edges = graph_index[origin] == graph_id
        denominators["directed_edges"] = int(graph_edges.sum())
        edge_mean = zero
        if denominators["directed_edges"]:
            edge_mean = gradient_error[graph_edges].mean()
        total = point_loss + 0.05 * edge_mean
        graph_losses.append(total)
        records.append(
            {
                "graph_id": int(graph_id),
                "normal_control": normal_control,
                "denominators": denominators,
                "mse": {
                    name: float(means[name].detach()) if name in means else None
                    for name in selections
                },
                "directed_edge_gradient_mse": float(edge_mean.detach()),
                "point_loss": float(point_loss.detach()),
                "gradient_loss": float((0.05 * edge_mean).detach()),
                "total_loss": float(total.detach()),
            }
        )
    return torch.stack(graph_losses).mean(), records
