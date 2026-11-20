"""Use the retained interprocess ledger with the six registered read-only slots."""

from common import PRIOR, SLOTS, load


_ledger = load('_local_first_original_ledger', PRIOR / 'harness/budget.py')
LIMITS = {'Blender_start_attempts': 6, 'all_rasters': 24, 'consumer_tasks': 0,
          'tools_per_slot': 2, 'rasters_by_slot': {label: 4 for label in SLOTS}}
_ledger.LIMITS = LIMITS
Budget, encoded, save = _ledger.Budget, _ledger.encoded, _ledger.save
