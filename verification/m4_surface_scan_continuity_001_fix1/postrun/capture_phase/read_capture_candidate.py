"""Unapplied reader for completed worker outputs available before response send.

The frozen active fact validator is reused. This reader establishes capture
content from closed call files and the fsynced worker event. It makes no claim
about response transmission or the later WIRE archive.
"""

import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
BATCH = HERE.parents[1]
SOURCE = BATCH / "qualification/verify_continuity.py"
spec = importlib.util.spec_from_file_location("_fix1_frozen_capture_qualification", SOURCE)
qualification = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualification)
qualification.require(qualification.digest(SOURCE.read_bytes()) == "6f623d99279586d11d2c34a5f1fac93465212803093b61f75160d5b530c29ee9", "frozen_qualification_source")
require = qualification.require


def logical_bytes(raw, *, expected_size=None, expected_sha=None):
    """Select the unique recorded byte string under Windows text-file writing.

    Accept the physical bytes or precisely CRLF-to-LF. The worker's original
    byte count or code hash must choose one unique value. No trimming occurs.
    """
    possibilities = {raw, raw.replace(b"\r\n", b"\n")}
    matches = [value for value in possibilities
               if (expected_size is None or len(value) == expected_size)
               and (expected_sha is None or qualification.digest(value) == expected_sha)]
    require(len(matches) == 1, "unique_worker_text_reconstruction")
    return matches[0]


def read_capture(native_workspace, host_event):
    """Resolve current capture plus earlier completed outputs in the same worker."""
    workspace = Path(native_workspace)
    target = host_event["sequence"]
    require(type(target) is int and 0 < target <= 128, "capture_sequence")
    events_path = workspace / "WORKER_EVENTS.jsonl"
    events_raw = events_path.read_bytes()
    events = [json.loads(line) for line in events_raw.splitlines()]
    completed = [event for event in events if type(event.get("sequence")) is int
                 and event["sequence"] <= target and "script_sha256" in event]
    sequences = [event["sequence"] for event in completed]
    require(sequences == sorted(set(sequences)) and target in sequences, "completed_capture_event_order")
    selected = next(event for event in completed if event["sequence"] == target)
    require(qualification.canonical(selected) == qualification.canonical(host_event), "recorded_host_event_binding")
    resources, origins, sources = {}, {}, []
    current, origin = None, None
    for event in completed:
        number = event["sequence"]
        require(event["status"] == "completed" and event["script_error"] is None, "completed_worker_output")
        require(event["terminal_geometry_and_file_checks_passed"] is True, "worker_output_terminal_protection")
        require(event["changed_or_new_PNG_files"] == [] and event["render_events_before"] == event["render_events_after"], "worker_output_zero_images")
        folder = workspace / ("call_" + str(number))
        physical = {name: (folder / name).read_bytes() for name in ("SCRIPT.py", "stdout.txt", "stderr.txt")}
        code = logical_bytes(physical["SCRIPT.py"], expected_sha=event["script_sha256"])
        stdout = logical_bytes(physical["stdout.txt"], expected_size=event["stdout_bytes"])
        stderr = logical_bytes(physical["stderr.txt"], expected_size=event["stderr_bytes"])
        require(stderr == b"", "capture_worker_stderr_empty")
        code.decode("utf8")
        lines = stdout.decode("utf8").splitlines()
        prefix = "HUMAN_EYE_BLENDER_MCP:"
        captures = [line[len(prefix):] for line in lines if line.startswith(prefix)]
        if not captures:
            continue
        require(len(captures) == len(lines) == 1, "single_worker_capture_envelope")
        envelope = json.loads(captures[0])
        require("error" not in envelope and type(envelope.get("result")) is dict, "worker_capture_result")
        delta = envelope["result"]
        require(delta.get("schema") == "human-eye-scene-delta-v1", "capture_delta_schema")
        binding = delta["capture"]["binding"]
        identity = (binding["host_source_sha256"], binding["host_identity"]["document_epoch"])
        require(identity[0] == qualification.HOST_SOURCE_SHA and (origin is None or origin == identity), "capture_history_same_host_document")
        origin = identity
        supplied = set()
        for resource in delta["resources"]:
            key = (resource["id"], resource["revision"])
            require(type(key[0]) is str and type(key[1]) is int and key[1] > 0 and key not in supplied, "capture_resource_identity")
            require(key not in resources or qualification.canonical(resources[key]) == qualification.canonical(resource), "capture_resource_revision_immutable")
            supplied.add(key)
            resources[key] = resource
            origins[key] = number
        sources.append({"sequence": number, "script_sha256": qualification.digest(code),
                        "logical_stdout_sha256": qualification.digest(stdout), "logical_stderr_sha256": qualification.digest(stderr),
                        "event_sha256": qualification.digest(qualification.canonical(event)),
                        "physical_files": [{"path": str(folder / name), "bytes": len(raw), "sha256": qualification.digest(raw)}
                                           for name, raw in physical.items()]})
        if number == target:
            current = delta
    require(current is not None, "current_capture_record_required")
    return {"sequence": target, "script_sha256": host_event["script_sha256"], "delta": current,
            "retained_resources": list(resources.values()),
            "resource_origins": [{"id": key[0], "revision": key[1], "sequence": origins[key]} for key in resources],
            "wire_sources": [], "capture_sources": sources,
            "event_file_sha256": qualification.digest(events_raw),
            "evidence_phase": "completed worker output and event before response send",
            "transport_confirmation": "not established by this reader; actual response and post-close wire are separate evidence",
            "scope": "current completed output plus prior immutable resource outputs in this worker"}
