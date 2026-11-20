"""Apply the frozen qualification and formal budgets to the retained ledger."""

import time
import uuid

from common import PRIOR, SLOTS, load


_ledger = load('_dense_panel_retained_ledger', PRIOR / 'harness/budget.py')
LIMITS = {
    'Blender_start_attempts': 8,
    'all_rasters': 84,
    'consumer_tasks': 6,
    'tools_per_slot': 12,
    'specific_tool_limit': {'QP': 1},
    'rasters_by_slot': {slot: 6 if phase == 'qualification' else 12
                        for slot, (_, phase) in SLOTS.items()},
}
_ledger.LIMITS = LIMITS
encoded, save = _ledger.encoded, _ledger.save


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
            counts, slot = snapshot['counts'], snapshot['slots'].get(label, {})
            if kind in ('Blender_start', 'consumer_task') and any(
                    row['claim']['kind'] == kind and row['claim']['label'] == label
                    for row in snapshot['records']):
                raise RuntimeError('registered_slot_already_admitted/' + kind)
            if kind == 'Blender_start' and counts['Blender_start_attempts'] >= LIMITS['Blender_start_attempts']:
                raise RuntimeError('Blender_start_budget_exhausted')
            if kind == 'consumer_task' and counts['consumer_admissions'] >= LIMITS['consumer_tasks']:
                raise RuntimeError('model_consumer_budget_exhausted')
            tool_limit = LIMITS['specific_tool_limit'].get(label, LIMITS['tools_per_slot'])
            if kind == 'business_tool' and slot.get('business_admissions', 0) >= tool_limit:
                raise RuntimeError('business_tool_budget_exhausted')
            if kind == 'raster_attempt' and (counts['all_raster_upper'] >= LIMITS['all_rasters'] or
                    slot.get('raster_upper', 0) >= LIMITS['rasters_by_slot'][label]):
                raise RuntimeError('raster_budget_exhausted')
            token = uuid.uuid4().hex
            save(self.claims / (token + '.json'), {'token': token, 'kind': kind, 'phase': phase, 'label': label,
                'reserved_upper_bound': upper, 'claimed_ns': time.perf_counter_ns()})
            return token
