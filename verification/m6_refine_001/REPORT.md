# M6-REFINE-001 实际定向精修

本批把大模型计算位移、修改独立 Blender 副本、保存及新进程回读连成完整闭环。两例使用事前固定的初始平滑法向、核心、保护层和局部尺度幅度，六次真实 Pro 会话均保留原文、操作记录和模型。

## 实际结果

| 轮次 | 来源 | 组别 | 回读 | 中心位移/h | 核心中位数/h | 工具数 | 会话秒 |
|---|---|---|---|---:|---:|---:|---:|
| v1 | s01 | native | pass | 0.999985 | 0.936959 | 4 | 76.639 |
| v1 | s01 | facts | pass | 0.999985 | 0.936959 | 4 | 67.716 |
| v1 | s02 | facts | pass | 1.000011 | 0.933985 | 3 | 59.513 |
| v1 | s02 | native | pass | 1.000011 | 0.926961 | 3 | 67.645 |
| v2 | s02 | facts | pass | 1.000011 | 0.926961 | 3 | 67.402 |
| v2 | s01 | facts | pass | 0.999985 | 0.936959 | 4 | 78.539 |

初末模型由额外十二个新 Blender 进程再次打开。独立核验重算了位移、连通、保存精度、拓扑、场景和完整网格相关自交候选，最终结果见 QUALITY_VERIFICATION.json。消费者最终回答中的操作、文件引用及测量值另行核对。

s01 为 Yanyite 的固定 410 点空间选区，允许修改 274 点，h 为 0.714294 毫米。s02 为 face 正常观察 o0002 的 384 点区域，允许修改 220 点，h 为 0.01191649 原生单位。s02 的物理单位未知，两个无局部三角形连接的点保留零位移。

I 外的宿主 float32 坐标逐位保持。原生多边形顶点环、source ID、矩阵、其他对象、材质、UV 和打包图片分别核对。Yanyite 原有十个退化三角形继续保留，其与本次受影响域的相关候选通过精确 AABB 和交叠核检查。

## 模型与同机位图片

每行模型均来自该消费者实际保存的完整 blend。局部 OBJ 与三向前后 PNG 位于同一结果目录，全部文件身份见 VIEWABLES.json。前图在完整 baseline blend 摘要和相机规格一致时复制已核验渲染，复制成本单列。后图由实际保存几何重新渲染。

- v1_s01_facts 的[完整模型](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_refine_001/private/sessions/v1_s01_facts/versions/001/model.blend)、[修改前](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_refine_001/private/results/v1_s01_facts/before_views/view_01.png)和[修改后](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_refine_001/private/results/v1_s01_facts/after_views/view_01.png)。
- v1_s01_native 的[完整模型](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_refine_001/private/sessions/v1_s01_native/versions/001/model.blend)、[修改前](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_refine_001/private/results/v1_s01_native/before_views/view_01.png)和[修改后](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_refine_001/private/results/v1_s01_native/after_views/view_01.png)。
- v1_s02_facts 的[完整模型](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_refine_001/private/sessions/v1_s02_facts/versions/001/model.blend)、[修改前](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_refine_001/private/results/v1_s02_facts/before_views/view_01.png)和[修改后](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_refine_001/private/results/v1_s02_facts/after_views/view_01.png)。
- v1_s02_native 的[完整模型](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_refine_001/private/sessions/v1_s02_native/versions/001/model.blend)、[修改前](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_refine_001/private/results/v1_s02_native/before_views/view_01.png)和[修改后](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_refine_001/private/results/v1_s02_native/after_views/view_01.png)。
- v2_s01_facts 的[完整模型](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_refine_001/private/sessions/v2_s01_facts/versions/001/model.blend)、[修改前](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_refine_001/private/results/v2_s01_facts/before_views/view_01.png)和[修改后](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_refine_001/private/results/v2_s01_facts/after_views/view_01.png)。
- v2_s02_facts 的[完整模型](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_refine_001/private/sessions/v2_s02_facts/versions/001/model.blend)、[修改前](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_refine_001/private/results/v2_s02_facts/before_views/view_01.png)和[修改后](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_refine_001/private/results/v2_s02_facts/after_views/view_01.png)。

图片采用统一中性材质、冻结的相机和真实位移尺度。前期过曝图和调整光照的预览原件均保留。face 区域近乎平片，固定幅度下变化细微。工程规格由规划合同确定，美术满意度仍需人工观看判断。

## 一次性能优化与恢复修复

四个首版结果固定后，用 session 和版本绑定的二进制 NPZ 几何包替换重复大数组 JSON 传输。八次首版 Python 调用共传输 52,746,408 字节请求 JSON，四次重复了同版本快照。冷创建、复用、数组逐位一致和普通 SciPy 调用另有本地对照，详见 TRANSPORT_SUMMARY.json。两次优化会话继续从独立原始模型开始，其位移由各自消费者计算。

独立审计同时复现了 reader 在创建输出目录前失败后的重试标签冲突。修复将下一次 reader 编号在启动前写入状态。真实故障注入后保留已保存模型，另一新进程回读成功，版本只增加一次。六个正式消费者均未触发这一异常路径，速度变化的解释单独列出该修复。

六次本地传输对照的 snapshot 加 executor 合计为 inline 4.9414 秒、NPZ 3.4641 秒。正式两次 v2 事实会话合计 145.9407 秒，首版两次事实会话合计 127.2288 秒。两例按固定次序单次运行，模型 token 缓存、执行顺序和会话差异共同影响总时间，当前样本量仅覆盖这两例。组件成本及逐任务总时间见 CONSUMER_PERFORMANCE.json。

## 成本与原件

真实 Pro 会话共 6 次，累计会话墙钟 417.453 秒。训练次数为 0。数值阶段控制器累计 93.606 秒，峰值采样进程树工作集 413.02 MiB。Blender 和 Python 子调用属于嵌套成本，独立预检与失败恢复均保留分类记录。完整成本见 COSTS.json 和 private/costs/FULL_COSTS.json。

输入、缓存输入、输出 token 按 CLI 实际事件统计。货币费用、提供方内部重试及完整 CLI 进程树 CPU/RSS 缺少测量值，记为 unknown。MANIFEST.json 覆盖本地原件字节身份，原模型、数组、图片、完整回执和模型回答留在本机。公开提交包含脚本、规格及紧凑统计。

首版分析器在绑定后追加 Blender 作业状态，审核文件随后追加恢复回归结果。v2 运行前补记了证据身份，原始绑定另存 private/optimization/BOUND_ORIGINAL.json。原四个消费者及 session 原件保持固定，性能选择与目标保持原绑定。此前聚合文件的早期完整字节未单独留存，其身份和全部原始事件继续可查。

## 执行入口与下一批

consumer_runner.py 驱动固定会话，consumer_bridge.py 提供普通 Python 计算和提交工具，session_api.py 提供 submit_edit、state、save_readback 及版本化实际保存。blender_edit.py 和 blender_read.py 分别执行修改与独立导出。verify_quality.py 从实际 blend 重读核验。每次 payload 与 operation ID 保留独立身份，读取恢复状态后可安全查询既有结果。

建议下一批在新区域加入真实美术修改指令和人工前后判定，复用本批已经验证的保存、保护和独立回读链路。该批固定提交回报规划后，继续既有独立复核和明确派工循环。
