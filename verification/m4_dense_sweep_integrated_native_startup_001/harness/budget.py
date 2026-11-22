"""Retain existing per-slot rules and cap the new formal-only ledger."""

from pathlib import Path


_source = Path(__file__).resolve().parents[2] / 'm4_dense_sweep_integrated_native_pilot_001/harness/budget.py'
exec(compile(_source.read_bytes(), str(_source), 'exec'))

LIMITS = {**LIMITS, 'Blender_start_attempts': 2, 'all_rasters': 24}
previous.LIMITS = previous._ledger.LIMITS = LIMITS
