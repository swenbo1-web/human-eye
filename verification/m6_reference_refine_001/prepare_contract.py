"""Bind the reference task, unmodified source art and fixed planning bytes."""

import hashlib
import json
from pathlib import Path
import subprocess
import time

HERE = Path(__file__).resolve().parent
CONTRACT_COMMIT = "dff6c9b78493d2438ebedcde69fb2c69b9f8568d"
PLANNING = "C:/Users/Administrator/.codex/worktrees/1212/hefe"


def identity(path):
    path = Path(path)
    raw = path.read_bytes()
    return dict(path=str(path.resolve()), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def main():
    started, cpu = time.perf_counter(), time.process_time()
    for name, target in (("docs/M6_REFERENCE_REFINE_001_TASK.md", "CONTRACT.md"), ("docs/M6_REFINE_RECOVERY_002_REVIEW.md", "PRIOR_REVIEW.md")):
        raw = subprocess.check_output(["git", "-C", PLANNING, "show", CONTRACT_COMMIT + ":" + name])
        (HERE / target).write_bytes(raw)
    inputs = [Path("D:/Projects/fps/outputs/character-design/Yanyite/Yanyite_Front_v1.png")]
    inputs += [Path(PLANNING) / "verification/m6_refine_recovery_002_review/private/visual" / (name + ".png") for name in ("whole_front", "forearm_front", "forearm_side")]
    result = dict(cycle_id="M6-REFERENCE-REFINE-001", baseline_commit="d121d7fd86db16c3cf4f2338704359685571df9a", contract_commit=CONTRACT_COMMIT,
        inputs=[identity(path) for path in inputs],
        authority=dict(source_thread="01a1d986-24a4-73f1-9689-6845d1f01ef3", latest_actual_human_turn="01a1dfd9-ba09-7a11-8b02-cf3bf79a7d65", latest_actual_human_message="01a1dfd9-bef1-7291-b17f-7bbe7e9b2455", text="为什么不继续推进", planning_scope="Reference-directed forearm contour task selected by the fixed planning contract in the ongoing implementation and review cycle"),
        measurements_pending=True, new_training=0, original_images_modified=0, wall_s=time.perf_counter()-started, cpu_s=time.process_time()-cpu)
    (HERE / "INPUT_BINDING.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf8", newline="\n")
    print("fixed contract and source images bound", flush=True)


if __name__ == "__main__":
    main()
