"""CF view ranking and finite-action residual learning from real feedback."""

import numpy as np

from ._cf_features import (
    ACTION_COLUMNS,
    CANONICAL_STEPS,
    FIXED_ORDER,
    VIEW_COLUMNS,
    ConditionalConstant,
    FiniteAction,
    action_features,
    command_group,
    geometry_delta,
    triangle_pair_distance,
    view_features,
)


EXPERIENCE_CAPACITY = 4096
_VIEW_SHAPE = (len(FIXED_ORDER), len(VIEW_COLUMNS))


def sigmoid(scores):
    """Logistic link without overflow for either score sign."""
    return np.exp(-np.logaddexp(0.0, -scores))


class LinearHead:
    """Linear readout on a frozen standardized linear or quadratic basis."""

    def __init__(self, mean, scale, weights, *, quadratic, regularization, view):
        self.mean = np.array(mean, dtype=np.float64, copy=True)
        self.scale = np.array(scale, dtype=np.float64, copy=True)
        self.weights = np.array(weights, dtype=np.float64, copy=True)
        self.quadratic = quadratic
        self.regularization = regularization
        self.view = view
        self._products = np.triu_indices(len(self.mean)) if quadratic else None

    @staticmethod
    def transform(features, *, view):
        raw = np.asarray(features, dtype=np.float64)
        if not view:
            return raw
        transformed = raw.copy()
        np.log1p(transformed[..., 2:], out=transformed[..., 2:])
        return transformed

    def design(self, features):
        raw = np.asarray(features, dtype=np.float64)
        dimensions = len(self.mean)
        design = np.empty((*raw.shape[:-1], len(self.weights)), dtype=np.float64)
        base = design[..., :dimensions]
        base[...] = raw
        if self.view:
            np.log1p(base[..., 2:], out=base[..., 2:])
        base -= self.mean
        base /= self.scale
        if self._products is not None:
            first, second = self._products
            np.multiply(base[..., first], base[..., second], out=design[..., dimensions:-1])
        design[..., -1] = 1.0
        return design

    def scores(self, features):
        return self.design(features) @ self.weights

    def rank(self, features):
        return tuple(map(int, np.argsort(-self.scores(features), kind="stable")))

    def predict_delta(self, features, meters):
        return float(meters * (features[1] + self.scores(features)))

    def _update(self, design, error):
        rate = .05 / (1.0 + design @ design)
        self.weights[:-1] *= 1.0 - rate * self.regularization
        self.weights -= rate * error * design

    def learn_view(self, row, safe):
        design = self.design(row)
        error = sigmoid(design @ self.weights) - safe
        self._update(design, error)

    def learn_action(self, features, residual):
        design = self.design(features)
        error = design @ self.weights - residual
        self._update(design, error)

    def clone(self):
        return type(self)(self.mean, self.scale, self.weights, quadratic=self.quadratic,
                          regularization=self.regularization, view=self.view)


class ExperienceBank:
    """Fixed-capacity per-head ring of keys, observed feedback, and masks."""

    def __init__(self, key_shape, value_shape, mask_shape, *, capacity=EXPERIENCE_CAPACITY):
        self.capacity = capacity
        self.writes = 0
        self.keys = np.empty((capacity, *key_shape), dtype=np.float64)
        self.values = np.empty((capacity, *value_shape), dtype=np.float64)
        self.known = np.empty((capacity, *mask_shape), dtype=np.bool_)

    def __len__(self):
        return min(self.writes, self.capacity)

    def append(self, key, values, mask=True):
        slot = self.writes % self.capacity
        self.keys[slot] = key
        self.values[slot] = values
        self.known[slot] = mask
        self.writes += 1

    def append_view(self, key, index, safe, rays):
        slot = self.writes % self.capacity
        self.keys[slot] = key
        self.values[slot].fill(0.0)
        self.values[slot, index] = (safe, rays)
        self.known[slot].fill(False)
        self.known[slot, index] = True
        self.writes += 1

    def rank(self, key, scale):
        count = len(self)
        if not count:
            return FIXED_ORDER

        delta = self.keys[:count] - key
        delta /= scale
        np.square(delta, out=delta)
        distances = delta.reshape(count, -1).sum(axis=1)
        # Physical order wraps at the next write. Search the older segment first
        # so that an equal distance always selects the earliest live insertion.
        oldest = self.writes % self.capacity if count == self.capacity else 0
        slot = oldest + np.argmin(distances[oldest:])
        if oldest:
            newer = np.argmin(distances[:oldest])
            if distances[newer] < distances[slot]:
                slot = newer

        safe, rays = self.values[slot].T
        known = self.known[slot]
        priority = np.where(known, 2 * safe, 1)
        observed_rays = np.where(known, rays, 0)
        return tuple(map(int, np.lexsort((FIXED_ORDER, observed_rays, -priority))))

    def _copy_into(self, clone):
        count = len(self)
        clone.keys[:count] = self.keys[:count]
        clone.values[:count] = self.values[:count]
        clone.known[:count] = self.known[:count]
        clone.writes = self.writes

    def close(self):
        self.keys = self.values = self.known = None
        self.writes = 0


class CerebellarFlash:
    """Independent CF state for one consumer session."""

    def __init__(self, view_head, action_head, *, retrieval_scale, capacity=EXPERIENCE_CAPACITY):
        self.view_head = view_head.clone() if view_head is not None else None
        self.action_head = action_head.clone() if action_head is not None else None
        self.retrieval_scale = np.array(retrieval_scale, dtype=np.float64, copy=True)
        self.views = ExperienceBank(_VIEW_SHAPE, (_VIEW_SHAPE[0], 2), (_VIEW_SHAPE[0],),
                                    capacity=capacity)
        self.actions = ExperienceBank((len(ACTION_COLUMNS),), (1,), (1,), capacity=capacity)

    def rank_view(self, features, arm):
        if arm == "R":
            return self.views.rank(features, self.retrieval_scale)
        if arm == "L":
            return self.view_head.rank(features)
        return FIXED_ORDER

    def predict_delta(self, features, meters):
        return self.action_head.predict_delta(features, meters)

    def learn_view(self, features, index, safe, rays, *, update_model=True):
        self.views.append_view(features, index, safe, rays)
        if update_model:
            self.view_head.learn_view(features[index], safe)

    def learn_action(self, features, meters, delta):
        residual = delta / meters - features[1]
        self.actions.append(features, residual)
        self.action_head.learn_action(features, residual)

    def clone(self):
        clone = type(self)(self.view_head, self.action_head, retrieval_scale=self.retrieval_scale,
                           capacity=self.views.capacity)
        self.views._copy_into(clone.views)
        self.actions._copy_into(clone.actions)
        return clone

    def close(self):
        self.views.close()
        self.actions.close()
        self.view_head = self.action_head = self.retrieval_scale = None
