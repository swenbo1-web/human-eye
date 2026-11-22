"""Retain the earlier durable ledger with four registered Yanyite slots."""

from common import FORMAL, SLOTS, load_retained


previous = load_retained('_yanyite_budget',FORMAL/'harness/budget.py')
if previous.SLOTS is not SLOTS:
    raise ValueError('wrong_ledger_slot_registration')
LIMITS = {'Blender_start_attempts':4,'all_rasters':48,'consumer_tasks':2,
          'tools_per_slot':12,'rasters_by_slot':dict.fromkeys(SLOTS,12)}
previous.LIMITS = previous._ledger.LIMITS = LIMITS
Budget, encoded, save = previous.Budget, previous.encoded, previous.save
