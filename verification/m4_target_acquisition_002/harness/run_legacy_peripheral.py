"""Run B once on the unchanged old peripheral control; reuse its existing A."""

import argparse
import hashlib
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_case import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("D:/he_m4_target_002/controls/B_legacy_peripheral"))
    parser.add_argument("--ledger", type=Path, default=Path("D:/he_m4_target_002/budget"))
    args = parser.parse_args()
    plan = json.loads((HERE.parent / "fixtures/LEGACY_PERIPHERAL_PLAN.json").read_bytes())
    for pin in plan["source_pins"]:
        if hashlib.sha256(Path(pin["path"]).read_bytes()).hexdigest() != pin["sha256"]:
            raise ValueError("old_peripheral_control_source_changed")
    result = run(binding_path=args.binding, asset=plan["asset"], output=args.output,
                 ledger=args.ledger, phase="qualification", label="B_legacy_peripheral", variant="B")
    print(json.dumps({"passed_operationally": result["passed"], "output": str(args.output),
                      "A_reference": plan["A_reference"], "independent_comparison": "pending"}))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
