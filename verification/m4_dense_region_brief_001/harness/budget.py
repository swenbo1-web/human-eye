"""Retain the qualified ledger with the single-slot projection test limits."""

from common import DENSE, load


_retained = load('_dense_region_brief_budget', DENSE / 'harness/budget.py')
LIMITS = {'Blender_start_attempts': 1, 'all_rasters': 2, 'consumer_tasks': 0,
          'tools_per_slot': 1, 'specific_tool_limit': {'QP': 1}, 'rasters_by_slot': {'QP': 2}}
_retained.LIMITS = _retained._ledger.LIMITS = LIMITS
Budget, encoded, save = _retained.Budget, _retained.encoded, _retained.save
