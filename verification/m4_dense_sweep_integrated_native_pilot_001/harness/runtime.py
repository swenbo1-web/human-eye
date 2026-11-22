"""Reuse the reviewed observed production launcher and actual EOF verification."""

from pathlib import Path


_source = Path(__file__).resolve().parents[2] / 'm1_region_task_first_packet_consumption_holdout_recovery_001/harness/runtime.py'
exec(compile(_source.read_bytes(), str(_source), 'exec'))
