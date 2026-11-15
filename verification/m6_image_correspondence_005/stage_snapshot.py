"""Bind terminal consumer traces, actual models and independent stage results."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("v1", "v2"), required=True)
    stage = parser.parse_args().stage
    destination = HERE / ("STAGE_" + stage.upper() + "_SNAPSHOT.json")
    if destination.exists():
        raise RuntimeError("stage_snapshot_already_exists")
    files = []
    for route in ("native", "facts"):
        consumer = HERE / "private/consumers" / stage / "repair" / route
        if read(consumer / "CONSUMER.json")["status"] not in ("completed", "failed"):
            raise RuntimeError("terminal_stage_pair_required")
        name = stage + "_repair_" + route
        roots = (consumer, HERE / "private/sessions" / name,
            HERE / "private/final_verify" / name, HERE / "private/results" / name)
        for root in roots:
            files.extend(path for path in root.rglob("*") if path.is_file())
    for name in ("FINAL_VERIFICATION_" + stage + ".json", "CONSUMER_STATS_" + stage + ".json",
                 "VIEWABLES_" + stage + ".json", "FIT_AUDIT_" + stage + ".json", "TOOL_FREEZE_" + stage + ".json"):
        path = HERE / name
        if not path.is_file():
            raise RuntimeError("stage_evidence_missing_" + name)
        files.append(path)
    files = sorted(set(files))
    rows = [identity(path) for path in files]
    write(destination, dict(cycle_id="M6-IMAGE-CORRESPONDENCE-005", stage=stage,
        status="frozen_terminal_stage", UTC=datetime.now(timezone.utc).isoformat(), files=rows,
        file_count=len(rows), bytes=sum(row["bytes"] for row in rows),
        interpretation="Both raw sessions, their final actual saved files, independent quality, actual fitting diagnostics and stage runtime are fixed before any subsequent optimization or stage."))
    print(dict(stage=stage, frozen_files=len(rows), bytes=sum(row["bytes"] for row in rows)))


if __name__ == "__main__":
    main()
