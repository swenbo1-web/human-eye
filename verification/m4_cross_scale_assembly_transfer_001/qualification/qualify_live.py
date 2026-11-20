"""Recheck the two original packets with cross-process object-order normalization."""

import hashlib
import json
from pathlib import Path
import runpy
import sys


HERE = Path(__file__).resolve().parent
NS = HERE.parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    record = json.loads((HERE / 'ORDER_COMPATIBILITY.json').read_bytes())
    original = HERE / 'qualify.py'
    current_scorer = NS / 'scoring/score_live.py'
    original_scorer = NS / 'scoring/score.py'
    if (sha(original) != record['frozen_qualifier_sha256']
            or sha(original_scorer) != record['frozen_scorer_sha256']
            or sha(current_scorer) != record['compatible_scorer_sha256']
            or sha(HERE / 'ORIGINAL_GATE.json') != record['original_gate_sha256']):
        raise ValueError('original_or_compatible_qualification_evidence_changed')
    sys.path.insert(0, str(HERE))
    execution = runpy.run_path(str(original))
    actual_globals = execution['assess_slot'].__globals__
    load = actual_globals['legacy']

    def select_scorer(name, path):
        if path == original_scorer:
            return load(name, current_scorer)
        return load(name, path)

    actual_globals['legacy'] = select_scorer
    return execution['main']()


if __name__ == '__main__':
    raise SystemExit(main())
