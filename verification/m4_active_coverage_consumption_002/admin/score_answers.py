"""Reuse the frozen scoring code with an explicit new-batch answer scope."""
import hashlib
import importlib.util
from pathlib import Path
import types


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
LEGACY_SOURCE = ROOT / "verification/m4_active_coverage_consumption_001/admin/score_answers.py"
LEGACY_SHA256 = "76f0157254f54425e9354f7dbf292f00e5bb719fecdbd2252eaa84608ee06a9e"
if hashlib.sha256(LEGACY_SOURCE.read_bytes()).hexdigest() != LEGACY_SHA256:
    raise ValueError("frozen_scoring_source_changed")

_specification = importlib.util.spec_from_file_location("_coverage_002_frozen_grader", LEGACY_SOURCE)
legacy = importlib.util.module_from_spec(_specification)
_specification.loader.exec_module(legacy)
Grader = legacy.Grader

_grading_globals = dict(legacy.main.__globals__)
_grading_globals.update(HERE=HERE, BATCH=BATCH, __file__=str(Path(__file__).resolve()))
main = types.FunctionType(legacy.main.__code__, _grading_globals, legacy.main.__name__,
                          legacy.main.__defaults__, legacy.main.__closure__)
main.__kwdefaults__ = None if legacy.main.__kwdefaults__ is None else dict(legacy.main.__kwdefaults__)
main.__module__ = __name__


if __name__ == "__main__":
    main()
