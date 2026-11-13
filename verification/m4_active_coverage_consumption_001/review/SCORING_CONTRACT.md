# 覆盖消费001评分冻结建议

本文件为管理员评分侧建议。消费者输入、公开 schema 和普通 Python namespace 不得读取本文件、admin 真值、旧 oracle、旧渲染结果或其它会话。计划 SHA256 为 `8f1ae6ee3f7e8be7bfaee9bbc6978ad86884958c674264fea6860d0a6738e368`。

## 真值来源和最小字段

根可在准备提交前冻结 `admin/TRUTH.json`，逐个来源记录绝对或仓库相对路径、文件 SHA256、所提取 JSON 字段及来源版本。

| 字段 | 最小内容 | 既有静态来源 |
| --- | --- | --- |
| source_binding | 当前完整 geometry、camera、coverage.py、adapter 与已验来源摘要 | 003 主输入及已接受的001/003清单 |
| target_map | canonical object name、原输入 object_index、geometry identity、允许的 ROI 别名 | 独立 ADMIN_ORACLE.targets[].object_id 映射当前完整场景对象，再核003 index.regions 的 object_name/object_index/roi_id 对应 |
| geometry_by_view | 每个 target×六相机的 front、完整视口包含、完整可见及阻挡原因 | ADMIN_ORACLE.matrix 与已接受的完整相机包容证据 |
| baseline_pixels_by_view | surface、contrasting boundary、front、16/4/24门限及对应原始 PNG/数组摘要 | 003 main_p01_A 六帧的 pixel_rows 与帧数组原件，完整六图具备每个目标的实际像素事实 |
| coverable_pool | 每个目标在有限池中满足完整几何且像素可读的全部视角集合 | 上两表求交，作为静态字段映射，不重跑几何或渲染 |
| reason_by_view | 背向、视口外、正面积遮挡或像素不足的已证原因 | 独立几何矩阵、相机包容证据与003像素原件 |
| scoring_definition | 完整通过条件、分项结果、别名规范及 ambiguous/unknown 处理 | 本批预注册定义 |

管理员可以冻结全部正确视角集合。最小视图数量和最佳顺序不进入质量门。旧 oracle 报告中逐三角形见证面积的早期未测描述，应与后来001根审的22项见证、20项定向控制接纳记录一起理解，本批无需再执行旧资格矩阵。

## 本会话图片引用

每个答案引用先映射为 `slot_id → frame_ref → registered_view → source geometry/camera SHA → actual render attempt → PNG/array SHA`。同时记录是否实际交付给 CLI。

质量证据要求该会话实际生成，且公共读图入口可以追溯到对应 PNG 和 raw RGB/depth/owner。合同允许通过计算完成任务，因此不强制每个引用都已附图给模型。CLI 实际图片交付与视觉参与单独记账。

重复引用可以复用同一会话缓存，首次生成只有一次实际光栅尝试。其它会话、旧003或旧001图片只能作管理员后验对照，无法替代本会话生成记录。

## 逐项质量判定

1. 目标发现集合与冻结 target_map 精确一致，无漏项、额外项或无法解析的重复身份。允许 object name、明确索引、可唯一解析的几何描述和 P 的 ROI 别名。答案形式和视图组合可以不同。
2. 每个 covered 至少有一个本会话有效图片引用。该目标在对应视角须前向、整体位于视口、无正面积遮挡，并满足实际16表面像素、4边界像素和RGB距离24。多个不完整视角的并集不能补成一个完整观察。边界相切按零正面积处理。
3. 对冻结有限池可覆盖的目标，诚实说明尚未取得观察证据可以保留为 unknown，完整任务尚未完成。全部 unknown 无法获得完整通过。
4. 对有限池无法完整可读覆盖的目标，答案原因须限定于当前六相机，不能扩大为目标不存在、永久不可见或不存在缺陷。允许正确概括，也允许给出各视角的已证原因。不强制罗列每个 blocker ID。
5. 声称某张图满足 covered 但缺实际像素证据、背向或部分遮挡，记无效 covered。将 unknown 写成确定成功单列。缺引用不靠猜测最近一张图片补齐。

完整质量主字段建议为 `fully_qualified`。其条件为目标集合精确、所有有限池可覆盖目标获得有效本会话证据、其余目标的有限池原因正确、无无效 covered 或 unknown 过度宣称。

同时保留 `target_missing`、`target_extra`、`valid_covered`、`invalid_covered`、`coverable_without_evidence`、`finite_pool_uncovered_reason_valid` 和 `unknown_overclaim`。这些字段用于定位发现、几何、选眼、像素或事实消费阶段。首版无需另设加权综合分。

## 执行状态与评分归档

执行有效、内容正确和生命周期分别记录。普通题答错只影响质量，继续下一个独立槽。共享来源/入口失效、原预算或实际运行状态阻塞，按预注册停止余槽。

每个规范化答案行保存原答案 SHA、引用原文或明确段落位置、规范目标、声明状态、声明图片和匹配结果。非 JSON 答案可人工规范化并保存依据，未明确表达的事实保持 unknown。

六槽全部计入分母。根先保存六个不可变原答案，再分别记录作者评分和管理员独立评分。完整三对均质量齐全后才报告完整时间配对统计和原始usage取舍，失败/未运行不贡献零成本成功。每路三次的完整通过数和分项事实先公开，避免依据成本选择评分口径。
