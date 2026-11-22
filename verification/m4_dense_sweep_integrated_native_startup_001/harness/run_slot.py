"""Use the approved pilot run slot in the isolated recovery namespace."""

from pathlib import Path


_source = Path(__file__).resolve().parents[2] / 'm4_dense_sweep_integrated_native_pilot_001/harness/run_slot.py'
exec(compile(_source.read_bytes(), str(_source), 'exec'))
