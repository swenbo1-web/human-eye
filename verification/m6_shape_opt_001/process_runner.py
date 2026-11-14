"""Reuse the frozen process monitor with ledgers rooted in this batch."""

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
source = HERE.parent / "m6_shape_train_001/process_runner.py"
spec = importlib.util.spec_from_file_location("m6_shape_original_process_runner", source)
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
previous.HERE = HERE
process_metrics = previous.process_metrics
run = previous.run
