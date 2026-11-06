# E0/E1候选独立复审：返工后完成限定原生资格

2026-11-06，主审024。结论 **REWORK_BEFORE_NATIVE_QUALIFICATION**。解析算法与任务级入口方向正确，但不能据24项CPU合同测试和工具回包放行：原生5例全部在PID断言处退出，缺独立终态RNA；候选还带入了本阶段明确不需要的防御策略和资源重复创建。原失败保持，先一次修正，再按[限定复验](LLM_ENTRY_RECHECK_PROTOCOL.md)执行，不先重跑旧候选。

## 独立核对结果

交付manifest SHA `4b4da2c2825aef8b84d1bc6f2f2b1dc4b4fac7f5b33ed0ebab624bb25316f56c`，source ZIP SHA `b8e04f01a331d21e4d1f53ab72f41a77c8f49fc9589a66593089a51b8fafde3e`。根侧与独立审查核对38源、10证据引用及ZIP，17个已验收内核字节不变，用户规格保持原hash。没有运行新的Blender/模型/性能批次。

| 项目 | 可接受的证据 | 不能据此宣称 |
| --- | --- | --- |
| 传输5/5 | 实际TCP/pipe转发；首轮沙箱限制、第二轮平台短写假设失败均保留 | 真实宿主/模型已经接入 |
| CPU24/24 | Stub/Mock合同、单次执行、实际和计划位移分开、按需输出 | 真实setter/depsgraph或图像可见性；CPU PNG只是不可解码占位bytes |
| CPU首轮4失败 | 3fail+1error源于helper与unittest内部`_outcome`重名；归档29源仅测试helper改名 | 生产经历一次修复后才通过，或失败可以删除 |
| 原生0/5 | 真实stdio/TCP、11工具回包、4次written/reached和1次零写回执；一张可解码SECTION PNG | 独立终态达标；五份after RNA均缺失 |
| PID修正 | 独立Windows probe支持启动器父/子PID；修正版finally独立取RNA控制流通过离线核对 | 原五例的父子链已被追溯证明，或修正版已原生通过 |
| 正式草案smoke | 14个数学recipe、28合成配对、11负例；独立支撑上下界核对有效 | 28次真实原生/LLM任务，或合理native实测需要三步 |

GUI虽然exit0，summary为FAIL，启动器正确未放行。主线程/EOF/stop断言在原PID断点前经过，但实际字典未落盘，报告区分路径证据与可重算原件。原GUI首次观测确实可见，worker随后隐藏；不能把启动参数`hidden:true`写成从创建起从未可见。

## 必须一次修完的四项

**R1 删除跨任务写锁。** `CloseGapSession._blocked`和`Binding._write_blocked`可跨新目标、重连持续拒绝；甚至有真实有限Outcome的错误也被锁住。独立probe复现。错误如实交付，失效证据清空；后续明确run从fresh observe重新开始。本次命令不自动重试，不新增unlock、审批或重绑定流程。

**R2 去掉热路径防御审查和重复数值门。** 每次run重新遍历对象/父链、拒绝modifier/shape等不是解析求解需要，可信独立刚体前提应由绑定合同承担；删除或移出该运行时审查，不借此宣称扩展到任意驱动/依赖。候选额外`isclose(hypot(witness),distance,rel_tol=1e-9)`还会拒绝已验BC的合法输出：距离0.000999998934674593m与witness范数只差约5.14e-11m，却触发硬拒绝。删除未经误差合同支持的重复门，由实际after与任务容差判结果。必要数值输入、主线程、当前观测和真实写状态语义保留。

**R3 图像资源真正按连接常驻。** 当前两次新图产生两次VGRenderer构造/关闭，即GPUOffScreen/shader重复创建。按连接惰性创建、复用并在EOF/stop释放；数值任务零创建。只证明结构次数，尚无GPU时间/内存收益，不以此宣称测得提速，不重开VG算法。

**R4 当前结果与图像详细证据可按需取回。** 当前inspect只有directory/witness/image，无法恢复完整当前结果；renderer还丢弃实际相机/单位等metadata。缓存唯一当前结果与当前图metadata，显式inspect result/camera可取，不重新run或重渲染来补证。默认返回仍紧凑，不把矩阵和日志重新塞进每次模型上下文，不建历史数据库。

已有数值主线可承接：一次run完成全局before→解析Translate→实际执行/全局回读；没有TD/fullAO/CF/默认图片；结果是实际控制差，未达标不自动循环。纯字节relay/pump不需要重写。root/独立审查未发现需要修改已验收17源的依据。

## 正式任务协议尚未冻结

原14个recipe提供有效稠密网格、单位/父变换与遮挡负载，但均由已知tip分离轴认证。正式前仅替换其中两D为真实edge-edge和vertex-face interior见证，保持12复杂＋2控制总数和当前动作域；独立oracle需从真实RNA的边/面内点给上界、支撑面给下界，不调用候选BC或固定错误顶点。原草案保持历史，不把这当作一般三维规划能力。

合理native脚本/helper/批处理/缓存能力、全部成本、质量门和2倍时间目标可以承接；实际N工具配置、RNA/写入审计、V01–04真实相机/切面/图像标签仍缺。视觉样点混合意见要给明确判定，SECTION按实际切开几何评分；不能用未切场景或四例unknown代替视觉资格。当前图原件不通过重渲染补旧相机证据。

全样本轮数必须照报；native多轮子集减半只是条件诊断，子集为空不成立。文字token缺测是未验子项，不能标E1整体通过；费用与图像token不按字节猜测。未冻结这些前不跑正式模型或宣布复杂任务收益。

三份独立报告/探针、根身份核对和作者原始候选/失败记录归档于`llm_entry_preflight_review_evidence.zip`。当前仍是同一未完成模块的具体返工，不是已达标后重新优化。修正及限定自测完成后实施端主动唤醒主干，主干再验流程、算法架构和退化；E1收益过门前不进入E2。
