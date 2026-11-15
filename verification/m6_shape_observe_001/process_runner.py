"""Reuse the existing process-tree monitor with this batch's ledger paths."""

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "_m6_observe_process_runner", HERE.parent / "m6_shape_train_001/process_runner.py")
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
previous.HERE = HERE
process_metrics = previous.process_metrics
run = previous.run
