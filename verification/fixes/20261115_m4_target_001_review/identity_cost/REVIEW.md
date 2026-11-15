# M4-TARGET-001 独立来源与成本复核

本轮结论：保存的来源与当次账本可闭合；未发现新的身份、字节、计时或预算缺陷。**不代表目标见证通过，也不能计算 A/B 优化收益。** 当次 `not_realized` 结论应保留。

复核人 `/root/target001_identity_cost`；当前 AL assignment `e5d54595-8858-4234-ab59-509afd896bad`，父任务只读。固定 final `03eb4e2971891dfe0160972cbcf974e3dcf1a21c`，基线 `fde0e9ab21fb6eaee1750befd64ad1bebdde2961`，A 产品提交 `cbbbd2611031f3c2d469280a71bcd410fb47447a`。

## 本轮实际执行的检查

仅执行自编标准库离线检查器 `audit_identity_cost.py`。`RESULT.json` 记录 **829/829 个保存证据断言通过、766 个不同路径的读取哈希**；多数断言是文件身份核对，不能将它们说成 829 个产品功能测试。新增产品调用、Blender、raster、模型消费均为 0。

- Git HEAD 固定，工作树状态干净；基线到 final 共 346 个变更路径 = 7 产品文件 + 339 个本批 namespace 文件。
- CONTENT_MANIFEST 中 345 个文件、11,239,742 字节全部重算 SHA/大小并核到 final Git blob；manifest 自身另核 Git blob，覆盖 346 个变更路径。
- 141 份运行源逐一核对 A 产品提交、final 提交、worktree、wheel、安装目录五方同字节；按 runtime_identity 公开规则独立重算 aggregate 为 `b7868c46119b2f5dcb3ca426e78a2ac9bb45b51167a01d323516c7707eb81e76`，三份来源清单一致。wheel SHA、freeze SHA 与 RUN_BINDING 一致，包顶层源码枚举无额外源。
- RUNTIME_ARCHIVE 全部 272 份归档、8,507,203 字节与其原始 runtime 文件逐字节核对；14 个旧保护 pin 复核通过。没有递归重扫这些 pin 所引用的所有历史内层文档。
- 独立复算原始时钟、stdio/Host TCP 字节、公开文本 UTF8/图片 base64、预算 claims/settlements 与原始 render events。作者的 358 项运行检查和 38 项产品检查本轮未机械重跑，不并入本轮分母。

## 实际成本与未运行项

| 区间 | 本轮原始字段复算 |
|---|---:|
| A02 单业务 request→reply | 922.8983 ms |
| A02 客户端完整 call | 924.4404 ms |
| A02 完整 session | 2778.8254 ms |
| A02 结束后保存校验 | 50.3591 ms |
| A01 失败 session | 2105.2332 ms |
| A01 结束后保存校验 | 34.5704 ms |
| 固定资产 builder | 1290.7864 ms |
| 注册→作者最终审计墙钟 | 3824.6355123 s |

这些区间包含嵌套时钟，不能相加制造一个“端到端优化时间”。墙钟还包括准备、协作和审计，不是模型推理时间；注册之前的计划/AL/worktree 步骤不包含其中。

实际 owned Blender 启动 3 次（builder、A01 失败、A02），实际只构造 **1 张 SCENE**。原始记录没有 LEFT raster。B 实现 0，正式计划 12 槽实跑 0；focal-only/rack 仅准备资产，没有运行观察；新实验模型调用 0。模型 tokens/费用为未运行，协调/复核 tokens、现金、RSS 峰值仍未测。

Host TCP 业务请求 100,372 B、响应 261,682 B；close 另为 17/62 B。MCP target 原始 RX 12,139 B，TX 257 B。I/O audit RX 为写入 stdout 前 LF 文本 12,138 B，SHA 经 CRLF→LF 精确对齐；这 1 B 差异不是遗失响应。公开文本 7,088 UTF8 B、PNG 3,223 B、base64 4,300 字符、1 image block，均从原 RX 解码复算，不能将这些嵌套表示重复相加。

## 预算和退出状态

一条 raster claim 预留 6，实际原始 render_attempt/completed 都为 1；结算保留该 1 次成本，仅释放 5 次已证实没有构造的预留。A01 失败仍计一次 Blender 启动，未改写为免费；最终 raster actual=upper=1，pending=0。静态预算实现对 `actual=None` 保留预留上界。当次没有“构造后超时/交付失败”的动态场景，本轮不声称这类反例已重跑。

A02 MCP runtime 保留句柄确认退出 0；两个 owned Blender worker 都有 reaped、原期限一致、前后几何指纹一致。**A01 实际 MCP runtime 句柄不可用，退出仍 unknown**；其 stdio wrapper 的退出 0 不能代替实际 runtime 证明。A01 原失败及 cleanup error 保留；本轮未杀进程、未尝试删除缓存。作者记录中被自动审批拒绝删除的本地 bytecode 仍不在交付清单，本轮没有读取/删除该缓存或绕过策略。

## 限制及检查器日志

本报告只审来源和保存的运行账本；几何正确性由另一复核任务处理，尤其不能用本报告的全部通过覆盖其新发现。`passed=true` 仅指上述保存证据断言通过。

检查前曾将 `build_install.py` 误写为 `harness/build_install.py`，只读 rg 返回 exit 1；随后通过文件枚举纠正。之后只读 rg 曾探测不存在的 `PLAN.md`/`DECISION.md`，exit 1；实际决定文件为 `DECISION.json`，已读取确认计划12槽、实跑0。错误仅为文件定位，没有修改产品或原始证据。首次审计脚本执行 829/829 通过，无异常覆盖或删除。
