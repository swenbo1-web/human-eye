"""Enforce two owned slots, four business admissions and three attempt callbacks."""

from common import FORMAL, load_retained


previous = load_retained('_m4_active_view_retained_budget', FORMAL / 'harness/budget.py')
LIMITS = {'Blender_start_attempts': 2, 'all_rasters': 3, 'consumer_tasks': 0,
          'tools_per_slot': 2, 'rasters_by_slot': {'A': 1, 'B': 2}}
previous.LIMITS = previous._ledger.LIMITS = LIMITS
Budget, encoded, save = previous.Budget, previous.encoded, previous.save
