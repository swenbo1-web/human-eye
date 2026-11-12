"""Seal the final anonymous handoff without scoring answers or analyzing cost."""

import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import zipfile


HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_bytes())


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf8", newline="\n")


def main():
    plan = read(HERE / "PLAN.json")
    preparation = read(HERE / "PREPARATION_MANIFEST.json")
    for row in preparation["files"]:
        raw = (HERE / row["path"]).read_bytes()
        assert len(raw) == row["bytes"] and sha(raw) == row["sha256"], row["path"]
    for relative, digest in plan["dispatch_input_sha256"].items():
        assert sha((HERE / relative).read_bytes()) == digest, relative
    for name, digest in plan["external_input_sha256"].items():
        assert sha(Path(name).read_bytes()) == digest, name

    integrity = read(HERE / "preflight/POSTRUN_INTEGRITY.json")
    check = read(HERE / "scoring/FORMAL_HANDOFF_CHECK.json")
    original = read(HERE / "HANDOFF_VERIFICATION.json")
    redaction = read(HERE / "quality/ADMIN_REDACTION.json")
    package = read(HERE / "quality/PACKAGE_RECEIPT.json")
    assert integrity["status"] == check["status"] == "pass"
    assert integrity["formal_quality_scoring_performed"] is False and check["formal_scoring_performed"] is False
    assert original["quality_scoring_performed"] is False
    assert integrity["execution_counts"] == original["execution_counts"] == {"completed": 7, "failed": 2}
    assert integrity["not_run"] == 0 and integrity["final_present"] == check["finals_present"] == 9
    assert integrity["fresh_model_contexts"] == 9 and integrity["full_initial_final_snapshots_verified"] == 18
    assert integrity["owner_cleanup_confirmed"] == 9
    assert check["administrative_clock_fields_removed"] == len(redaction["removals"]) == 2
    assert check["other_41_public_files_byte_identical"] is True
    assert check["failed_exit0_final_present_not_promoted_to_completed"] is True
    public = HERE / "quality/public"
    manifest = redaction["final_public_manifest"]
    assert len(manifest) == 42
    digest = sha(canonical(manifest))
    assert digest == package["public_canonical_sha256"] == check["final_public_manifest_sha256"] == redaction["final_public_manifest_sha256"]
    index = read(public / "INDEX.json")
    assert index["fixed_slots"] == 9 and index["scoring_performed"] is False
    assert Counter(row["cell_execution_state"] for row in index["answers"]) == {"completed": 7, "failed": 2}
    archive_path = HERE / "quality" / package["final_public_zip"]
    assert sha(archive_path.read_bytes()) == package["sha256"]
    with zipfile.ZipFile(archive_path) as archive:
        assert set(archive.namelist()) == {row["path"] for row in manifest}
        for row in manifest:
            raw = (public / row["path"]).read_bytes()
            assert len(raw) == row["bytes"] and sha(raw) == row["sha256"]
            assert archive.read(row["path"]) == raw

    ready = {
        "callback": "M4-SURFACE-SCAN-COMPACT-CONSUMPTION-001_FORMAL_QUALITY_READY",
        "phase": "anonymous_quality_handoff_before_quality_scoring_and_cost_analysis",
        "preparation_commit": "3a1ba86c5fce2fe125671cc68a84b14031d318cb",
        "plan_sha256": sha((HERE / "PLAN.json").read_bytes()),
        "root_plan_document_sha256": sha((HERE / "ROOT_PLAN.md").read_bytes()),
        "product_profiles": {
            name: {key: read(HERE / "installations" / (name + "_READY.json"))[key]
                   for key in ("commit", "source_sha256", "source_count", "version", "wheel_sha256")}
            for name in ("O", "C")
        },
        "input_scene_sha256": plan["inputs"]["scene_sha256"], "input_prompt_sha256": plan["inputs"]["prompt_sha256"],
        "fixed_slots": 9, "actual_consumers_started": 9,
        "execution_counts": {"completed": 7, "failed": 2, "not_run": 0}, "final_texts_present": 9,
        "retained_failure_scope": "Two consumers each recorded a CLI stream reconnect/response-decoding error, then completed their turn, exited zero and wrote matching final files; frozen valid_completion remains false.",
        "formal_quality_scoring_performed": False, "group_quality_or_cost_analysis_performed": False,
        "final_anonymous_zip": "quality/" + package["final_public_zip"],
        "final_anonymous_zip_sha256": package["sha256"], "final_public_canonical_sha256": digest,
        "final_public_files": 42, "administrative_error_timestamps_removed": 2,
        "initial_packer_tree_and_zip_preserved": True,
        "postrun_integrity_checks": integrity["checks"], "anonymous_handoff_checks": check["checks"],
        "initial_final_snapshots_bound": 18, "business_attempts_retained": 27,
        "thin_client_exit_receipt_states": integrity["thin_client_exit_receipt_states"],
        "limitations": [
            "Actual business content can reveal route, so anonymity is limited.",
            "Actual resolved model/version/effort and provider input rendering remain unconfirmed.",
            "Provider request count, cash fees, subscription debits and full coordination costs remain unmeasured.",
            "Thin-client EXIT unknowns and generic close-event script status retain their separate evidence scope.",
            "Agent Learning is unbound and task synchronization awaits host reconnect.",
        ],
        "next_step": "Send the authorized administrator callback and stop for independent anonymous quality review.",
    }
    save(HERE / "FORMAL_QUALITY_READY.json", ready)
    records = []
    for path in sorted(HERE.rglob("*"), key=lambda p: p.relative_to(HERE).as_posix()):
        if not path.is_file() or path == HERE / "DELIVERY_MANIFEST.json":
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        raw = path.read_bytes()
        if path.suffix == ".json":
            json.loads(raw)
        if path.suffix == ".py":
            ast.parse(raw.decode("utf-8-sig"), filename=str(path))
        records.append({"path": path.relative_to(HERE).as_posix(), "bytes": len(raw), "sha256": sha(raw)})
    delivery = {"callback": ready["callback"], "phase": ready["phase"],
                "preparation_commit": ready["preparation_commit"], "file_count": len(records),
                "total_bytes": sum(row["bytes"] for row in records), "files": records,
                "manifest_scope": "All batch evidence except this manifest itself and local bytecode"}
    path = HERE / "DELIVERY_MANIFEST.json"
    save(path, delivery)
    print(json.dumps({"file_count_including_manifest": len(records) + 1,
                      "manifest_sha256": sha(path.read_bytes()), "execution_counts": ready["execution_counts"],
                      "final_texts_present": 9, "formal_quality_scoring_performed": False,
                      "final_anonymous_zip_sha256": package["sha256"]}))


if __name__ == "__main__":
    main()
