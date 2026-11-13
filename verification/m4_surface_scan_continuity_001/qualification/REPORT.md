# 连续观察工程资格的离线核验器

2026-11-13。本目录提供新工程 episode 的事实核验接口。当前结果来自既有工程原件回放和合成合同测试，新增 Blender、产品进程、模型消费者及推理 API 调用均为零。

## 固定输入与复用范围

原资格提交为 `96fce78b98cb749885792112e039a406744d282b`。按原 qualification_binding 核对已提交 QUALIFICATION_READY、SOURCE_OUTPUT_MANIFEST 及九份承诺文件，全部一致。20 份实际读取的来源文件、字节数和 SHA256 保存在 SOURCE_BINDINGS.json。

BASE/EDIT 真值分别固定为 `a0f14b1a48601590445ce5e2d13bb34f56647caa2acedf3eeac97b32e8a656c7` 和 `ccbc66e4071dd3fc8f7fc4c7195e29a6a5a58db39fa1e0a86457b2a8929b1e91`。原场景 SHA 为 `7f6452d1d706a9f2db31126eb3aa7d08622e37a28abb9610992006bad5f5ad66`。候选产品固定 `452b44d2dcf231d6675bef54e568db0431a29261`，138 源摘要为 `4067c864c3db1ba586cd7179e6430db5acc4d71675b5295416d471632851a9f6`。

核验复用 compact_facts_001/engineering/run_candidate.py 中既有独立事实验证函数及紧凑表解码，文件 SHA 固定为 `7e7c75172190681ea138465c9bc3a777a953d9ae0d91c7bb51f2cb164e3321cc`。验证器读取完整 276 对 disposition，对照原独立有理真值检查阈值成员、已排除下界、已测距离，再逐行核对对象 ID/name、原始米值位模式和毫米派生值。它未导入被测产品作为答案，也未重新执行几何求解矩阵。

## 实际工程记录的调用接口

`verify_c_turn(result, audit_rows, host_events, source_snapshot, turn, request)` 接受 BASE、REPEAT 或 EDIT。request 可以是普通 tools/call JSONRPC 或对应 params。它要求 ordinary surface_scan、2 毫米阈值、缺省 response_detail、无图片请求，并保留实际 session_id。

私有 audit 按 result.trace_id 精确连接唯一 observe 和 request_trace，核同一 runtime PID。host_events 应由 runner 使用该次业务实际开始、结束时刻筛选，只含本次业务的 worker 事件。验证器要求唯一完成的宿主捕获、终态几何及文件保护、零新图片、零渲染和唯一已完成 host.capture span。初末 QA 应单独计量。

完整 actual snapshot 与固定 BASE/EDIT snapshot 对照后，验证器分别要求匹配 71/71/72、新 kernel 112/0/10。返回报告保留完整 binding、实际 trace/session/PID、acquisition_work 和前后测量缓存摘要。

`verify_c_sequence(reports)` 接受上述三份核验报告，检查轮次、同 session/runtime、三个独立 trace、BASE 与 REPEAT binding 相同、EDIT binding 失效，以及两次薄客户端边界前后的缓存 entry 数量。owner、Blender、产品 PID 的实际持续性和薄客户端启停由 runner 的生命周期记录另外核验。

`verify_n_sequence(rows)` 接受三份原生 marker 调用的解析 stdout。固定 marker_token 为 continuity-engineering-N-001、generation 为 1。三个包必须保留同一 PID、namespace_id、24 个对象的 session_uid、单位和当前矩阵。所有矩阵直接对照固定 BASE/BASE/EDIT snapshot。

登记的十进制 Z 位移为 −0.00075 米。Blender 对应冻结 EDIT 矩阵中的实际值为 −0.000750000006519258 米，验证按该原值逐项对照。BASE 与 REPEAT 包相等，EDIT 仅有登记姿态变化。N 标记核验覆盖工程 namespace 保留和当前姿态读取，模型记忆与任务解算器仍需各自证据。

## 离线检查

首次九个测试方法通过。增加原始数值和 actual snapshot 篡改反例后，第二次十个测试方法通过，两个阶段均为零 failure、零 error，记录分别为 OFFLINE_CHECK_01 和 OFFLINE_CHECK_02。

正例读取原五观察工程中的真实 BASE default 和 EDIT default 回执。REPEAT 单元 fixture 使用历史 brief 的同状态事实，并合成缺省请求，专门检查验证接口。N marker 包由冻结姿态合成。这些 fixtures 仅验证离线合同，真实薄客户端跨轮和新的 112/0/10 连续运行待工程 runner 记录。

反例覆盖错误工具、显式 brief、图片、阈值、session 缺失、重复 audit、捕获数量、宿主失败与保护状态、渲染、trace、kernel、改动后的 binding、原始距离、完整实际几何、marker、namespace/PID、单位、对象身份和 stale EDIT 姿态。验证器自身未出现运行失败。

## 已测与未测

本目录已验证固定来源的字节、既有数值事实及新核验器的合成接受和拒绝条件。新的两个工程 episode、六次业务调用、原绝对期限、实际 owner/thin-client 生命周期和完整成本均由 runner 输出。本目录没有生成新模型收益结论。

真正模型线程续接、真实模型上下文保留、逐轮 provider usage 的累积定义、弃流 token 覆盖和现金费用尚未实测。Agent Learning 仍为 context_bound=false、host_epoch=5，未借用其他聊天句柄。

以下命令只读取旧原件并在本目录新增离线核验日志。

```powershell
& 'D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe' -I -B -X utf8 verification/m4_surface_scan_continuity_001/qualification/test_verify_continuity.py
```
