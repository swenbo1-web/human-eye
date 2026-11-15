"""Reuse the frozen monitor with process ledgers contained in this batch."""

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("_objective_monitor", HERE.parent / "m6_shape_train_001/process_runner.py")
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
previous.HERE = HERE
process_metrics = previous.process_metrics
run = previous.run
