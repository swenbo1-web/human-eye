# FIX1 来源、原分母和关闭独立复核

固定交付 `1875bf45c09e8cca606f4de3fd8f0e821cc0d8a5`；最终准备 `e06597f92d1193b40e9a62b78919a3125e4e346d`。结论：来源和状态没有阻止新 owned C 工程批的遗留问题；本批资格仍为失败，不能因关闭后的正确结果升级通过。

## 本轮实际验证

- 自编离线脚本 76 个断言通过，记录 1,676 个输入路径哈希。断言数是文件/状态核查数，**不是实验样本量**，未采用作者 4,008 检查数作为独立成绩。
- 新增交付为 1,313 成员加 manifest，共 1,314 文件：逐字核 SHA256、大小、完整集合及交付 Git blob。最终准备为 1,189 成员加 PREPARATION，共 1,190；核固定准备 Git 与 362 外部输入哈希。旧 CONTINUITY-001 Git 目录和 manifest 未改，复用上一审结论，未重跑旧矩阵。
- actor 与旧 CONTINUITY-001 原字节一致；实际 helper、stdio、entry 由准备输入和实际 argv/session 绑定。已安装 138 源逐项核固定产品 `452b44d2` 的 Git 字节及安装 binding。实际运行身份为 `4067c864…851a9f6`，计 138 源。
- `8000b52f` 原 PREPARATION 副本与其 Git 完全一致。旧 runner 在 reservation 之前比较了旧批 PREPARATION 路径，其字节确与本批不同，因而该路径守卫会失败。保留原 FAILURE。最终 e06597f 的正确准备校验先于独占 reservation；提交时间早于记录推导的最早 reservation 约 12.234 秒。
- 真实目录只有一个 C episode：四条 thin 输入（初始化、通知、列工具、一次业务）和三条返回与桥接原件一致，thin EXIT 及 launcher wait/reap 均为正常退出；桥接明确未关闭外层 owner。
- BASE 工具返回 complete、71 matches、24 objects、276 pairs、unknown/deferred 均零。随后资格函数读取尚未发布的 `WIRE/INDEX.json` 抛 FileNotFoundError。原 `RESULTS`、`TURN_BASE`、`ENGINEERING_RESULT` 保留 failed=1、not_run=2、completed=0；无 REPEAT/EDIT 产物，无新 N。
- owner 的四次管理操作为 status/status/begin_turn/end_turn；end_turn 后 active_turn=null，owner 身份与期限不变。无 qa_advance、无 EDIT；初末完整几何均等于 BASE，initial/accepted/final 指纹相同。
- 原 590 秒期限贯穿 session、worker、thin、actor；单工具配置 30 秒，实际工具约 1.77 秒。完整失败 episode 为 4.1995286 秒，含关闭和结果写出。actor、产品 launcher、实际 runtime 以及 Blender 分别有退出确认；正常退出码均 0，关闭错误为空。
- runtime proof 的 `before_stdin=false` 与实际顺序一致：初始 QA、元数据、runtime proof、业务。一次扫描前 measurement cache 空，worker resident before 为空；未见额外几何预热。
- 四个 host wire 原件对应初始快照、一次扫描、最终快照和 close。前三条 call 文件与 wire 的逻辑内容按固定 Windows 文本写入规则精确相符，完成事件有源码 hash、成功状态与终态检查。第四条事件保留 `status=unknown`，但其请求明确是 close，响应为同一 PID 的 closed，且随后正常 reap；这不是未确认写动作。

## 限定与下一步

首次 prelaunch 的 0-live 结论由作者原失败回执、可独立确定的前置字节不等以及实际唯一运行目录相互支持；本轮没有独立历史进程探针。未把合成 consumer 目录算成真实运行。

原冻结 reader 仍依赖 terminal WIRE；worker 源码只在结束时 `meter.flush` 发布它。关闭后 WIRE 存在以及 postrun reader 候选通过，不改变本批失败。没有验证真实 C 的三轮 71/71/72、112/0/10；没有验证模型 resume、真实 usage 或完整收益。缺失丰富来源字段保持未记录；终态一致不声称检测所有短暂后又还原的修改。

按根已收敛的 [FIX2 方案](D:/hefe/docs/M4_SURFACE_SCAN_CONTINUITY_001_FIX2_PLAN.md)，冻结阶段顺序修复后启动**唯一新的 owned C**：runner 三轮收集 → 唯一 finish → 复用原 WIRE reader 逐轮后验，不采用新 online reader。在线 EDIT 回读等现有执行检查保持；不增加 N，不做模型/API调用。旧失败 1、未运行 2 永久保留。现有原件没有需要恢复或盲重试的未知动作状态。本次仅更新推进描述；原检查、脚本和证据结果未改、未重跑。

本轮新增产品、Blender、模型、API运行均为 0；没有修改作者文件、Git、产品或默认配置。

## 核查自身记录

第一次脚本把 Windows `write_text` 的 CRLF 文件直接等同 wire LF 文本，产生 3 个独立检查误判。已保留 `ATTEMPT_01.json`、`ATTEMPT_01_CHECKS.json`、`ATTEMPT_01_SCRIPT.py`；修正为精确 LF→CRLF 写入字节与逻辑代码 hash 后重跑通过。没有放宽作者验收。初次 AL 参数错误也保留于 `SELF_ISSUES.json`。

AL 自身 handle `eedb2e6559c7410dbf9007536acc04f1`：assignment 仍属于旧 write611，current=false；父当前 write622。按父明确委派执行本次离线任务，未借父句柄或改父任务。
