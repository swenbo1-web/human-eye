"""Review saved six-cell evidence. This script never imports or runs the product."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path


OUTPUT = Path(__file__).resolve().parent
BATCH = OUTPUT.parents[1]
SOURCES: dict[str, dict] = {}


def source(path: Path) -> dict:
    resolved = path.resolve()
    raw = resolved.read_bytes()
    item = {
        "path": resolved.as_posix(),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    SOURCES[item["path"]] = item
    return item


def read_json(path: Path):
    source(path)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_jsonl(path: Path) -> list[dict]:
    source(path)
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line]


def compact(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


ANNOTATIONS = {('grc01', 1): {'category': 'directory_or_identity',
                'role': '核对象类型、位置、点数、modifier 与单位。',
                'before': '尚无任务几何或表面距离。',
                'after': '取得对象身份信息，尚无表面距离。',
                'mesh_evaluations': 0},
 ('grc04', 1): {'category': 'directory_or_identity',
                'role': '遍历当前场景的对象名与类型。',
                'before': '尚无任务几何或表面距离。',
                'after': '取得对象身份信息，尚无表面距离。',
                'mesh_evaluations': 0},
 ('grc05', 1): {'category': 'directory_or_identity',
                'role': '核四对象完整世界矩阵、modifier、单位和名称。',
                'before': '尚无任务几何或表面距离。',
                'after': '取得对象身份信息，尚无表面距离。',
                'mesh_evaluations': 0},
 ('grc01', 2): {'category': 'new_information',
                'role': '求值四份网格，以 float64 世界矩阵运算缓存几何，并输出全部26世界顶点、36三角和54边。',
                'before': '只有对象身份和单位。',
                'after': '完整几何已供本格后续求解，任务距离尚未求出。',
                'mesh_evaluations': 4},
 ('grc01', 3): {'category': 'new_information',
                'role': '复用 geom，首次计算三对点面/边边距离、边面相交及双方全部顶点 winding。',
                'before': '已有完整几何，尚无任务距离或包含结论。',
                'after': '首次交付三对距离、见证及相交和包含检查。',
                'mesh_evaluations': 0},
 ('grc04', 2): {'category': 'new_information',
                'role': '用 mathutils 矩阵乘积读取世界点，再存入 float64 数组；输出计数、界与单位。',
                'before': '只有对象目录。',
                'after': '建立第一份几何缓存，尚未计算任务距离。',
                'mesh_evaluations': 4},
 ('grc04', 3): {'category': 'new_information',
                'role': '重读局部点和世界矩阵，改用 float64 乘积，首次求三对距离并检查相交、全顶点 winding 和边面流形。',
                'before': '有 mathutils 世界点缓存，距离尚未求出。',
                'after': '首次交付完整距离和包含事实。',
                'mesh_evaluations': 4,
                'repeat_geometry_refresh': {'meshes': 4,
                                            'vertices': 26,
                                            'triangles': 36,
                                            'reason_in_saved_code': 'Re-read stored local vertices and world '
                                                                    'matrix, then multiply in NumPy float64 '
                                                                    'before first distance computation.',
                                            'refresh_only_duration_ns': None}},
 ('grc05', 2): {'category': 'new_information',
                'role': '求值四份网格并做 float64 世界变换，缓存点面，同时检查全部边的面关联计数。',
                'before': '只有对象身份、矩阵和单位。',
                'after': '取得几何、边关联与范围，尚无距离。',
                'mesh_evaluations': 4},
 ('grc05', 3): {'category': 'new_information',
                'role': '复用 geo，首次计算点面/边边距离、相交及双向全顶点 winding。',
                'before': '完整几何已知，尚无任务距离。',
                'after': '三对任务事实首次完整交付。',
                'mesh_evaluations': 0},
 ('grc02', 1): {'category': 'new_information',
                'role': '请求 spatial_relation、surface_proximity 和额外 closed_solid_relation，获取三对完整事实。',
                'before': '尚无本格有效任务事实。',
                'after': 'A走有界精确闭壳分支，B/C走充分支撑分离；三对关系、距离和见证完整。',
                'mesh_evaluations': 4},
 ('grc03', 2): {'category': 'new_information',
                'role': '请求 spatial_relation、surface_proximity 和额外 closed_solid_relation，获取三对完整事实。 同时获取四份额外 '
                        'aabb。',
                'before': '尚无本格有效任务事实。',
                'after': 'A走有界精确闭壳分支，B/C走充分支撑分离；三对关系、距离和见证完整。',
                'mesh_evaluations': 4},
 ('grc06', 1): {'category': 'new_information',
                'role': '请求 spatial_relation、surface_proximity 和额外 closed_solid_relation，获取三对完整事实。',
                'before': '尚无本格有效任务事实。',
                'after': 'A走有界精确闭壳分支，B/C走充分支撑分离；三对关系、距离和见证完整。',
                'mesh_evaluations': 4},
 ('grc03', 1): {'category': 'new_information',
                'role': '首次请求把 nearest_witness 作为独立事实名，合同验证拒绝。',
                'before': '尚无本格有效任务事实。',
                'after': '取得不执行错误，tool_outcome保留unknown，几何事实尚未提供。',
                'mesh_evaluations': 0,
                'outcome': 'invalid_request'}}


def review_cell(cell_name: str) -> dict:
    cell_dir = BATCH / "cells" / cell_name
    owner = cell_dir / "owner"
    consumer = read_json(cell_dir / "CONSUMER.json")
    worker_file = owner / "native" / "WORKER_EVENTS.jsonl"
    worker_events = read_jsonl(worker_file)
    audit_file = owner / "audit.jsonl"
    audit = read_jsonl(audit_file) if audit_file.exists() else []
    rpc_file = owner / "plugin" / "RPC.json"
    rpc = read_json(rpc_file) if rpc_file.exists() else None
    final_file = cell_dir / "PUBLIC_FINAL.txt"
    final_source = source(final_file)
    final_text = final_file.read_text(encoding="utf-8-sig")
    source(owner / "INITIAL.json")
    source(owner / "FINAL.json")
    source(owner / "TOOLS.json")
    steps = []
    last_end = consumer["started_ns"]
    assigned_sequences = set()
    for tool_dir in sorted(owner.glob("tool_*")):
        attempt_file = tool_dir / "ATTEMPT.json"
        request_file = tool_dir / "REQUEST.json"
        response_file = tool_dir / "RESPONSE.json"
        attempt = read_json(attempt_file)
        request = read_json(request_file)
        response = read_json(response_file)
        image = read_json(tool_dir / "IMAGE_CONSTRUCTION.json")
        step = dict(ANNOTATIONS[(cell_name, attempt["attempt"])])
        args = request["params"]["arguments"]
        start = attempt["started_ns"]
        end = start + attempt["elapsed_ns"]
        step.update({
            "attempt": attempt["attempt"],
            "tool": attempt["name"],
            "arguments": args,
            "request_source": source(request_file),
            "response_source": source(response_file),
            "attempt_source": source(attempt_file),
            "actor_clock": "perf_counter_ns",
            "actor_started_ns": start,
            "actor_ended_ns": end,
            "actor_elapsed_ns": attempt["elapsed_ns"],
            "offset_from_consumer_started_ns": start - consumer["started_ns"],
            "preceding_unassigned_wall_gap_ns": start - last_end,
            "actor_accounted_response_envelope_bytes": attempt["response_bytes"],
            "produced_response_envelope_bytes": attempt["produced_response_bytes"],
            "arguments_compact_json_utf8_bytes": len(compact(args)),
            "image_construction": image,
            "is_error": attempt["is_error"],
            "exception": attempt["exception"],
            "native_recompute_of_already_complete_task_facts": False,
        })
        last_end = end
        host_events = [
            event for event in worker_events
            if "script_sha256" in event and start <= event["started_ns"] <= end
        ]
        assert len(host_events) == (0 if step.get("outcome") == "invalid_request" else 1)
        step["host_business_executions"] = []
        for event in host_events:
            seq = event["sequence"]
            assigned_sequences.add(seq)
            call_dir = owner / "native" / f"call_{seq}"
            script_source = source(call_dir / "SCRIPT.py")
            logical_script_sha = hashlib.sha256((call_dir / "SCRIPT.py").read_text(encoding="utf-8").encode("utf-8")).hexdigest()
            assert logical_script_sha == event["script_sha256"]
            step["host_business_executions"].append({
                "event": event,
                "event_source": source(worker_file),
                "script_source": script_source,
                "script_logical_text_sha256": logical_script_sha,
                "script_hash_semantics": "Worker hashes logical UTF-8 script text. SCRIPT.py is written with Windows newline translation. Raw file hash is retained separately.",
                "stdout_source": source(call_dir / "stdout.txt"),
                "stderr_source": source(call_dir / "stderr.txt"),
            })
        if attempt["name"] == "execute_blender_code":
            step["code_utf8_bytes"] = len(args["code"].encode("utf-8"))
            receipt_file = tool_dir / "NATIVE_RECEIPT.json"
            receipt = read_json(receipt_file)
            step["native_receipt_source"] = source(receipt_file)
            step["native_receipt_elapsed_ns"] = receipt["elapsed_ns"]
            step["native_stdout"] = receipt["response"]["result"]["result"]
        else:
            text = response["result"]["content"][0]["text"]
            body = json.loads(text)
            step["product_business_result"] = body
            step["product_body_text_utf8_bytes"] = len(text.encode("utf-8"))
            matches = [r for r in rpc["requests"] if r["method"] == "tools/call" and r["request_id"] == request["id"]]
            assert len(matches) == 1
            step["product_rpc"] = matches[0]
            step["product_rpc_source"] = source(rpc_file)
            trace_matches = [
                item["trace"] for item in audit
                if item.get("event") == "request_trace"
                and item["trace"].get("annotations", {}).get("mcp_request_id") == request["id"]
            ]
            assert len(trace_matches) == 1
            step["product_trace"] = trace_matches[0]
            step["product_trace_source"] = source(audit_file)
            if not attempt["is_error"]:
                observed = [r for r in audit if r.get("event") == "observe" and r.get("trace_id") == body["trace_id"]]
                assert len(observed) == 1
                step["product_task_work"] = observed[0]["task_work"]
                step["product_task_work_source"] = source(audit_file)
                assert len(body["pairs"]) == 3
                for pair in body["pairs"]:
                    facts = pair["facts"]
                    assert facts["spatial_relation"]["status"] == "measured"
                    assert facts["spatial_relation"]["value"] == "separated"
                    assert facts["surface_proximity"]["status"] == "measured"
                    assert facts["closed_solid_relation"]["status"] == "measured"
                    assert facts["closed_solid_relation"]["value"] == "separated"
                assert body["summary"]["nearest_separated_complete"] is True
                assert body["summary"]["unresolved_relations"] == []
                assert body["summary"]["unresolved_distances"] == {}
                assert compact(body).decode("utf-8") == text
        steps.append(step)
    public_calls = consumer['tool_calls']
    assert len(public_calls) == len(steps)
    for public_call, step in zip(public_calls, steps, strict=True):
        assert public_call['item']['tool'] == step['tool']
        assert public_call['item']['arguments'] == step['arguments']
    qa_events = [e for e in worker_events if "script_sha256" in e and e["sequence"] not in assigned_sequences]
    assert len(qa_events) == 2
    assert qa_events[0]["script_sha256"] == qa_events[1]["script_sha256"]
    for event in qa_events:
        call_dir = owner / "native" / f"call_{event['sequence']}"
        for name in ("SCRIPT.py", "stdout.txt", "stderr.txt"):
            source(call_dir / name)
    p_success = [s for s in steps if s["tool"] == "human_eye_scene_observe" and not s["is_error"]]
    requested_required = any(
        {"spatial_relation", "surface_proximity"} <= set(s["arguments"]["query"]["requested_facts"])
        for s in p_success
    )
    return {
        "cell": cell_name,
        "group": consumer["group"],
        "round": consumer["round"],
        "task": consumer["task"],
        "consumer_source": source(cell_dir / "CONSUMER.json"),
        "consumer_started_ns": consumer["started_ns"],
        "final_received_ns": consumer["final_received_ns"],
        "unassigned_last_tool_to_final_ns": consumer["final_received_ns"] - last_end,
        "quality": "complete_correct_from_administrator_seal_no_rescoring",
        "steps": steps,
        "qa_snapshot_executions_excluded_from_consumer_tool_count": qa_events,
        "final": {"source": final_source, "text": final_text},
        "mechanism": {
            "naturally_requested_both_required_facts": requested_required if consumer["group"] == "P" else None,
            "used_correctly": True if consumer["group"] == "P" else None,
            "correct_use_basis": "Complete raw final manually compared with successful body, administrator quality seal confirms all 13 required facts. No new scorer was run.",
            "native_tool_calls": sum(s["tool"] == "execute_blender_code" for s in steps),
            "native_recompute_after_complete_answer_count": 0,
        },
    }



def write_report(result):
    lines = [
        '# 凹槽迁移六格的实际消费机制', '',
        '本次使用固定六格原件。质量引用已封存的6/6完整正确、78/78事实正确结果。机制审读覆盖全部请求代码、响应及最终答案，模型消费者、Blender、产品和业务API新增运行计数为0。', '',
        '## 实际机制', '',
        'P三格均自然请求spatial_relation和surface_proximity，直接使用完整事实形成正确答案。P原生工具调用、必要原生补完和已完成事实后的原生重算均为0，冻结机制条件达到3/3。三对关系均measured，正确答案在本题上由引擎事实独立支持。最终文字同时与spatial及closed返回值一致，现有记录无法区分模型读取了哪个同值关系字段。', '',
        '## 完整调用轨迹', '',
        '| 格/步 | 组 | 主分类 | handler毫秒 | 响应包络字节 | 作用 |',
        '|---|---|---|---:|---:|---|',
    ]
    for cell in result['cells']:
        for step in cell['steps']:
            lines.append(f"| {cell['cell']}/{step['attempt']} | {cell['group']} | {step['category']} | {step['actor_elapsed_ns']/1e6:.4f} | {step['actor_accounted_response_envelope_bytes']} | {step['role']} [请求]({step['request_source']['path']}) [响应]({step['response_source']['path']}) |")
    lines += [
        '',
        '全部13步的请求参数、源代码、原始业务响应、stdout、host执行、产品trace和最终答案均在RESULTS.json中，源文件SHA见SOURCES.json。目录3步、新增信息10步，单独未知补证0步、已有完整事实后重算0步。每格前后QA共12次单列，业务host execute共12次，其中N原生9次、P内部采集3次。', '',
        '## A闭壳与B/C充分分离', '',
        'A的候选支撑方向未严格分离，support_work.reason为spatial_support_not_strictly_separated。空间关系实际调用bounded_exact_closed_shell_v1，返回disjoint_boundaries_with_exact_parity。B/C的空间关系采用exact_sufficient_spatial_relation_v1及strict_all_referenced_vertex_support。', '',
        '| 每次成功P请求 | 空间关系分支 | closed work_units | pair/self/cross tests | 射线/查询 | 显式closed的作用 |',
        '|---|---|---:|---|---|---|',
    ]
    for item in result['closed_branch_analysis']['per_successful_request_pairs'][:3]:
        work = item['closed_solid_work']
        lines.append(f"| {item['candidate_name']} | {item['spatial_method']} | {work['work_units']} | {work['pair_tests']}/{work['self_pair_tests']}/{work['cross_pair_tests']} | {work['ray_tests']}/{work['point_queries']} | {item['explicit_closed_role']} |")
    closed = result['closed_branch_analysis']
    lines += [
        '',
        f"三次成功请求共记录closed工作{closed['all_closed_work_units']} units。其中A必要空间关系回退为{closed['required_A_fallback_work_units']} units，显式closed直接采用同一bundle.closed，第二次A闭壳调用为0。B/C因额外closed字段进入独立分类，共{closed['optional_BC_closed_work_units']} units。", '',
        '源码task_query._closed_surface_facts先取空间关系bundle，仅当bundle.closed为空才调用额外closed测量。A已有闭壳结果，B/C充分分离后仍因显式请求closed而追加分类。三对每请求的closed_solid_pair_count均为1。', '',
        '记录的pair/result缓存命中均为false或0。A的同请求结果直接复用与缓存命中分别描述。三对均prepared_pair_reused=true、prepared_trees_reused=false，每对闭壳工作新建2棵world tree。A的cross_pair_tests=0表示候选已被精确预检查排除，分类器仍执行树遍历、自体嵌入检查和双向奇偶检查。', '',
        'trace只保存observation.task_facts包含式时段，没有独立closed时段。全部task_facts耗时与独立闭壳耗时分别列账，删除额外字段后的完整耗时和token变化为未测。', '',
        '## 拒绝请求与精度刷新', '',
    ]
    invalid = result['invalid_nearest_witness_request']
    lines += [
        f"grc03/1请求nearest_witness独立事实名，原响应tool_outcome=unknown、executed=false、execution_status=not_executed、host_mutation_started=false。该步host执行0，actor窗口{invalid['actor_elapsed_ns']/1e6:.4f}毫秒，响应{invalid['actor_response_envelope_bytes']}字节，产品stdio发送/接收{invalid['rpc_sent_bytes']}/{invalid['rpc_received_bytes']}字节，产品RPC窗口{invalid['rpc_elapsed_ns']/1e6:.4f}毫秒。", '',
        f"至修正请求开始的空档为{invalid['unassigned_gap_to_correction_ns']/1e9:.7f}秒，归因保持未测。grc03/2删去nearest_witness后成功，其余requested_facts包括aabb。四份AABB值组件的紧凑JSON为{result['simplification']['extra_aabb']['value_component_bytes']}字节，字段投影差{result['simplification']['extra_aabb']['compact_body_projection_difference_bytes']}字节。该投影仅量化已保存数据的组成。", '',
        'grc04/2先经mathutils得到世界点再装入float64，grc04/3重新读取局部点和世界矩阵并在NumPy float64计算。重读4份几何、26点、36面，发生在首次距离求解之前。步骤3同时首次给出距离、见证、相交、包含及边流形数据，因此归类为新增信息。初始mathutils缓存的距离答案没有保存，刷新对冻结精度的必要性、独立刷新耗时及删去旧读取后的整题变化均未测。', '',
        'N三格最终求解均同时给出边界相交及双向全顶点winding数据。当前质量已由封存评分确认，其算法在本题之外的适用范围未测。', '',
        '## 有据简化与归因边界', '',
        '| 项目 | 可定位的既有记录 | 时延/因果边界 |',
        '|---|---|---|',
        f"| 额外B/C closed | 6次分类，{closed['optional_BC_closed_work_units']} work_units，{closed['optional_BC_world_tree_builds']}次world tree构建 | 独立closed耗时及完整任务节省未测 |",
        f"| 显式closed输出值 | 9个已测值组件，共{closed['closed_fact_value_component_bytes']}紧凑JSON字节，其中A字段共{closed['A_closed_fact_value_component_bytes']}字节复用既有结果 | 组件大小与实际删字段后wire分别解释 |",
        f"| 无效事实名请求 | 1次，{invalid['actor_response_envelope_bytes']}字节，host执行0 | 自纠空档及整题后果未归因 |",
        '| 数值精度刷新 | 4网格、26点、36面的一次重读 | 首次求值前，独立刷新成本未拆分 |',
        '',
        '仅请求spatial_relation和surface_proximity时，源码仍会为A运行必要闭壳回退，B/C的显式closed分支可跳过。上述15,276 units是已发生的可定位分支工量，真实请求删减后的完整时延、token和费用仍为未测。此项分析使用现有控制流及审计，消融运行计数为0。', '',
        '唯一后续方向沿管理员主线转向无预给对象的全场候选发现、按需精查和覆盖停止。当前结果限定该小规模凹槽装配，后续广泛发现能力与成本需由该主线证据判定。', '',
        '## 计量与可重放性', '',
        'handler是包含式actor窗口。内部RPC、host采集与task_facts属于嵌套区间，各层保持原计量。空档保持未归因。响应预算使用compact UTF-8 JSON RPC包络加LF，SOURCES保存原始文件字节SHA；private product stdio帧按RPC.json另列。', '',
        f"[完整结果]({(OUTPUT/'RESULTS.json').as_posix()}) [输入SHA]({(OUTPUT/'SOURCES.json').as_posix()}) [分析脚本]({(OUTPUT/'analyze_trajectories.py').as_posix()})", '',
    ]
    (OUTPUT / 'REPORT.md').write_text('\n'.join(lines), encoding='utf8', newline='\n')


def main():
    plan = read_json(BATCH / 'PLAN.json')
    work_order = read_json(OUTPUT.parent / 'WORK_ORDER.json')
    frozen = read_json(BATCH / 'MECHANISM_CLASSIFICATION.json')
    seal_path = OUTPUT.parent / 'quality_source/QUALITY_SEAL.json'
    seal = read_json(seal_path)
    assert source(seal_path)['sha256'] == 'a493bd997b2003c595795ad90ae3bc9420e9a2a884a0adcf6225493f880f0c21'
    assert seal['formal_commit'] == work_order['author_commit'] == '4a90bbe95ef46c6666050ef1a1096fc6719c3b97'
    assert seal['quality']['complete_correct'] == 6 and seal['quality']['facts_correct'] == 78
    assert work_order['new_consumer_allowance'] == work_order['new_Blender_or_product_run_allowance'] == 0
    source(OUTPUT.parent / 'quality_source/QUALITY_REVIEW.md')
    source(BATCH / 'runtime/actor.py')
    source(BATCH.parent / 'native_plugin_complex_003/actor.py')
    source(BATCH / 'runtime/consumer_transport.py')
    source(BATCH / 'scoring/SCORING_CONTRACT.json')
    source(BATCH / 'scoring/TRUTH.json')
    snapshot = read_json(BATCH / 'scoring/ACTUAL_SNAPSHOT.json')
    binding = read_json(BATCH / 'preflight/SOURCE_BINDING.json')
    root = BATCH.parents[1]
    branch_sources = []
    for name in ('human_eye_plugin/task_query.py', 'human_eye_plugin/surface_proximity.py', 'human_eye_plugin/surface_geometry.py'):
        expected = next(row['sha256'] for row in binding['source_manifest'] if row['path'] == name)
        item = source(root / name)
        assert item['sha256'] == expected
        branch_sources.append(item)
    mapping = read_json(BATCH / 'private/ANON_MAP.json')
    quality_by_id = {row['answer_id']: row for row in seal['anonymous_answers']}
    cells = [review_cell(f'grc{i:02}') for i in range(1, 7)]
    for cell, mapped in zip(cells, mapping['rows'], strict=True):
        assert cell['cell'] == mapped['cell'] and cell['group'] == mapped['group']
        assert cell['final']['source']['sha256'] == quality_by_id[mapped['anonymous_id']]['answer_sha256']
        cell['anonymous_id'] = mapped['anonymous_id']
    steps = [step for cell in cells for step in cell['steps']]
    successes = [step for step in steps if 'product_task_work' in step]
    closed_rows = []
    for cell in cells:
        for step in cell['steps']:
            if 'product_task_work' not in step:
                continue
            for pair, work_pair in zip(step['product_business_result']['pairs'], step['product_task_work']['pairs'], strict=True):
                index = pair['candidate_index']
                facts = pair['facts']
                expected_method = 'bounded_exact_closed_shell_v1' if index == 0 else 'exact_sufficient_spatial_relation_v1'
                assert facts['spatial_relation']['method'] == expected_method
                assert work_pair['closed_solid_pair_count'] == 1
                assert work_pair['closed_solid_pair_cache_hit'] is False
                if index == 0:
                    assert work_pair['support_work']['reason'] == 'spatial_support_not_strictly_separated'
                else:
                    assert work_pair['support_work']['reason'] is None
                    assert facts['spatial_relation']['certificate'] == 'strict_all_referenced_vertex_support'
                closed_rows.append({
                    'cell': cell['cell'], 'attempt': step['attempt'], 'candidate_index': index,
                    'candidate_name': ('Part_A', 'Part_B', 'Part_C')[index],
                    'spatial_method': expected_method, 'spatial_fact': facts['spatial_relation'],
                    'closed_fact': facts['closed_solid_relation'],
                    'closed_fact_compact_json_bytes': len(compact(facts['closed_solid_relation'])),
                    'surface_work': work_pair['surface_work'], 'support_work': work_pair['support_work'],
                    'closed_solid_work': work_pair['closed_solid_work'],
                    'explicit_closed_role': 'reuse_required_spatial_fallback_bundle' if index == 0 else 'additional_explicit_closed_classification',
                    'explicit_closed_additional_classifier_calls': 0 if index == 0 else 1,
                    'closed_only_duration_ns': None,
                })
    assert len(steps) == 13 and len(successes) == 3 and len(closed_rows) == 9
    categories = Counter(step['category'] for step in steps)
    routes = {}
    for group in ('N', 'P'):
        selected = [step for cell in cells if cell['group'] == group for step in cell['steps']]
        routes[group] = {'consumer_tool_attempts': len(selected),
            'native_calls': sum(step['tool'] == 'execute_blender_code' for step in selected),
            'product_calls': sum(step['tool'] == 'human_eye_scene_observe' for step in selected),
            'actor_handler_elapsed_ns_sum': sum(step['actor_elapsed_ns'] for step in selected),
            'actor_response_envelope_bytes_sum': sum(step['actor_accounted_response_envelope_bytes'] for step in selected)}
    assert routes['N']['native_calls'] == 9 and routes['P']['native_calls'] == 0
    invalid = cells[2]['steps'][0]
    bad_body = invalid['product_business_result']
    assert bad_body['tool_outcome'] == 'unknown' and bad_body['executed'] is False
    assert bad_body['execution_status'] == 'not_executed' and not invalid['host_business_executions']
    correction = cells[2]['steps'][1]
    assert correction['arguments']['query']['requested_facts'] == ['aabb', 'spatial_relation', 'surface_proximity', 'closed_solid_relation']
    aabb_body = correction['product_business_result']
    aabb_values = aabb_body['facts']['aabb']
    without_aabb = dict(aabb_body, facts={})
    a_rows = [row for row in closed_rows if row['candidate_index'] == 0]
    bc_rows = [row for row in closed_rows if row['candidate_index'] != 0]
    p_cells = [cell for cell in cells if cell['group'] == 'P']
    assert all(cell['mechanism']['naturally_requested_both_required_facts'] for cell in p_cells)
    result = {
        'schema': 'm4-grooved-saved-consumption-mechanism-v1',
        'scope': 'Fixed original six cells, saved-data semantic review. New consumer, Blender, product and API runs are zero.',
        'fixed_identity': {'evidence_commit': work_order['author_commit'], 'quality_commit': work_order['quality_review_commit'],
            'product_commit': plan['fixed_product_commit'], 'source_sha256': plan['candidate_source_sha256'],
            'plan_sha256': source(BATCH / 'PLAN.json')['sha256']},
        'quality_seal': {'source': source(seal_path), 'quality': seal['quality']},
        'frozen_classification': frozen, 'branch_control_flow_sources': branch_sources,
        'cells': cells, 'classification_counts_primary': {name: categories[name] for name in frozen['categories']},
        'route_tool_totals': routes,
        'mechanism_verdict': {'passed': True, 'eligible_P_consumers': 3, 'qualified_P_consumers': 3,
            'required_minimum': 2, 'P_native_calls': 0, 'P_necessary_native_completion_cells': 0,
            'P_engine_independent_complete_fact_responses': 3, 'P_native_recomputations_of_complete_facts': 0,
            'same_value_field_attribution': 'Final relations match both spatial and closed facts. The exact same-value field read by the model is unobserved.'},
        'invalid_nearest_witness_request': {'cell': 'grc03', 'attempt': 1,
            'actor_elapsed_ns': invalid['actor_elapsed_ns'], 'actor_response_envelope_bytes': invalid['actor_accounted_response_envelope_bytes'],
            'rpc_sent_bytes': invalid['product_rpc']['sent_bytes'], 'rpc_received_bytes': invalid['product_rpc']['received_bytes'],
            'rpc_elapsed_ns': invalid['product_rpc']['elapsed_ns'], 'host_executions': len(invalid['host_business_executions']),
            'original_outcome': bad_body, 'unassigned_gap_to_correction_ns': correction['preceding_unassigned_wall_gap_ns'],
            'counterfactual_whole_task_saving': None},
        'closed_branch_analysis': {'per_successful_request_pairs': closed_rows,
            'all_closed_work_units': sum(row['closed_solid_work']['work_units'] for row in closed_rows),
            'required_A_fallback_work_units': sum(row['closed_solid_work']['work_units'] for row in a_rows),
            'A_explicit_closed_additional_classifier_calls': sum(row['explicit_closed_additional_classifier_calls'] for row in a_rows),
            'optional_BC_closed_work_units': sum(row['closed_solid_work']['work_units'] for row in bc_rows),
            'optional_BC_classifier_calls': len(bc_rows),
            'optional_BC_world_tree_builds': sum(row['closed_solid_work']['world_tree_builds'] for row in bc_rows),
            'closed_fact_value_component_bytes': sum(row['closed_fact_compact_json_bytes'] for row in closed_rows),
            'A_closed_fact_value_component_bytes': sum(row['closed_fact_compact_json_bytes'] for row in a_rows),
            'optional_BC_closed_fact_value_component_bytes': sum(row['closed_fact_compact_json_bytes'] for row in bc_rows),
            'required_fact_unknown_count': 0,
            'observed_task_facts_inclusive_spans': [dict(cell=cell['cell'], attempt=step['attempt'],
                **next(span for span in step['product_trace']['spans'] if span['name'] == 'observation.task_facts'))
                for cell in p_cells for step in cell['steps'] if 'product_task_work' in step],
            'closed_only_duration_ns': None, 'counterfactual_whole_task_saving': None,
            'cache_scope': 'All observed result/pair hits are false/zero. A explicit fact directly reuses bundle.closed. Prepared pair geometry reuse is separately recorded.'},
        'simplification': {'invalid_request_count': 1,
            'extra_aabb': {'cell': 'grc03', 'attempt': 2, 'value_count': len(aabb_values),
                'value_component_bytes': len(compact(aabb_values)),
                'compact_body_projection_difference_bytes': len(compact(aabb_body)) - len(compact(without_aabb)),
                'projection_scope': 'Derived existing compact-body field footprint, unobserved actual modified request/response.'},
            'N_precision_geometry_refresh': {'cell': 'grc04', 'attempt': 3, 'meshes': 4, 'vertices': 26, 'triangles': 36,
                'occurred_before_first_distance_solution': True, 'independent_refresh_elapsed_ns': None,
                'necessity_for_frozen_scoring_precision': None,
                'unobserved_counterfactual': 'No distance answer computed from the initial mathutils geometry cache was saved.'},
            'causal_whole_task_savings': None, 'new_ablation_runs': 0},
        'measurement_semantics': {'actor_response_bytes': 'Compact UTF-8 JSON RPC envelope plus LF charged by base.encoded. Original disk source hashes are retained.',
            'inclusive_spans': 'Actor, RPC, host and task_facts nest. Kept separately, not added as exclusive algorithm costs.',
            'unassigned_gaps': 'Attribution among provider, model, client, transport and other work is unmeasured.',
            'component_bytes': 'Compact JSON value footprint or stated projection. Actual changed-request wire and token savings unmeasured.'},
        'single_next_direction': 'Administrator-led target-free scene discovery, on-demand detailed checks and coverage stopping.',
        'analysis_execution': {'new_consumer_Blender_product_API_runs': 0, 'quality_rescoring': False},
    }
    original_index = read_json(OUTPUT.parent / 'ORIGINAL_DATA_INDEX.json')
    indexed = {(root / row['path']).resolve().as_posix(): row for row in original_index['original_batch_files']}
    for name, item in SOURCES.items():
        if name in indexed:
            assert item['sha256'] == indexed[name]['sha256'] and item['bytes'] == indexed[name]['bytes']
    source(Path(__file__))
    result['saved_source_files'] = len(SOURCES)
    (OUTPUT / 'RESULTS.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8', newline='\n')
    (OUTPUT / 'SOURCES.json').write_text(json.dumps({'schema': 'saved-input-sha256-manifest-v1', 'files': sorted(SOURCES.values(), key=lambda row: row['path'])}, ensure_ascii=False, indent=2) + '\n', encoding='utf8', newline='\n')
    write_report(result)
    print(json.dumps({'cells': len(cells), 'steps': len(steps), 'qualified_P': 3,
                      'optional_BC_closed_work_units': result['closed_branch_analysis']['optional_BC_closed_work_units'],
                      'source_files': len(SOURCES)}))


if __name__ == '__main__':
    main()
