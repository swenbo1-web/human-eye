"""Retain the per-slot ledger and identical A/B limits."""

from common import FORMAL, SLOTS, load_retained


previous = load_retained('_task_entry_formal_budget', FORMAL / 'harness/budget.py')
if previous.SLOTS is not SLOTS:
    raise ValueError('task_entry_budget_loaded_wrong_slots')
LIMITS = {'Blender_start_attempts': 4, 'all_rasters': 48, 'consumer_tasks': 2,
          'tools_per_slot': 12, 'rasters_by_slot': {label: 12 for label in SLOTS}}
previous.LIMITS = previous._ledger.LIMITS = LIMITS
Budget, encoded, save = previous.Budget, previous.encoded, previous.save
