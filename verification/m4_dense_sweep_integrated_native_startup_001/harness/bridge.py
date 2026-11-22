"""Use the approved pilot bridge in the isolated recovery namespace."""

from pathlib import Path


_source = Path(__file__).resolve().parents[2] / 'm4_dense_sweep_integrated_native_pilot_001/harness/bridge.py'
exec(compile(_source.read_bytes(), str(_source), 'exec'))
