# 已封存六格的调用机制复查

本次仅分析既有六格原件。质量沿用管理员已封存的 6/6 完整正确、78/78 必要事实结果，分组和成本在封存后解封。未新增模型、Blender、产品运行、训练或质量评分。工具名称和业务内容可能透露路线，本批遮蔽范围为分组标签与成本。

## 冻结准则的结果

P 三格均自然请求 spatial_relation 与 surface_proximity，随后正确使用返回的当前关系、距离和见证点。P 共四次产品尝试，其中一次参数拒绝、三次成功，原生工具调用为零，满足预登记的至少 2/3 采用条件。每格的最终答案及来源都完整保存在 RESULTS.json。

这项结果限定为同一指定对象任务的三次重复消费，图像为零。未见任务迁移、一般三维优势以及整任务成本准入由各自证据判定。

## 逐步轨迹

下表列出全部十二次业务工具尝试。处理时长来自 ATTEMPT 的包含式 handler 墙钟窗口，响应字节来自 actor 对 UTF-8 JSON 响应包络的实际记账。完整单调时钟起止、请求参数和代码、响应、内部 RPC、host 执行、trace、最终答案及 SHA 均列入 RESULTS.json 与 SOURCES.json。

| 格与顺序 | 路线 | 主分类 | handler 毫秒 | 响应包络字节 | 本步作用及原件 |
|---|---|---|---:|---:|---|
| spc01/01 | N | directory_or_identity | 38.4066 | 1805 | 核对四个指定对象的类型、世界矩阵、尺寸、modifier 和单位。 [请求](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_spatial_fact_consumption_001/cells/spc01/owner/tool_01/REQUEST.json) [响应](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_spatial_fact_consumption_001/cells/spc01/owner/tool_01/RESPONSE.json) |
| spc01/02 | N | new_information | 895.8193 | 17036 | 求值四份网格，双精度转换到世界坐标，缓存几何，并将 Target 的全部 256 个世界顶点输出给消费者。 [请求](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_spatial_fact_consumption_001/cells/spc01/owner/tool_02/REQUEST.json) [响应](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_spatial_fact_consumption_001/cells/spc01/owner/tool_02/RESPONSE.json) |
| spc01/03 | N | new_information | 194.8773 | 766 | 复用 geo，以双向点面、边边和边面测试首次计算三个表面距离、见证点和交叉检查。 [请求](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_spatial_fact_consumption_001/cells/spc01/owner/tool_03/REQUEST.json) [响应](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_spatial_fact_consumption_001/cells/spc01/owner/tool_03/RESPONSE.json) |
| spc02/01 | P | new_information | 5.5156 | 857 | 尝试获取事实，将 nearest_witness 作为独立 requested_fact，合同校验拒绝。 [请求](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_spatial_fact_consumption_001/cells/spc02/owner/tool_01/REQUEST.json) [响应](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_spatial_fact_consumption_001/cells/spc02/owner/tool_01/RESPONSE.json) |
| spc02/02 | P | new_information | 4210.0433 | 8464 | 删去无效 nearest_witness，保留 spatial_relation、surface_proximity 和额外 closed_solid_relation，获取三组任务事实。 [请求](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_spatial_fact_consumption_001/cells/spc02/owner/tool_02/REQUEST.json) [响应](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_spatial_fact_consumption_001/cells/spc02/owner/tool_02/RESPONSE.json) |
| spc03/01 | P | new_information | 3536.1299 | 8464 | 自然请求 spatial_relation、surface_proximity 和额外 closed_solid_relation，一次获取三组任务事实。 [请求](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_spatial_fact_consumption_001/cells/spc03/owner/tool_01/REQUEST.json) [响应](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_spatial_fact_consumption_001/cells/spc03/owner/tool_01/RESPONSE.json) |
| spc04/01 | N | directory_or_identity | 37.8159 | 1685 | 核对四个对象的类型、矩阵、原网格计数、modifier 和单位。 [请求](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_spatial_fact_consumption_001/cells/spc04/owner/tool_01/REQUEST.json) [响应](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_spatial_fact_consumption_001/cells/spc04/owner/tool_01/RESPONSE.json) |
| spc04/02 | N | new_information | 194.3275 | 1963 | 求值四份完整几何，双精度转换，计算双向点面和边边距离、边面交叉，并以双向单顶点 winding 补充包含检查。 [请求](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_spatial_fact_consumption_001/cells/spc04/owner/tool_02/REQUEST.json) [响应](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_spatial_fact_consumption_001/cells/spc04/owner/tool_02/RESPONSE.json) |
| spc05/01 | N | directory_or_identity | 67.9421 | 2232 | 核对对象和单位，同时求值四份网格，先用 mathutils 世界坐标转换后装入 float64 数组。 [请求](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_spatial_fact_consumption_001/cells/spc05/owner/tool_01/REQUEST.json) [响应](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_spatial_fact_consumption_001/cells/spc05/owner/tool_01/RESPONSE.json) |
| spc05/02 | N | new_information | 741.6732 | 775 | 重读四份网格，改为局部坐标和世界矩阵均以 float64 运算，再以三角形笛卡尔积首次求距、见证点和交叉数。 [请求](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_spatial_fact_consumption_001/cells/spc05/owner/tool_02/REQUEST.json) [响应](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_spatial_fact_consumption_001/cells/spc05/owner/tool_02/RESPONSE.json) |
| spc05/03 | N | unresolved_verification | 89.4564 | 622 | 复用 geo，检查四网格边流形，并对三个候选的双方全部顶点计算 solid-angle winding，补充排除包含。 [请求](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_spatial_fact_consumption_001/cells/spc05/owner/tool_03/REQUEST.json) [响应](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_spatial_fact_consumption_001/cells/spc05/owner/tool_03/RESPONSE.json) |
| spc06/01 | P | new_information | 3430.6008 | 8464 | 自然请求 closed_solid_relation、surface_proximity 和 spatial_relation，一次获取三组任务事实。 [请求](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_spatial_fact_consumption_001/cells/spc06/owner/tool_01/REQUEST.json) [响应](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_spatial_fact_consumption_001/cells/spc06/owner/tool_01/RESPONSE.json) |

spc05 第二步重读 4 份几何、576 点和 1136 三角形，代码明确把坐标转换改为双精度。该步发生在首次距离答案之前。第三步补充全顶点 winding 包含检查，复用已有几何。两步分别归入新增信息和未决核验，已完整回答事实后的原生重算计数为零。

spc01 第二步将 Target 的 256 个世界顶点整体输出给消费者，响应包络达到 17036 字节。其余几何缓存在 host 进程供下一步求距。该数据体积是实测消费轨迹，独立删减后的行为和收益未观测。

每格前后各有一次 QA 几何快照，共 12 次，已单列保留。它们与消费者业务工具调用分别计数。P 的成功产品调用内部各有一次 host 采集，共 3 次，仍属于其产品调用的内部工作。

## 无效请求与修正

spc02 首次将 nearest_witness 作为独立 requested_fact。请求校验返回 executed=false 和 not_executed，host 执行为 0。该次额外尝试确认为 handler 5.5156 毫秒、响应包络 857 字节，产品 stdio 边界发送 1273 字节、接收 869 字节，内部 RPC 窗口为 2.3475 毫秒。

下一次请求删去该项，并保留其余三类事实。首次 handler 结束至修正 handler 开始间隔为 7970.9631 毫秒。它是可见的未归因墙钟间隔，无法确定各环节的耗时份额，也无法据此预测避免该错误后的整题节省。

## 九项额外 closed unknown

三次成功 P 请求都额外要求 closed_solid_relation。每次三个候选均返回 closed_solid_work_budget unknown，共九项。必要的 spatial_relation 与 surface_proximity 均为 measured，最近者 summary 为完整，整体 partial 来自额外事实。最终答案保留了这一限制，封存评分确认必要任务完成。

| 格 | closed 项数 | closed work_units | closed pair_tests | closed node_pair_visits | task_facts 包含式毫秒 |
|---|---:|---:|---:|---:|---:|
| spc02 | 3 | 786432 | 5733 | 119335 | 4101.0992 |
| spc03 | 3 | 786432 | 5733 | 119335 | 3445.2689 |
| spc06 | 3 | 786432 | 5733 | 119335 | 3355.4937 |

共确认 2359296 个 closed work_units。各候选复用了已准备的 pair/trees，但仍进行闭壳验证，最终触及工作预算。九个 closed 值按实际正文的紧凑 JSON 单独计量，各 229 字节，共 2061 字节。这是既有正文组件的大小，删字段后的实际包络和传输大小尚未发生。

现有 trace 只给出 surface、support、closed、ranking 等共用的 task_facts 窗口，缺少 closed 独立时段。上表的全部 task_facts 时长不能归为额外 closed 耗时。原件中没有一次仅请求必要事实的成功反事实运行，因此无法测得去除 closed 后的整题耗时、token 或成本变化。

## 可确认的局部成本及归因边界

| 路线 | 业务尝试 | 原生调用 | 产品调用 | handler 总毫秒 | 响应包络总字节 |
|---|---:|---:|---:|---:|---:|
| N | 8 | 8 | 0 | 2260.3183 | 26884 |
| P | 4 | 0 | 4 | 11182.2896 | 26249 |

这里的 handler 合计仅覆盖工具处理窗口。模型任务的完整耗时、启动清理、输出入 token 与费用由成本报告独立统计。内部 RPC、host 采集及 trace 与外层 handler 含有嵌套工作，分别保留后不相加。空档时间保留为未归因，未命名为推理或插件延迟。

## 一次简化分析与下一方向

当前保存数据已足以识别一次无效参数往返、九项未增加闭壳结论的额外请求工量，以及原生路线的一次精度刷新。P 的零原生重算说明本题事实交付被实际消费。以上均为本批观测，尚不能计算删去这些步骤后的因果收益。

建议仅保留一个后续方向。在整任务成本满足父报告准入后，冻结一个未见的小范围任务，验证必要事实的自然消费能否迁移。当前不实施改动或训练。额外 closed 工量作为本批待证机会保留，后续评审可结合迁移任务判断。

## 证据与可重放性

分析脚本只读取既有文件，并输出本目录的 JSON 和报告。[分析脚本](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_spatial_fact_consumption_001/cost_review_01/mechanism/analyze_trajectories.py) [完整结果](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_spatial_fact_consumption_001/cost_review_01/mechanism/RESULTS.json) [输入 SHA 清单](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_spatial_fact_consumption_001/cost_review_01/mechanism/SOURCES.json)

质量结论直接引用管理员封存件。[质量报告](D:/hefe/docs/M4_SPATIAL_FACT_CONSUMPTION_001_QUALITY_REVIEW.md) [封存件](D:/hefe/verification/fixes/20261112_m4_spatial_fact_consumption_review/QUALITY_SEAL.json)
