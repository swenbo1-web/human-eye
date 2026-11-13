# CONTINUITY-001：独立来源、分母与关闭复核

**本范围通过；没有发现妨碍从新 owned 实例重跑 C 的真实状态或来源阻塞。** 前提是先修正并冻结准备层接口，采用新的 episode、输出目录和实例，保留旧 C 的失败与两轮未运行。原工程资格仍未通过，本轮离线核对不能把旧 C 改成通过。

固定交付 `a206a96e51ca6293ea555f17960b964ba02f0606`，准备提交 `1c96846cbbf948b80860a5366f5442407e1cbabd`。本轮独立脚本 **1,357 项检查全部通过，700 个输入路径摘要**。作者 654 项检查没有计入本轮。新增 Blender、产品、模型及 API 运行均为零，没有修改作者原件、产品或 Git。

## 来源与准备顺序

- 367 个内容文件加 DELIVERY_MANIFEST 自身，共 **368 份交付文件**，全部匹配固定 Git 字节；文件集合、大小和 SHA256 一致。
- 64 个冻结内容文件加 PREPARATION 自身，共 **65 份准备文件**，匹配准备提交和当前原件；332 份冻结外部输入摘要一致。仅作本批来源绑定，没有重跑旧产品测试矩阵。
- ENGINEERING_STARTED 原件记录上述准备提交。固定 runner 在建立独占 reservation 前核已提交 PREPARATION、内部文件和外部摘要；reservation 早于两个实际 episode。
- 用 C runtime 的 Windows 创建时间减去 reservation 到 proof 完成的完整单调时差，得到 reservation 的保守时间下界，仍晚于准备提交约 9.84 秒。这与代码顺序和实际 reservation 共同支持“先冻结、后运行”。
- 实际 C 固定为产品 `452b44d2`、138 源摘要 `4067c864…a9f6`，安装入口、实际 runtime 身份、audit 与返回的 source binding 一致。

## 原分母与四个真实薄客户端

| 组 | 计划轮次 | 实际业务与薄客户端 | 原工程完成 | 原工程失败 | 未运行 |
| --- | ---: | ---: | ---: | ---: | ---: |
| N | 3 | 3 | 3 | 0 | 0 |
| C | 3 | 1 | 0 | 1 | 2 |

四个真实薄客户端进程分别有退出码 0、Popen 回收和内层 EXIT 原件。每轮原始 TX/RX、四条附件请求、三条响应、owner REQUEST/RESPONSE 与轮次记录一致；均为 initialize、initialized、tools/list、一次 tools/call。内层 EXIT 的字节统计匹配原帧，全部 `backend_close_requested=false`。没有把同一 RPC 的副本当成多次业务，没有隐藏重试。

每轮前后管理记录表明 owner、Blender PID、workspace 和原期限保持一致，thin 退出没有关闭后端。N 三轮还核同一 namespace、内存标记、24 个对象 session_uid，BASE/REPEAT 的完整对象矩阵与冻结 BASE 一致，EDIT 与冻结 EDIT 一致。管理事件和原 ADMIN 文件时间包含关系对应，登记编辑只发生一次。

C 只有 BASE 一轮实际传输。其 default 扫描回执为 complete、71 匹配、24 对象、276 对，unknown/deferred 为 0；audit 显示一次 observe、112 个新 kernel、缓存条目从 0 到 112。C REPEAT、EDIT 文件与输出目录不存在，不能声称已证明 C 的跨轮缓存或持续性。

## 失败后状态及关闭

C 工具返回成功、thin 正常退出，owner 已记录 `end_turn(BASE)`，随后准备层资格核验抛出原 AssertionError。原错误、accepted_success=false、0 completed/1 failed/2 not_run 均保留。

C 的 `active_turn=null`，`edit_attempted=false`、`edit_verified=false`、registered_pose_applied=false；worker initial、accepted、final 指纹相同，初末几何投影与 BASE 一致。产品 launcher Popen、实际 runtime retained handle 和 Blender Popen 分别确认退出码 0。没有未知动作需要恢复或重试。

N 的 geometry_unchanged=false 正确保留，因为它完成了登记 EDIT；其最终几何匹配冻结 EDIT，accepted/final worker 指纹一致，清理有效。不能把这一预期变化误判为资产被意外污染。

两个 episode 均确认 owner launcher、后端和适用产品清理，原资产与 owned input.blend 字节保持一致。完整 RESULTS 写入关闭和计时发布均早于各自原 **590 秒**绝对期限。N 完整区间 2.2573118 秒，C 为 3.9755011 秒；两组业务不同，这些数值仅属工程资格记录，不能计算插件相对原生收益。

## 下一步界限

新的 C 工程批可以使用新 owned 实例；不要复用已关闭旧实例或覆盖其旧记录。新批应固定最小准备层合同修复，并验证 C BASE/REPEAT/EDIT 完整序列和独立终态回读后，再决定模型消费者实验。本轮不审核快照兼容候选的语义完备性，不签发正式多轮 CLI 消费资格；这些由根的其他复核范围合并判定。

本轮没有真实模型消费者、resume 或 usage；不能把三个薄客户端的进程持续性升级为模型线程记忆持续性。历史进程内存、所有已撤销瞬时行为和 fsync 级持久化仍不在证明范围。

## 自身检查记录

首轮只有一项核验器失败：误把 Windows 目录枚举顺序当业务轮次顺序。`ATTEMPT_01.json` 已保留。修正为目录集合核对，业务顺序继续单独按原 RESULTS 与管理事件核对，最终全部通过；没有修改任何作者证据。

AL 自身句柄 `eedb2e6559c7410dbf9007536acc04f1` 的旧 assignment 仍 current=false，未借父句柄、未覆盖父任务。本轮依据根任务 `3a93462f` 的直接委派。脚本、结果、输入摘要和本报告仅写根指定 binding 目录。
