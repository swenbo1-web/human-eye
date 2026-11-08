"""Archive and index the already-finished RUN-002. Never starts a consumer."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from datetime import datetime, timezone
import zipfile

ROOT = Path(__file__).resolve().parents[3]
RUN = ROOT / "verification/consumption_run_002"
OUT = RUN / "actual_invocation_001"
NEUTRAL = Path("C:/Users/Administrator/AppData/Local/Temp/he-consumption-run-002")
COORD = Path("D:/hefe/verification/fixes/20261107_nearest_contract")
BASE = "34496064288ee8789da6e51a17a0dd894eeba11b"
TOKEN = "CONSUMPTION-RUN-002-20261108T0405Z-3449606-ONLY"
INDEX = RUN / "EVIDENCE_INDEX.json"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def put(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def main():
    assert not INDEX.exists(), "sealed evidence is never overwritten"
    assert git("rev-parse", "HEAD").decode().strip() == BASE
    assert not git("diff", "--name-only")
    assert not git("diff", "--cached", "--name-only")
    frozen = {
        p.relative_to(RUN).as_posix(): sha(p.read_bytes())
        for p in (RUN / "actual_01").rglob("*") if p.is_file()
    }
    assert frozen["actual_01/RESULTS.json"] == "2ff3ab2c042f0de9bafc91853b8d33b0f853c5d4cc44a0ff634afa1285fc97e3"
    for name in ("runner.py", "bridge.py", "he_bootstrap.py", "PLAN.json", "PACKAGE.json"):
        assert (RUN / name).read_bytes() == (COORD / "consumption_run_002_activation" / name).read_bytes()
    counts = load(OUT / "COUNTS_AUDIT.json")
    cleanup = load(OUT / "CLEANUP_AUDIT.json")
    assert counts["slot_status_counts"] == {"error": 1, "not_run": 7}
    assert counts["answers_received"] == 1 and counts["valid_completion_count"] == 0
    assert cleanup["component_count"] == 17 and all(x["matches"] for x in cleanup["component_checks"])
    assert cleanup["product_source_count"] == 131
    assert cleanup["product_canonical_sha256"] == "01c296b5dac9c8733670b7b82886fe774fb6e50222d1b935d6ac27efa04760de"

    approval_path = COORD / "CONSUMPTION_RUN_002_APPROVAL.json"
    approval = approval_path.read_bytes()
    assert sha(approval) == "3fc6c263b978a01913cdd2ef41388f5cfdae50df8ee197f8123d7a3bf9be7030"
    (OUT / "APPROVAL.snapshot.json").write_bytes(approval)
    assignment_path = COORD / "CONSUMPTION_RUN_002_ASSIGNMENT.md"
    (OUT / "ASSIGNMENT.snapshot.md").write_bytes(assignment_path.read_bytes())
    state_path = Path("D:/hefe/verification/fixes/20261106_parallel_coordination/STATE.json")
    performance_window = load(state_path)["performance_window"]
    assert TOKEN in json.dumps(performance_window)
    now = datetime.now(timezone.utc)
    put(OUT / "AUTHORIZATION_SNAPSHOT.json", {
        "cycle_id": "CONSUMPTION-RUN-002",
        "captured_utc": now.isoformat(),
        "scope": "post-execution evidence snapshot; no approval renewal and no STATE mutation",
        "approval_source": str(approval_path),
        "approval_sha256": sha(approval),
        "assignment_source": str(assignment_path),
        "assignment_sha256": sha(assignment_path.read_bytes()),
        "activation_package_source": str(COORD / "consumption_run_002_activation/PACKAGE.json"),
        "activation_package_sha256": sha((RUN / "PACKAGE.json").read_bytes()),
        "state_source": str(state_path),
        "performance_window_only": performance_window,
        "root_manages_window_release": True,
    })

    archive_path = OUT / "NEUTRAL_RAW.zip"
    assert not archive_path.exists()
    neutral_rows = []
    with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(NEUTRAL.rglob("*")):
            if not path.is_file():
                continue
            assert path.resolve().is_relative_to(NEUTRAL.resolve())
            data = path.read_bytes()
            rel = path.relative_to(NEUTRAL).as_posix()
            zi = zipfile.ZipInfo(rel, (2026, 11, 8, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(zi, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
            assert sha(path.read_bytes()) == sha(data), "neutral input changed during archiving"
            neutral_rows.append({"path": rel, "bytes": len(data), "sha256": sha(data)})
    with zipfile.ZipFile(archive_path) as archive:
        assert sorted(archive.namelist()) == sorted(x["path"] for x in neutral_rows)
        for row in neutral_rows:
            assert sha(archive.read(row["path"])) == row["sha256"]
    put(OUT / "NEUTRAL_RAW_INDEX.json", {
        "source_root": str(NEUTRAL), "archive": archive_path.name,
        "archive_sha256": sha(archive_path.read_bytes()),
        "file_count": len(neutral_rows), "files": neutral_rows,
        "source_deleted_or_moved": False,
        "scope": "all files from this run's private neutral root; no shared/global logs",
    })

    # Locate the prior recorded result by tracked path if the historic layout differs.
    tracked = git("ls-files", "verification/*/actual_01/RESULTS.json").decode().splitlines()
    old_rows = []
    for rel in tracked:
        if rel.startswith("verification/consumption_run_002/"):
            continue
        data = (ROOT / rel).read_bytes()
        baseline = git("show", f"{BASE}:{rel}")
        assert data == baseline
        old_rows.append({"path": rel, "sha256": sha(data), "same_as_baseline_git_blob": True})
    assert old_rows, "prior tracked actual result must be anchored"
    put(OUT / "PRESERVATION.json", {
        "baseline_HEAD": BASE,
        "tracked_worktree_changes_before_new_run_staging": [],
        "old_actual_results_compared_without_body_interpretation": old_rows,
        "old_full_evidence_matrix_rerun": False,
        "frozen_new_run_files": frozen,
        "activation_files_exact": True,
        "component_count": cleanup["component_count"],
        "product_source_count": cleanup["product_source_count"],
        "product_canonical_sha256": cleanup["product_canonical_sha256"],
    })

    turn_start = datetime.fromtimestamp(1794110447, timezone.utc)
    invocation_started = datetime.fromisoformat("2026-11-08T04:02:34.897320+00:00")
    invocation_ended = datetime.fromisoformat("2026-11-08T04:03:34.254347+00:00")
    put(OUT / "MANAGEMENT_CLOCK.json", {
        "thread_id": "01a1afc7-b09d-7272-be04-53b3e76ee71c",
        "turn_id": "01a1b950-df78-7fd0-a3ca-2419eb95af83",
        "metadata_source": "Codex app read_thread; timestamps/status only, no reasoning text",
        "turn_started_utc": turn_start.isoformat(),
        "turn_completed_utc": None,
        "snapshot_cutoff_utc": now.isoformat(),
        "turn_elapsed_through_snapshot_s": (now - turn_start).total_seconds(),
        "preparation_through_controller_dispatch_s": (invocation_started - turn_start).total_seconds(),
        "controller_end_to_snapshot_s": (now - invocation_ended).total_seconds(),
        "scope": "management interval is a lower bound through snapshot, includes the nested real invocation and parallel audits; do not sum nested intervals; excludes earlier preparation turns and final commit/callback tail",
    })

    rows = "\n".join(f"| {s['ordinal']} | {s['task_id']} | {s['arm']} | {s['status']} |" for s in counts["slots"])
    report = f"""# CONSUMPTION-RUN-002 actual delivery

One authorized invocation finished. It received **1 public final**, but the frozen first-slot status is **error** with **0 valid completions**; the other **7 slots are not_run**. No retry, replacement answer, inline repair, resumed 001 run, or quality scoring occurred. A returned final does not establish task correctness or engine benefit.

| Slot | Task | Arm | Frozen status |
|---|---|---|---|
{rows}

Every unstarted slot retains reason `previous_slot_cleanup_not_confirmed_no_further_start` and null dispatch. The first slot's original reason remains null. `actual_01/RESULTS.json`, per-slot `RESULT.json`, `CONSUMER.json`, and public final are unchanged originals.

## Observable failure and stopping boundary

The sole public `native.execute_blender_code` attempt failed with the captured message **`MCP tool call requires approval, but approval policy is never`**. It was not forwarded as MCP `tools/call` or native `execute_code`. This public approval error is distinct from the frozen slot invalidity: native bridge PID 14744 has STARTED but no EXIT receipt. The runner therefore kept `registered_tree_cleanup.confirmed=false`, `tree_reaped=false`, and `safe_to_continue=false`, and stopped before slot 2. No claim is made about why EXIT was absent.

The CLI terminal turn completed and its process exited 0. `complete=true` does not override `valid_completion=false`. The original 180-second answer timer did not fire. Three discarded ordinary stderr lines (554 bytes) and one discarded public error event remain unavailable under the frozen filter; no private log or replay was used to recover them.

## Calls, bytes, images and usage

- Actual CLI contexts: 1; returned finals: 1; original native Blender sessions: 1; P/HE slots started: 0.
- Public tool attempts: 1; admitted server tool actions: 0; native execute RPCs: 0; product capture RPCs: 0. The one physical native RPC was administrative close, outside the execute ledger.
- MCP frames: initialize, notifications/initialized, tools/list; TX 409 bytes / published RX 787 bytes. No tools/call frame. Native close TX 17 bytes / RX 62 bytes.
- Complete tools array: 563 UTF-8 bytes, one descriptor: 561 bytes. Actual model-delivered schema bytes are unexposed (`null`).
- Public text ledger: 2,093 bytes = prompt 911 + tools array 563 + final 619. The final artifact is 632 bytes because of 13 CRLF expansions. These are separate measurements.
- Render events, PNG files, generated image blocks: 0.
- Terminal usage counted once: input 48,129 tokens, cached input 35,456 (subset of input), output 1,328. Provider request count, fees, and actual backend are unexposed/null; no monetary estimate is substituted.

## Time and ownership

The full recorded argv is in `actual_invocation_001/STARTED.json` and `OWNED_PROCESS.json`. The exact root-provided runner ran once with the existing isolated Python interpreter and approval file. Controller start 2026-11-08T04:02:34.897320Z; end 04:03:34.254347Z.

| Observed interval | Seconds | Scope |
|---|---:|---|
| Outer Popen/wait/reap | 59.3571895 | Complete controller invocation |
| Runner wall | 59.2669521 | Through result construction |
| First whole cell | 58.9164216 | Dispatch through cleanup |
| Answer receive latency | 49.6407478 | Dispatch to received final; not certified completion |
| Consumer wall | 57.4009768 | Entry through consumer cleanup |
| Native close owner receipt | 0.1227544 | Administrative close and owner reap |
| Native close wire meter | 0.1352274 | Separate wrapper observation |

These intervals are nested and must not be summed. They do not measure engine speed or successful task completion. `MANAGEMENT_CLOCK.json` separately records this management turn's start, preparation interval, and elapsed lower bound through sealing; final commit/callback tail and prior preparation turns are outside that cutoff.

Controller 15456, CLI 20884, and Blender 18996 were owner-reaped with exit 0. Native close returned closed, poison=false, unchanged geometry fingerprint, unchanged original session deadline, and protected/source files unchanged. Bridge 14744 lacks EXIT. A later targeted scan found none of the four known PIDs alive; that observation does not repair the missing receipt or prove arbitrary descendant cleanup. All frozen false flags remain false.

## Identity and delivery evidence

Baseline HEAD: `{BASE}`. Product remains commit `17db41c481397965a9bae3f4571c59a5a80939c9`, 131 source entries, canonical SHA256 `01c296b5dac9c8733670b7b82886fe774fb6e50222d1b935d6ac27efa04760de`. All 17 PLAN components and original assets were independently rechecked. The five activation files are byte-identical to the root package; PLAN SHA256 `11cbfa7445c5d4075ca291321bebcc48d116ad9a4928807d087cb54c52cb7980`.

`APPROVAL.snapshot.json`, `ASSIGNMENT.snapshot.md` and `AUTHORIZATION_SNAPSHOT.json` preserve authorization metadata. The root owns STATE/window release; no STATE write occurred. `NEUTRAL_RAW.zip` preserves all {len(neutral_rows)} raw files of this run's private neutral root; `NEUTRAL_RAW_INDEX.json` gives member hashes. It excludes shared/global logs. Original neutral files were neither deleted nor moved.

`COUNTS_AUDIT.json/.md` and `CLEANUP_AUDIT.json/.md` are independent read-only audits. `PRESERVATION.json` anchors frozen outputs and prior tracked actual results without interpreting answer bodies. Only new RUN-002 materials are submitted. Old RUN-001 stays 1 error + 7 not_run, 0 returned finals. No truth was read; root may score separately.

`EVIDENCE_INDEX.json` hashes every new RUN-002 evidence file except itself and Python bytecode/cache. All raw run frames and received answer artifacts are included. The delivery callback supplies the final commit and index SHA256 after the Git blob comparison.
"""
    (RUN / "REPORT.md").write_text(report, encoding="utf-8", newline="\n")

    for rel, digest in frozen.items():
        assert sha((RUN / rel).read_bytes()) == digest
    evidence = []
    for path in sorted(RUN.rglob("*")):
        if not path.is_file() or path == INDEX or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        data = path.read_bytes()
        evidence.append({"path": path.relative_to(RUN).as_posix(), "bytes": len(data), "sha256": sha(data)})
    put(INDEX, {
        "schema": "consumption-run-002-evidence-index-v1",
        "cycle_id": "CONSUMPTION-RUN-002", "baseline_HEAD": BASE,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "path_base": "verification/consumption_run_002", "file_count": len(evidence),
        "excludes": ["EVIDENCE_INDEX.json (self)", "__pycache__/**", "*.pyc"],
        "files": evidence,
    })
    print(json.dumps({"indexed_files": len(evidence), "neutral_files": len(neutral_rows),
                      "report_sha256": sha((RUN / "REPORT.md").read_bytes()),
                      "index_sha256": sha(INDEX.read_bytes())}))


if __name__ == "__main__":
    main()
