"""Inspect existing M4 request archives without importing or calling the product."""

import ast
import collections
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path(__file__).resolve().parent
BASELINE = "8f2a739e789b777358d84a168154bc7c50b929e5"
INPUTS = {}
CACHED = {}
ARCHIVE_ROWS = {}
DIRECTORY_NEEDLE = re.compile(rb"[\"']mode[\"']\s*:\s*[\"']directory[\"']")


def read_bytes(path):
    path = Path(path).resolve()
    key = str(path)
    if key not in CACHED:
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        expected = ARCHIVE_ROWS.get(key)
        if expected is not None:
            assert digest == expected["sha256"], key
            assert len(raw) == expected["bytes"], key
        INPUTS[key] = {"path": key, "bytes": len(raw), "sha256": digest}
        CACHED[key] = raw
    return CACHED[key]


def read_json(path):
    return json.loads(read_bytes(path))


def local_archive_path(family, row):
    path = Path(row.get("archive_path", row.get("archive", "")))
    if path.parts[0] != "verification":
        path = family / path
    return (ROOT / path).resolve()


def request_summary(payload):
    params = payload.get("params", {})
    params = params if isinstance(params, dict) else {}
    arguments = params.get("arguments", {})
    arguments = arguments if isinstance(arguments, dict) else {}
    query = arguments.get("query", {})
    query = query if isinstance(query, dict) else {}
    return {
        "id": payload.get("id"),
        "method": payload.get("method", payload.get("type")),
        "tool_name": params.get("name"),
        "mode": query.get("mode"),
    }


def directory_needle(raw):
    return b"capture_directory" in raw or bool(DIRECTORY_NEEDLE.search(raw))


def embedded_host_result(path):
    reply = read_json(path)
    text = reply["result"]["result"]
    prefix = "HUMAN_EYE_BLENDER_MCP:"
    return json.loads(text.split(prefix, 1)[1])["result"]


def function_lines(path, names):
    tree = ast.parse(read_bytes(path).decode("utf8"))
    return {
        node.name: {"first_line": node.lineno, "last_line": node.end_lineno}
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
    }


def main():
    for name in ("M2_DIRECTORY_RESOURCE_REUSE_001_PLAN.md", "M1_M5_PROGRESS_AND_NEXT_PLAN_20261115.md"):
        read_bytes(Path("D:/hefe/docs") / name)

    families = sorted((ROOT / "verification").glob("m4_*"))
    archive_inventory = []
    mapped_requests = []
    for family in families:
        for name in ("EXTERNAL_ARCHIVE.json", "RUNTIME_ARCHIVE.json"):
            path = family / name
            if not path.is_file():
                continue
            document = read_json(path)
            rows = document.get("files", [])
            for row in rows:
                ARCHIVE_ROWS[str(local_archive_path(family, row))] = row
            selected = []
            for row in rows:
                original = row.get("original_path", row.get("source", ""))
                if PureWindowsPath(original).name != "TX.bin":
                    continue
                archived = local_archive_path(family, row)
                raw = read_bytes(archived)
                request = read_json(archived)
                item = dict(request_summary(request), family=family.name,
                            archive_path=str(archived), original_path=original,
                            directory_needle=directory_needle(raw))
                selected.append(item)
                mapped_requests.append(item)
            archive_inventory.append({
                "family": family.name,
                "manifest": str(path),
                "indexed_files": len(rows),
                "root": next((document[k] for k in
                              ("external_root", "original_root", "runtime_root") if k in document), None),
                "indexed_TX_files": len(selected),
                "request_methods": dict(collections.Counter(str(item["method"]) for item in selected)),
                "explicit_modes": dict(collections.Counter(str(item["mode"]) for item in selected)),
            })

    raw_inventory = []
    raw_requests = []
    for family in families:
        paths = sorted(family.rglob("TX.bin"))
        errors = []
        rows = []
        for path in paths:
            raw = read_bytes(path)
            try:
                document = json.loads(raw)
            except (ValueError, UnicodeError) as error:
                errors.append({"path": str(path), "error": type(error).__name__})
                continue
            if not isinstance(document, dict):
                errors.append({"path": str(path), "error": "non_object_request"})
                continue
            item = dict(request_summary(document), family=family.name,
                        path=str(path), directory_needle=directory_needle(raw))
            rows.append(item)
            raw_requests.append(item)
        raw_inventory.append({
            "family": family.name,
            "literal_TX_files": len(paths),
            "decoded_objects": len(rows),
            "decode_failures": errors,
            "explicit_modes": dict(collections.Counter(str(item["mode"]) for item in rows)),
            "directory_candidates": [item for item in rows if item["directory_needle"]],
        })

    # These are the exact owned full/candidate capture batches already archived.
    capture_batches = []
    for name in ("m4_capture_qa_001", "m4_capture_opt_001"):
        family = ROOT / "verification" / name
        manifest = read_json(family / "DELIVERY_MANIFEST.json")
        scripts = []
        for row in manifest["files"]:
            path = family / row["path"]
            if path.name != "SCRIPT.py":
                continue
            raw = read_bytes(path)
            assert hashlib.sha256(raw).hexdigest() == row["sha256"]
            scripts.append({"path": str(path), "directory_call_present": b"capture_directory" in raw})
        read_bytes(family / "REPORT.md")
        cases = sorted({str(Path(row["path"]).relative_to(family).parts[1]) for row in scripts})
        assert len(scripts) == 22 and len(cases) == 11
        assert not any(row["directory_call_present"] for row in scripts)
        capture_batches.append({"family": name, "owned_sessions": len(cases),
                                "capture_scripts": len(scripts), "directory_calls": 0,
                                "case_ids": cases, "scripts": scripts})

    # Four actual live-host observation sessions. Brief delivery and subsequent
    # fixed-capture consumer comparisons are separately present in the census.
    live_families = {
        "m4_active_observation_host_bridge_001",
        "m4_active_observation_patch_ownership_001",
        "m4_active_observation_region_anchors_001",
    }
    live_stdio = [row for row in mapped_requests
                  if row["family"] in live_families and "\\stdio\\" in row["original_path"]]
    live_sessions = collections.defaultdict(list)
    for row in live_stdio:
        live_sessions[str(PureWindowsPath(row["original_path"]).parents[2])].append(row)
    for row in mapped_requests:
        if row["family"] in live_families:
            original = Path(row["original_path"])
            assert original.is_file()
            assert read_bytes(original) == read_bytes(row["archive_path"])

    host_family = ROOT / "verification/m4_active_observation_host_bridge_001"
    run = host_family / "external_archive/run/acceptance_02"
    protocol = read_json(host_family / "HARNESS_PROTOCOL.json")
    read_bytes(host_family / "run_acceptance_r2.py")
    read_bytes(host_family / "qa_worker.py")
    read_bytes(host_family / "REPORT.md")
    read_bytes(host_family / "external_archive/payload_r2/HARNESS_PROTOCOL.json")
    read_bytes(host_family / "external_archive/payload_r2/run_acceptance.py")
    legacy = [row for row in protocol["fixed_requests"] if row["id"] == "old_readonly_regression"]
    assert len(legacy) == 1 and legacy[0]["query"] == {"mode": "directory"}

    trajectory = []
    for rpc in sorted((run / "stdio").glob("rpc_*")):
        request = read_json(rpc / "TX.bin")
        receipt = read_json(rpc / "RECEIPT.json")
        response = read_json(rpc / "RESPONSE.json")
        trajectory.append(dict(request_summary(request), rpc=str(rpc),
                               started_ns=receipt["started_ns"], closed_ns=receipt["closed_ns"],
                               isError=response.get("result", {}).get("isError")))
    assert [row["id"] for row in trajectory][-4:] == [
        "nonplanar_source", "bad_active_query", "ping_after_bad_request", "old_readonly_regression"]
    assert all(a["closed_ns"] <= b["started_ns"] for a, b in zip(trajectory, trajectory[1:]))

    capture = read_json(run / "server/CAPTURE_03.json")
    delta = embedded_host_result(run / "qa/rpc_005/RX.bin")
    directory = embedded_host_result(run / "qa/rpc_006/RX.bin")
    scripts = [read_bytes(run / f"qa/rpc_{number:03d}/SCRIPT.py").decode("utf8") for number in (5, 6)]
    modules = [re.search(r"_sys\.modules\.get\('([^']+)'\)", script).group(1) for script in scripts]
    tags = [re.search(r"_resident_tag', None\) != '([^']+)'", script).group(1) for script in scripts]
    assert len(set(modules)) == len(set(tags)) == 1
    assert all("_host = _module._mcp_resident_host" in script for script in scripts)
    token = capture["capture_state"]
    assert all(token[key] == directory["capture_state"][key] for key in ("instance_id", "epoch", "revision"))
    assert directory["cache_hit"] is False
    assert capture["host_identity"]["document_epoch"] == directory["binding"]["host_identity"]["document_epoch"]
    assert capture["host_identity"]["object_instances"] == directory["binding"]["host_identity"]["object_instances"]
    assert len(capture["meshes"]) == len(directory["objects"]) == len(delta["resources"]) == 1
    mesh = capture["meshes"][0]
    resource = delta["resources"][0]
    pose = delta["capture"]["meshes"][0]["_scene_resource"]
    assert len(mesh["vertices"]) == len(resource["vertices_local"]) == 4
    assert len(mesh["faces"]) == len(resource["faces"]) == 2
    measured = directory["objects"][0]
    assert mesh["object_id"] == measured["object_id"]
    assert measured["bbox_min"] == [min(v[axis] for v in mesh["vertices"]) for axis in range(3)]
    assert measured["bbox_max"] == [max(v[axis] for v in mesh["vertices"]) for axis in range(3)]
    events = [json.loads(line) for line in read_bytes(run / "qa/EVENTS.jsonl").splitlines()]
    assert [row["type"] for row in events[4:6]] == ["execute_code", "execute_code"]
    assert all(row["status"] == "completed" and row["stage_after"] == "nonplanar" for row in events[4:6])
    close = read_json(run / "qa/CLOSE.json")
    ready = read_json(run / "qa/READY.json")
    live_config = read_json(run / "LIVE_CONFIG.json")
    assert ready["port"] == live_config["blender"]["port"] and ready["pid"] == close["pid"]
    final_mesh = close["final_snapshot"]["objects"][0]
    assert final_mesh["matrix_world"] == pose["matrix"]
    assert final_mesh["vertices"] == resource["vertices_local"]
    assert close["final_snapshot"]["scale_length"] == pose["scale"] == directory["binding"]["scale_length"]
    host_source = ROOT / "human_eye_plugin/blender_host.py"
    helper_source = ROOT / "human_eye_plugin/scene_residency.py"
    host_functions = function_lines(host_source, {"capture_scene", "capture_directory", "_resource_stamp",
                                                 "_resident_capture", "_sync_residency"})
    helper_functions = function_lines(helper_source, {"sync", "updated", "token", "reset"})
    assert hashlib.sha256(read_bytes(host_source)).hexdigest() == directory["binding"]["host_source_sha256"]

    # This list is the pre-existing related D:/he_* metadata boundary. No assets,
    # installed products, dependency trees, .blend files, images or arrays opened.
    external_names = [
        "he_anchor_001", "he_brief_001", "he_complete_witness_001", "he_consume_001",
        "he_core_001", "he_explicit_001", "he_host_001", "he_loc_001",
        "he_occluded_transfer_001", "he_patch_001", "he_routed_001",
        "he_source_face_001", "he_view_reuse_001",
    ]
    external_metadata = []
    for name in external_names:
        path = Path("D:/") / name
        external_metadata.append({"root": str(path), "exists": path.is_dir(),
                                  "top_level_names": sorted(p.name for p in path.iterdir()) if path.is_dir() else []})

    result = {
        "schema": "m2-existing-m4-directory-opportunity-review-v1",
        "baseline_commit": BASELINE,
        "reviewer_association": "M1 product author performing this read-only historical M4 investigation",
        "conclusion": "not_actionable_on_qualified_natural_task_evidence",
        "technical_reuse_opportunity_count": 1,
        "qualified_natural_task_hits": 0,
        "natural_task_demand_unknown": True,
        "scope": {
            "verification_families": len(families),
            "literal_TX_files": sum(row["literal_TX_files"] for row in raw_inventory),
            "literal_TX_decode_failure_count": sum(len(row["decode_failures"]) for row in raw_inventory),
            "mapped_TX_files": len(mapped_requests),
            "TX_counts_are_artifact_census_not_independent_task_samples": True,
            "actual_live_observation_sessions": len(live_sessions),
            "actual_live_observation_stdio_requests": len(live_stdio),
            "actual_live_observation_active_requests": sum(row["mode"] == "active_observation" for row in live_stdio),
            "actual_live_observation_successful_active_requests": 13,
            "actual_live_observation_directory_requests": sum(row["mode"] == "directory" for row in live_stdio),
            "older_owned_capture_sessions": sum(row["owned_sessions"] for row in capture_batches),
            "older_owned_capture_scripts": sum(row["capture_scripts"] for row in capture_batches),
            "actual_host_session_denominator_with_directory_observation": 26,
            "capture_replay_and_fixed_packet_consumers_excluded_from_natural_host_hits": True,
            "live_model_consumer_trajectories_with_proven_Blender_residency": 0,
            "historical_logs_are_incomplete_for_global_natural_frequency": True,
        },
        "technical_hit": {
            "family": host_family.name,
            "run": str(run),
            "trajectory": trajectory,
            "predeclared_request": legacy[0],
            "demand_origin": "Predeclared old_readonly_regression compatibility check, after bad-query/ping recovery",
            "origin_evidence": {
                "protocol": str(host_family / "HARNESS_PROTOCOL.json"),
                "controller": str(host_family / "run_acceptance_r2.py"),
                "controller_lines": [222, 225],
                "assertion": "isError false and text-only content; no downstream directory-dependent task recorded",
            },
            "direct": {
                "resident_module": modules[0], "resident_tag": tags[0],
                "host_reference": "_module._mcp_resident_host",
                "historical_product_source_sha256": live_config["expected_identity"]["source_sha256"],
                "current_product_source_aggregate_is_not_this_historical_runtime": True,
                "QA_pid": ready["pid"], "QA_port": ready["port"],
                "capture_token": token, "directory_token": directory["capture_state"],
                "document_epoch": capture["host_identity"]["document_epoch"],
                "object_instances": capture["host_identity"]["object_instances"],
                "resource_id": resource["id"], "resource_revision": resource["revision"],
                "resource_vertices": len(resource["vertices_local"]), "resource_triangles": len(resource["faces"]),
                "pose": pose, "directory_binding": directory["binding"],
                "cache_hit": directory["cache_hit"], "directory_bounds": measured,
                "same_source_forward_bounds_recomputed_equal": True,
                "intervening_private_scene_controls": 0,
                "readonly_QA_guard_completed_both_calls": True,
                "close_snapshot_matches_resource_pose_and_geometry": True,
            },
            "source_inferences": {
                "stamp_unchanged": "Same instance/epoch/revision after sync, same source and no intervening scene control support unchanged dirty/signature state. Per-object _resource_stamp tuple was not serialized.",
                "resident_world_mesh_available": "capture_scene calls _capture(_resident=True), _resident_capture stores transformed mesh and pose; delta publishes this same resource29. No evidence of host reset or resource eviction before directory.",
                "directory_work_on_miss": {"to_mesh_calls": 1, "vertices_forward_mapped": 4,
                                            "basis": "Source-implied successful miss path for the one 4-vertex object"},
                "triangle_budget": {"value": 2, "basis": "Original triangular fixture two polygons, six loops, max(0,6-2*2)"},
                "host_function_lines": host_functions,
                "residency_function_lines": helper_functions,
            },
            "not_exposed": ["literal resource stamp before/after", "resource mesh identity at directory entry",
                            "residency_work counter snapshots", "independent native operation profiler",
                            "per-stage directory cost", "complete natural task cost or demand frequency"],
            "technical_qualification": "one historical real-host resource-before-first-directory-miss opportunity",
            "natural_task_qualification": "not established because recorded demand is the frozen compatibility regression",
        },
        "raw_request_inventory": raw_inventory,
        "mapped_archive_inventory": archive_inventory,
        "mapped_requests": mapped_requests,
        "live_observation_sessions": dict(live_sessions),
        "older_capture_batches": capture_batches,
        "related_external_root_metadata": external_metadata,
        "execution": {"new_Blender_processes": 0, "new_product_observations": 0, "new_model_calls": 0,
                      "new_rasters": 0, "new_evaluator_calls": 0, "product_imports": 0,
                      "product_or_installation_edits": 0, "new_asset_search": False},
        "input_files": sorted(INPUTS.values(), key=lambda row: row["path"]),
    }
    assert len(live_sessions) == 4 and len(live_stdio) == 24
    assert result["scope"]["actual_live_observation_active_requests"] == 14
    assert result["scope"]["actual_live_observation_directory_requests"] == 1
    assert len(capture_batches) == 2
    report = f"""# M4 既有宿主轨迹复核

本次只读核查基线为 `{BASELINE}`。结论为 `not_actionable_on_qualified_natural_task_evidence`。保留 1 条真实技术复用机会，符合本批自然任务要求的命中为 0。目录在自然任务中的需求频率仍为 unknown。

## 分母与核查边界

核查现有 {len(families)} 个 M4 命名空间中的原始 TX，以及 {len(archive_inventory)} 份既有外部归档索引。按实际宿主会话计算，主动观察为 4 条 owned 会话，合计 24 条 stdio RPC，包含 13 次成功主动观察、1 次错误查询和1次目录。另两批旧采集各11条 owned 会话，共44份真实采集脚本，均未调用目录。合计26条有明确实际宿主记录的有限工程会话。这些会话的资产重复，不能当成26种独立资产覆盖。

原始文件计数为 {result['scope']['literal_TX_files']} 份 literal TX 和 {len(mapped_requests)} 份索引映射 TX，二者存在副本重叠。文件数、协议层副本和初始化请求均未加入自然任务分母。非对象或无法JSON解码的 {result['scope']['literal_TX_decode_failure_count']} 份原件逐项保留。CAPTURE_REPLAY及固定packet消费不提供真实Blender驻留证据。现有归档不覆盖全部历史自然使用。

## 保留的技术命中

`m4_active_observation_host_bridge_001` 的 acceptance_02 依次为 baseline观察、重命名观察、nonplanar_source观察、bad_active_query、ping、old_readonly_regression目录。最后一次成功观察与目录之间没有私有场景控制。QA脚本005与006取同一个 resident module、tag 和 `_mcp_resident_host`，QA PID为 {ready['pid']}。

资源为 `{resource['id']}`，版本 {resource['revision']}，对象实例277，4个顶点、2个三角形。捕获与目录的 instance、epoch、revision分别为 `{token['instance_id']}`、{token['epoch']}、{token['revision']}，目录明确 `cache_hit=false`。局部坐标、单位尺度与单位矩阵直接记录，目录边界逐轴与前一实际世界捕获一致，退出快照也保持相同几何和矩阵。nonplanar ROI的unknown状态仍保留，该状态不使完整网格捕获失效。

历史运行的产品整体SHA为 `{live_config['expected_identity']['source_sha256']}`。宿主单文件SHA为 `{directory['binding']['host_source_sha256']}`，与当前基线同名单文件一致。这是历史真实入口证据，当前3748整体版本的新实测次数为0。资源29指该mesh的revision编号，驻留资源总数未测。源码证明 capture_scene 进入驻留路径，存储 world mesh、pose和资源。相同同步revision、未改变场景及成功只读守卫支持资源未失效的推断。实际 `_resource_stamp` 元组和目录入口的内部mesh引用没有直接侧录，因此JSON中将这两项与直接证据分开。不得声称测得新方案时延。

目录miss成功代码路径对这一个对象执行1次to_mesh和4次顶点世界变换。该数量来自确定代码路径与实际对象规模，原件未保存前后residency_work计数或独立native profiler。原三角预算为6 loops减2×2 polygons，等于2。没有把三角数量替代一般多边形预算规则。

## 请求目的与自然任务资格

原 `HARNESS_PROTOCOL.json` 的 fixed_requests 已登记 `old_readonly_regression`。实际 `run_acceptance_r2.py` 第222至225行以同名请求调用目录，仅校验成功和纯文本交付。该请求紧随错误查询与ping，原报告也将其称作旧directory只读入口回归。日志未记录后续依赖目录完成的业务任务。由此保留技术重复工作事实，同时本批“自然任务中首次需要目录”的资格仍为0。未以“工程测试”这一名称否定真实宿主调用，也未将兼容回归推成自然任务收益。

## 执行与限制

只读取既有相关归档及固定的13个 D:/he_* 根目录元数据，相关live TX与其D盘原件逐字节核对。未打开blend、图像或数组，新增Blender、产品观察、模型、raster、evaluator和产品import均为0。源码、安装和旧记录保持原字节。复核人参与过M1产品实现，此关联在JSON中登记。

完整请求顺序、原始输入SHA、直接字段、推断和未暴露项见同目录 M4_TRACE_REVIEW.json。当前结果可支持按计划结束本批资格核查。自然任务机会及端到端收益仍须由后续实际轨迹提供。
"""
    json_path = OUTPUT / "M4_TRACE_REVIEW.json"
    md_path = OUTPUT / "M4_TRACE_REVIEW.md"
    with json_path.open("x", encoding="utf8", newline="\n") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    with md_path.open("x", encoding="utf8", newline="\n") as handle:
        handle.write(report)
    print(json.dumps({"technical_reuse_opportunity_count": 1, "qualified_natural_task_hits": 0,
                      "live_sessions": len(live_sessions), "owned_capture_sessions": 22,
                      "input_file_count": len(INPUTS),
                      "outputs": [{"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                                  for path in (Path(__file__), json_path, md_path)]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
