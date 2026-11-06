# E0/E1一次限定修正与原生复验

2026-11-06。依据[主审024](LLM_ENTRY_PREFLIGHT_REVIEW.md)，用户已授权自动推进与实施自测唤醒。原两个原生进程已耗尽且0/5 FAIL，本文件**新增一次恰好2进程、原5个场景的修正后复验**，不是清空旧额度或无限重试。先完成R1–R4，再跑修订源；不先为旧候选单独补测。

## 源与证据所有权

沿原[工作单](LLM_ENTRY_WORK_ORDER.md)作者文件范围。只修local_tasks、llm_entry、example及相应测试/草案，确需桥生命周期接线才最小修改bridge；纯relay不改，17个已验收源不改。交付原件`revision_002/delivery_001`和所有native/CPU/transport初次失败保持。当前来源与源ZIP是修正前基线。

新代码/运行登记放`artifacts/llm_entry/preflight_001/revision_003/`；新建限定runner，引用旧批次路径与hash，执行前登记当前源/输入/命令和进程数。不能删除旧launch markers，也不修改旧runner的禁止重跑逻辑来伪装首跑。除新必要脚本外不创建工作树、不动Git/根文档/用户GUI/旧默认注册。

## 先完成四项返工

1. 删除两层跨请求写锁；本次错误保持真实write_status/已知Outcome，后续明确run重新observe，不自动重试、不新增unlock。
2. 可信刚体/稳定场景前提写入绑定说明；去每run通用对象/父链依赖扫描及1e-9 witness重复一致性门。只保留正常求解和真实执行所需检查，不放大支持域。
3. VGRenderer按连接惰性常驻，终态图复用，EOF/stop释放；默认数值任务不建GPU资源。不改变VG取景/渲染算法。
4. 唯一当前结果与同一实际图的相机/单位/切面metadata可显式inspect；正常run不多发内容，不为取详细证据再次执行或渲染。

CPU仅运行受改动影响的合同和小型回归：两次明确请求不会被旧失败锁死且未自动重试；正常数值结果与原候选含义一致；两次真正新图只创建一个renderer，重复同图/取相机不重渲染，关闭释放，数值零创建；当前结果恢复不执行动作。删除断言永久写锁的旧期望，保留原测试日志。不重跑无关transport/全内核边界，不补大型性能批次。

## 原生复验：两个进程，五个原场景

使用修正后的PID记录和finally RNA保存。background原3例`nonconvex / parented / already-reached`，GUI原2例`occluded / parented-rescaled`；参数、容差、初态、实际动作和独立RNA/oracle不变。GUI的occluded可在同一例加入两张不同模式图、重复当前图、相机与结果取回的生命周期检查；这些额外调用只为功能覆盖，不能拿来计算正常任务模型往返。

每例必须保存：全部请求/响应、真实parent/client/launcher PID关系、主线程dispatch/close与listener/timer记录、独立before/after RNA、实际写/渲染/资源构造关闭次数、工具结果及独立数值/作用范围检查。已写后失败也要落终态RNA；异常继续保留失败，不把finally完成当作通过。GUI退出0仍须summary所有案例通过。

GPU例用本次实际PNG及同一渲染metadata验证图像/frame/对象/模式与场景，不用新图为旧图补证。原PNG、raw回包只能承接原记录意义，不能填原缺失RNA。没有真实模型消费，本批不能称模型收益或实际宿主资格通过。

两个原生进程串行，均是自有factory进程。启动继续请求Hidden；将owned-window hide提前到GUI脚本初始化、案例timer之前，若本机CLI有不抢焦点选项可在只读help确认后使用。只操作当前新进程PID窗口，保存首次观察及各例前后可见性。**测试操作期间必须隐藏；启动创建至Python获得控制之间不可见尚无证明，报告不得声称从未闪现。** 不为诊断这一段再增GUI进程，不操作现有用户窗口。

本批任一失败完整回报具体原因，不再自行加第三个进程。未受阻CPU/文档工作可继续。不要通过换目录、换runner名字恢复两进程预算。

## 同步修正正式草案，暂不运行模型

保持14例总数，在D族用edge-edge与vertex-face interior替换两例；给独立上/下界oracle和纯数学核对，保留旧清单，不扩大shape/旋转。补实际N helper、RNA/写入审计的可执行设计；V标签混合样点规则、SECTION切面/相机/PNG同源记录具体化。四个正式V例的真实标签尚未取得时明确未冻结，不借本次单occluded例冒充全部完成。

真正宿主协商、模型收图、28次正式双臂任务、时间/token仍不在本次运行额度内，待功能资格与具体协议齐备后推进。token缺测不得E1整体PASS，native单轮则往返优势未证明；完整时间/质量门不改。

完整交付后冻结所有新源/记录，主动一次唤醒主干聊天`01a1a993-669e-7632-98c2-a75754546eef`（host local），报告所有初次失败、修正、未测项和源摘要。主干不轮询等待，也不因换聊天重启优化链。
