"""Bounded fake-only checks for the N/P/G reuse delta and zero-start handoff."""

import argparse
from contextlib import ExitStack, redirect_stdout
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import traceback
import types
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
OLD = ROOT / "verification/m4_local_relation_consumption_001"
CYCLE = "M4-SELECTED-GEOMETRY-CONSUMPTION-001"
IMAGE_SHA = "42466e241a4239552fa418b7f79bf1fd73c10092f174c3e87444ed5e93cbed0a"


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load(path, name):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(path.read_bytes(), str(path), "exec", dont_inherit=True), module.__dict__)
    return module


def plan_fixture(driver):
    common = "synthetic-common-python"
    installations = {profile: {"source_sha256": driver.SOURCE_BY_PROFILE[profile], "source_count": 137,
        "commit": driver.COMMIT_BY_PROFILE[profile], "dependency_python": common} for profile in ("P", "G")}
    sequence = [{"cell": "sgc" + str(index + 1).zfill(2), "round": index // 3 + 1, "task": "T1", "group": group}
                for index, group in enumerate(driver.GROUP_ORDER)]
    return {"synthetic": True, "cycle_id": CYCLE, "batch": CYCLE, "sequence": sequence,
        "logical_denominator": 9, "per_arm": 3, "image_count": 1, "new_images": 0,
        "installation_ready": installations["P"], "installations": installations,
        "arms": {group: {"actor_group": "N" if group == "N" else "P",
            "installation_profile": "P" if group in ("N", "P") else "G",
            "source_sha256": None if group == "N" else driver.SOURCE_BY_PROFILE[group]}
            for group in ("N", "P", "G")}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()
    output = HERE / arguments.output
    assert output.parent.resolve() == HERE.resolve() and output.name not in (".", "..")
    output.mkdir(exist_ok=False)
    checks, evidence, attempts = [], {}, []
    source_paths = [BATCH / "runtime" / name for name in ("driver.py", "actor.py", "consumer_transport.py", "pack_quality.py")]
    sources = {str(path): path.read_bytes() for path in source_paths}

    def put(path, raw):
        assert path.resolve().is_relative_to(output.resolve())
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(raw)

    def check(name, passed):
        checks.append({"check": name, "passed": bool(passed)})

    def forbidden(*args, **kwargs):
        attempts.append("external process/socket/signal")
        raise AssertionError(attempts[-1])

    error = None
    try:
        with ExitStack() as guard:
            for name in ("Popen", "run", "call", "check_call", "check_output"):
                guard.enter_context(patch.object(subprocess, name, side_effect=forbidden))
            for name in ("socket", "create_connection"):
                guard.enter_context(patch.object(socket, name, side_effect=forbidden))
            for name in ("system", "kill"):
                guard.enter_context(patch.object(os, name, side_effect=forbidden))
            driver = load(BATCH / "runtime/driver.py", "_sgc_driver_synthetic")
            actor = load(BATCH / "runtime/actor.py", "_sgc_actor_synthetic")
            transport = load(BATCH / "runtime/consumer_transport.py", "_sgc_transport_synthetic")
            pack = load(BATCH / "runtime/pack_quality.py", "_sgc_pack_synthetic")
            plan = plan_fixture(driver)
            digest = "a" * 64
            go = {"task": CYCLE, "authorized": True, "plan_sha256": digest, "max_consumers": 9}
            driver.go_contract(go, plan, digest)
            check("fixed_nine_NPG_PGN_GNP", tuple(row["group"] for row in plan["sequence"]) == ("N", "P", "G", "P", "G", "N", "G", "N", "P"))
            mappings = []
            for slot in plan["sequence"]:
                old = copy.deepcopy(slot)
                internal, ready, profile = driver.arm_runtime(plan, slot)
                check(slot["cell"] + ":private_mapping_preserves_external_slot", slot == old
                      and internal["external_group"] == slot["group"] and internal["group"] == ("N" if slot["group"] == "N" else "P"))
                mappings.append({"slot": slot, "internal": internal, "profile": profile, "ready": ready})
            for changes, expected in (({"task": "M4-LOCAL-RELATION-CONSUMPTION-001"}, "wrong_consumption_GO"),
                                      ({"max_consumers": 6}, "GO_not_bound_to_nine_frozen_slots"),
                                      ({"plan_sha256": "b" * 64}, "GO_not_bound_to_nine_frozen_slots")):
                try:
                    driver.go_contract({**go, **changes}, plan, digest)
                except AssertionError as exception:
                    check("reject_foreign_GO_" + next(iter(changes)), str(exception) == expected)
                else:
                    check("reject_foreign_GO_" + next(iter(changes)), False)
            bad = copy.deepcopy(plan)
            bad["arms"]["G"]["source_sha256"] = driver.SOURCE_BY_PROFILE["P"]
            try:
                driver.arm_runtime(bad, plan["sequence"][2])
            except AssertionError as exception:
                check("G_source_cross_binding_rejected", str(exception) == "arm_source_changed")
            else:
                check("G_source_cross_binding_rejected", False)
            evidence["arm_mappings"] = mappings

            check("transport_byte_identical", (BATCH / "runtime/consumer_transport.py").read_bytes() == (OLD / "runtime/consumer_transport.py").read_bytes())
            check("actor_byte_identical", (BATCH / "runtime/actor.py").read_bytes() == (OLD / "runtime/actor.py").read_bytes())
            check("fixed_CLI_bytes", sha(transport.EXE.read_bytes()) == "01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6")
            settings = transport.settings()
            check("common_model_effort_login_route", settings["model"] == "gpt-6.1-sol" and settings["model_reasoning_effort"] == "medium"
                and settings["forced_login_method"] == "chatgpt" and settings["model_provider"] == "openai_http"
                and settings["model_providers.openai_http"]["base_url"] == "https://chatgpt.com/backend-api/codex")
            check("hooks_and_memories_disabled", all(settings[key] is False for key in
                ("features.hooks", "features.apps", "features.memories", "memories.use_memories", "features.multi_agent", "features.plugins"))
                and settings['plugins."agent-learning@agent-learning-local".enabled'] is False)
            image = (OLD / "input/INITIAL.png").read_bytes()
            assert sha(image) == IMAGE_SHA
            fixture_root = output / "i"
            put(fixture_root / "input/INITIAL.png", image)
            image_plan = {**plan, "inputs": {"image": "input/INITIAL.png", "image_bytes": len(image), "image_sha256": IMAGE_SHA}}
            transport.HERE = fixture_root
            image_meta = transport.initial_image_metadata(image_plan)
            argvs = {}
            for group in ("N", "P", "G"):
                internal = "N" if group == "N" else "P"
                cell = fixture_root / group / "cell.json"
                put(cell, encoded({"group": internal, "endpoint": "SYNTHETIC-INERT-ENDPOINT"}))
                argv = transport.argv_for("synthetic-python", cell, cell.parent / "w", cell.parent / "f.txt", initial_image=image_meta["path"])
                check(group + ":real_image_argument", argv[argv.index("--image") + 1] == image_meta["path"])
                check(group + ":fixed_model_argument", argv[argv.index("-m") + 1] == "gpt-6.1-sol" and "--ignore-user-config" in argv
                      and "--ignore-rules" in argv and "--ephemeral" in argv and "--strict-config" in argv)
                argvs[group] = argv
            evidence["argv"] = argvs
            evidence["image"] = image_meta
            evidence["settings"] = settings
            evidence["account_verification"] = {"synthetic_verifies_requested_chatgpt_login_path": True,
                "Pro_entitlement_checked_by_synthetic": False, "resolved_model": None, "resolved_effort": None}

            semantic = {"synthetic": True, "condition": {"profile": "semantic"}, "group": "geometry group",
                "usage": {"condition": "semantic usage"}, "unknown_field": ["retained", {"cost": 7}],
                "path": "C:\\SYNTHETIC source folder\\a.txt"}
            text = " \r\n" + json.dumps(semantic, ensure_ascii=False, indent=3) + "\n  "
            product_result = {"content": [{"type": "text", "text": text}], "isError": False,
                "measurement_contracts": semantic, "context": {"profile": semantic}, "unknown_future": semantic}
            owner = actor.Owner.__new__(actor.Owner)
            owner.out = output / "o"
            owner.out.mkdir()
            owner.calls = owner.bytes = 0
            owner.logs = []
            owner.image_construction_violation = False
            owner.read_names = actor.TOOLS_BY_GROUP["P"]
            owner.peer = types.SimpleNamespace(call=lambda request, timeout_s: {"jsonrpc": "2.0", "id": request["id"], "result": copy.deepcopy(product_result)})
            owner.image_construction_status = lambda: {"observed": False, "status": "not_observed_in_recorded_scope"}
            request = {"jsonrpc": "2.0", "id": "synthetic-full-result", "method": "tools/call",
                "params": {"name": "human_eye_spatial_relations", "arguments": {"target": {"id": "a"}, "candidates": [{"id": "b"}]}}}
            response = owner.handle(copy.deepcopy(request))
            check("default_complete_result_passthrough", response["result"] == product_result and response["result"]["content"][0]["text"] == text)
            evidence["default_passthrough"] = {"synthetic": True, "request": request, "response": response}

            def package_zero(name, consumer_record):
                folder = output / name / "e"
                folder.mkdir(parents=True)
                mapping = {"synthetic": True, "generated_before_consumer": True, "rows": [dict(slot,
                    anonymous_id="answer_" + sha(("synthetic|" + slot["cell"]).encode())[:16]) for slot in plan["sequence"]]}
                mapping_raw = encoded(mapping)
                prompt = b"SYNTHETIC packaging input; no task answer or consumer.\n"
                package_plan = {**plan, "tasks": {"T1": {}}, "private_anonymous_map_sha256": sha(mapping_raw),
                    "inputs": {"image": "input/INITIAL.png", "image_sha256": IMAGE_SHA, "image_bytes": len(image),
                               "prompt": "input/PROMPT.txt", "prompt_sha256": sha(prompt)}}
                plan_raw = encoded(package_plan)
                slot = plan["sequence"][0]
                row = {**slot, "consumer": consumer_record, "finish": None, "errors": [] if consumer_record else [{"type": "SyntheticStartError", "message": "synthetic before consumer"}],
                    "cell_started_ns": 30, "cell_ended_ns": 40, "full_cell_wall_ns": 10, "within_570s": True}
                run = {"synthetic": True, "records": [row], "stop": "synthetic terminal stop; no replacement",
                    "started_cells": 1, "maximum_consumers": 9, "all_planned_dispatched": False, "no_replacements": True,
                    "batch_started_ns": 10, "batch_ended_ns": 50, "batch_wall_ns": 40}
                controls = {"PLAN.json": plan_raw, "FREEZE.json": encoded({"plan_sha256": sha(plan_raw)}),
                    "private/ANON_MAP.json": mapping_raw, "RUN_RESULT.json": encoded(run),
                    "GO.json": encoded({"task": CYCLE, "authorized": True, "max_consumers": 9, "plan_sha256": sha(plan_raw)}),
                    "STARTED.json": encoded({"started_ns": 20, "max_consumers": 9, "plan_sha256": sha(plan_raw)}),
                    "input/INITIAL.png": image, "input/PROMPT.txt": prompt,
                    "SYNTHETIC_SCOPE.json": encoded({"synthetic": True, "real_GO": False, "real_consumers": 0})}
                for relative, raw in controls.items():
                    put(folder / relative, raw)
                if consumer_record is not None:
                    put(folder / "cells" / slot["cell"] / "CONSUMER.json", encoded(consumer_record))
                pack.HERE, pack.EVAL = folder / "q", folder
                pack.HERE.mkdir()
                previous = sys.argv
                capture = io.StringIO()
                try:
                    sys.argv = ["synthetic-pack-only", "h"]
                    with redirect_stdout(capture):
                        pack.main()
                finally:
                    sys.argv = previous
                put(output / name / "STDOUT.txt", capture.getvalue().encode())
                index = json.loads((folder / "q/h/public/INDEX.json").read_bytes())
                by_id = {answer["anonymous_id"]: answer for answer in index["answers"]}
                ordered = [by_id[row["anonymous_id"]] for row in mapping["rows"]]
                check(name + ":all_nine_slots_retained", index["fixed_slots"] == len(ordered) == 9 and index["scoring_performed"] is False)
                check(name + ":first_failed_tail_eight_not_run", ordered[0]["execution_record_state"] == ("failed_before_consumer" if consumer_record is None else "failed")
                    and ordered[0]["answer_state"] == "missing" and all((answer["execution_record_state"], answer["answer_state"]) == ("not_run", "not_run") for answer in ordered[1:]))
                control = {key: value for key, value in controls.items() if key.endswith(".json")}
                wrong = dict(control, **{"GO.json": encoded({"task": "M4-LOCAL-RELATION-CONSUMPTION-001", "authorized": True, "max_consumers": 9, "plan_sha256": sha(plan_raw)})})
                try:
                    pack.validate_zero_launch_failure(run, wrong)
                except AssertionError as exception:
                    check(name + ":old_GO_rejected", str(exception) == "zero-launch GO binding mismatch")
                else:
                    check(name + ":old_GO_rejected", False)
                return {"synthetic": True, "logical_slots": 9, "not_run_tail": 8, "output": str(folder / "q/h")}

            evidence["zero_start_none"] = package_zero("a", None)
            first = plan["sequence"][0]
            failed = {**first, "group": "N", "external_group": "N", "consumer_pid": None,
                "status": "failed", "valid_completion": False, "thread_id": None, "final": None,
                "errors": [{"type": "SyntheticPopenError", "message": "synthetic Popen failed"}]}
            evidence["zero_start_dict"] = package_zero("b", failed)
            for slot in plan["sequence"][:3]:
                internal = "N" if slot["group"] == "N" else "P"
                consumer = {**slot, "group": internal, "external_group": slot["group"], "status": "completed", "final": text}
                tool_response = {"jsonrpc": "2.0", "id": "synthetic", "result": product_result}
                source = {"CONSUMER.json": encoded(consumer), "PUBLIC_FINAL.txt": text.encode(),
                    "owner/tool_01/REQUEST.json": encoded(request), "owner/tool_01/RESPONSE.json": encoded(tool_response)}
                destination = output / "c" / slot["group"]
                answer, _ = pack.handoff_one(slot, {"anonymous_id": "answer_" + sha(slot["group"].encode())[:16]}, slot, source, destination)
                tools = json.loads((destination / "tool_evidence.json").read_bytes())
                check(slot["group"] + ":group_binding_and_semantic_payload", answer["answer_state"] == "present"
                    and (destination / "answer.txt").read_bytes() == text.encode()
                    and tools["owner_attempts"][0]["responses"][0]["value"] == {"result": product_result})
                wrong = dict(source, **{"CONSUMER.json": encoded(dict(consumer, external_group="synthetic_wrong"))})
                try:
                    pack.handoff_one(slot, {"anonymous_id": "synthetic-wrong"}, slot, wrong, output / "never-created")
                except AssertionError as exception:
                    check(slot["group"] + ":wrong_external_binding_rejected", str(exception) == "consumer external/internal group binding mismatch")
                else:
                    check(slot["group"] + ":wrong_external_binding_rejected", False)
    except BaseException:
        error = traceback.format_exc()
    unchanged = all(Path(path).read_bytes() == raw for path, raw in sources.items())
    report = {"cycle_id": CYCLE, "synthetic": True, "passed": not error and not attempts and unchanged and all(row["passed"] for row in checks),
        "checks": checks, "check_count": len(checks), "failed_checks": [row for row in checks if not row["passed"]],
        "unexpected_error": error, "external_operation_attempts": attempts, "runtime_sources_unchanged": unchanged,
        "source_sha256": {path: sha(raw) for path, raw in sources.items()}, "test_source_sha256": sha(Path(__file__).read_bytes()),
        "model_consumers": 0, "Blender_sessions": 0, "real_product_calls": 0, "paid_API_calls": 0,
        "real_GO_created": False, "new_images_rendered": 0,
        "scope": "reuse delta only; synthetic cells, controls, finals and endpoints stay under this output"}
    put(output / "RESULTS.json", encoded(report))
    put(output / "EVIDENCE.json", encoded(evidence))
    print(json.dumps({"passed": report["passed"], "checks": len(checks), "unexpected_error": error}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
