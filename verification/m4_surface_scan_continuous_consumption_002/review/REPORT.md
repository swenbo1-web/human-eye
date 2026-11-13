# 连续消费002的变更入口审查

本审查针对根提交 `79ed3bff7c87d4ac68e2b2bf382de05d41b731c6` 派发的 `M4-SURFACE-SCAN-CONTINUOUS-CONSUMPTION-002`。新计划 SHA256 为 `43d19c8c94c4b4ec66ea5589f7ea64c21686501dab4dcfdc2d35d38a3c13a726`，继承的001计划为 `95a334c39672a72ac771beba0f02e6c17735771a5e0f8411203d46e2769feba5`。

## 实际 wrapper 与归档

实际 `COORDINATOR` 指向已经独立审核的 interface-fix wrapper。三份固定 episode、transport、compatibility 文件的 SHA256 与新计划一致。coordinator 的函数全局 transport、consumer 的函数全局 archive_turn 均指向已审的新接线，原 consumer 与 coordinator 函数仍复用 FIX1。

该 wrapper 确实没有 pack 字段。002 的完整 `run_one` 已显式使用 `coordinator.legacy.pack.capture_cell`，其函数来源为原同字节 packer。输入检查、启动、每轮原期限、sole finish、postclose、共享绑定核查、outer ZIP、manifest 以及结果写入关闭继续处于同一590秒原绝对时界。每轮450秒仍由原 coordinator 截到它。

runtime 使用全新 `.m4cc2/<cell>`，没有复用 `.m4cc1`。六个匿名 episode ID 与001不重叠，正式输入题面、预算及 N/C 工具设置沿冻结合同。driver 的准备验证动态使用当前002目录及其相对路径，固定源码摘要纳入已审 wrapper、compatibility 和 stop 条件。

## 具体 attempt 的停批接线

新增核查只提取 consumer 原 `business_original_binding` 中明确的请求或结果不一致项。它使用 `BUSINESS_SOURCE_BINDING.json` 的实际尝试顺序定位对应 CLI 完成事件，再读取同 attempt 的原 owner response，并验证 consumer 归档拷贝与 owner 字节一致。

固定窄谓词要求 owner 无 RPC error、明确 `isError=false`，CLI 明确 completed 且 error 键为 null，并存在两端正文。满足后才向现有 stop_reasons 加入 shared_success_binding_fault。sole finish 和原件收口先完成，现有 run_batch 随后保留已运行结果，将余下固定 episode 置为 not_run 并退出。普通工具错误和正文答错沿原合同处理。

现有 provider 不可用、生命周期未确认、执行不明等停止逻辑继续保留。原 exact 回执匹配及同表示工具错误处理未被新分支改写。旧001的执行策略和成本原件保持独立。

## 定向离线验证

`check_contract.py` 的三十三项文件、AST、纯导入及离线归档检查全部通过。已有14成功、3真实错误和四场景进程回放作为已审来源复用，本审查没有重跑该矩阵。最终检查与源码摘要见 `CHECK.json`。

已逐段审查 `runtime/test_wiring.py` 并核验 `runtime/offline/a01/RESULT.json`，三项必要接线测试通过。

- 完整 run_one 测试实际加载固定 wrapper，明确断言其没有 pack。它只替换 Popen 与 owner RPC，原 consumer 读取循环、原 coordinator、finish、postclose、legacy.pack、归档与发布均实际执行。三次 CLI 启动由内存进程替身返回合成事件，sole finish 信号为一次。该替身没有业务工具调用，接口正文语义继续复用已审原件回放证据。
- 独立读取实际 outer ZIP，逐项重算八十一成员的字节数和 SHA256，与 manifest 完全一致，并核对 CLOSE、SOURCE_GUARD_AFTER、ACTUAL_WIRING 及 consumer episode 原件。结果与 authoritative timing 文件均已发布，postclose 及完整时界通过。
- 两项调度测试调用真实 run_batch，run_one 替身提供具体 attempt 原件和已收尾记录。双端明确成功但正文不同的绑定故障只运行 N1，保留一 failed、十七 not_run 后停止。owner true／CLI failed 的普通工具错误走完六个既定集，保留六 failed、十二 not_run，无该停批原因。实际唯一收尾调用另由完整 run_one 测试证明。

`publish` 与 `run_batch` 的 AST 继续同001一致，新增分支通过既有 stop_reasons 与固定余槽逻辑接入。上述合成成绩只说明新增入口、归档、发布及调度接线符合合同。

## 实际证据边界

准备审查没有调用模型、provider、Blender、产品或 Git。合成依赖替身不构成实际模型 resume 证据。正式后只有本批白名单 UUID 的必要数值计量可用于 usage scope 检查，成本在独立质量封存前保持封闭。无可证 scope 时继续保留 unknown 与 aggregation null。

本目录的文件在 root 准备冻结后保持固定。正式后新增的必要数值范围证据单独写入 `review/actual_usage`。
