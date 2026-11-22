"""Use the approved pilot closure in the isolated recovery namespace."""

from pathlib import Path


_source = Path(__file__).resolve().parents[2] / 'm4_dense_sweep_integrated_native_pilot_001/harness/closure.py'
exec(compile(_source.read_bytes(), str(_source), 'exec'))
