"""Apply this batch's fixed caps to the established interprocess ledger."""

import time
import uuid

from common import PRIOR, SLOTS, load


_ledger = load('_cross_task_prior_ledger', PRIOR / 'harness/budget.py')
LIMITS = {'Blender_start_attempts': 4, 'all_rasters': 48, 'consumer_tasks': 2,
          'tools_per_slot': 12, 'rasters_by_slot': {slot: 12 for slot in SLOTS}}
_ledger.LIMITS = LIMITS
encoded = _ledger.encoded
save = _ledger.save


class Budget(_ledger.Budget):
    def reserve(self, kind, label, phase='qualification', upper=1):
        if label not in SLOTS or phase != SLOTS[label][1] or type(upper) is not int or upper != 1:
            raise ValueError('registered_slot_phase_and_unit_required')
        if kind not in ('Blender_start', 'consumer_task', 'business_tool', 'raster_attempt'):
            raise ValueError('unknown_budget_kind')
        if kind == 'consumer_task' and phase != 'formal':
            raise ValueError('qualification_model_consumer_forbidden')
        with self.lock():
            snapshot = self._snapshot()
            counts = snapshot['counts']
            slot = snapshot['slots'].get(label, {})
            if kind in ('Blender_start', 'consumer_task') and any(
                    row['claim']['kind'] == kind and row['claim']['label'] == label
                    for row in snapshot['records']):
                raise RuntimeError('registered_slot_already_admitted/' + kind)
            if kind == 'Blender_start' and counts['Blender_start_attempts'] >= LIMITS['Blender_start_attempts']:
                raise RuntimeError('Blender_start_budget_exhausted')
            if kind == 'consumer_task' and counts['consumer_admissions'] >= LIMITS['consumer_tasks']:
                raise RuntimeError('model_consumer_budget_exhausted')
            if kind == 'business_tool' and slot.get('business_admissions', 0) >= LIMITS['tools_per_slot']:
                raise RuntimeError('business_tool_budget_exhausted')
            if kind == 'raster_attempt' and (counts['all_raster_upper'] >= LIMITS['all_rasters'] or
                    slot.get('raster_upper', 0) >= LIMITS['rasters_by_slot'][label]):
                raise RuntimeError('raster_budget_exhausted')
            token = uuid.uuid4().hex
            save(self.claims / (token + '.json'), {'token': token, 'kind': kind, 'phase': phase, 'label': label,
                'reserved_upper_bound': upper, 'claimed_ns': time.perf_counter_ns()})
            return token
