"""Bind the one performance change to immutable completed initial evidence."""

from datetime import datetime, timezone
from pathlib import Path
import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write


def main():
    if (HERE / "OPTIMIZATION_BINDING.json").exists():
        raise ValueError("optimization_already_bound")
    evidence = []
    for task, route in (("s01", "native"), ("s01", "facts"), ("s02", "facts"), ("s02", "native")):
        path = HERE / "private/consumers/v1" / task / route / "CONSUMER.json"
        receipt = read(path)
        state = read(HERE / "private/sessions" / ("v1_" + task + "_" + route) / "session.json")
        if receipt["status"] != "completed" or state.get("pending") or not state["operations"]:
            raise ValueError("all_initial_actual_results_required")
        evidence.append(dict(task_id=task, route=route, consumer=identity(path), session=identity(HERE / "private/sessions" / ("v1_"+task+"_"+route) / "session.json"),
            wall_s=receipt["wall_s"], quality=state["operations"][-1]["quality"]["status"]))
    binding = dict(bound_at_UTC=datetime.now(timezone.utc).isoformat(), initial_results=evidence,
        source_version=identity(HERE / "TOOL_FREEZE.json"), analysis=identity(HERE / "CONSUMER_STATS_v1.json"),
        evidence=dict(Python_calls=8, inline_geometry_JSON_bytes=52746408, same_version_repeated_snapshots=4,
            Python_execution_wall_s=4.2457, Python_worker_wall_s=2.8586, bridge_snapshot_remainder_s=.7592,
            required_submission_wall_s=20.7032, total_tool_wall_s=26.5522, total_consumer_wall_s=271.5125685),
        selected_performance_change="Version-bound binary NPZ geometry transport and reuse for fresh ordinary Python workers, replacing repeated array-to-list JSON serialization and parsing",
        invariant="Every exposed array, dtype, namespace name and submitted value stays identical; fresh interpreter and saved-model readback semantics remain the same",
        target="reduce measured input geometry JSON bytes and repeated local transport cost, measure first creation and reuse separately",
        correctness_fix=dict(evidence=identity(HERE / "AUDIT_IMPLEMENTATION.json"),
            issue="A reader failure before creating its output directory reserves the job label, and retry can select that same label",
            repair="Persist a monotonically advancing read-attempt number before each independent reader launch",
            consumer_occurrences_in_v1=0, speedup_attribution=False, required_real_recovery_regression=True),
        future_runs=[["s02", "facts"], ["s01", "facts"]], additional_Pro_sessions=2, additional_training=0,
        comparison_limits="Two tasks, sequential runs, provider token cache and cold local packet creation can affect timings; component savings and single-run task wall are reported separately",
        native_answers_reused=False, thresholds_or_targets_changed=False)
    write("OPTIMIZATION_BINDING.json", binding)
    print("one performance change bound to four completed actual results")


if __name__ == "__main__":
    main()
