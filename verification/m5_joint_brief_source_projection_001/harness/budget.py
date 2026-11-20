"""Enforce one owned qualification, one public call, and three rasters."""

from common import DENSE, load_retained


previous = load_retained('_m5_projection_dense_budget', DENSE / 'harness/budget.py')
LIMITS = {'Blender_start_attempts': 1, 'all_rasters': 3, 'consumer_tasks': 0,
          'tools_per_slot': 1, 'specific_tool_limit': {'B': 1}, 'rasters_by_slot': {'B': 3}}
previous.LIMITS = previous._ledger.LIMITS = LIMITS
Budget, encoded, save = previous.Budget, previous.encoded, previous.save
