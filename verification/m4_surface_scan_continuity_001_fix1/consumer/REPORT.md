# FIX1 消费循环与三轮协调接线

2026-11-13。实际 consume_turn 事件及进程循环已接入固定三轮 run_episode。零 provider 的本地子进程贯通首轮持久化、明确 UUID 续接、共享工作目录、同一 endpoint、原期限、CLI 与薄客户端清理、业务原件及三轮匿名信封。新增 Blender、模型消费者和推理 API 调用均为零。

## 实际调用路径

episode.py 的 run_episode 接收同一 episode 的 cell、install、plan、共同题面、共享 work、绝对 episode 期限与每轮预算，以及外层既有 control、finish 回调。它调用新 runtime/consumer_transport.py 的实际 consume_turn，端点及后台 identity 在轮次前后核对。BASE、REPEAT 完成后才由外层执行一次 qa_advance，EDIT 题面保持共同文本。每轮只结束 CLI 与 attached thin client，finally 统一调用一次外层 finish。

fake_cli.py 是本地 Python 子进程，实际读取 loop 生成的 exec/resume argv、MCP 配置和 stdin。首轮在共享目录写合成上下文标记，续轮要求显式同一 UUID，读取原标记。它从同一 MCP 配置启动固定原字节 stdio_attach.py，与 fake_owner.py 的本机 socket broker 交换真实 initialize、notification、tools/list 和业务消息。这个 broker 仅为测试替身，未启动 Blender 或产品服务。

正常 N、C 各三轮均经过完整 loop/coordinator。N 暴露原生工具，C 对应内部 P 并增加普通 observe。三个独立 CLI PID、三个独立薄客户端启停、共享 cwd、同 endpoint 和显式 UUID 均由原始记录验证。合成姿态只在 REPEAT 后变更一次，下一轮业务可以读到变化。

该接口接收已经准备好的 owner。consumer 的 full_episode_wall_ns 从进入消费协调开始，覆盖轮次、最终 finish、归档及 EPISODE_RESULT 写入关闭，FINAL_TIMING 发布另列。owner 启动位于外层更早的原绝对 episode 预算内。正式完整 episode 账本须由外层在后台启动前开始计时，并覆盖本接口及最终清理和发布。

## 原件和匿名归档

consume_turn 将实际 CLI completed MCP 事件与 owner 新增 tool_XX 的 REQUEST、RESPONSE 和 ATTEMPT 核对，按轮复制原件，保留原始事件及薄客户端 TX/RX/EXIT，再生成每轮 raw ZIP。

协调入口复用旧 pack_quality 的 request_projection、without_rpc_envelope 和 capture_cell。三轮质量信封与实际 consumer/owner 原件 ZIP、PRIVATE_BINDING 的逐文件 SHA 相连，公开工具事件与 owner 回执分别保留。业务字符串中的 group、id 和 perf_ns 数据经测试完整保留，缺失证据保留缺失状态。答案内容继续 unscored。

## 零模型端到端结果

attempt_03 的完整十方法全部通过。随后把归档目录创建也纳入同一终态保护，attempt_04 仅运行两个归档异常定向方法，两个均通过。两阶段覆盖十一项不同方法，其中一个归档方法重叠。保存全部原始测试日志及各 case 的 EPISODE_RESULT、FINAL_TIMING、原件归档和匿名输出。

- N、C 正常三轮，工作标记、明确续接、原始 usage、业务归档和一次最终 finish。
- 重连错误后 final 和 exit0 仍保留 failed，EDIT 为 not_run。
- 缺 final、错误线程 UUID、非零退出、非 JSON stdout 分别保留原错误与后续未运行。
- 真实绝对期限触发本地 CLI 回收并停止后续轮次。
- provider 开关关闭时不启动消费者。
- 消费循环已成功完成后，注入最终原件打包失败或质量目录创建失败，仍只 finish 一次，保存原三轮 completed 分母、episode 失败及完整终态计时。

归档失败会标 archive_status=failed，并记录具体错误。已经完成的轮次保持真实完成状态，整体 qualified_execution=false。失败回执自身无法写入时，错误仍进入 EPISODE_RESULT。

## 准备错误与纠正

attempt_01 在任何 case 启动前，将输出目录属性命名为 run，覆盖了 unittest.TestCase.run，触发 WindowsPath 不可调用错误。现改为 run_directory，原失败单独保留。

attempt_02 使用完整方法名作为案例目录，原薄客户端的嵌套路径超过本机路径边界，导致首轮 fake CLI 的 stdio_attach 无法创建目录。十方法中九个失败，一个 provider 关闭用例通过。案例目录改用六位哈希，CASE.json 保留完整方法名，原薄客户端文件保持固定。最终最深薄客户端 RX 路径为 239 字符。原失败输出和已关闭替身记录均保留。

本轮准备错误只发生于本地测试替身。SOURCE_BINDINGS.json 保存最终源码摘要、消费循环摘要和四个离线阶段记录。没有改写旧冻结材料、actor、worker、stdio_attach 或被测产品。

## 未测边界

本地线程文件和 usage 事件属于合成 fixture。实际模型 thread 历史保持、真实模型记忆、provider 的逐轮 usage 是本轮量还是累计量、弃流计量覆盖和费用尚未实测。raw usage 原样保留，usage_aggregation 为 null。

该接线已具备真实 consume 循环入口，provider 启动仍由冻结计划中的 model_consumer_enabled 控制，准备阶段保持关闭。正式 episode 数量、顺序、期限和收益门等待管理员另冻。工程资格由根另行运行唯一 C 三轮，其证据与本目录合成 E2E 分列。
