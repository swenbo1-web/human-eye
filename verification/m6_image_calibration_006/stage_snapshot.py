"""Freeze first-stage actual files, protocol traces, source archive and cost."""

from datetime import datetime, timezone
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write


def main():
    started, cpu = time.perf_counter(), time.process_time()
    destination = HERE / "STAGE_V1_SNAPSHOT.json"
    if destination.exists():
        raise RuntimeError("first_stage_already_frozen")
    files = []
    for proposal_id in ("v1_native", "v2_facts"):
        for prefix in ("CALIBRATION_v1_", "IMAGE_SELECTION_FREEZE_v1_"):
            path = HERE / (prefix + proposal_id + ".json")
            read(path)
            files.append(path)
    for name in ("CALIBRATION_SCORES_v1.json", "COSTS_v1.json", "TOOL_FREEZE_v1.json"):
        path = HERE / name
        read(path)
        files.append(path)
    roots = [HERE / "private" / name for name in ("jobs", "processes", "measured", "protocol", "tool_versions/v1")]
    roots += list((HERE / "private/sessions").glob("v1_*"))
    roots += list((HERE / "private/calibrations").glob("v1_*"))
    roots += list((HERE / "private/calibration_scores").glob("v1*"))
    for root in roots:
        files.extend(path for path in root.rglob("*") if path.is_file())
    rows = [identity(path) for path in sorted(set(files))]
    write(destination, dict(status="frozen_first_stage", UTC=datetime.now(timezone.utc).isoformat(),
        files=rows, file_count=len(rows), bytes=sum(row["bytes"] for row in rows),
        source="Six actual cold candidates, both image choices frozen before private scoring, actual warm protocol reuse and exact v1 runtime archive.",
        wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu, new_Pro=0, new_Blender=0))
    print(dict(frozen_files=len(rows), bytes=sum(row["bytes"] for row in rows)))


if __name__ == "__main__":
    main()
