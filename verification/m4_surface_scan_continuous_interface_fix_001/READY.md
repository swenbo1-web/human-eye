# 连续消费接口兼容修复交付

本批为 M4-SURFACE-SCAN-CONTINUOUS-INTERFACE-FIX-001。执行依据为管理员提交 cb64613c358b506690a879c7a2105fcd6b770a3f 中的冻结计划及质量 seal，准备提交为 1adbf71062f5821dbd6b15c9138c58bc05355a45。

## 最小实现

新增 compatibility.py 校验已记录的成功包装。owner 必须明确 isError=false，CLI 必须明确 completed、error=null，业务 content 按完整 JSON 值、类型、文本和顺序对应。新增分支支持 CLI 省略 false 错误位并加入 structured_content=null。content 中的同名字段和 JSON 字符串按原值保留。

archive_turn 仅在旧整表示比较不等时调用新成功判据。原 exact 分支、工具错误状态及后续处理沿既有消费链传递。同表示工具错误的控制回放确认旧绑定行为保留，新成功判据返回 false。最小函数 diff 见 integration/ARCHIVE_TURN_DIFF.txt。

新 runtime 直接复用原 consume_turn 和三轮 coordinator，通过函数全局绑定接入新 archive_turn。进程循环使用复现真实 CLI 转换的本地 fixture。

## 验收结果

| 范围 | 结果 |
| --- | --- |
| 14 份真实成功 | 旧绑定全部复现失败，新绑定全部通过 |
| 3 份同冻结 CLI 的历史真实工具错误 | 继续保留原失败语义 |
| 定向变体 | 25 个，覆盖参数、正文、缺失、类型、RPC 和结构数据边界 |
| 原件回放检查 | 381 项通过 |
| 纯函数与 AST 接线复查 | 52 项通过 |
| 定稿本地进程循环 | 4 个场景通过，共 12 个 fixture 槽位 |
| fixture 预期执行状态 | 10 completed、1 failed、1 not_run |
| 新模型、provider、Blender、产品调用及正式样本 | 均为 0 |

两种成功工具配置均连续完成三个本地 fixture 回合。真实错误形状在第二轮保留失败，第三轮未运行。同表示错误控制验证了既有后续处理。该接线证据使用本地 Python 进程和 socket fixture。

准备期共四次本地进程测试尝试，合计 44 个 fake CLI 与 44 个 thin-client Python 进程。a03 在测试通过后因 Windows 路径前缀重复而归档退出失败，修正后的 a04 完整退出成功。各次原始结果、失败回执、源码摘要及归档均保留。

准备提交后，根核对 44 份准备材料、520 个外部来源、5 份完整 ZIP 的 2400 个成员及本地原件，全部一致。ROOT_VERIFICATION.json 保留复查结果。深层回放目录继续在本地保留，Git 跟踪完整 ZIP、成员清单和浅层结果。

## 历史失败成本

accounting/LEDGER.json 和 REPORT.md 整理旧001六个首轮的完整 outer 时界、consumer 时界、十四次工具尝试、响应字节与原始 usage。十二个未运行槽位保留未测，费用及完整共享准备、协调、打包开销保持 unknown。

管理员已封存旧批六份首轮回答完整正确、依据充分的结论。旧执行状态仍为 6 failed、12 not_run，真实 resume 为 0。旧交付的 145 个文件及复用来源经摘要核对保留。

## 后续验收边界

真实模型 resume、REPEAT/EDIT 消费及连续收益等待新的正式批验证。旧批六份 thin EXIT 回执及续接 usage 语义继续为 unknown，usage aggregation 保持 null。新增成功兼容覆盖本批两种明确包装，其他结构返回不兼容并保留原件。

下一正式批的共享 harness 故障停止建议见 review/STOP_CASES.json，条件限定为双方明确成功仍出现请求或结果绑定故障。该候选等待管理员在新正式合同中冻结。

Agent Learning 当前上下文未绑定，任务状态未同步。本批完成后交管理员独立复核。
