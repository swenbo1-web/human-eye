# 显式消费 001：执行链与关键成本独立核查

本子审计核对固定作者交付 `8030a99b081e9e604fe87797c2daf74c2f6618f7` 的原始运行记录和源码。自写标准库离线审计 80/80 项通过，实际输入 80 份，每份摘要见 RESULTS.json；未执行作者审计器、产品、模型、Blender、raster 或 benchmark。一次纯 compile/marshal 见证没有执行编译产物。全量 Git、冻结及安装来源由根另行核验。

结论：作者披露的关键时间、额度及退出记录可复算；新增 launcher 使用 marshal 字节摘要判定运行身份稳定性存在明确缺陷。该末端缺陷发生在原消费失败已经返回之后，不是前面重算或缺少完整答案的原因。

## 两个失败按时间分开

第一段是任务未在给定工具额度内完成。原始 CLI 有 13 个 completed 工具事件，首个 active_observation、随后 12 个 execute_python。owner 第 13 次在执行 Python 之前拒绝，错误 `route_twelve_tool_call_limit`；12 次业务准入是本次最大执行量，不将被拒绝请求写成已执行。第 4 次工具的批量渲染保留 `six_actual_raster_attempt_limit`，第 11 次保留 `KeyError: (5, 'BACK')`。六份 durable intent 和实际 trace 为产品 SCENE/BACK/LEFT 三帧、原生 SCENE/TOP/LEFT 三帧，全部 6 次完成；第七次构造未获准。

继承 consumer 收到第 13 个 completed 事件后主动抛出同一工具限额错误，进入 finally 清理。`PUBLIC_FINAL.txt` 写入在正常事件循环结束之后，因此这条异常路径没有发布它。原始事件只有四条 agent_message 进度文字，没有 turn.completed、turn.failed 或 usage。CONSUMER 的 `final` 和 route 的 `answer_present=true` 只保存最后一条进度，不能据此说正式答案存在。完整消费失败正确；不能把缺最终答另说成已证明的 provider 自行崩溃。

第二段是 launcher 收尾缺陷。源码顺序和现存产物相符：route 返回失败 → 保存 RUN_RESULT → 再核源文件 → 保存 ENTRY_PROOF_AFTER → 比较整个前后 proof → 因摘要变化抛异常。原 launcher exit1、LAUNCH_RESULT/LAUNCH_TIMING 缺失均保留。该异常不能反向解释前面模型为何重算，也没有使原有 route/consumer 的真实终态消失。

## marshal 判据的独立反例

实际 ENTRY_PROOF 的差异仅有三项：accepted_route.code_sha256、single_route.code_sha256、old_connect.code_sha256。其余路径、模块、限定名及记录字段一致。17 项布尔检查均 true，其中只有 9 项在本次 pointer_proof 中重新计算，8 项是旧 connect 的快照，不能统称 17 项新鲜检查。

自写见证在当前 Python 3.12.14 中仅 compile 一小段函数定义，然后保留 `code.co_consts` 引用，前后不调用或 exec 编译结果。保持同一 code 对象、相同 co_code，marshal 字节仍变化；两份 marshal 解码后的 code 对象相等。原始 marshal 摘要因此不适合作为同一进程内代码未变的稳定判据。RESULTS.json 保存前后摘要、字节差位置及 Python 版本。

这个反例证明判据能误报，不证明原进程的三个变化一定由同一种引用变化造成。原进程未保留原 marshal 字节或稳定 co_code 快照，精确内部变化仍未知；现有源码和实际指针证据未显示执行代码替换。不能用一个不稳定序列化摘要直接推断来源被篡改。

## 时界与真实终态

|范围|独立复算秒数|
|---|---:|
|父进程调用至返回|239.3891515|
|route 启动至结果关闭|236.7672871|
|consumer 启动至记录关闭|235.2134068|
|提交 prompt 至 CLI 收到产品结果|17.3692427|
|产品结果收到至 CLI 退出观测|216.8612707|
|首个产品工具服务|4.4010909|
|其余 12 请求服务累计|2.9078431|

上述时界从原始 perf_counter_ns 重新计算。父/route/consumer 是嵌套范围，不相加；整个父周期在原 450 秒绝对期限之内，期限未延长。工具外时间包含模型服务、传输与本机处理，不能全称纯推理。

当前 CLI 实际收到三张 PNG，共 8,819 B，与 owner 构造及发出记录一致。后续三帧原生构造仍计入六次预算，批量请求失败不退还额度。一次实际捕获重放、零实际 Blender 采集。

actor 持有进程退出0，CLI退出1，thin 持有只读句柄确认退出0，相关持有句柄关闭可证。正常 thin EXIT 回执缺失、EOF 为 unknown。后置 stop_process 的 kill_requested=false 仅反映该调用自身：consumer 的更早 finally 还可能直接 process.kill，那里没有单独回执，不能宣称从未请求终止。未发现动作重试；本批无用户资产写操作。

usage null 与原始事件无 usage 一致，input/output/cached/image tokens、现金费、provider 实际请求数继续未测。元数据刷新超时和 fallback model metadata 警告存在，当前没有证据将它们判为消费失败的确定原因。

## 下一启动器的最小处理

不要为此增加新的代码序列化层。保留已有源字节绑定，使用已持有的函数与 code 对象引用检查实际调用指针；删除 marshal 摘要必须前后相等这一错误要求，或将其仅作为不参与通过判定的诊断字段。继承的旧快照明确标注为旧快照。

结果发布应保留先前 route 的完成/失败及所有执行状态，在 finally 发布末端状态与时间；尾部检查异常独立记录，不能吞掉主体结果、把已完成动作当未执行或自动重跑。只需一个无模型、无图的离线最小状态发布检查验证成功/失败都能收口，既有六槽和渲染矩阵无需重跑。

本次工具及 raster 限额按约束起作用。修正 launcher 误报不会自动解决模型重复计算及证据整合，消费改进仍须以真实产品事实被使用为验收。
