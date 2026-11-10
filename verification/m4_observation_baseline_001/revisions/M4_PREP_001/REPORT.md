# M4-PREP-001：PREP_FIX_READY

本修订只修复匿名质量材料的语义丢失，supersedes 准备提交 `9c85ab9a0518e1fe2369113f59ce308a2d97b8d3` 的投影实现和绑定。cycle 仍为 `M4-OBSERVATION-BASELINE-001`。消费者为 **0**，没有正式 GO、cells、STARTED 或结果；没有模型、Blender、产品、安装、几何预检或旧消费重跑。

原脚本、SOURCE_REUSE、PLAN、FREEZE、INDEX、REPORT 的原字节已从 Git 9c85 与当前字节逐项比对后归档到 `original_9c85ab9a/`。管理员反例、独立反例、复核报告及重放脚本按原字节保存为 `reference/` 数据；未在原目录执行会写入旧报告的重放脚本。旧版失败和旧准备证据没有覆盖。

## 最小修正

`quality_handoff/pack_quality.py` 删除全局 ADMIN/FACTS/PROTECTED 递归机制及任意文本路径替换。`audit_projection` 保留原调用签名，但对任意 payload 只做 deepcopy，不解码 JSON 字符串，不靠字段名推断语义。

实际 `handoff_one` 的 owner RESPONSE/ERROR_RESPONSE 只剥离已知 RPC 顶层 id/jsonrpc/_meta；其中 result/error 整体保留。公开工具事件仍使用原已知 item 信封字段，但其 arguments/result/error/command 不再递归清洗。请求代码、query、嵌套 JSON 对象、JSON 文本、原生 stdout、合法同名字段、未知字段和路径字符串均保留。

额外管理删除仅发生在两个调用点：`worker_closed` 生产者信封的直接 pid/closed_ns/original_deadline_ns，以及 owner exception 直接 traceback。嵌套同名字段、message、data、false/null、poisoned、未知状态不删除，也不晋升为成功。最终答案按原字节保留，事件、失败、缺响应和重复尝试不合并。main、归档、排序、请求处理等七个未修改函数与原脚本 AST 一致。

事实完整性优先于完美盲法。工具语义、事实载荷中的合法同名字段或诊断路径仍可能透露路线；不通过扩充保护字段白名单、要求模型包装 facts、广泛关键字替换或路径替换制造匿名性。结构化值保持相等，文本及 JSON 字符串保持原字符/空白；外层 JSON 仍是重新编码的投影，不称原网络帧字节。

## 定向合成验证

同一固定测试脚本和同一 synthetic fixture 分别加载 SHA 绑定的旧版、修正版，结果如下。所有 fixture、伪槽位、惰性请求字符串及生成文件均标记 SYNTHETIC，并位于本修订测试目录，与正式六格及匿名映射分开。没有执行其中的代码或启动消费者。

| 版本 | 实际结果 |
| --- | --- |
| 9c85 原脚本 | 4 项中恰好 2 项预期语义 AssertionError，另外 2 项通过，0 errors；契约结果保持 false、进程退出 1 |
| 修正脚本 | 4/4 通过，0 failures、0 errors，进程退出 0 |

第一反例精确复现 `condition` 三条件、`profile` 通孔截面被删除。第二项直接调用真实 `handoff_one`，核 owner result/error 和公开工具事件两路径中的嵌套 JSON、JSON 字符串、原生输出、空白、路径及未知字段。另两项核原 final/code、失败/not_run、三次重复/缺响应尝试，以及已知 RPC/meta/worker/exception 删除位置和原 false/null/来源摘要。Import/File 等错误不会算有效旧失败，实际两版均为 0 errors。

原始 fixture、实际公开投影、每项移除记录、完整断言及日志在 `tests/baseline_01/`、`tests/revised_01/`。独立代理只读逐值核对这些生成结果，与上述结论一致。此有限验收不代表任意未来 CLI/schema、正式六格消费或完美匿名已通过。

## 绑定与不变量

- 原 packager：`34a0480c318408826404ea76197ac22bfe1083c977fd9a83959de3ac3e10fe33`。
- 修正 packager：`afa802bdb085ad9e174f04c4ba91ff05bdacdbc7b0bb892162a7b7e14d580cbc`。
- 定向测试：`c6861fa01a05e4c2e6a44655b11f9fe3e4c66da0c67fb7f18240e552f46bc6b3`。
- 新 PLAN：`376339732b468fd1eb2c6008f2b97141ffdd6c7902fc047adb3facce15cf4619`。

产品仍为 `107641ec` /137 源/canonical `7a3d108bc5658508d76d98fe24b8f3dee4feac2d50856202b2ea7395c3dc9cc1`。原资产、初图、共同 PROMPT、真值、评分、收益合同、匿名映射、六格顺序、预算和三个消费运行器原字节保持。PLAN 只改七个质量投影/修订绑定位置，明细见 `PLAN_DIFF.json`；没有改变正式试验条件。

新 FREEZE/INDEX 明确 supersede 旧冻结，原字节在归档中保留。管理员对旧 M1 的 549 条删除记录仅做过有限 `condition/profile` 追溯，本轮未重查或修改旧记录，也不泛称历史全部无影响。

自身 Agent Learning 仍未有 Hook 绑定，登记待宿主同步，未借用其他对话句柄。Google/key/API 和默认配置不变。完成固定修订包后交管理员定向复核，等待新 PLAN 摘要对应的六格正式 GO。
