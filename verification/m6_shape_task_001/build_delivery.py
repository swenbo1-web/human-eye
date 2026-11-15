"""Build the source-backed task definition using text and saved JSON only."""

import ctypes
import hashlib
import json
from pathlib import Path
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = "66e171ceb72c930ba534e1eb8317791d00bd2dba"


def read(path):
    return json.loads(path.read_bytes())


def write(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                             encoding="utf-8", newline="\n")


def own_metrics():
    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("faults", ctypes.c_ulong)] + [
            (name, ctypes.c_size_t) for name in ("peak", "working", "qpp", "pp", "qpnp", "pnp", "page", "peakpage", "private")]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(Counters), ctypes.c_ulong]
    valid = psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
    return {"CPU_s": time.process_time(), "peak_working_set_bytes": int(counters.peak) if valid else None}


def main():
    started, cpu_started = time.perf_counter(), time.process_time()
    attempts_path = HERE / "BUILD_ATTEMPTS.json"
    attempts = read(attempts_path)["attempts"] if attempts_path.exists() else []
    if not attempts and (HERE / "RUN_LOG.json").exists():
        prior = read(HERE / "RUN_LOG.json")
        attempts.append({key: prior[key] for key in ("build_wall_s_before_final_write", "build_main_CPU_s_before_final_write",
                                                     "own_process_lifetime_before_final_write")})
    interface_audit = read(HERE / "INTERFACE_AUDIT.json")
    baseline_review = read(HERE / "BASELINE_REVIEW.json")
    evidence = read(ROOT / "verification/m6_shape_observe_001/EVIDENCE_PLAN.json")
    witness = next(row for row in evidence["evidence"] if row["evidence_id"] == "validation_center")
    case_id = witness["case_id"]
    index = read(ROOT / "verification/m6_shape_train_001/PUBLIC_DATASET_INDEX.json")
    case = next(row for row in index["cases"] if row["id"] == case_id)
    baselines = read(ROOT / "verification/m6_shape_train_001/BASELINE_RESULTS.json")
    baseline = next(row for row in baselines["validation"]["cases"] if row["id"] == case_id)
    assert case_id == "Stanford_Armadillo_patch_03/sample_06"
    assert case["allowed_vertices"] == 384 and case["free_vertices"] == 323
    assert case["boundary_vertices"] == 61 and case["damaged_vertices"] == 105
    inputs = {
        "cycle_id": "M6-SHAPE-TASK-001",
        "field_classification": [
            {"fields": ["vertices_world", "triangles"], "source": "task_query.project_task_geometry current evaluated capture",
             "status": "implemented_capture_fields", "meaning": "observed geometry and captured vertex order, desired shape unspecified"},
            {"fields": ["task_instruction", "task_kind"], "source": "task_intent.classify_task_intent",
             "status": "user_or_trusted_host_supplied", "meaning": "routing/request text, no target coordinates inferred"},
            {"fields": ["indices"], "source": "surface_task_service.query and surface_owned.indices",
             "status": "explicit_selection_for_a_bound_reference_operation", "meaning": "chosen write points, semantic damage truth not supplied by the list"},
            {"fields": ["allowed_mask", "boundary_mask", "free_mask", "mapping.context_source_ids"],
             "source": "offline features.prepare_topology and data_io.load_sample",
             "status": "available_in_synthetic_offline_record", "deployment_requirement": "actual operator region and current-source identity/mapping required"},
            {"fields": ["reference_file", "reference_sha256", "reference_intent.provenance",
                        "reference_intent.semantic_target", "reference_intent.correspondence", "reference_ref"],
             "source": "surface_owned.load_config and surface_reference.ReferenceRegistry",
             "status": "implemented_trusted_owner_reference_path_activation_unverified",
             "meaning": "owner supplies intended same-index reference, source binding and compatibility checks apply"},
            {"fields": ["reference_id", "target_clearance_m"], "source": "goal_segment pair goal",
             "status": "implemented_spatial_pair_fields", "meaning": "reference object and clearance target, no target mesh implied"},
            {"fields": ["reference_local.npy", "target_normalized", "damaged_mask", "center_vertex_id", "radius_ratio", "amplitude_ratio"],
             "source": "synthetic generation and label/evaluation records",
             "status": "synthetic_supervision_or_generation_metadata", "proposed_no_reference_inference_use": False},
            {"fields": ["approved repair before/after pair", "pre-edit operator region", "accepted output identity"],
             "source": "future owner-authored editing record", "status": "missing_for_actual_no_reference_task",
             "meaning": "training/evaluation target evidence, held out from inference"},
        ],
        "scenarios": [
            {"id": "import_without_target", "runtime_inputs": ["current source-bound geometry", "task text"],
             "user_inputs_needed": ["actual permitted region", "meaning of desired edit"],
             "unknown_to_predict": "intended 3D displacement over free vertices",
             "available_evaluation": ["domain preservation", "geometric validity predicates within supported scope"],
             "target_answer_source": "no approved real repair target in this batch", "learning_entry": False},
            {"id": "trusted_same_topology_reference", "runtime_inputs": ["current raw mesh identity", "owner-bound reference_ref", "explicit indices"],
             "user_or_owner_inputs_needed": ["trusted intended reference with same-index provenance", "semantic target acknowledgement"],
             "compatibility": ["vertex count/edges/polygons", "matrix_world/unit_scale", "object_instance/document_epoch"],
             "target_answer_source": "accepted reference vertices", "unknown_shape_to_learn": None,
             "direct_baseline": "existing preview_restore and bounded RestoreController", "learning_entry": False},
            {"id": "coarse_region_without_target", "runtime_inputs": ["current geometry", "operator region", "task text"],
             "region_adds": "permitted support of edits and fixed-domain constraints",
             "unknown_to_predict": "which allowed vertices should move, displacement direction and magnitude, retained natural features",
             "target_answer_source": "requires independently accepted repair or equivalent measurable target", "learning_entry": False},
        ],
        "cache_semantics": "scene_cache snapshots are observation-only; a previous state can become a target only through explicit trusted reference intent and correspondence",
        "appearance_reference": "2D appearance reference has no established same-index 3D vertex target in this task",
        "new_schema_or_runtime_implemented": False,
    }
    write("TASK_INPUTS.json", inputs)
    concrete = {
        "cycle_id": "M6-SHAPE-TASK-001", "task": "undo the recorded artificial dent while preserving the same-index unperturbed shape",
        "case_id": case_id, "witness_source_vertex_id": witness["source_vertex_id"],
        "classification": "synthetic research example, real imported-asset repair acceptance unestablished",
        "observed_input_sources": ["inputs/sample_06.npz", "observed/sample_06.npy", "graph.npz", "mapping.npz"],
        "region_provenance": "384-vertex synthetic patch plan; real operator coarse-region evidence not present",
        "counts": {"context": 520, "allowed": 384, "boundary": 61, "free": 323, "true_support_evaluation_only": 105,
                   "normal_allowed": 279, "normal_free": 218, "free_coordinate_unknowns": 969},
        "desired_output": "same-topology coordinates Y with Y_fixed=X_fixed; if accepted R provided, Y_free=R_free",
        "target_answer_source": "reference_local.npy copied from unperturbed Stanford snapshot during public pair generation",
        "true_support_center_radius_vector_in_inference": False,
        "no_reference_proposal": {"inputs": ["X,T,current identity", "actual operator allowed region", "declared edit intent"],
                                  "output_type": "free-domain 3D displacement", "target_coordinates_available": False},
        "reference_given_direct_baseline": {"formula": "Y_i=R_i for i in F, Y_i=X_i otherwise",
                                            "preconditions": ["R approved for this edit", "same-index correspondence", "compatible frame/scale", "R_fixed=X_fixed for exact full-target agreement"],
                                            "unknown_shape_variables_after_reference": 0,
                                            "numerical_score_run": False, "basis": "coordinate assignment equation and existing kernel source"},
        "coarse_region_ambiguity": {"formula": "Y=X+t*w on free vertices, w_fixed=0; varying t preserves the same fixed boundary",
                                   "implication": "boundary constraints leave shape degrees of freedom; regularization chooses an objective-specific solution"},
        "saved_direct_baselines": {name: {"actual_changed_vertices": baseline[name]["actual_changed_vertices"],
                                           "A_rmse_over_scale": baseline[name]["errors"]["A"]["rmse_over_scale"],
                                           "S_rmse_over_scale": baseline[name]["errors"]["S"]["rmse_over_scale"]}
                                   for name in ("no_op", "mls")},
        "existing_product_coverage": {"owned_limits": {"vertices": 128, "selected": 8, "displacement_m": .001, "duration_s": 30},
                                      "reference_preview_selected_limit": 64, "case_free_vertices": 323,
                                      "public_physical_units": "unconfirmed", "this_case_product_execution": "not_verified"},
        "historical_undo": "requires a retained exact prior state or a known invertible edit and valid identity; current generic observation cache and rigid rollback records do not establish arbitrary sculpt undo",
        "geometry_arrays_opened_this_batch": 0,
    }
    prior_identities = read(ROOT / "verification/m6_shape_observe_001/REUSED_INPUTS.json")
    representative_folder = ROOT / "verification/m6_shape_train_001/private/public_data/patches/Stanford_Armadillo_patch_03"
    wanted = {str((representative_folder / name).resolve()) for name in (
        "reference_local.npy", "graph.npz", "mapping.npz", "observed/sample_06.npy", "inputs/sample_06.npz", "labels/sample_06.npz")}
    binary_references = [dict(row, identity_source="OBSERVE001 accepted REUSED_INPUTS.json", current_binary_read=False)
                         for row in prior_identities["reused_input_files"] if str(Path(row["path"]).resolve()) in wanted]
    assert len(binary_references) == 6
    concrete["inherited_geometry_file_identities"] = binary_references
    write("CONCRETE_TASK.json", concrete)
    decision = {
        "cycle_id": "M6-SHAPE-TASK-001", "decision": "do_not_enter_learning",
        "current_no_reference_local_dent_training_route": "closed",
        "new_learning_candidate": None, "model_architecture_selected": None,
        "reasons": ["trusted same-index target determines coordinates and has an existing direct kernel",
                    "import/coarse-region scenarios lack independently approved real repair targets and task records",
                    "two old model trials failed quality; finite descriptor diagnosis did not establish new learning value"],
        "deployment_limitations": ["representative large native-unit case has no verified current bounded-product execution coverage"],
        "minimum_missing_artifacts": [
            {"artifact": "one complete genuine repair task record", "source": "owner-approved editing session",
             "contents": ["before geometry/identity", "task text and coarse region recorded before editing", "approved after geometry", "topology/coordinate correspondence and acceptance author"]},
            {"artifact": "inference/evaluation separation", "source": "that same record",
             "contents": ["document which task fields exist before repair", "keep approved after-shape as supervision/evaluation only"]},
            {"artifact": "direct-method comparison on the specified intended output", "source": "fixed task record after target exists",
             "contents": ["no-op and a task-appropriate direct method", "same write domain and preservation metrics", "complete preparation/save/readback cost"]},
        ],
        "missing_artifact_interpretation": "one record establishes task meaning; sufficiency for learning and held-out generalization still needs a separately scoped data decision, with no arbitrary sample quota imposed here",
        "scope": "closure of the current no-reference local-dent learning route only",
        "root_cause_claim": "complete-input insufficiency and benefits of additional task conditions remain unproven",
        "next_family_or_training_dispatched": False,
    }
    write("DECISION.json", decision)
    sources = [
        "human_eye_plugin/task_query.py", "human_eye_plugin/task_intent.py", "human_eye_plugin/scene_cache.py",
        "human_eye_plugin/goal_segment.py", "human_eye_plugin/host_motion_ledger.py", "human_eye_plugin/live_spatial_mcp.py",
        "human_eye_plugin/surface_reference.py", "human_eye_plugin/surface_restore.py", "human_eye_plugin/surface_owned.py",
        "human_eye_plugin/surface_owned_mcp.py", "human_eye_plugin/surface_owned_task.py", "human_eye_plugin/surface_task_service.py",
        "human_eye_plugin/surface_geometry.py", "human_eye_plugin/blender_host.py", "human_eye_plugin/mesh_structure.py",
        "verification/m6_shape_data_001/features.py", "verification/m6_shape_data_001/generate.py",
        "verification/m6_shape_train_001/data_io.py", "verification/m6_shape_train_001/prepare_public.py",
        "verification/m6_shape_train_001/PUBLIC_DATASET_INDEX.json", "verification/m6_shape_train_001/BASELINE_RESULTS.json",
        "verification/m6_shape_observe_001/EVIDENCE_PLAN.json", "verification/m6_shape_observe_001/SUMMARY.json",
        "verification/m6_shape_observe_001/REUSED_INPUTS.json",
    ]
    records = []
    for relative in sources:
        path = ROOT / relative
        blob = path.read_bytes()
        assert subprocess.check_output(["git", "show", BASE + ":" + relative], cwd=ROOT) == blob
        records.append({"path": str(path), "bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest(), "base_commit_bytes_equal": True})
    write("SOURCE_MANIFEST.json", {"cycle_id": "M6-SHAPE-TASK-001", "base_commit": BASE, "source_files": records,
                                    "inherited_geometry_file_identities": binary_references,
                                    "geometry_or_weight_files_opened": 0, "binary_identity_scope": "prior accepted manifests and evidence JSON only; no new binary rehash"})
    prefix = HERE.as_posix()
    report = f"""# M6-SHAPE-TASK-001 任务收口

2026-11-15。基线 `{BASE}`，合同 `7dbbdd4fe53273b867d9c34e31ab367cad75f88f`。本批采用源码和保存JSON，几何/权重数组读取0，模型前向和训练0。

**决定为不进入当前局部凹陷学习立项，收口无可信目标参考的导入/粗选区训练路线。** 本局部形状类当前没有获准的新学习模型。可信同拓扑参考恢复已有确定性代码，其形状目标由参考坐标确定。

## 实际输入与目标

| 情形 | 实际来源和字段 | 输出目标与当前缺口 |
| --- | --- | --- |
| 导入模型、任务描述 | 当前capture的vertices_world/triangles，用户task_instruction；vertex顺序绑定本次capture | 可评价修改域保持和有限几何合法性，期望修复坐标需要独立认可来源 |
| 可信同拓扑参考 | operator的reference_file/reference_sha256及reference_intent，注册reference_ref | 同索引参考坐标直接确定目标，形状预测未知量为0 |
| 只有粗部位 | 操作者明确选区；本离线数据的allowed/free/boundary来源于合成patch计划 | 许可域和固定边界已知，域内哪些点该动及方向、幅度仍待目标证据 |

原参考绑定已实现 `ReferenceIntent(provenance, semantic_target, correspondence)`，要求same_index_from_owned_copy，并检查顶点数量、edges/polygons、matrix_world/unit_scale和目标实例身份。意图声明由受信操作者提供，内容真实性仍由作者负责。普通scene_cache的旧snapshot为观察历史，认可为目标需要另外建立意图和对应关系。空间任务的reference_id与target_clearance_m表达参考物和间隙量。[参考绑定]({(ROOT/'human_eye_plugin/surface_reference.py').as_posix()}:14) [缓存]({(ROOT/'human_eye_plugin/scene_cache.py').as_posix()}:290) [字段表]({prefix}/TASK_INPUTS.json)

## 直接基线已经解决哪一部分

对于已认可参考R与观察X，写域F内直接赋值Y_i=R_i，其他点Y_i=X_i。R固定域与X相同时，这一赋值实现完整参考目标。现有preview_restore逐选点复制参考坐标，受控RestoreController另有身份、方向、接触和回读流程。该判断来自方程与源码，本批数值刷分0、执行0。[直接预览]({(ROOT/'human_eye_plugin/surface_reference.py').as_posix()}:138) [受控恢复]({(ROOT/'human_eye_plugin/surface_restore.py').as_posix()}:107)

已有有限owned入口限制128顶点、8选点、1mm、30秒，reference preview限制最多64选点。它们是既有实现范围。当前Armadillo见证520点context、323自由点且物理单位未知，完整示例的接入、执行资格与产品成本均未验收。参考已给定时，扩大确定性工程覆盖所需的形状目标仍已确定。[现有范围]({(ROOT/'human_eye_plugin/surface_owned.py').as_posix()}:12)

历史撤销需要精确前态或已知可逆编辑、稳定身份及适用范围。现有运动rollback记录涵盖对应受控操作，任意导入资产的既往雕刻过程仍无恢复依据。2D原画的同索引3D目标未建立。

## 一个固定原件任务

采用六见证中的 **Stanford_Armadillo_patch_03/sample_06**，源点172749，任务为撤销该条记录的人工凹陷并保留原形状。它属于合成研究情形。A=384、边界61、F=323、真实S=105、正常自由点218。真实S、扰动中心/半径和目标位移只作监督与评价。此处宽域来自合成计划，真实操作者选区记录缺失。

可信参考分支的答案来自生成前snapshot保存的reference_local.npy，直接对应赋值已确定输出。无参考分支的输出虽可写成F上的3D残差，仍有969个自由坐标量；固定边界允许Y=X+t*w等多种形状，其中w在固定域为0。光顺正则可选择一个解，其与作者期望形状的关系需要目标证据。

该例旧no-op与冻结MLS均改点0，已保存A RMSE/观察尺度约0.45241、S约0.86517。它们只提供旧合成任务的直接基线记录，其他直接方法的能力未由此确定。本批没有重新评分或制造零误差实验。[具体任务]({prefix}/CONCRETE_TASK.json)

## 缺口及最小证据来源

当前缺的是一条真实、可验收的修复任务记录，具体包括编辑前源几何和身份、编辑前记录的粗选区与任务要求、操作者认可的编辑后形状及对应关系。最小来源为已有作者认可的实际编辑会话。认可后的形状用于监督/评价，推理只接收编辑前实际可得字段。随后才能在相同写域上检查直接方法的剩余误差和完整成本，判断是否存在值得学习的未知量。一条记录可核对任务含义，学习所需数据覆盖另由规划者依据证据立项。

这次收口依据是目标来源、直接基线和现有失败记录。完整观察的信息上限、额外任务条件的实际收益仍未证明。旧学习候选继续关闭，本批确定不进入学习，未选下一架构或问题族。[决定]({prefix}/DECISION.json)

## 执行与成本

本批完成接口/基线源码审查、代表JSON核对和交付身份检查。新数组读取、模型前向、训练、描述/门限搜索、Bunny、Blender、Google/付费API及产品动作均为0。未核实本机运行配置是否已激活合格参考，也未新验收大网格产品流程。源码与JSON对固定基线逐字节核对，原件二进制身份沿用已接受记录。[来源]({prefix}/SOURCE_MANIFEST.json) [运行记录]({prefix}/RUN_LOG.json) [成本]({prefix}/COSTS.json)
"""
    (HERE / "REPORT.md").write_text(report, encoding="utf-8", newline="\n")
    run = {"cycle_id": "M6-SHAPE-TASK-001", "status": "completed_task_definition", "text_source_files_verified": len(records),
           "representative_metadata_records": 1, "geometry_arrays_opened": 0, "weights_opened": 0,
           "new_model_forwards": 0, "training": 0, "threshold_or_description_search": 0, "Bunny_arrays_or_scores": 0,
           "Blender_calls": 0, "product_calls": 0, "API_calls": 0, "new_installations": 0,
           "new_reference_restore_execution": 0, "new_zero_error_baseline_scoring": 0,
           "decision": decision["decision"], "build_failures": [],
           "recovered_read_search_incidents": {
               "interface_audit": interface_audit["read_search_incidents"],
               "baseline_review": baseline_review["read_command_failure_log"]},
           "build_wall_s_before_final_write": time.perf_counter() - started,
           "build_main_CPU_s_before_final_write": time.process_time() - cpu_started,
           "own_process_lifetime_before_final_write": own_metrics()}
    write("RUN_LOG.json", run)
    attempts.append({key: run[key] for key in ("build_wall_s_before_final_write", "build_main_CPU_s_before_final_write",
                                              "own_process_lifetime_before_final_write")})
    write("BUILD_ATTEMPTS.json", {"cycle_id": run["cycle_id"], "attempts": attempts,
                                   "scope": "text/JSON delivery builds only, no model or geometry operations"})
    write("COSTS.json", {"cycle_id": run["cycle_id"], "task_kind": "text/JSON task-definition review; no performance benchmark",
                          "build_and_source_identity": run, "delivery_build_attempts": attempts,
                          "interface_audit_costs": interface_audit["cost"],
                          "baseline_review_costs": baseline_review.get("costs", baseline_review.get("measurement", {})),
                          "missing": ["complete source-reading/tool and model-interaction wall/CPU/monetary costs",
                                      "short-lived git source-check child CPU and final serialization/exit",
                                      "product restore preparation/execution/readback costs for this task"],
                          "historical_baseline_costs": "old batches only; no repeat run", "new_training_paid_API_or_install": 0})
    print(json.dumps({"decision": decision["decision"], "case_id": case_id, "source_files": len(records), "arrays_read": 0,
                      "wall_s": run["build_wall_s_before_final_write"]}))


if __name__ == "__main__":
    main()
