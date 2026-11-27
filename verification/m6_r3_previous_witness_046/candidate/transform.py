"""Single local transformation of the frozen C exact solver."""
from __future__ import annotations

import ast


_HELPER = r'''
class _PreviousWitnessProjection(_FastWitnessProjection):
    """One lazily allocated, strictly tested predecessor direction."""

    __slots__ = ()
    _PREVIOUS_BUILD_COST = 18
    _PREVIOUS_SELECTION_COST = 2

    @staticmethod
    def _bounded_axis(descriptor):
        if descriptor[0] not in ('points', 'face', 'edge', 'edges'):
            return None
        for item in descriptor[1:]:
            if type(item) is tuple:
                if len(item) != 3 or any(type(x) is not int or x.bit_length() > 128 for x in item):
                    return None
            elif type(item) is not bool and (type(item) is not int or item.bit_length() > 128):
                return None
        axis = _fast_descriptor_direction(descriptor)
        if axis is None:
            return None
        scale = math.gcd(axis[0], math.gcd(axis[1], axis[2]))
        if not scale:
            return None
        if next(x for x in axis if x) < 0:
            scale = -scale
        primitive = tuple(x // scale for x in axis)
        return primitive if all(x.bit_length() <= 128 for x in primitive) else None

    @classmethod
    def _make_previous(cls, previous, best, prep_a, prep_b, budget):
        budget.consume(cls._PREVIOUS_BUILD_COST, 'previous_witness_build')
        bn, bd, current = best
        if not (bn > 0 and bd > 0 and bn.bit_length() <= 512 and bd.bit_length() <= 512):
            return None, 'rank_bits'
        axis = cls._bounded_axis(previous)
        current_axis = cls._bounded_axis(current)
        if axis is None or current_axis is None:
            return None, 'direction_unavailable'
        if axis == current_axis:
            return None, 'parallel'
        norm_sq = _dot(axis, axis)
        p = cls()
        p.axis, p.norm_sq, p.best = axis, norm_sq, (bn, bd)
        p.cutoff_strict = p.cutoff_tie = math.isqrt((norm_sq * bn) // bd)
        p.node_a, p.node_b = {}, {}
        p.tri_a, p.tri_b = {}, {}
        p.prep_a, p.prep_b = prep_a, prep_b
        p.epoch = -1
        return p, None

    def _tri_interval(self, idx, tri_cache, prep_side, budget):
        hit = tri_cache.get(idx)
        if hit is not None:
            return hit
        points = prep_side[idx][0]
        budget.tick('previous_witness_tri_dots', len(points))
        dots = [_dot(p, self.axis) for p in points]
        hit = min(dots), max(dots)
        tri_cache[idx] = hit
        return hit

    def _reserve(self, left, right, budget):
        budget.consume(self._PREVIOUS_SELECTION_COST, 'previous_witness_selection')
        return 1 + self._cold_interval_upper(left, self.node_a) + self._cold_interval_upper(right, self.node_b)

    def _gap(self, left, right, budget):
        budget.tick('previous_witness_tests')
        la = self._node_interval(left, self.node_a, self.tri_a, self.prep_a, budget)
        rb = self._node_interval(right, self.node_b, self.tri_b, self.prep_b, budget)
        if la is None or rb is None:
            return 0
        return max(0, la[0] - rb[1], rb[0] - la[1])


class _PreviousWitnessTrial:
    """Single capture retained until the bound changes or the trial is retired."""

    __slots__ = ('descriptor', 'pair', 'tests_at_capture', 'prunes_at_capture',
                 'projection', 'misses', 'retired')
    _MISS_LIMIT = 8

    def __init__(self, descriptor, pair, counts):
        self.descriptor, self.pair = descriptor, pair
        self.tests_at_capture = counts.get('witness_projection_tests', 0)
        self.prunes_at_capture = counts.get('witness_projection_pruned_pairs', 0)
        self.projection = None
        self.misses = 0
        self.retired = False
        counts['previous_witness_held_source_pair'] = pair

    def retire(self, counts, reason):
        if not self.retired:
            self.retired = True
            counts['previous_witness_retired_reason'] = reason

    @staticmethod
    def _paid(credit, upper, operation):
        counts = credit.budget.counts
        before = counts['work_units']
        try:
            return credit.try_run(upper, operation)
        finally:
            spent = counts['work_units'] - before
            if spent:
                counts['previous_witness_work_units'] = counts.get('previous_witness_work_units', 0) + spent

    def prunes(self, left, right, best, best_pair, completed, prepared, credit):
        if (self.retired or completed < _FAST_WP_AFTER_COMPLETED
                or (left[7] is not None and right[7] is not None)
                or left[6] > 512 or right[6] > 512):
            return False
        budget = credit.budget
        counts = budget.counts
        if self.projection is None:
            if counts.get('witness_projection_pruned_pairs', 0) != self.prunes_at_capture:
                self.retire(counts, 'current_projection_productive')
                return False
            if counts.get('witness_projection_tests', 0) <= self.tests_at_capture:
                return False
            build = _PreviousWitnessProjection
            ok, value = self._paid(credit, build._PREVIOUS_BUILD_COST,
                lambda: build._make_previous(self.descriptor, best, prepared[0], prepared[1], budget))
            if not ok:
                return False
            counts['previous_witness_builds'] = 1
            self.projection, reason = value
            if self.projection is None:
                self.retire(counts, reason)
                return False
            counts['previous_witness_enabled_after_exact'] = completed

        p = self.projection
        ok, upper = self._paid(credit, p._PREVIOUS_SELECTION_COST, lambda: p._reserve(left, right, budget))
        if not ok:
            return False
        before_visits = counts.get('witness_projection_node_visits', 0)
        try:
            ok, gap = self._paid(credit, upper, lambda: p._gap(left, right, budget))
        finally:
            extra_visits = counts.get('witness_projection_node_visits', 0) - before_visits
            if extra_visits:
                counts['previous_witness_node_visits'] = counts.get('previous_witness_node_visits', 0) + extra_visits
        if not ok:
            return False
        if gap <= p.cutoff_strict:
            self.misses += 1
            if self.misses == self._MISS_LIMIT:
                self.retire(counts, 'paid_non_prune_streak')
            return False

        self.misses = 0
        if _NODE_PRUNE_OBSERVER is not None:
            _NODE_PRUNE_OBSERVER({
                'left': left, 'right': right, 'axis': p.axis, 'norm_sq': p.norm_sq,
                'best': p.best, 'best_pair': best_pair, 'previous_pair': self.pair,
                'epoch': p.epoch, 'strict': True, 'source': 'previous_witness_slab',
                'gap': gap, 'cutoff': p.cutoff_strict,
            })
        pairs = left[6] * right[6]
        counts['previous_witness_node_calls_pruned'] = counts.get('previous_witness_node_calls_pruned', 0) + 1
        counts['previous_witness_pruned_pairs'] = counts.get('previous_witness_pruned_pairs', 0) + pairs
        counts['witness_projection_pruned_pairs'] = counts.get('witness_projection_pruned_pairs', 0) + pairs
        counts['witness_projection_node_pruned_pairs'] = counts.get('witness_projection_node_pruned_pairs', 0) + pairs
        counts['subtree_pruned_pairs'] += pairs
        credit.earn_node_prune(2)
        return True


'''


def transform(source):
    out = source.decode('utf-8')

    def once(a, b):
        nonlocal out
        assert out.count(a) == 1, a
        out = out.replace(a, b, 1)

    anchor = 'def _nearest_tree(prepared, roots, budget, witness_pair=None, *, projection_mode=None):\n'
    once(anchor, _HELPER + anchor)
    once('    fast_proj_epoch = 0\n\n    def invalidate_fast_proj():',
         '    fast_proj_epoch = 0\n    previous_trial = None\n\n    def invalidate_fast_proj():')
    once('nonlocal best, best_pair, best_floor, tie_floor, completed_exact, projection\n',
         'nonlocal best, best_pair, best_floor, tie_floor, completed_exact, projection, previous_trial\n')
    old = '                    if comparison < 0 or (comparison == 0 and pair < best_pair):\n'
    # The following anchor includes best_floor, distinguishing the fast tree
    # from any other identical-looking exact comparison elsewhere.
    old = ('                    if comparison < 0 or (comparison == 0 and pair < best_pair):\n'
           '                        best, best_pair = candidate, pair\n'
           '                        best_floor = best[0] // best[1]\n')
    once(old,
         '                    if comparison < 0 or (comparison == 0 and pair < best_pair):\n'
         '                        if previous_trial is not None:\n'
         "                            previous_trial.retire(budget.counts, 'best_changed')\n"
         '                        elif (proj_enabled and fast_ints and shift == 0 and comparison < 0\n'
         '                              and best[0] > 0 and candidate[0] > 0):\n'
         '                            previous_trial = _PreviousWitnessTrial(best[2], best_pair, budget.counts)\n'
         '                        best, best_pair = candidate, pair\n'
         '                        best_floor = best[0] // best[1]\n')
    old = ('                        credit.earn_node_prune(saved_np)\n'
           '                        continue\n'
           '        if left[7] is not None and right[7] is not None:\n')
    once(old,
         '                        credit.earn_node_prune(saved_np)\n'
         '                        continue\n'
         '            if previous_trial is not None and previous_trial.prunes(\n'
         '                    left, right, best, best_pair, completed_exact, prepared, credit):\n'
         '                continue\n'
         '        if left[7] is not None and right[7] is not None:\n')
    defs = lambda code: {n.name:ast.dump(n) for n in ast.parse(code).body
                         if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
    original, changed = defs(source), defs(out)
    assert changed.keys() - original.keys() == {'_PreviousWitnessProjection','_PreviousWitnessTrial'}
    assert {n for n in original if original[n] != changed[n]} == {'_nearest_tree'}
    return out.encode('utf-8')
