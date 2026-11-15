"""Read-only live-task source, device, transport, clocks and closure audit."""

import argparse
import ast
import base64
import hashlib
import json
from pathlib import Path
import zlib


HERE = Path(__file__).resolve().parent
RUNTIME = Path("D:/he_m4_target_consume_001")
SOURCE = "776b0f0914e116fece16d2b3875ee16ffebf4896a7e394861287ffaa6fe025be"
ORDER = ["N1", "P1", "P2", "N2", "N3", "P3"]


def read(path):
    return json.loads(Path(path).read_bytes())


def rows(path):
    return [json.loads(line) for line in Path(path).read_bytes().splitlines() if line.strip()]


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


class Review:
    def __init__(self):
        self.pins, self.checks, self.records = {}, [], []

    def pin(self, path, role):
        path = Path(path).resolve()
        key = str(path)
        if key not in self.pins:
            raw = path.read_bytes()
            self.pins[key] = {"path": key, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "roles": []}
        if role not in self.pins[key]["roles"]:
            self.pins[key]["roles"].append(role)
        return self.pins[key]

    def check(self, name, passed, actual=None):
        value = {"name": name, "passed": bool(passed)}
        if actual is not None:
            value["actual"] = actual
        self.checks.append(value)

    def install(self):
        path = HERE / "PRODUCT_RUN_BINDING.json"
        binding = read(path)
        self.pin(path, "fixed product binding")
        for item in binding["source_manifest"]:
            actual = self.pin(Path(binding["install_root"]) / item["path"], "fixed installed source")
            self.check("installed/" + item["path"], actual["sha256"] == item["sha256"])
        identity = {name: binding[name] for name in ("base_version", "implementation_revision")}
        identity["files"] = binding["source_manifest"]
        self.check("installed/source141", len(binding["source_manifest"]) == 141
                   and hashlib.sha256(encoded(identity)).hexdigest() == binding["source_sha256"] == SOURCE)
        self.binding = binding

    def native_wire(self, folder, label):
        resources, captures, raw_sources = {}, [], []
        wire = read(folder / "native/WIRE/INDEX.json")
        manifest = {item["path"]: item["sha256"] for item in self.binding["source_manifest"]}
        loaded = []
        for item in wire:
            path = folder / "native/WIRE" / f"{item['sequence']:03}"
            tx, rx = (path / "REQUEST.bin").read_bytes(), (path / "RESPONSE.bin").read_bytes()
            self.pin(path / "REQUEST.bin", "actual native TCP request")
            self.pin(path / "RESPONSE.bin", "actual native TCP response")
            self.check(label + "/native_wire/" + str(item["sequence"]), len(tx) == item["request_bytes"]
                       and len(rx) == item["response_attempted_bytes"] and item["response_sendall_completed"] is True)
            request, response = json.loads(tx), json.loads(rx)
            if request["type"] != "execute_code":
                continue
            code = request["params"]["code"]
            for node in ast.walk(ast.parse(code)):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == "compile" and len(node.args) >= 2):
                    continue
                expression = node.args[0]
                if not (isinstance(expression, ast.Call) and isinstance(expression.func, ast.Attribute)
                        and expression.func.attr == "decompress"):
                    continue
                blob = zlib.decompress(base64.b64decode(ast.literal_eval(expression.args[0].args[0]), validate=True))
                source = Path(ast.literal_eval(node.args[1]))
                relative = source.relative_to(Path(self.binding["install_root"])).as_posix()
                actual = hashlib.sha256(blob).hexdigest()
                self.check(label + "/executed_product_source/" + relative,
                           actual == manifest[relative] == self.pin(source, "actual loaded host source")["sha256"])
                loaded.append(relative)
            stdout = response.get("result", {}).get("result", "")
            for line in stdout.splitlines():
                if line.startswith("CURRENT_RAW_SCENE:"):
                    raw_sources.append({"sequence": item["sequence"], "packet": json.loads(line.split(":", 1)[1]),
                                        "script_sha256": hashlib.sha256(code.encode()).hexdigest()})
                if line.startswith("HUMAN_EYE_BLENDER_MCP:"):
                    inner = json.loads(line.split(":", 1)[1])
                    packet = inner.get("result", {})
                    if isinstance(packet, dict):
                        for resource in packet.get("resources", []):
                            resources[(resource["id"], resource["revision"])] = resource
                        capture = packet.get("capture", packet)
                        if isinstance(capture, dict) and capture.get("meshes"):
                            captures.append(capture)
        return {"wire": wire, "loaded_source_paths": sorted(set(loaded)), "raw_sources": raw_sources,
                "captures": captures, "materialized_resources": len(resources)}

    def slot(self, label, phase):
        folder = RUNTIME / phase / label
        result = read(folder / "SLOT_RESULT.json")
        publication = read(folder / "SLOT_PUBLICATION.json")
        close = read(folder / "RUNTIME_CLOSE.json")
        runtime = close["runtime"]
        self.pin(folder / "SLOT_RESULT.json", "original closed slot result")
        self.pin(folder / "SLOT_PUBLICATION.json", "result publication boundary")
        self.check(label + "/closed_success", result["status"] == publication["status"] == "completed"
                   and result["errors"] == close["errors"] == runtime["errors"] == [])
        clocks = result["clocks"]
        self.check(label + "/absolute_deadlines", clocks["consumer_deadline_ns"] - clocks["slot_started_ns"] == 450_000_000_000
                   and clocks["owned_deadline_ns"] - clocks["slot_started_ns"] == 600_000_000_000
                   and runtime["consumer_deadline_ns"] == clocks["consumer_deadline_ns"]
                   and runtime["owned_deadline_ns"] == clocks["owned_deadline_ns"])
        self.check(label + "/full_slot_publication", publication["complete_slot_ns"] == publication["slot_result_published_ns"] - clocks["slot_started_ns"]
                   and publication["result_sha256"] == self.pin(folder / "SLOT_RESULT.json", "original result")["sha256"]
                   and publication["owned_budget_passed"] is True
                   and clocks["cleanup_closed_ns"] <= publication["slot_result_published_ns"] < clocks["owned_deadline_ns"])
        cleanup = result["cleanup"]
        self.check(label + "/held_actor_exit", cleanup["actor_exit_code"] == 0 and cleanup["actor_process_handle_closed"] is True)
        for kind in (("native", "mcp") if result["group"] == "P" else ("native",)):
            spawn = read(folder / kind / "SPAWN.json")
            proof = read(folder / ("ROOT_" + kind.upper() + "_PROOF.json"))
            held = cleanup[kind]
            self.check(label + "/held_child/" + kind, spawn["pid"] == proof["runtime_pid"]
                       and spawn["parent_pid"] == result["owned"]["actor_pid"]
                       and proof["confirmed"] is True and held["confirmed"] is True and held["exit_code"] == 0
                       and held["handle_closed"] is True and held["forced_by_root"] is False)
        native = close["Blender_status"]["closed"]
        self.check(label + "/owned_native_restore", close["Blender_close"]["exit_code"] == 0
                   and close["Blender_close"]["process_reaped"] is True and native["poisoned"] is False
                   and native["initial_geometry_fingerprint"] == native["final_geometry_fingerprint"]
                   and close["Blender_status"]["source_file_unchanged"] is True)
        if result["group"] == "P":
            self.check(label + "/MCP_actor_retained_exit", close["MCP_stdio_close"]["confirmed"] is True
                       and close["MCP_stdio_close"]["exit_code"] == 0 and close["MCP_retained_exit"]["confirmed"] is True
                       and close["MCP_retained_exit"]["exit_code"] == 0 and close["MCP_retained_exit"]["handle_closed"] is True)
        device = runtime["device"]
        self.check(label + "/shared_device_load", self.pin(device["path"], "common raw camera fixture")["sha256"] == device["sha256"]
                   and device["loaded_elapsed_ns"] == device["loaded_closed_ns"] - device["loaded_started_ns"]
                   and clocks["slot_started_ns"] <= device["loaded_started_ns"] <= device["loaded_closed_ns"] < clocks["owner_ready_ns"])
        wire = self.native_wire(folder, label)
        saved = read(folder / "SAVED_EVIDENCE.json")
        events = rows(folder / "native/WORKER_EVENTS.jsonl")
        for source in saved["sources"]:
            actual = read(source["path"])
            self.check(label + "/actual_raw_source/" + source["source_ref"],
                       self.pin(source["path"], "actual current native source")["sha256"] == source["sha256"])
            native_call = runtime["native_calls"][source["native_call_index"] - 1]
            sequences = {event["sequence"] for event in events if "sequence" in event
                         and native_call["started_ns"] <= event["started_ns"] <= native_call["closed_ns"]}
            matches = [row for row in wire["raw_sources"] if row["sequence"] in sequences and row["packet"]["source"] == {
                key: value for key, value in actual["source"].items() if key != "asset_sha256"} and row["packet"]["objects"] == actual["objects"]]
            self.check(label + "/raw_source_wire_binding/" + source["source_ref"], len(matches) == 1)
        for frame in saved["frames"]:
            self.check(label + "/producer_frame/" + frame["ref"],
                       self.pin(frame["PNG"], "actual producer PNG")["sha256"] == frame["PNG_sha256"]
                       and self.pin(frame["NPZ"], "actual producer NPZ")["sha256"] == frame["NPZ_sha256"]
                       and len(frame["source_face_offsets"]) == len(frame["object_names"]) + 1
                       and frame["source_face_offsets"][0] == 0 and frame["camera_sha256"] == device["sha256"])
        product_calls = []
        if result["group"] == "P":
            index = rows(folder / "product_full/INDEX.jsonl")
            self.check(label + "/one_producer_per_public_call", len(index) == len(runtime["public_requests"]))
            for position, record in enumerate(index):
                full = read(record["path"])
                request = runtime["public_requests"][position]
                self.check(label + "/default_brief_and_original_archive/" + str(position),
                           "response_detail" not in request["request"]["params"]["arguments"]
                           and self.pin(record["path"], "same producer backstage result")["sha256"] == record["sha256"]
                           and record["new_observations_for_archive"] == 0)
                texts = [json.loads(block["text"]) for block in request["response"]["result"]["content"] if block["type"] == "text"]
                self.check(label + "/public_brief_has_no_full_frames/" + str(position), len(texts) == 1 and "frames" not in texts[0])
                captures = [cap for cap in wire["captures"] if cap.get("observation_target", {}).get("camera_plan")]
                self.check(label + "/actual_own_camera_generation/" + str(position), bool(captures))
                if captures:
                    expected_views = read(device["path"])["views"]
                    actual_views = captures[position if position < len(captures) else -1]["observation_target"]["camera_plan"]["views"]
                    projected = [{key: row[key] for key in expected_views[0]} for row in actual_views]
                    self.check(label + "/camera_matches_shared_device/" + str(position), encoded(projected) == encoded(expected_views))
                receipt = request["receipt"]
                io = [row for row in rows(folder / "mcp_io/MCP_IO.jsonl") if row["id"] == request["id"]]
                self.check(label + "/public_request_clock/" + str(position), len(io) == 1
                           and request["complete_client_call_ns"] == request["closed_ns"] - request["started_ns"]
                           and request["client_flush_to_received_ns"] == receipt["received_complete_ns"] - receipt["stdin_flushed_ns"])
                if io:
                    product_calls.append({"id": request["id"], "server_ns": io[0]["request_to_reply_ns"],
                        "client_transport_ns": request["client_flush_to_received_ns"],
                        "complete_client_call_ns": request["complete_client_call_ns"],
                        "server_start_ns": io[0]["request_received_ns"], "server_end_ns": io[0]["reply_completed_ns"],
                        "client_start_ns": receipt["stdin_flushed_ns"], "client_end_ns": receipt["received_complete_ns"],
                        "relation": "server and transport are independently enclosed by outer call, no strict nesting between them"})
            if phase == "qualification":
                self.check(label + "/qualification_one_product_call", len(index) == 1)
                self.check(label + "/common_uses_same_product_frame", len(saved["frames"]) == 1 and saved["frames"][0]["origin"] == "product")
        if phase == "qualification":
            self.check(label + "/no_model_qualification", result["consumer_path"] is None and result["consumer_record"] is None)
        metrics = read(folder / "owner/METRICS.json")
        self.check(label + "/tool_cap", metrics["tool_attempts"] <= 12)
        self.records.append({"label": label, "group": result["group"], "phase": phase,
            "complete_slot_ns": publication["complete_slot_ns"], "actor_runtime_ns": close["complete_actor_runtime_ns"],
            "device_load_ns": device["loaded_elapsed_ns"], "public_requests": product_calls,
            "native_TCP": wire["wire"], "actual_loaded_product_source_paths": wire["loaded_source_paths"],
            "current_raw_source_reads": saved["sources"], "frames": saved["frames"], "tool_attempts": metrics["tool_attempts"],
            "content_metrics": metrics["public_content"], "wrapper_work": runtime["wrapper_work"],
            "actual_qualified_P_work": read(folder / "product_full/call_001/SERVICE_RESULT.json").get("work") if result["group"] == "P" else None})

    def budget(self, qualification_only):
        root = RUNTIME / "budget"
        claims = [read(path) for path in sorted((root / "claims").glob("*.json"))]
        starts = [row for row in claims if row["kind"] == "Blender_start"]
        attempts = [row for row in claims if row["kind"] == "raster_attempt"]
        business = [row for row in claims if row["kind"] == "business_tool"]
        counts = {phase: {"actual": 0, "upper": 0, "unsettled": 0} for phase in ("qualification", "formal")}
        for claim in starts + attempts:
            settlement = root / "settlements" / (claim["token"] + ".json")
            self.check("budget/settled/" + claim["token"], settlement.is_file())
            if not settlement.is_file():
                counts[claim["phase"]]["upper"] += claim["reserved_upper_bound"]
                counts[claim["phase"]]["unsettled"] += 1
                continue
            settled = read(settlement)
            self.check("budget/source_binding/" + claim["token"], self.pin(root / "claims" / (claim["token"] + ".json"), "persistent admission")["sha256"] == settled["claim_sha256"])
            if claim["kind"] == "raster_attempt":
                count = counts[claim["phase"]]
                count["actual"] += settled["actual_attempts"] or 0
                count["upper"] += claim["reserved_upper_bound"] if settled["actual_attempts"] is None else settled["actual_attempts"]
                self.check("budget/unit_attempt/" + claim["token"], settled["actual_attempts"] == settled["confirmed_attempts_lower_bound"] == 1)
        per_slot = {label: sum(claim["label"] == label for claim in attempts) for label in {row["label"] for row in claims}}
        per_business = {label: sum(claim["label"] == label for claim in business) for label in per_slot}
        self.check("budget/fixed_caps", len(starts) <= 8 and counts["qualification"]["upper"] <= 12
                   and counts["formal"]["upper"] <= 36 and sum(row["upper"] for row in counts.values()) <= 48
                   and all(value <= 6 for value in per_slot.values()) and all(value <= 12 for value in per_business.values()))
        if qualification_only:
            self.check("budget/two_qualification_starts_two_attempts", len(starts) == 2 and len(attempts) == 2
                       and counts["qualification"]["actual"] == counts["qualification"]["upper"] == 2)
        return {"starts": len(starts), "attempts": len(attempts), "phases": counts,
                "per_slot_attempts": per_slot, "business_admissions": per_business,
                "business_settlement": "business admissions are committed at admission and have no asynchronous settlement"}

    def finish(self, qualification_only):
        self.install()
        labels = ["N_qual", "P_qual"] + ([] if qualification_only else ORDER)
        for label in labels:
            self.slot(label, "qualification" if label.endswith("_qual") else "formal")
        budget = self.budget(qualification_only)
        baseline = read(HERE / "BASELINE.json")
        for path, sha in baseline["protected_old_pins"].items():
            self.check("history/" + sha[:10], self.pin(path, "protected old namespace seal")["sha256"] == sha)
        for name in ("owned_runtime.py", "mcp_entry.py", "budget.py", "qual_driver.py", "run_slot.py", "bridge.py", "native_tools.py",
                     "fixtures/DEVICE_PREPARATION.json", "PREPARED.json", "STATIC_PREPARATION_FAILURES.json"):
            self.pin(HERE / name, "current frozen preparation source")
        self.pin(Path(__file__), "this runtime review source")
        self.check("inputs_unchanged_after_review", all(Path(row["path"]).stat().st_size == row["bytes"]
                   and hashlib.sha256(Path(row["path"]).read_bytes()).hexdigest() == row["sha256"] for row in self.pins.values()))
        passed = all(row["passed"] for row in self.checks)
        result = {"schema": "target-task-runtime-review-v1", "passed_checked_scope": passed,
                  "qualification_only": qualification_only, "checks": self.checks,
                  "failed_checks": [row for row in self.checks if not row["passed"]],
                  "records": self.records, "budget": budget,
                  "source_scope": "141 installed files checked, actual transmitted host source subset separately listed",
                  "author_association": "Reviewer authored owned runtime, helper copies, budget, native audit and qualification driver. Root alone ran the live slots. Independent geometry/pixel/task grading belongs to other reviewers.",
                  "time_scope": "Four windows remain separate. Complete slot includes result fsync, excludes final marker publication. Device preparation, actual per-slot load, P own-camera generation and whole-scene wrapper guard work are separate. Wrapper visits remain unmeasured/source-derived.",
                  "quality_and_cost_boundary": "Qualification clocks are plumbing observations only. Formal task timing benefits require sealed full quality and comparable consumer usage. This source/runtime review does not price or rank model costs.",
                  "historical_preservation": "Static edit parse failure and removed unexecuted retry snapshot preserved. Old cleanup denial and extra-runtime unknown are not replaced by new process evidence.",
                  "new_operations": {"Blender_starts": 0, "product_calls": 0, "rasters": 0, "models": 0},
                  "input_pins": sorted(self.pins.values(), key=lambda row: row["path"])}
        prefix = "QUAL_RUNTIME_REVIEW" if qualification_only else "RUNTIME_REVIEW"
        path = HERE / (prefix + ".json")
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        md = ["# 当前任务运行证据复核", "", f"`passed_checked_scope={str(passed).lower()}`，{len(self.checks)}项检查。", "",
              f"本次范围包含{len(labels)}个关闭槽。owned启动{budget['starts']}次，逐次raster准入{budget['attempts']}次。", "",
              "安装141源与实际传输的宿主源码子集分别核对。P默认brief与后台同producer归档、共同图片复用、真实Blender原始读取和源面输入顺序按原件核查。", "",
              "共享device每槽实际加载单列，P仍实际生成自身相机。NativeSession保护本身遍历全场，相关时间包含在槽内，循环访问次数保持unmeasured/source-derived。", "",
              "服务端和客户端传输各有自身起止，二者允许轻微交叉，均由外层调用及完整槽覆盖。完整槽计至结果fsync后，最后标记文件发布另列。资格时界用于核对链路，正式模型收益需先封存完整质量和可比usage。", "",
              "本复核者同时编写了运行器和资格适配，实际执行由根完成。独立几何、像素和答案评分另行处理。新增Blender、产品、raster和模型调用均为0。完整输入摘要及逐项结果见JSON。"]
        md_path = HERE / (prefix + ".md")
        with md_path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write("\n".join(md) + "\n")
        print(json.dumps({"passed_checked_scope": passed, "checks": len(self.checks), "failed": result["failed_checks"],
                          "JSON_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                          "MD_sha256": hashlib.sha256(md_path.read_bytes()).hexdigest()}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qualification", action="store_true")
    args = parser.parse_args()
    Review().finish(args.qualification)


if __name__ == "__main__":
    main()
