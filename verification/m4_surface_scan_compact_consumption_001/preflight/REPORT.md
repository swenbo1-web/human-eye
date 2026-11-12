# 九格三路消费的离线准备

准备复用已接受的六格 bootstrap、plan、freeze 和匿名原件核验代码。适配三组安装选择与固定九格，在新模块内保存原脚本 `.before`、逐文件 diff 和来源摘要。本子任务新增 Blender、产品服务、模型消费者和推理 API 运行均为 0，安装重建为 0。

## 固定安装与输入

O 使用旧扫描 OPT1 `c1cb2da32034e056a270384e691a2cde8dddbc0d`，138 源摘要为 `c4832b1a1ced9438f904e25a431e2327c2d7532e2f4efbb34e34ce58a7ed1943`。C 使用紧凑候选 `452b44d2dcf231d6675bef54e568db0431a29261`，138 源摘要为 `4067c864c3db1ba586cd7179e6430db5acc4d71675b5295416d471632851a9f6`。两组分别核 Git、固定构建 manifest、wheel、隔离安装、入口和绑定文件，当前源码另与 C 一致。

两份完整普通 observe 声明分别来自已有实际 `tools/list` 回执，并核对各自交付 Git 字节。共同原生声明沿原 literal schema。N 只暴露原生，O/C 各暴露同一原生及各自完整 observe 声明。两组 schema 和默认说明保留版本自身内容。

BASE、快照和精确真值沿原资格提交及原 SHA，题面逐字复制前轮 `PROMPT.txt`，SHA256 为 `6a78e38a474647c0c0c49558be215864cb672932273b3e15ca6ba7f9fa02b4fc`。九格顺序固定为 N1/O1/C1、O2/C2/N2、C3/N3/O3。匿名 ID 由随机源在消费者启动前生成，私有映射 SHA 进入准备合同。

实际 CLI executable 的 SHA 与旧六格 PLAN 相同。原本地 `--help` 和 `--version` 捕获按原 Git 字节复用，并在 `CLI_REUSE.json` 明确来源，本子任务新 CLI 进程为 0。共同模型及隔离设置由原函数保持，运行时解析的模型版本仍按真实可见证据记录。

## Plan 和验收边界

`installations` 有 O/C 两项，N 使用 O 的共同依赖 Python 并保持原生 actor。内部 actor/transport 沿 N/P，外部标签通过 `external_group` 绑定 N/O/C。产品源与提交在 PLAN 中按 profile 分别记录。

准备保留消费者 450 秒、整格 570 秒、actor 40 秒、32 工具尝试、128 非 close 宿主请求、单工具 30 秒、累计返回 1 MiB 和代码 256 KiB。两项安装共用同一依赖解释器。dispatch 绑定全部 runtime/scoring Python、题面、源与 schema，external 输入另绑定实际安装源码及入口。正式冻结由根执行 `runtime/freeze_plan.py`。

根已完成冻结，PLAN 的 SHA256 为 `e12e20c08e5801e317c847f14a9eb953179c1f8a7fabc5b4b78e24a860d80322`，FREEZE 与 GO 均记录该 PLAN 摘要。冻结后再次逐项核对 dispatch 和 external 文件摘要通过，本子任务随后停止写入。

质量负责人最后补入两个离线评分反例后，`score_answer.py` 与 `test_compact_contract.py` 晚于第一次 prepare 发生变化。冻结前保留原 PLAN 到 `PLAN_PREPARED_01.json`，刷新这两项 dispatch 摘要，更新记录存 `PLAN_REBIND.json`。产品、预算、题面、顺序与匿名映射保持原准备值。

原生收益和旧展示对照门分别写入 `BENEFIT_CONTRACT.json`。质量先封存，成本后解封。根已登记的空结果离线表示增加 697 B 边界作为已知事项保留。

## 离线检查

8 个准备方法和 3 个 post-run 核验器 fixture 方法通过。测试覆盖资格 SHA、无答案泄漏题面、两份真实完整 schema、九格顺序/轮次/随机映射、两安装归属、同一 CLI、隔离设置，以及新旧业务值和错误字段的无损投影。

新 `verify_handoff.py` 采用九格、两 profile 核验，保留全部原 final、原 ZIP、业务请求响应、缺失和 unknown，输出执行与证据计数。它不执行答案评分。其 main 在本次准备阶段没有运行，正式原件存在后由根指示调用。

源码、原日志、初次 PLAN 与更新记录均保留。当前 Agent Learning 未绑定，host epoch 为 5，需要宿主重连，未借用其他聊天句柄。准备工作按现有授权完成，任务同步状态保持真实范围。
