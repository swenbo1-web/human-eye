"""Reuse the prior owned N/P harness within this pilot namespace."""

from pathlib import Path


_source = Path(__file__).resolve().parents[2] / 'perf050_dense_micro_surface_holdout_recovery_001/harness/frame_device.py'
exec(compile(_source.read_bytes(), str(_source), 'exec'))
