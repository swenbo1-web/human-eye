"""Bind the retained reservation ledger to the frozen formal-only caps."""

from common import OLD, ORDER, load

_retained = load('_rail_original_budget', OLD / 'harness/budget.py')
LIMITS = {'Blender_start_attempts': 6, 'all_rasters': 72, 'consumer_tasks': 6,
          'tools_per_slot': 12, 'rasters_by_slot': dict.fromkeys(ORDER, 12)}
_retained.LIMITS = _retained._ledger.LIMITS = LIMITS
Budget, encoded, save = _retained.Budget, _retained.encoded, _retained.save
