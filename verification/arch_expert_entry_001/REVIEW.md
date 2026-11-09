# 专家入口独立审查

固定产品 `c5116e30024ed12825aea6119c0f5172e6b9b46d` 和 actual_run_02 原始证据审计通过，未发现待修产品阻断。主审为 `/root/expert_entry_review`，M5 原始数据子审为其 `m5_raw_audit`。两者仅使用 Git、文件读取和 stdlib 数据解析；未写文件、导入或执行产品及测试、启动 Blender、发送 RPC、查询实时 PID 或杀进程。进程结束结论依据 QA 清理查询和退出原件。

## 产品与来源

审查覆盖 8 份产品文件（含 worker mirror）、接受的来源及四个依赖、原 SourceGuard、QA 四份执行脚本快照和六轮 CPU 结果/日志/测试快照。此前发现的唯一产品缺陷是普通 Python 相等比较使等值 float/bool 暖 selection 绕过来源层整数检查。固定产品采用递归精确类型比较，新增回归覆盖 vertex_indices/sections 中的 float/bool、拒绝前 capture 为 0、旧 bound/prepared 保留及合法查询恢复。

逐一核对 136 个当前磁盘来源与 136 个固定 Git blob，独立重算 canonical SHA256 为 `239cc00a3cf09e9c18874cf0071e811e3244695c93590f806048fab97129b3b9`，与运行前后 identity 一致。owned/owned_task 的实际默认 worker 表达式包含相同 136 manifest、loader pin 和最终 guard.exec_path，无 worker_path override。shared 的 10 个真实 socket execute_code 逐 AST 解包，3 个 ordinary、7 个 expert；首包的 host、residency 和四个专家依赖冻结载荷解压 SHA 全符 manifest，后 9 包不重带来源。

私有别名仍经既有 `_exec_source_snapshot` 和 `SourceGuard.exec_path(expected_blob)`，执行见证以真实来源路径为依据。未新增 loader、finder 或 namespace 白名单。以 8,192 个十位 native ID、128 截面及最长 Unicode 名称构造 selection，stdlib 尺寸核算约为 owned MCP 199,533 B、shared inner 199,026 B、outer 208,320 B；首包六份冻结 b64 字符串合计 77,992 B，处于现有通道上限内。该构造尺寸核算不是实际最大 selection 的 Blender 执行，也不意味着无界整数均可放入通道。

## 专家原始结果和返回链

实际专家数据 1,779 个 ck 谓词和返回链 244 个 ck 谓词均通过。每次 ck 调用计一项，数组聚合谓词也算一项；合计 2,023 项是只读数据审计谓词，不能计入产品测试分母或视作去重功能数。

14 个成功报告各含 25 个区域，350 个严重度与直接 native RNA → raw packet → 同一默认模型 oracle 完全相同，最大绝对差为 0；截面号、原始顶点 ID 和 flag 一致。各 packet 均有 1,602 选中顶点、3,200 三角形、25×64 截面点和 2 骨，权重域/归一化及局部索引合法。独立 Gauss-Jordan 矩阵逆及 LBS 重算 22,428 个当前点，最大坐标绝对误差 `1.1277573164e-7 m`，与来源披露在 `1e-12 m` 内一致。pose 改变 current/骨矩阵而 rest 不变，static 改变 rest，load 恢复 initial packet 并进入 epoch 2，recovered 恢复 static packet。每个进程 oracle 的默认模型 identity 唯一。这验证同一模型的来源及接线一致性，不是模型预测准确性的独立评价。

25 条 stdio 请求/响应的 ID、参数、逐行字节、isError、报告均与 RESULTS 一致；16 次专家 bridge selection 及成功的 worker/event/service 返回链一致，service 只追加来源摘要及 trace。两个域外原始错误均为 `ArmTwistSourceError: unsupported_modifier_use_deform_preserve_volume`。25 次读取前后 ledger SHA 不变，最终 3 份账本仍为原始 65 B opaque 文本；工具 profile 中 `_locked`、`_runtime`、`_save`、`_atomic_write` 均未进入。

实际最终分母为 3 次 observed task、6 次 complete nearest、14 次 estimated、2 次预期错误。首轮另有 2 次工具尝试：1 次 task 成功、1 次 nearest 域拒绝；0 次专家和 apply，失败由 stdio raw、metrics 和 traceback 证明。首轮没有 tool_attempts 文件。

累计工作为 captures 14、static_reads 11、preparations 7、rest_vertices 17,622、weight_rows 17,622、current_vertices 22,428、rest_bones 22、pose_bones 28、topology_reads 11。capture/analyze/_inspect 方法入口各为 16（含 2 次拒绝），MLP predict_prepared/_report 各 14，产品冷 get_default_expert 调用为 3。三次 repeat 无静态读取和 prepare；pose/recovered 各静态核验一次，prepare 为 0 且 prepared 保持；首次 3 次、static 2 次、load 2 次各 prepare 一次。

产品 profiler 在直接 oracle 前暂停，product_method_ms 在 oracle 前截取；完整 RTT 仍含 oracle，控制另计，inclusive 时间不能相加。25 工具 stdio TX/RX 为 314,427/205,041 B；全部 46 条 stdio 消息含 initialize/list/control 等为 316,216/289,329 B。owned 测量工具 bridge TX/RX 为 136,803/92,641 B，全生命周期为 137,370/111,516 B；shared 测量及全部连接均为 228,123/96,819 B；owned_task 测量为 39,608/38,849 B，全生命周期为 39,935/49,190 B。实际 selection 为 19,374 B，跨过旧小上限。三个 fixture 副本与 original SHA 一致，四份 QA 执行快照与当前脚本字节一致。

## CPU 分母和 M5

独立汇总六份 CPU 机器结果为 521 次执行：517 通过、3 失败、1 错误、0 跳过，最终 165/165 通过。早期夹具/目录错误保留。affected_02 的原执行测试字节缺失，只能使用已标记的 RECONSTRUCTED 文件，不视为原字节见证。

M5 子审另有 862 个 stdlib 谓词通过，其中 535 项来源/guard/raw、327 项 native/postfacts；同样不加入产品测试分母。三个 worker 的 136 来源与默认表达式一致，83 对 TX/RX 帧和 host 记录匹配。0/1/4 次 apply、原生 translation assignment、confirmed/newsetter 相等，未 assign_matrix。loop RPC 为 15/19/28，whole 为 22/26/35，额外 task/nearest/task 共 9 次单独计算。

M5 原生 gap 分别为 `0.0040000006556510925`、`0.0035000070929527283`、`0.0010000094771385193 m`，目标误差最大约 `9.48e-9 m`。BluePart 仅沿 Z 移动，另三个对象及其顶点、面、颜色不变；9 次后读及 ledger SHA 一致，fixture 字节不改，save 8/9/15 已 committed。三组 shutdown closed、Blender quit、返回码 0 一致。

## 覆盖边界和审计修正

unknown 本次 CPU 与实际均未单独动态覆盖，仅从静态实现确认正常报告语义。ordinary 正例处于移除 Armature 的合法静态域，控制随后 relink 原对象。实际 loaded 名单没有单列 rig_pose；四依赖的逐模块编译复用证明来自 CPU 和接线/冻结载荷审查，不能声称实际 profiler 测得四次 compile。BMesh 保留全 mesh 的 C 层工作，不能据局部行数推出 O(selected) 或完整原生收益。

shared 受控 terminate 返回码 1；owned/owned_task stdio 和 M5 返回码 0。cleanup 原件明确 PID 37792 已由无关 VSSVC.exe 复用，没有将所有数值 PID 消失作为结论。

审计探索脚本曾错误假定 shared 控制事件在 Blender observer 中、首轮存在 attempt 文件、原始 float32 矩阵可用正交转置求逆，以及把真实 M5 对象 Far00 误当成 Far02。修正这些只读审计假设后，上述最终谓词通过。这些是审计脚本错误，不计作产品或 QA 失败。父代理首次交互汇总也因 ordinary 事件无 work_delta 而出现 KeyError，未写出结果；正式 `summarize_results.py` 使用可缺省字段并成功生成汇总。

总报告中的 unknown 覆盖、首轮失败日志、oracle pose 比较及 PID 复用措辞已按证据修正。交付前另以 226 个 ck 谓词核对 REPORT、RESULTS、ACTUAL_QA_REPORT、ACTUAL_COSTS、PROCESS_CLEANUP，逐次成本表、CPU 原件分母、opaque 账本、cleanup 副本和限制均一致。上述 226 项也是只读数据核对，不加入 521 次产品测试分母。
