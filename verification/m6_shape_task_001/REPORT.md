# M6-SHAPE-TASK-001 任务收口

2026-11-15。基线 `66e171ceb72c930ba534e1eb8317791d00bd2dba`，合同 `7dbbdd4fe53273b867d9c34e31ab367cad75f88f`。本批采用源码和保存JSON，几何/权重数组读取0，模型前向和训练0。

**决定为不进入当前局部凹陷学习立项，收口无可信目标参考的导入/粗选区训练路线。** 本局部形状类当前没有获准的新学习模型。可信同拓扑参考恢复已有确定性代码，其形状目标由参考坐标确定。

## 实际输入与目标

| 情形 | 实际来源和字段 | 输出目标与当前缺口 |
| --- | --- | --- |
| 导入模型、任务描述 | 当前capture的vertices_world/triangles，用户task_instruction；vertex顺序绑定本次capture | 可评价修改域保持和有限几何合法性，期望修复坐标需要独立认可来源 |
| 可信同拓扑参考 | operator的reference_file/reference_sha256及reference_intent，注册reference_ref | 同索引参考坐标直接确定目标，形状预测未知量为0 |
| 只有粗部位 | 操作者明确选区；本离线数据的allowed/free/boundary来源于合成patch计划 | 许可域和固定边界已知，域内哪些点该动及方向、幅度仍待目标证据 |

原参考绑定已实现 `ReferenceIntent(provenance, semantic_target, correspondence)`，要求same_index_from_owned_copy，并检查顶点数量、edges/polygons、matrix_world/unit_scale和目标实例身份。意图声明由受信操作者提供，内容真实性仍由作者负责。普通scene_cache的旧snapshot为观察历史，认可为目标需要另外建立意图和对应关系。空间任务的reference_id与target_clearance_m表达参考物和间隙量。[参考绑定](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/human_eye_plugin/surface_reference.py:14) [缓存](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/human_eye_plugin/scene_cache.py:290) [字段表](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_task_001/TASK_INPUTS.json)

## 直接基线已经解决哪一部分

对于已认可参考R与观察X，写域F内直接赋值Y_i=R_i，其他点Y_i=X_i。R固定域与X相同时，这一赋值实现完整参考目标。现有preview_restore逐选点复制参考坐标，受控RestoreController另有身份、方向、接触和回读流程。该判断来自方程与源码，本批数值刷分0、执行0。[直接预览](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/human_eye_plugin/surface_reference.py:138) [受控恢复](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/human_eye_plugin/surface_restore.py:107)

已有有限owned入口限制128顶点、8选点、1mm、30秒，reference preview限制最多64选点。它们是既有实现范围。当前Armadillo见证520点context、323自由点且物理单位未知，完整示例的接入、执行资格与产品成本均未验收。参考已给定时，扩大确定性工程覆盖所需的形状目标仍已确定。[现有范围](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/human_eye_plugin/surface_owned.py:12)

历史撤销需要精确前态或已知可逆编辑、稳定身份及适用范围。现有运动rollback记录涵盖对应受控操作，任意导入资产的既往雕刻过程仍无恢复依据。2D原画的同索引3D目标未建立。

## 一个固定原件任务

采用六见证中的 **Stanford_Armadillo_patch_03/sample_06**，源点172749，任务为撤销该条记录的人工凹陷并保留原形状。它属于合成研究情形。A=384、边界61、F=323、真实S=105、正常自由点218。真实S、扰动中心/半径和目标位移只作监督与评价。此处宽域来自合成计划，真实操作者选区记录缺失。

可信参考分支的答案来自生成前snapshot保存的reference_local.npy，直接对应赋值已确定输出。无参考分支的输出虽可写成F上的3D残差，仍有969个自由坐标量；固定边界允许Y=X+t*w等多种形状，其中w在固定域为0。光顺正则可选择一个解，其与作者期望形状的关系需要目标证据。

该例旧no-op与冻结MLS均改点0，已保存A RMSE/观察尺度约0.45241、S约0.86517。它们只提供旧合成任务的直接基线记录，其他直接方法的能力未由此确定。本批没有重新评分或制造零误差实验。[具体任务](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_task_001/CONCRETE_TASK.json)

## 缺口及最小证据来源

当前缺的是一条真实、可验收的修复任务记录，具体包括编辑前源几何和身份、编辑前记录的粗选区与任务要求、操作者认可的编辑后形状及对应关系。最小来源为已有作者认可的实际编辑会话。认可后的形状用于监督/评价，推理只接收编辑前实际可得字段。随后才能在相同写域上检查直接方法的剩余误差和完整成本，判断是否存在值得学习的未知量。一条记录可核对任务含义，学习所需数据覆盖另由规划者依据证据立项。

这次收口依据是目标来源、直接基线和现有失败记录。完整观察的信息上限、额外任务条件的实际收益仍未证明。旧学习候选继续关闭，本批确定不进入学习，未选下一架构或问题族。[决定](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_task_001/DECISION.json)

## 执行与成本

本批完成接口/基线源码审查、代表JSON核对和交付身份检查。新数组读取、模型前向、训练、描述/门限搜索、Bunny、Blender、Google/付费API及产品动作均为0。未核实本机运行配置是否已激活合格参考，也未新验收大网格产品流程。源码与JSON对固定基线逐字节核对，原件二进制身份沿用已接受记录。[来源](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_task_001/SOURCE_MANIFEST.json) [运行记录](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_task_001/RUN_LOG.json) [成本](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_task_001/COSTS.json)
