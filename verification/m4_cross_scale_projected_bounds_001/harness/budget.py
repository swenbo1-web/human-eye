"""Use the retained interprocess attempt ledger without any model slots."""

from common import PRIOR, SLOTS, load


_ledger = load('_projected_bounds_retained_ledger', PRIOR / 'harness/budget.py')
LIMITS = {'Blender_start_attempts': 6, 'all_rasters': 18, 'consumer_tasks': 0,
          'tools_per_slot': 2, 'rasters_by_slot': {label: 3 for label in SLOTS}}
_ledger.LIMITS = LIMITS
Budget, encoded, save = _ledger.Budget, _ledger.encoded, _ledger.save
