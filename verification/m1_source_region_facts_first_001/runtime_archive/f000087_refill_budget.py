"""Bounded engineering allowances for optional resolution-dependent labels.

These are compute limits, not action permission or certified product SLOs.
The router derives them from its own raster size, never from model requests or
collector receipts. Attention's separate internal 40ms limit is unchanged.
"""
from dataclasses import dataclass


POLICY_REVISION = 'resolution_refill_v1_20261027'
POLICY_MODE = 'resolution'


@dataclass(frozen=True, slots=True)
class RefillBudget:
    quad_size: int | None
    incremental_ms: float
    shared_ms: float
    mode: str

    def descriptor(self):
        return {'policy_revision': POLICY_REVISION, 'mode': self.mode,
                'quad_size': self.quad_size, 'incremental_ms': self.incremental_ms,
                'shared_ms': self.shared_ms,
                'scope': 'optional_refill_incremental_and_post_Q1_Q3_wall_only',
                'basis': 'bounded_engineering_allowance_not_product_SLO',
                'execution_authority': False}


def refill_budget_for_quad_size(quad_size=None):
    # Existing direct helper callers keep their original fixed allowance.
    if quad_size is None:
        return RefillBudget(None, 5.0, 40.0, 'legacy_helper_fixed')
    if type(quad_size) is not int or not 64 <= quad_size <= 512:
        raise ValueError('Refill raster size must be an integer from 64 to 512')
    if POLICY_MODE not in {'fixed', 'resolution'}:
        raise ValueError('Unknown internal refill budget policy')
    if POLICY_MODE == 'fixed' or quad_size <= 256:
        return RefillBudget(quad_size, 5.0, 40.0, POLICY_MODE)
    if quad_size <= 384:
        fraction = (quad_size ** 2 - 256 ** 2) / (384 ** 2 - 256 ** 2)
        local, shared = 5.0 + 3.0 * fraction, 40.0 + 24.0 * fraction
    else:
        # The 512 anchor is an exploration hypothesis to test independently;
        # it is not certified merely by extrapolating the 384 measurements.
        fraction = (quad_size ** 2 - 384 ** 2) / (512 ** 2 - 384 ** 2)
        local, shared = 8.0 + 4.0 * fraction, 64.0 + 32.0 * fraction
    return RefillBudget(quad_size, round(local, 4), round(shared, 4), POLICY_MODE)
