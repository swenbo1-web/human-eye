"""Reuse frozen pilot identities with only the two unspent formal slots."""

from pathlib import Path


_source = Path(__file__).resolve().parents[2] / 'm4_dense_sweep_integrated_native_pilot_001/harness/common.py'
exec(compile(_source.read_bytes(), str(_source), 'exec'))

EXTERNAL = Path('D:/he_m4_dense_sweep_integrated_native_pilot_recovery_001')
QUALIFICATION = ()
SLOTS = {label: (label[0], 'formal') for label in FORMAL_LABELS}
ORDER = tuple(SLOTS)
SLOT_REQUESTS = {label: () for label in SLOTS}
