"""Retain original binding and append completed local evidence before v2 freeze."""

from datetime import datetime, timezone
from pathlib import Path
import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write


def main():
    if (HERE / "TOOL_FREEZE_v2.json").exists() or list((HERE / "private/consumers/v2").glob("*/*/CLAIM.json")):
        raise ValueError("supplement_must_precede_all_v2_consumers")
    path = HERE / "OPTIMIZATION_BINDING.json"
    archive = HERE / "private/optimization/BOUND_ORIGINAL.json"
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists():
        raise ValueError("binding_supplement_already_written")
    archive.write_bytes(path.read_bytes())
    binding = read(path)
    previous = dict(analysis=binding["analysis"], correctness_audit=binding["correctness_fix"]["evidence"])
    binding["analysis"] = identity(HERE / "CONSUMER_STATS_v1.json")
    binding["correctness_fix"]["evidence"] = identity(HERE / "AUDIT_IMPLEMENTATION.json")
    binding["correctness_fix"]["actual_recovery_regression"] = identity(HERE / "RECOVERY_REGRESSION.json")
    binding["evidence_supplement"] = dict(at_UTC=datetime.now(timezone.utc).isoformat(), original_binding=identity(archive),
        prior_metadata=previous, reason="Analyzer appended actual Blender-job status and audit appended completed recovery regression. Four raw consumer and session records remain byte-identical. Performance selection and numeric targets retain original binding.",
        v2_claims_before_supplement=0, selection_changed=False)
    write(path, binding)


if __name__ == "__main__":
    main()
