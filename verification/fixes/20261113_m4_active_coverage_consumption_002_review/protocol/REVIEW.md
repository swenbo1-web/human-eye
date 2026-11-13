# 002 入口、协议和生命周期独立复核

固定作者提交：`c556d29156e7d65fc02238dca63321ac062d2c1a`。

结论：**通过现有记录的独立复核，未发现需要继续修改协议或生命周期入口的实际缺陷。** 自写离线解析器首次执行完成 **1187/1187** 项检查，零不一致。检查分母是原件与接线断言，不是独立场景或模型测试数。

## 本轮实际检查

| 项目 | 独立核验结果 |
| --- | --- |
| 新启动入口 | AST 确认正式 main 唯一调用 `driver.run_batch(plan, runtime)`；实际路径为新 002/r，使用独占创建的 FORMAL_STARTED 与运行目录。没有改为执行旧 main。 |
| 冻结范围 | 新 188 项完整包含旧 176 项路径/SHA，候选 consumer/driver/result_contract 三项一致；新 launcher/plan/fake、评分入口及真值、CLI/base 解释器在清单内。根另负责完整 188 文件实际哈希与 Git 身份，本子审计没有重复整套核验。 |
| 实际接线 | 正式及 N/P 本地前后 POINTERS 原件相同，各 13 个断言均为 true。候选路径明确，新 batch/route/consumer/archive/common 连通，原函数 code、旧 globals 指针、原 outer gate 保持。静态读新 launcher 与已验候选代码核实这些断言的含义；本轮没有导入或运行候选。 |
| 本地错误恢复 | N/P 各一次实际 actor `ValueError`，经过 TCP、stdio MCP 与 fake CLI 的 failed/error:null/相同 content 投影，candidate archive 记录 tool_error；第二次 `print(6 * 7)` 得到 `42\n`，记录 success。两路首次通过，无本地重试。 |
| 本地正常关闭 | 原 EXIT 的 PID/nonce 与 STARTED 一致，normal_exit=true；fixture 明确关闭输入、普通 EOF，thin wait exit0，kill_requested=false，持有句柄已关闭。两个本地会话共 4 工具、0 Pro/图片构造/光栅。 |
| 正式分母 | 原顺序 N1/P1/P2/N2/N3/P3，全部 completed，6 个互异新线程，没有 resume、not_run 或替代槽记录。 |
| 正式工具原件 | 14 条实际调用均 success、业务错误 0。逐项比对原 stdout item.completed、consumer 事件、stdio TX/RX、TCP 包、owner request/response、复制原件及 candidate 分类，名称/参数/ID/完整 content 和状态一致。 |
| 真实进程退出 | 六个 CLI 和六个 actor 均 exit0、原句柄确认回收；六个 STARTED 后绑定的 stdio runtime 经进程创建时间/父子链/实际解释器哈希定位，持有句柄确认 exit1 并关闭。 |
| EXIT/EOF 未知 | 正式六份 EXIT 文件均缺失，bridge_cleanup 为 unknown，不能说成正常 EOF 或退出原因已知。原 gate 一直允许回执未知，同时要求实际绑定和实际退出均被确认；002 没有改变该资格规则。 |
| 原期限 | 每槽 started+450s 与 actor config、endpoint、consumer turn/episode、held-runtime wait、两层 FINAL_TIMING 同一终点。实际退出、归档和发布结束均在原期限内。 |
| 归档完整性 | 8 个本地/正式会话的双层 16 ZIP、784 成员逐字节等于原路径，成员集合无重复、大小/SHA 与登记一致。 |

正式原 stdout 中没有顶层 error/turn.failed，每槽一个 turn.completed；consumer 未记录可见重连或工具偏离。此结论限可见 CLI 事件，不能推断 provider 内部请求次数。

## 接线和关闭语义

静态读旧 driver/consumer 可确认原绝对期限与终态规则未变。新 launcher 仅显式覆盖候选和入口来源；候选 driver 克隆旧 run_route/run_batch 的 code 并在私有 globals 中接入候选 consumer/common，consumer 同样仅接入候选 archive。正式与本地记录对应同一入口链。

本地错误恢复证据证明实际候选消费链能够接受如实传递的工具报错并继续完成。正式六会话本次没有触发业务错误，因此不能把它们计为额外六次“模型从错误恢复”测试。此前真实错误回放、这次两本地链和六正式成功会话各自保留分母。

正式 stdio exit1 的原因未测，EXIT/EOF 仍未知；实际终态已经由保留的 Windows 进程句柄证明。该区分在旧001就存在，002没有通过修改完成门掩盖异常。没有依据为这次有限验收继续增加一轮退出方式试验，后续若出现真实功能或资源故障再针对处理。

## 准备说明更正

`PREPARATION.json` 原错误说明“removed nonexistent batch count lookup”仍保留。旧 driver 的 run_batch 确实返回 actual_CLI_processes，源 SHA 与 `PREPARATION_NOTE_CORRECTION.json` 一致；新 RUN_RESULT 由六条 consumer PID 独立记录 6 个 CLI。新 launcher 删除的是复制到 LAUNCH_RESULT 的冗余字段，没有改变运行次数或丢弃执行记录。该更正属于文案纠错，不需要再修改已冻结源。

## 边界与下一步

本轮仅静态读源码、自写纯数据解析并读取归档，不执行作者 matcher/archive/consumer/driver、捕获 Python 字符串或作者矩阵。新增模型、CLI、actor、Blender、光栅均为 0，没有重新打开历史 OS 句柄，也不声称重新观察了历史进程。实际退出证据的独立核查是原记录之间一致性及生成代码语义核查。

完整 Git/磁盘/manifest 来源核验由根负责；六答案空间质量和收益复算由其它独立审计负责。本子审计不替代这两项，不单凭退出码批准空间结论。

建议：**本协议与生命周期缺口收口，不再扩防御矩阵。** 下一批应解决主动观察真正尚缺的能力范围，而不是重复本固定六视角题或为未知的正常 EOF 字段再刷一次模型分母。

自身 Agent Learning 子句柄已绑定当前固定 assignment，task_access=parent_read_only；未借用父句柄、未更新父任务。所有新文件仅在本 protocol 审计目录，没有修改作者、旧源码、Git 或实施对话。

原件读取清单与哈希见 `INPUTS.json`，1187 项明细与 8 会话摘要见 `RESULTS.json`，可复算脚本见 `audit_protocol.py`。
