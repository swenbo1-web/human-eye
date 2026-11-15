"""Read-only live-task source, device, transport, clocks and closure audit."""

import argparse
import ast
import base64
import hashlib
import json
from pathlib import Path
import statistics
import time
import zlib


HERE = Path(__file__).resolve().parent
RUNTIME = Path("D:/he_m5_task_consume_001")
SOURCE = {"A":"776b0f0914e116fece16d2b3875ee16ffebf4896a7e394861287ffaa6fe025be", "B":"7d2d4352f462c64a46e6fccf447c6f030c08b96e95517a3b2b6776ed50b69a6a"}
ORDER = ["A1", "B1", "B2", "A2", "A3", "B3"]


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
        self.bindings = {}
        for group in ("A", "B"):
            path = HERE / (group + "_RUN_BINDING.json")
            binding = read(path)
            self.pin(path, "fixed product binding")
            for item in binding["source_manifest"]:
                actual = self.pin(Path(binding["install_root"]) / item["path"], "fixed installed source")
                self.check("installed/" + group + "/" + item["path"], actual["sha256"] == item["sha256"])
            identity = {name: binding[name] for name in ("base_version", "implementation_revision")}
            identity["files"] = binding["source_manifest"]
            self.check("installed/" + group + "/source141", len(binding["source_manifest"]) == 141
                       and hashlib.sha256(encoded(identity)).hexdigest() == binding["source_sha256"] == SOURCE[group])
            self.bindings[group] = binding

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
        self.binding = self.bindings[result["group"]]
        publication = read(folder / "SLOT_PUBLICATION.json")
        close = read(folder / "RUNTIME_CLOSE.json")
        runtime = close["runtime"]
        self.pin(folder / "SLOT_RESULT.json", "original closed slot result")
        self.pin(folder / "SLOT_PUBLICATION.json", "result publication boundary")
        self.check(label + "/closed_status_consistent", result["status"] == publication["status"]
                   and (result["status"] != "completed" or result["errors"] == close["errors"] == runtime["errors"] == []))
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
        for kind in ("native", "mcp"):
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
        if result["group"] in ("A", "B"):
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
        if result["group"] in ("A", "B"):
            index = rows(folder / "product_full/INDEX.jsonl")
            self.check(label + "/one_producer_per_public_call", len(index) == len(runtime["public_requests"]))
            for position, record in enumerate(index):
                full = read(record["path"])
                request = runtime["public_requests"][position]
                self.check(label + "/default_brief_and_original_archive/" + str(position),
                           (phase != "qualification" or "response_detail" not in request["request"]["params"]["arguments"])
                           and self.pin(record["path"], "same producer backstage result")["sha256"] == record["sha256"]
                           and record["new_observations_for_archive"] == 0)
                texts = [json.loads(block["text"]) for block in request["response"]["result"]["content"] if block["type"] == "text"]
                detail = request["request"]["params"]["arguments"].get('response_detail')
                self.check(label + "/public_default_brief_shape/" + str(position), len(texts) == 1
                           and (detail=='full' or "frames" not in texts[0]))
                self.check(label + '/standalone_actual_public_records/' + str(position),
                    self.pin(request['request_path'],'actual internal public request')['sha256']==request['request_sha256']
                    and self.pin(request['response_path'],'actual internal public response')['sha256']==request['response_sha256']
                    and read(request['request_path'])==request['request'] and read(request['response_path'])==request['response']
                    and request['producer_archive_index']==request['internal_public_call_index']==position+1)
                self.check(label + '/actual_stdio_public_bytes/' + str(position),
                    self.pin(request['actual_TX_path'],'actual product stdio TX')['sha256']==request['actual_TX_sha256']
                    and self.pin(request['actual_RX_path'],'actual product stdio RX')['sha256']==request['actual_RX_sha256']
                    and read(request['actual_TX_path'])==request['request'] and read(request['actual_RX_path'])==request['response'])
                if full.get("result_kind") == "active_observation":
                    captures = [cap for cap in wire["captures"] if cap.get("observation_target", {}).get("camera_plan")]
                    self.check(label + "/actual_own_camera_generation/" + str(position), bool(captures))
                    if captures:
                        expected_views = read(device["path"])["views"]
                        actual_views = captures[-1]["observation_target"]["camera_plan"]["views"]
                        projected = [{key: row[key] for key in expected_views[0]} for row in actual_views]
                        self.check(label + "/camera_matches_shared_device/" + str(position), encoded(projected) == encoded(expected_views))
                receipt = request["receipt"]
                io = [row for row in rows(folder / "mcp_io/MCP_IO.jsonl") if row["id"] == request["id"]]
                self.check(label + "/public_request_clock/" + str(position), len(io) == 1
                           and request["complete_client_call_ns"] == request["closed_ns"] - request["started_ns"]
                           and request["client_flush_to_received_ns"] == receipt["received_complete_ns"] - receipt["stdin_flushed_ns"])
                if io:
                    self.check(label + '/independent_public_windows_inside_complete_slot/' + str(position),
                        all(clocks['slot_started_ns']<=value<=publication['slot_result_published_ns'] for value in
                            (io[0]['request_received_ns'],io[0]['reply_completed_ns'],receipt['stdin_flushed_ns'],receipt['received_complete_ns'])))
                    product_calls.append({"id": request["id"], "server_ns": io[0]["request_to_reply_ns"],
                        "client_transport_ns": request["client_flush_to_received_ns"],
                        "complete_client_call_ns": request["complete_client_call_ns"],
                        "server_start_ns": io[0]["request_received_ns"], "server_end_ns": io[0]["reply_completed_ns"],
                        "client_start_ns": receipt["stdin_flushed_ns"], "client_end_ns": receipt["received_complete_ns"],
                        "actual_RX_bytes":receipt['RX_bytes'],"actual_TX_bytes":receipt['TX_bytes'],
                        "response_detail":detail,"actual_work":full.get('work'),"stages":full.get('stages'),
                        "retained_read_context":read(record['read_context']),
                        "relation": "server/client own samples lie inside complete slot; no strict cross-process or flush-vs-received sample nesting"})
            if phase == "qualification":
                self.check(label + "/qualification_expected_public_calls", len(index) == (2 if result["group"] == "A" else 1))
                self.check(label + "/common_uses_same_product_frame", len(saved["frames"]) == 1 and saved["frames"][0]["origin"] == "product")
        if phase == "qualification":
            self.check(label + "/no_model_qualification", result["consumer_path"] is None and result["consumer_record"] is None)
        metrics = read(folder / "owner/METRICS.json")
        bridge = read(folder/'owner/BRIDGE_RESULT.json')
        indices=[index for call in bridge['calls'] for index in call['internal_public_call_indices']]
        self.check(label+'/outer_to_internal_public_binding',indices==list(range(1,len(runtime['public_requests'])+1)))
        if phase=='qualification':
            first=bridge['calls'][0]
            self.check(label+'/single_outer_required_facts_batch',first['name']=='execute_python'
                and first['internal_public_call_indices']==list(range(1,(2 if result['group']=='A' else 1)+1)))
        self.check(label + "/tool_cap", metrics["tool_attempts"] <= 12)
        self.records.append({"label": label, "group": result["group"], "phase": phase,
            "complete_slot_ns": publication["complete_slot_ns"], "actor_runtime_ns": close["complete_actor_runtime_ns"],
            "device_load_ns": device["loaded_elapsed_ns"], "public_requests": product_calls,
            "native_TCP": wire["wire"], "actual_loaded_product_source_paths": wire["loaded_source_paths"],
            "current_raw_source_reads": saved["sources"], "frames": saved["frames"], "tool_attempts": metrics["tool_attempts"],
            "content_metrics": metrics["public_content"], "wrapper_work": runtime["wrapper_work"],
            "actual_product_work": [call['actual_work'] for call in product_calls],
            "outer_to_internal_public_calls":bridge['calls'],
            "process_status":dict(root_cleanup=cleanup,actor_runtime_close=close,
                worker_close_generic_event=events[-1]['status'],
                worker_close_scope='Generic unknown close event is preserved independently of explicit closed RPC, actual held exits and wait/reap.'),
            "slot_status":publication['status'],"slot_errors":result['errors']})

    def budget(self, qualification_only):
        root = RUNTIME / "budget"
        claims = [read(path) for path in sorted((root / "claims").glob("*.json"))]
        starts = [row for row in claims if row["kind"] == "Blender_start"]
        attempts = [row for row in claims if row["kind"] == "raster_attempt"]
        business = [row for row in claims if row["kind"] == "business_tool"]
        consumers = [row for row in claims if row["kind"] == "consumer_task"]
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
                   and all(value <= 6 for value in per_slot.values()) and all(value <= 12 for value in per_business.values())
                   and len(consumers)<=6)
        if qualification_only:
            self.check("budget/two_qualification_starts_no_consumers",len(starts)==2 and len(consumers)==0)
        return {"starts": len(starts), "attempts": len(attempts), "phases": counts,
                "per_slot_attempts": per_slot, "business_admissions": per_business,
                "consumer_admissions":len(consumers),"consumer_claims":consumers,
                "business_settlement": "Outer business and consumer admissions commit once before work; no asynchronous settlement. Internal MCP requests are separate."}

    def finish(self, qualification_only):
        started=time.perf_counter_ns()
        if not qualification_only:
            seal=read(HERE/'QUALITY_SEAL.json')
            if (seal.get('cost_unlocked') is not True or started<=seal['sealed_ns']
                    or self.pin(HERE/'QUALITY.json','sealed independent quality')['sha256']!=seal['quality_sha256']):
                raise ValueError('quality_seal_required_before_formal_cost_read')
            self.pin(HERE/'QUALITY_SEAL.json','root quality/cost boundary')
        self.install()
        labels=[('A_qual','qualification'),('B_qual','qualification')]
        formal=None
        if not qualification_only:
            formal=read(RUNTIME/'RUN_RESULT.json')
            self.pin(RUNTIME/'RUN_RESULT.json','actual fixed formal attempts and not_run suffix')
            self.check('formal/fixed_records_once',[(row['slot_id'],row['group']) for row in formal['records']]
                ==[(name,name[0]) for name in ORDER] and formal['formal_batch_attempts']==1
                and formal['outer_retries']==formal['replacement_samples']==0)
            labels += [(row['slot_id'],'formal') for row in formal['records']
                       if row.get('result_path') and Path(row['result_path']).exists()]
        execution_errors=[]
        for label,phase in labels:
            try:
                self.slot(label,phase)
            except BaseException as error:
                import traceback
                execution_errors.append(dict(label=label,phase=phase,type=type(error).__name__,message=str(error),traceback=traceback.format_exc()))
                self.check(label+'/available_saved_runtime_scope',False,execution_errors[-1])
        budget=self.budget(qualification_only)
        baseline=read(HERE/'BASELINE.json')
        member_count=0
        for path,expected in baseline['protected_old_pins'].items():
            self.check('history/'+expected[:10],self.pin(path,'protected old namespace seal')['sha256']==expected)
            if not qualification_only and Path(path).name=='CONTENT_MANIFEST.json':
                checkout=Path(path).parents[2]
                for member in read(path)['files']:
                    actual=self.pin(checkout/member['path'],'registered old manifest member')
                    self.check('history/member/'+str(checkout/member['path']),actual['sha256']==member['sha256'] and actual['bytes']==member['bytes'])
                    member_count+=1
        frozen_name='QUALIFICATION_FREEZE.json' if qualification_only else 'FROZEN.json'
        frozen=read(HERE/frozen_name)
        self.pin(HERE/frozen_name,'root frozen execution inputs')
        for row in frozen['files']:
            actual=self.pin(row['path'],'root frozen execution input')
            self.check('frozen/'+row['path'],actual['sha256']==row['sha256'] and actual['bytes']==row['bytes'])
        for name in ('fixtures/DEVICE_REUSE.json','harness/HARNESS_READY.json','harness/PREPARATION_FIXES.json',
                     'harness/REUSED_SOURCE_PINS.json','STATIC_CHECKS/RESULT.json'):
            self.pin(HERE/name,'preparation source and evidence')
        self.pin(Path(__file__),'this saved runtime audit source')
        cost=None if qualification_only else self.cost(formal)
        self.check('inputs_unchanged_after_review',all(Path(row['path']).stat().st_size==row['bytes']
            and hashlib.sha256(Path(row['path']).read_bytes()).hexdigest()==row['sha256'] for row in self.pins.values()))
        passed=all(row['passed'] for row in self.checks)
        result=dict(schema='m5-task-runtime-review-v1',passed_checked_scope=passed,qualification_only=qualification_only,
            checks=self.checks,failed_checks=[row for row in self.checks if not row['passed']],records=self.records,
            execution_errors=execution_errors,budget=budget,formal_dispatch=formal,cost=cost,
            history=dict(protected_pins=len(baseline['protected_old_pins']),registered_old_manifest_member_entries=member_count),
            source_scope='Both141 installations fixed separately; actual transmitted source payloads checked against the matching A or B install. Current worktree is not used as A proof.',
            author_association='Reviewer authored lifecycle/runtime/budget/qualification harness and passive archives. Root alone executes actual Blender/consumers. Independent source/geometry/pixel/task grading belongs to separate reviewers.',
            time_scope='Complete slot from root checks/start through CLI/actor/MCP/Blender close and SLOT_RESULT fsync. Client/server own samples stay separately bounded; no cross-process/flush-sample strict nesting. Inclusive nested stages are not summed.',
            limitations=['Array payload and retained ReadContext identity metadata do not measure allocation/copy count or transient memory.',
                'Native fingerprint guard traversals are source-derived, actual loop counts unmeasured, elapsed work included.',
                'Historical thin adapter missing EXIT/held exit1 is distinct from CLI Popen and from current actual A/B process exits. New actual states are reported as observed.',
                'No complete-six or eight-start minimum is imposed by the saved audit. Failed actual attempts and not_run suffix are retained. Complete comparable quality and usage are required for a positive consumer-cost decision.'],
            new_operations=dict(Blender_starts=0,product_calls=0,rasters=0,models=0),
            started_ns=started,closed_ns=time.perf_counter_ns(),input_pins=sorted(self.pins.values(),key=lambda row:row['path']))
        prefix='QUALIFICATION_RUNTIME_REVIEW' if qualification_only else 'RUNTIME_REVIEW'
        path=HERE/(prefix+'.json')
        with path.open('x',encoding='utf8',newline='\n') as stream:
            json.dump(result,stream,indent=2,ensure_ascii=False);stream.write('\n')
        if not qualification_only:
            with (HERE/'RAW_COST_CROSSCHECK.json').open('x',encoding='utf8',newline='\n') as stream:
                json.dump(dict(schema='m5-task-raw-cost-crosscheck-v1',passed_checked_scope=passed,
                    qualification_only=False,input_pins=result['input_pins'],cost=cost,
                    author_association=result['author_association']),stream,indent=2,ensure_ascii=False);stream.write('\n')
        print(json.dumps(dict(passed_checked_scope=passed,checks=len(self.checks),failed=result['failed_checks'],
            reviewed_actual_slots=len(self.records),owned_starts=budget['starts'],raster_attempts=budget['attempts'],
            JSON_sha256=hashlib.sha256(path.read_bytes()).hexdigest())))

    def cost(self, formal):
        consumer_rows=[]
        for slot in formal['records']:
            candidate=RUNTIME/'formal'/slot['slot_id']/'consumer/CONSUMER.json'
            if not candidate.exists():
                consumer_rows.append(dict(slot=slot['slot_id'],status=slot['status'],usage=None,complete_slot_ns=None))
                continue
            consumer=read(candidate)
            self.pin(candidate,'original CLI consumer report')
            stdout_path=candidate.parent/'stdout.raw.bin'
            raw=stdout_path.read_bytes()
            self.pin(stdout_path,'original CLI event byte stream')
            usage=[]
            offset=0
            for line in raw.splitlines(keepends=True):
                try:
                    event=json.loads(line)
                except (ValueError,UnicodeError):
                    offset+=len(line)
                    continue
                if event.get('type')=='turn.completed':
                    usage.append(dict(byte_start=offset,byte_end=offset+len(line),line_sha256=hashlib.sha256(line).hexdigest(),raw_event=event))
                offset+=len(line)
            publication=read(candidate.parent.parent/'SLOT_PUBLICATION.json')
            supplied=usage[0]['raw_event']['usage'] if len(usage)==1 else None
            binding=consumer.get('runtime_binding',{})
            row=dict(slot=slot['slot_id'],status=slot['status'],usage=supplied,raw_usage_events=usage,
                raw_usage_matches_consumer=supplied is not None and supplied==consumer.get('usage'),
                complete_slot_ns=publication['complete_slot_ns'],CLI_Popen_exit_code=consumer.get('exit_code'),
                CLI_process_cleanup=consumer.get('process_cleanup'),CLI_safe_to_continue=consumer.get('safe_to_continue'),
                thin_adapter_pid=binding.get('runtime_pid'),thin_adapter_actual_held_exit=consumer.get('runtime_exit'),
                thin_EXIT_receipt_present=bool(binding.get('STARTED_path') and Path(binding['STARTED_path']).with_name('EXIT.json').exists()),
                consumer_errors=consumer.get('errors'),actual_tool_rounds=len(consumer['tool_calls']))
            consumer_rows.append(row)
        comparable=len(consumer_rows)==6 and all(row['usage'] is not None and row.get('raw_usage_matches_consumer') for row in consumer_rows)
        actual={row['slot']:row for row in consumer_rows}
        pairs=[]
        for i in (1,2,3):
            a,b=actual['A'+str(i)],actual['B'+str(i)]
            ratio=None if a['complete_slot_ns'] is None or b['complete_slot_ns'] is None else b['complete_slot_ns']/a['complete_slot_ns']
            pairs.append(dict(pair=i,A_complete_slot_ns=a['complete_slot_ns'],B_complete_slot_ns=b['complete_slot_ns'],B_over_A=ratio))
        ratios=[row['B_over_A'] for row in pairs if row['B_over_A'] is not None]
        totals={group:None for group in ('A','B')}
        uncached=dict(totals)
        if comparable:
            for group in ('A','B'):
                selected=[row['usage'] for row in consumer_rows if row['slot'].startswith(group)]
                totals[group]=sum(row['input_tokens']+row['output_tokens'] for row in selected)
                uncached[group]=sum(row['input_tokens']-row['cached_input_tokens']+row['output_tokens'] for row in selected)
        return dict(records=consumer_rows,raw_usage_same_origin_comparable=comparable,
            paired_complete_slot_ratios=pairs,median_paired_B_over_A=statistics.median(ratios) if len(ratios)==3 else None,
            B_faster_pairs=sum(ratio<1 for ratio in ratios),raw_input_plus_output=totals,
            uncached_input_plus_output=uncached,provider_billing_scope='unconfirmed',provider_billing_amount=None,
            positive_signal_gate_scope='Root independent DECISION combines complete6quality,3Bjointfactadoption, comparable usage,median<=.90,>=2faster and Braw<=A. These saved values do not substitute quality.',
            qualification_time_scope='Qualification clocks excluded from formal paired cost. Preparation/qualification/scoring/archive measured separately.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qualification", action="store_true")
    args = parser.parse_args()
    Review().finish(args.qualification)


if __name__ == "__main__":
    main()
