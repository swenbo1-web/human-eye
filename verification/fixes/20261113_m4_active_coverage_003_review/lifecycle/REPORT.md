# 003 启动与生命周期独立复核

结论：**本轮启动修复、四个真实资格、14 次正式运行的进程身份与退出证据通过。未发现需要再开一轮修复的生命周期缺陷。** 可以结束该启动问题的工程修补。结论范围是这批固定输入与入口，不扩写成任意进程树、所有异常或产品通用可靠性证明。

本复核只读作者 `f2b9dc01621d5b7adb330c096b6460eb3be9c552` 的源码和原始记录。自行编写标准库离线解析器，未导入或运行作者 `validate.py`、`qualify.py`、评分器或引擎。解析 131 个文件，662 个交叉一致性检查通过；这是离线证据检查数量，不是新执行 662 个测试。新探针、光栅、Blender、模型/API 调用均为 0。

| 项目 | 原始事实 | 独立结论 |
|---|---|---|
| 正常启动 | Popen、HANDSHAKE、STATE、ENVIRONMENT、TRACE 均 PID 9672；exit 0；完成回执存在且环境摘要一致 | 通过 |
| 非零退出 | 同一 PID 17952；exit 1；STATE、stderr、末尾 trace 都保留 RegisteredProbeFailure；无完成回执 | 通过；失败业务状态保留 |
| 握手后超时 | 同一 PID 21920；依赖导入后写 waiting；父端确认后设置 250 ms 期限；期限到才 kill 原 Popen；exit 1；有界清理 3.6569 ms | 通过；并非导入未完即超时 |
| 动作后缺回执 | 同一 PID 18280；marker 文件及唯一 marker_written 事件摘要匹配；action_count 1；exit 0；回执缺失被拒绝，STATE 保留 action_executed_receipt_omitted | 通过；未重试动作 |
| 正式运行 | 12 主样本和 2 控制，严格等于预登记目录和顺序；14 次 Popen PID 都等于 child RESULT、loader environment 和全部 trace 的 PID；14 次 exit 0 | 通过 |
| 原句柄清理 | 全部 18 次使用同一 stop_process；正常退出仍 wait/reap 后 Close；超时 kill 后有界 wait；无需通过裸 PID 查找进程 | 通过 |
| 来源与顺序 | 资格与正式运行绑定同一 FROZEN 摘要和 158 项映射；7 个启动/控制源码当前摘要匹配；18 个实际环境都绑定同一 base exe、bootstrap、原 NumPy/PIL 路径/版本/init 摘要及 138 源产品映射；资格结束后才进入正式批次 | 通过；完整 158 当前文件复核由根汇总 |
| 旧 002 | Popen 23456 与 RESULT 20368 的不一致仍可在原件观察；1 failed、11 not_run 保留 | 旧失败不改写；旧进程亲缘与当时异常清理仍未测 |

## 源码语义核查

- `launch.py:40` 明确构造固定基础解释器命令；没有用 Windows venv launcher 代替 worker。`bootstrap.py:112` 只显式加入原 site-packages 并以 runpy 调用目标，不伪造虚拟环境 prefix。
- `bootstrap.py:70` 是 probe 和正式 runtime 共用的依赖加载函数，检查实际 executable、实际 NumPy/PIL 文件与固定产品来源；18 个环境的四个 prefix 都实际指向基础解释器目录。
- `launch.py:46` 清理接收原 Popen 对象；kill 与 wait 分为两个异常段，所以 kill 报错也仍尝试有界 wait。只有确认退出后才调用持有的 `_handle.Close()`。清理错误保留并导致 confirmed 为 false，没有把未知退出写成完成。
- `qualify.py:117` 处理握手刚发布而进程刚结束的轮询竞态：发现进程退出时再次检查原子发布的握手，再做 PID/环境核对。不是放宽 PID 条件。
- `probe.py:70` 在实际依赖加载后才握手。timeout 分支进入等待循环；receipt_failure 分支只写一次排他 marker、写一次动作状态、正常退出，不进入补发动作路径。`qualify.py` 每个 scenario 仅 dispatch 一次，没有失败自动重试循环。
- `runner.py:204` 在正式预留前核资格来源；每个正式 slot 前后核冻结图；`runner.py:182` 继续执行 Popen/runtime 严格 PID 比较。没有因为 002 的错误而删除检查。
- 正式 stdout/stderr 重定向到父端 `with` 管理的文件；Popen 自身的 stream 属性为空，因此 `pipes_closed` 字段本身不能证明父端文件已关闭。代码确实先退出该 `with` 再读取文件；本复核额外核对原 stdout/stderr 摘要和时间链。资格记录还显式保留 `parent_files_closed`。

## 保留的证据边界

本轮没有重新运行资格或正式工作负载，也没有独立 OS 历史 handle 遥测；句柄结论来自原始跨文件时序、实际 PID 记录及对应代码语义。完整第三方子模块/native extension 字节认证、恶意 pyc 替换不是这轮启动资格的测试内容；不能把固定 base/init/产品源映射说成这些攻击测试已经通过。也不据此增开新实验。

详见同目录 `RESULTS.json`、`INPUTS_SHA256.json` 和可复查的 `recheck_lifecycle.py`。作者原件未修改。
