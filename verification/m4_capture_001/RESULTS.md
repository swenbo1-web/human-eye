# M2-M4-CAPTURE-001 初版离线交付

**M2_M4_CAPTURE_001_READY，限离线候选就绪。** 已实现单次宿主主线程读取内的前置采集预筛，以及一条 BlenderMCPHost 内部运输命令。最终固定源码的 12 类新用例与 116 项旧入口/M3 回归共 **128 项通过**。真实 Blender 属性前提、取数收益与整任务收益均未验，尚不构成产品准入或最近对象查询上线。

工作树为 `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe`，分支 `codex/m4-single-pass-acquisition`，由 managed create_worktree 从 `82ef6ebcd8ae363bb336447d7a44e95c922f0ab2` 创建。该基线与 12a6c39 的产品文件无差异，131 源摘要 fb5a 与上一轮已接受证据一致。最终候选仍为 131 源，摘要为 **`776485105a0616b9aa19b4a7385e6fd01a15ef32bf535d9487444855b1a193e5`**。实际 import 的 host、MCP、M3 文件均来自本新工作树，见 candidate_runtime_identity.json。

## 实现与职责

产品只改 `human_eye_plugin/blender_host.py` 与 `blender_mcp_host.py`。

1. `capture_nearest_candidates(focal_id, deadline_ns, max_response_bytes)` 固定一次依赖图更新、完整对象全集、单位、帧、求值对象和身份。限定独立静态三角 mesh；父级、子级、约束、修改器、动画、形态键、实例、不可求值等明确拒绝该候选模式，不偷偷转全景后声称省读。
2. 第一遍读取 evaluated.bound_box 与 evaluated.data 的一个三角面，每对象最多读取该面的三个顶点作为见证。严格检查三角面非退化，孤立第零顶点不提供上界。用焦点与候选的真实三角顶点间向外舍入 L1 距离得到固定上界 U。它仅作采集上界，距离答案继续由原 M3 计算。
3. 八角点构成轴对齐局部盒后，对各乘法、求和与单位缩放向外扩张，包络与原 _capture 相同的二进制浮点坐标运算。第二遍计算向下舍入 L∞ 下界，仅严格 L>U 且有可靠见证的对象可排除；等号、并列、零间隙、坏/缺失/不可读取的边界及缺见证均保留。无排序、树、持久目录或跨 RPC 代际平台。
4. 小幅给 _capture 增加私有上下文，直接使用同一 graph/scale/objects/evaluated 对象展开所保留网格；不重调公共 capture_task，不受四 selector 限制。新模式才包裹有期限检查的顶点迭代器，旧循环不支付逐顶点期限分支。新捕获带独立 capture_scope，原场景验证器不能把它当成完整场景。
5. 收据列出全部对象、边界、见证、保留/严格排除、未决项及展开计数，绑定宿主源码、文档/实例、单位、帧和目录摘要；明确 `M3_qualification_performed=false`、`acquisition_only_not_nearest_result`、零动作权限。保留原始全场景几何数量上限，目录阶段累计检查；展开阶段继续原上限，最终 JSON 文档字节与发布期限统一检查。运输层把宿主期限取为调用方原期限与连接器期限的较早者，编码前即起算，不逐对象重置。

真实运输接线为 `BlenderMCPHost.capture_nearest_candidates` → 固定 `_OBSERVATION_COMMANDS` / exact-params 模板 → `_host.capture_nearest_candidates(**params)`。收据回读核对 protocol、focal、加载源码摘要及零权限。未新增公共工具/schema/提示词，未接 ProcessHost；旧明确两对象 task 入口仍走原方法。

## 实际验证与失败记录

最终验收采用 **offline_qualification_03.json**。其中保存 argv、cwd、UTC、退出码、原始 stdout/stderr、命令完整墙钟和前后 131 源 manifest。退出 0，128 tests，源码前后一致；测试进程墙钟约 1.796 秒。这是验收命令成本，**不是引擎耗时收益**。

预登记 12 类覆盖远物体排除、全重叠、并列/等界、零距离、旋转/非均匀变换、大平移/小尺度/次正规数的 Fraction 独立包络 oracle、坏/缺/读取失败边界、孤立点与退化见证、域外拒绝、旧入口绕过/固定命令到达、单次 graph/覆盖/来源改变、累计几何/文档/期限与异常清理。宿主桩里三对象例实际仅对两对象调用 to_mesh；这只证明调用路径，不能当 Blender 节省的字节或毫秒。

首次 12 类执行出现 9 个子断言失败，原因是测试错把按稳定 ID 排序的 coverage 当成插入顺序；已改为按 ID 核对。本批六次定向测试进程的规模为 12、70、128、128、128、128；扩展与复跑由新增回读、边界异常、期限交接反例及最后源码固定触发，不是性能重复采样。旧极端数值回归仍打印原 renderer bbox_center overflow 警告，断言通过；本轮没有修改该 renderer。

qualification_01/02 保留中间源码的通过记录，分别为 0e1eef…、ca37e8…，不作最终源码准入。03 对应最终 776485…；覆盖数量不累加。最终 QA 两脚本另经 AST 和 `--help` 检查，见 qa_preparation_check.json；真实场景未运行。最终 Git 空白检查另在提交前执行。

## 仍需根审和真实宿主核验

- **边界的数据前提**仍待目标 Blender 版本验证。离线证明的是给定包络后的数值保守性，桩无法证明 evaluated.bound_box 覆盖实际求值网格、访问 evaluated.data 的真实成本或原生惰性求值行为。真实 QA 会用完整捕获逐点核包络，逐面核见证。
- **未读对象没有完整 M3 准入证据**。有效的一个见证面不意味着整个 mesh 已通过 M3 的全部退化/位数/拓扑检查。收据绝不输出 complete/nearest，也不转换为旧 solid/top1 成功；后续正式消费必须明确来源合同和 M3 unknown 传播，不能拿排除名单假定全场景已准入。若这要求额外全量检查，其成本必须进入下一决定门。
- **上界可能松**。第一面见证点和 L1 上界不保证接近真正最小距离；全重叠和焦点缺见证会保留全部对象。不可用最优案例平均值掩盖这一退化。
- **旧入口时间未测**。行为回归通过不等于没有性能退化；宿主文件变大增加每次源读取/编译成本，新 QA 对照使用原 82ef6eb 宿主字节，使候选承担这项真实成本。新增纯 stdlib Fraction 见证检查的固定成本也待量测。
- **期限是合作检查**。Blender 原生 graph 更新/to_mesh/三角化不能在 Python 内强制中断；调用前后检查及客户端回读都拒绝过期成功，但不宣称硬实时抢占或外部编辑历史证明。

## 已准备的下一批真实 QA

real_qa.py / blender_assets.py 固定九个场景，逐场建立隔离新 scene，最终恢复原 scene 并只清理本脚本资源，不保存文件。对照为**82ef6eb 完整采集 + 原 M3**与**本候选预筛采集 + 同一 M3**，按 case 序号交替顺序，无 warmup，最多 36 RPC 尝试，不补样/重试；900 秒批次预算，额外最多一次 60 秒清理。请根审后安排 **20 分钟独占 Blender 窗口**，本线不等待或自行申请当前 MCP 窗口。

旧控制宿主是单文件只读导出，SHA256 `5d2605d9cac66b0755bb5c68af37d852f49285f109448c7dd9220d4d3494a307`，通过 --baseline-root 传入，不需要安装另一插件。两臂使用同一个未修改的 M3。脚本登记实际收发 TCP 字节、请求次数、完整 arm/turn 时间、对象/顶点/面、序列化字节、按成功源码路径推定的 to_mesh/三角化次数；这些推定与原生独立 profiling 明确区分。所有未运行成绩保持空白。

硬指标为完整最近值和 binary64 完整并列集合、来源绑定一致、全部对象有账、每个排除有严格证据、见证真实、无过期成功及清理。源码或属性前提失败即停，不能把失败场景换掉。产品级零 setter 与 QA 自己搭场景的写入分开；脚本不承诺已对用户原始网格做完整内容哈希。

本批 Blender 会话、安装、图片、模型消费者、外部模型 API、子 Agent 均为 0。旧 D:/hefe 分支核对仍为 f7f3c8e 且干净，未修改竞争/W-ENTRY、原资产、默认配置、主线 STATE 或上一轮证据。工作树保留供根审与后续 QA。实施首个时钟为 10:06:12Z，提交与唯一回报的最终 UTC 随回报附送；模型 token/费用及派单到首读时间未计量，不能用测试秒数代替完整 turn 成本。
