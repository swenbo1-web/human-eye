"""Use the established interprocess ledger with this probe's fixed caps."""

from common import GLOBAL_HARNESS, load


_ledger = load('_cross_scale_original_budget', GLOBAL_HARNESS / 'budget.py')
_ledger.LIMITS = {'Blender_start_attempts': 1, 'all_rasters': 6, 'consumer_tasks': 0,
                  'business_tools_per_slot': 2}

Budget = _ledger.Budget
encoded = _ledger.encoded
save = _ledger.save
