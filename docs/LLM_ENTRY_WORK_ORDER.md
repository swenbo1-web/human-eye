# 大模型接入实施：E0常驻通道＋E1解析间隙任务

**最新026执行状态**：N/V离线准备已[独立审查](LLM_HOST_PREPARATION_REVIEW.md)收口；真实模型原命令被自动审批拒绝且0启动/0外发。新计划已移除自动审批参数，用户随后明确授权两次测试，已派原实施聊天经正常审查执行冻结计划；不扩模型或原生批次，完整交付主动唤醒。

**当前追加（主验收025）**：R1–R4修正及两进程/五原场景已经[独立验收](LLM_ENTRY_FUNCTIONAL_REVIEW.md)，原0/5、额度marker和失败归档保持。当前仅按[真实宿主pilot](LLM_HOST_PILOT_PROTOCOL.md)做1数值＋1图模型消费，N/V仅可执行准备。下文是设计与此前执行范围的记录；不再次执行旧预检或限定复验，不提前运行正式模型收益批次。

2026-11-06，修订2，`codex/aggressive-v1`。依据[任务架构](LLM_ENTRY_ARCHITECTURE.md)推进。保留当前relay/pump成果，不重做已验收六模块，两端独立竞争。实施完整自测后主动唤醒主干，不让主干轮询等聊天。

## 当前阶段与文件所有权

已有候选是open/step/close＋完整AO转发，尚未验收。当前在同一未完成接入阶段改为任务入口，保留修订前源快照和运行记录，不等包装验收后再重启一次优化。代码存在不等于真实宿主或任务收益PASS。

作者可新增/修改：

- `human_eye_llm_stdio.py`、`human_eye_fast/llm_entry.py`、`human_eye_fast/blender_llm_bridge.py`、`examples/blender_llm_entry.py`。
- 新`human_eye_fast/local_tasks.py`、`verification/test_local_tasks.py`、`verification/llm_task_reference.py`，用于E1及其独立任务核对/公平实验草案。
- 原`verification/test_llm_entry.py`、`verification/test_llm_transport.py`、`verification/llm_entry_fixtures.py`、`verification/llm_entry_reference.py`。
- `docs/LLM_ENTRY_API_DRAFT.md`、`docs/LLM_ENTRY_PROTOCOL_DRAFT.md`、`docs/LLM_TASK_PROTOCOL_DRAFT.md`。
- `artifacts/llm_entry/preflight_001/`，修订2用独立子目录，旧失败/输入/源身份不覆盖。

不改17个已验收生产源、旧plugin、用户规格、当前GUI/默认注册，不stage/commit/push。打包/pyproject、README/进度/根报告由主干负责。额外seam需具体差异和原因，不能复制Session或改其私有状态。

## 本批必须完成

1. 复用纯bytes常驻relay和主线程nonblocking pump，不重新设计已解决的传输部分。
2. 默认目录只给结构化run及按需inspect。run可惰性建立明确绑定并直接执行，不要求模型先open/observe/预测再执行。宿主负责close；目录/绑定成本公开。细粒度开发接口不必全公开。
3. E1仅可信独立刚体对象对的close_gap：全局BC测d与最近点a/b，目标g满足0≤g≤d且d>0，用`(d-g)*(b-a)/d`求世界米平移，再public BlenderControl真实执行/全局回读。达标用实际误差判定，不隐藏候选搜索、强制CF/G预测、重试或回滚。
4. 纯数值任务跳过TD、全AO和图像。终态图按需复用同一bridge/readback与VGRenderer，正确捕获context/单位/对象，不创建第二Session重测。首批F视图，zero gap不用SECTION；renderer/control按生命周期释放。E1与完整Session不能并存独立current交替写同对象。
5. 默认结果是目标、实测误差/达标、对象/单位、实际控制变化。失败保留真实write_status/Outcome与必要定位；无整包before/after、全矩阵、全Top-K、训练状态、原mesh或全schema。不能只发done，或让正常任务必补第二轮才能理解结果。
6. V反馈可随下一业务请求，不为评分增加回合；没看图不贴标签。解析任务不为收集A强制L推理。shape求解和小模型均后置，本批不扩展通用规划。

## 有限功能预检

先保存源身份、合同、场景/命令/环境和已知限制。CPU重点是解析动作、公开结果、一次执行、真实失败状态和必要收发/EOF。主干32状态独立oracle设计检查可承接，不再穷举BC边界。

本阶段最多两个独立原生进程（background＋隐藏factory GUI），已运行的计入，不因修订/聊天重置；串行，不操作用户Blender。若额度已用，准确回传已完成和新主线尚缺项，由主干确定必要增量，不盲重跑。每进程最多6个组合案例，重点覆盖：

- 复杂非凸/多面对象解析缩隙，独立RNA/距离核对，正常一次执行。
- 非单位/父变换世界平移，reference与未请求对象不变；输入满足可信刚体独立前提，不新增全依赖扫描。
- 数值模式无TD/fullAO/PNG；按需图只生成终态图，实际协议内容能解码且绑定终态/模式。
- 当前结果inspect、已达目标不写入、一次实际执行错误或close/EOF组合，防止重复动作/假成功。

不为empty面、任意畸形输入、并发、多版本组合扩测。保留partial send/通知等会破坏真实主线的基本检查。headless循环不是GUI调度证明，mock不是宿主收图证明。当前不跑正式模型批次、付费API或凭证搜索，不修改宿主默认注册。

## 交付可执行的任务收益协议

E1草案是三类复杂任务各4episode，另2简单控制/臂。列出初态/目标/视觉需求/独立oracle、native通用helper、模型与计量边界；允许native脚本、批处理、常驻、缓存，不给本端私有定位。原predict→act→read→observe功能覆盖序列不能充当低回合任务流程。

事前主门：限定质量不退化，复杂任务完整均值至少快2倍，至少75%配对更快，各族与p95不劣。全部可见文字token目标少50%，native多轮子集串行决策往返中位少50%；native已一轮就按一轮比，缺usage不伪造。schema/目录/首次加载/模型等待/图片/补查/失败全计。精确协议由主干在正式运行前冻结，不换题调门通过。

旧桥20%和同wire B/I微基准降为有实际瓶颈时的归因实验，不先跑大量局部计时挤掉任务价值验证。实现/脚本功能、实际宿主接入、真实模型任务收益分列状态；E1收益验收前不推进E2。

## 回传与独立验收

完整预检交付后冻结源和证据，主动一次消息到主干host=`local`、thread=`01a1a993-669e-7632-98c2-a75754546eef`，给文件/摘要、所有运行/失败、精确协议与未测资格。用户已明确授权回报；具体阻塞可提前通知，独立工作继续。

主干至少一次独立核对流程/结果，再深审架构算法和相对实施达标版的退化；达标推进下一模块，有退化撤回主干候选，保留实施达标版。已确认优化不因更换执行者重做。本次是未完成接入阶段的设计纠偏，不是已验收模块的重复优化。
