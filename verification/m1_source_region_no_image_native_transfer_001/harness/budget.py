"""Use the same persisted per-slot accounting as the paired formal baseline."""

from common import FORMAL, SLOTS, load_retained


previous = load_retained('_perf050_formal_budget', FORMAL / 'harness/budget.py')
if previous.SLOTS is not SLOTS:
    raise ValueError('pilot_budget_loaded_wrong_slots')
LIMITS = {'Blender_start_attempts': 8, 'all_rasters': 96, 'consumer_tasks': 6,
          'tools_per_slot': 12, 'rasters_by_slot': {label: 12 for label in SLOTS}}
previous.LIMITS = previous._ledger.LIMITS = LIMITS
Budget, encoded, save = previous.Budget, previous.encoded, previous.save
