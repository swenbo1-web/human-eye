"""Reuse the audited one-shot process monitor with current-batch logs."""

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("_perception_monitor", HERE.parent / "m6_shape_train_001/process_runner.py")
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)
monitor.HERE = HERE
process_metrics = monitor.process_metrics
run = monitor.run
