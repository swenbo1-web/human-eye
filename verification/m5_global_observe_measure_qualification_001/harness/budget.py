"""Apply the single paired qualification caps to the retained unit ledger."""

from common import DENSE, SLOTS, load_retained


previous = load_retained('_m5_global_dense_budget', DENSE / 'harness/budget.py')
LIMITS = {'Blender_start_attempts': 2, 'all_rasters': 6, 'consumer_tasks': 0,
          'tools_per_slot': 2, 'specific_tool_limit': {'A': 2, 'B': 1},
          'rasters_by_slot': {label: 3 for label in SLOTS}}
previous.LIMITS = previous._ledger.LIMITS = LIMITS
Budget, encoded, save = previous.Budget, previous.encoded, previous.save
