"""Run the unchanged CLI registry probe with the recovery thin endpoint."""

from pathlib import Path
from runpy import run_path
from types import FunctionType

from common import PREVIOUS

NS = Path(__file__).resolve().parent
retained=run_path(str(PREVIOUS/'cli_probe.py'))['probe']
if retained.__globals__['NS'] != PREVIOUS:
    raise ValueError('expected_frozen_actual_CLI_probe')
probe=FunctionType(retained.__code__,dict(retained.__globals__,NS=NS))
