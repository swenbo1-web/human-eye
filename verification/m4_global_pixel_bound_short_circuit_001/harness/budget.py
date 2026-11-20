"""Apply the six-slot limits using the retained unit reservation ledger."""

from common import DENSE, SLOTS, load


_retained = load('_pixel_bound_dense_budget', DENSE / 'harness/budget.py')
LIMITS = {'Blender_start_attempts': 6, 'all_rasters': 12, 'consumer_tasks': 0,
          'tools_per_slot': 1, 'specific_tool_limit': {},
          'rasters_by_slot': {label: 2 for label in SLOTS}}
_retained.LIMITS = _retained._ledger.LIMITS = LIMITS
Budget, encoded, save = _retained.Budget, _retained.encoded, _retained.save
