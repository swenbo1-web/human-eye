# M6-REFINE-RECOVERY-002 公共回读重试修复

2026-11-16。用户已要求持续推进。REFINE001六例几何结果通过独立复核，公共 `save_readback` 入口的一处失败重试缺陷已被固定源码控制流反例复现。本批只处理这一类恢复问题，完成后回报规划继续既有任务循环。

唯一实施者 `local/01a1d9cc-0cc2-7702-ba1f-7e210022ba6b`，继续实际工作树 `C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe`、分支 `codex/m6-model-selection-001`，固定基线 `154ff39a9a0fa0ed25c59aec282f0bbd315a8a15`。

允许最小修改 `verification/m6_refine_001/session_api.py`，新增 `verification/m6_refine_recovery_002/` 的定向回归与证据。旧批manifest和聚合结果继续绑定154ff39a，原文件不改写。新提交记录修复前后源码摘要，重现旧版使用固定Git字节。其余运行模块必要调整只能直接服务同一attempt编号缺口，需明确说明。

## 固定反例

当前 `save_readback` 按已有readbacks目录数决定编号，并由session与编号生成唯一job标签。reader在创建输出目录前失败时，background已保留job目录。下次readback仍选相同编号，标签冲突。

根复核已实际提取固定源码函数，在替代reader的预启动失败控制下得到RuntimeError随后FileExistsError，路径和标签相同。反例原件位于规划分支 `verification/m6_refine_001_review/RESULTS.json`。根未运行此异常分支的真实Blender注入，真实reader恢复需由本批覆盖。

## 实现

在session锁内、reader启动前持久化独立读取attempt编号，使每次尝试取得新的输出目录及job标签。读取失败保留尝试记录，后续只读取已保存模型，版本和operations保持真实值。

兼容缺少新字段的既有session，覆盖已有失败job标签而没有readback目录的遗留情况。不能只从成功输出目录数量初始化计数；初始化及分配需要避开已使用attempt标识。复用已有pending编辑回读与幂等逻辑，保持调用者已有返回字段。

## 定向验收

先运行旧版反例，固定失败；随后在新候选跑同样控制。至少覆盖正常独立readback、创建job后/创建输出前失败、已有输出但回执缺失、旧session缺计数字段且旧失败标签已存在。普通故障在本批修复并保留原记录。

在一个本轮副本上真实调用save_readback。注入启动前失败，保留已有模型；下一次启动真实新Blender读取成功。检查新标签/目录、实际reader坐标、返回状态和完整来源身份。

整个回读恢复期间，保存blend SHA、version、operation列表均保持；reader尝试可以增加。已有保存后pending编辑的恢复回归与重复operation幂等检查也需通过，确认修改没有影响既有写状态。源原件和之前六个模型的几何摘要保持，旧消费者答案继续保留。

用旧版保存的六例作为输入回读控制，必要时复用已固定真实数组，至少一个Yanyite与一个face新进程回读。新消费者调用和训练均为0，图片沿用实际原件。

## 成本与交付

记录所有attempt、故障注入、新Blender调用、墙钟和状态差异。单线程定向验收，数值/Blender预算30分钟；超预算保留可解释结果并回报。不要为本次计数修复重跑Pro对照或增加新的性能优化。

交付修复源码、旧/新反例、真实独立回读恢复、遗留session兼容、pending/idempotency回归、状态前后差异、报告及成本。原始模型和大数组保持私有，公共源码与紧凑统计固定提交。

回报 `cycle_id=M6-REFINE-RECOVERY-002`、提交、报告与原件、实际通过/失败/未运行项及完整成本。回报后结束本批，由规划独立复核后继续选择参考图与真实模型区域对应的下一项。完成回报驱动，无定时兜底或新用户聊天。
