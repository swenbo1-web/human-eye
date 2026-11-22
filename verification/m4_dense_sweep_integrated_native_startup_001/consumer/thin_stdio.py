"""Run the approved image-bearing wire transport on the recovery bridge."""

from pathlib import Path


_source = Path(__file__).resolve().parents[2] / 'm4_dense_sweep_integrated_native_pilot_001/consumer/thin_stdio.py'
exec(compile(_source.read_bytes(), str(_source), 'exec'))
