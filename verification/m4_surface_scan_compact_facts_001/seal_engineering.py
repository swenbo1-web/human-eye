"""Seal the one engineering candidate and its existing five-observation evidence."""

import ast
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_bytes())


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf8", newline="\n")


def main():
    candidate = read(HERE / "CANDIDATE_SOURCE.json")
    install = read(HERE / "installation/run_01/READY.json")
    semantics = read(HERE / "semantics/FINAL_RESULT.json")
    root = read(HERE / "ROOT_POSTCHECK.json")
    quality = read(HERE / "audits/quality/QUALITY_RESULT.json")
    binding = read(HERE / "audits/binding/BINDING_RESULT.json")
    timing = read(HERE / "engineering/run_01/FINAL_TIMING.json")
    results = read(HERE / "engineering/run_01/RESULTS.json")
    assert root["status"] == quality["status"] == binding["status"] == "pass"
    assert root["candidate_commit"] == quality["candidate_commit"] == binding["commit"] == candidate["commit"] == install["commit"]
    assert root["source_sha256"] == quality["candidate_source_sha256"] == binding["runtime_source_sha256"] == candidate["source_sha256"] == install["source_sha256"]
    assert timing["accepted_success"] is True and binding["accepted_success"] is True
    assert results["execution_counts"] == root["engineering_counts"] == {"attempted": 5, "completed": 5, "failed": 0, "not_attempted": 0}
    assert semantics["successful"] and semantics["tests_run"] == 180
    assert semantics["external_schema_cases"] == 13
    for relative, digest in semantics["evidence"].items():
        assert sha((HERE / "semantics" / relative).read_bytes()) == digest, relative
    expected_bytes = [7911, 7911, 34754, 7912, 35209]
    assert [row["business_text_utf8_bytes"] for row in root["actual_five_business_rows"]] == expected_bytes
    assert [row["body_bytes"] for row in quality["rows"]] == expected_bytes
    assert [row["body_utf8_bytes"] for row in binding["business"]] == expected_bytes
    assert [row["kernel_calls"] for row in binding["business"]] == [112, 0, 0, 10, 0]
    assert binding["all_host_rpc"] == 9 and binding["business_host_rpc"] == 5 and binding["outside_business_rpc"] == 4
    assert install["no_default_activation"] is True
    assert sha((HERE / "audits/binding/RUNTIME_PROOF_ERRATUM.json").read_bytes()) == binding["runtime_proof_erratum_sha256"]
    ready = {
        "callback": "M4-SURFACE-SCAN-COMPACT-FACTS-001_ENGINEERING_READY",
        "status": "engineering_ready_for_independent_review",
        "engineering_gate_pass": True,
        "candidate_commit": candidate["commit"], "source_sha256": candidate["source_sha256"],
        "source_count": 138, "distribution_version": install["version"], "wheel_sha256": install["wheel_sha256"],
        "isolated_install_ready": "installation/run_01/READY.json", "default_activation_changed": False,
        "planned_and_actual_business_rows": 5, "execution_counts": results["execution_counts"],
        "business_rows": root["actual_five_business_rows"],
        "compact_whole_text_limit_bytes": 10240,
        "actual_whole_text_bytes_in_fixed_order": expected_bytes,
        "independent_matched_rows": 357, "full_witness_points": 286,
        "new_kernel_calls": [112, 0, 0, 10, 0], "host_captures_per_business": [1, 1, 1, 1, 1],
        "host_RPC": {"all": 9, "business": 5, "outside_business_QA_and_close": 4},
        "complete_engineering_session_ns": timing["full_session_wall_ns"],
        "offline_methods": {"candidate_and_related_regression": 180, "new_candidate": 24,
                            "existing_regression": 156, "schema_cases_separate": 13, "runner_contract": 12,
                            "old_schema_method_not_executed_under_python312": semantics["existing_schema_methods_not_executed_in_python312"]},
        "same_originals_postchecks": {"root": root["checks"], "quality": quality["checks"],
                                     "binding": binding["check_count"], "check_counts_are_not_new_task_samples": True},
        "compatibility": [
            "surface_scan omitted response_detail and explicit brief now use surface-scan-task-table-v1.",
            "Clients expecting the old default matches object structure need encoding-aware decoding or explicit full.",
            "Explicit full remains a new current detailed observation; scene/source bindings govern combination.",
            "The object table covers delivered matching endpoints; coverage.objects retains scene scope.",
            "Non-scan defaults retain the prior display contract.",
        ],
        "retained_corrections": [
            "Initial 38 offline test errors are preserved; environment adaptations and a real optional-display fallback defect were resolved before candidate freeze.",
            "The root commit command proceeded after the default CRLF whitespace check failed; committed bytes subsequently passed the corrected cr-at-eol check.",
            "The runtime proof's inherited before_stdin=true label is invalid for first stdin; raw timestamps attest ownership after metadata and before geometry.",
        ],
        "limitations": [
            "New model consumers and inference API calls are zero; actual model input rendering, token and complete task benefits remain unmeasured.",
            "10 KiB is the fixed synthetic engineering benchmark gate; unsupported display structures retain full fallback.",
            "Schema validation uses an existing Python 3.14 environment; product tests use the existing Python 3.12 environment.",
            "Historical fixtures and validation environments are source-bound local dependencies.",
            "Recorded identity and initial/terminal checks retain their stated scope for historical memory and transient changes.",
            "Physical disk persistence, timing-publication receipt's own write, and full coordination costs are unmeasured.",
            "Agent Learning context is unbound; task synchronization requires host reconnect.",
        ],
        "new_model_consumers": 0, "new_inference_API_calls": 0,
        "artifacts": ["REPORT.md", "COMPATIBILITY.md", "CANDIDATE_SOURCE.json", "ROOT_POSTCHECK.json",
                      "semantics/FINAL_RESULT.json", "engineering/run_01/RESULTS.json",
                      "engineering/run_01/FINAL_TIMING.json", "audits/quality/QUALITY_RESULT.json",
                      "audits/binding/BINDING_RESULT.json", "audits/binding/RUNTIME_PROOF_ERRATUM.json", "DELIVERY_MANIFEST.json"],
        "next_step": "Send the engineering callback and stop for the administrator's independent review.",
    }
    write(HERE / "ENGINEERING_READY.json", ready)
    files = []
    excluded = []
    for path in sorted(HERE.rglob("*"), key=lambda value: value.relative_to(HERE).as_posix()):
        if not path.is_file() or path == HERE / "DELIVERY_MANIFEST.json":
            continue
        relative = path.relative_to(HERE).as_posix()
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            excluded.append(relative)
            continue
        raw = path.read_bytes()
        if path.suffix == ".json":
            json.loads(raw)
        if path.suffix == ".py":
            ast.parse(raw.decode("utf-8-sig"), filename=relative)
        files.append({"path": relative, "bytes": len(raw), "sha256": sha(raw)})
    manifest = {"callback": ready["callback"], "candidate_commit": candidate["commit"],
                "source_sha256": candidate["source_sha256"], "file_count": len(files),
                "manifest_scope": "This module's evidence files except this manifest itself and local bytecode",
                "total_bytes": sum(row["bytes"] for row in files), "excluded_local_bytecode": excluded, "files": files}
    path = HERE / "DELIVERY_MANIFEST.json"
    write(path, manifest)
    print(json.dumps({"engineering_gate_pass": True, "content_files": len(files),
                      "delivery_files_including_manifest": len(files) + 1,
                      "manifest_sha256": sha(path.read_bytes()), "total_bytes": manifest["total_bytes"]}))


if __name__ == "__main__":
    main()
