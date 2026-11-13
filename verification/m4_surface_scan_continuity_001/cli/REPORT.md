# 连续消费 CLI 接口准备

2026-11-13。冻结本机 CLI 的 help、版本和参数解析检查通过，30 个纯合成测试方法通过。本目录新增模型消费者及推理 API 调用均为 0。真实模型续接、记忆保留与跨轮 usage 语义尚待正式阶段取得证据。

## 接口依据

使用旧 PLAN 绑定的 standalone `0.152.1` 可执行文件，SHA256 为 `01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6`。本次读取 `--version`、`--help`、`exec --help`、`exec resume --help` 四份实际输出，原始 stdout、stderr 和时界保存在 CLI_INTERFACE.json 及同名文件。

`exec resume` 支持显式 SESSION_ID、stdin 的 `-`、`--json`、`--ignore-user-config`、`--ignore-rules`、`--strict-config`、`-c`、`-m` 和 `-o`。`-C` 与 `--color` 由 exec 父层接收。用旧 N/C 实际 argv 模板构造首轮和续轮共四份参数，再附 `--help` 验证解析，均 exit0。ARGV_HELP_VALIDATION.json 保留完整命令、摘要及经过时间。这些命令只进入 help 路径。

旧 consumer argv 带有 `--ephemeral`，该选项的 help 明确说明不持久保存会话文件。连续消费首轮需要去掉这一项，给后续显式 UUID 续接提供持久会话。`argv_for_turn` 直接复用旧 argv/config，首轮执行 persisted exec，后两轮执行明确 UUID 的 exec resume。工作目录与颜色参数放在 exec 父层，其余原参数归 resume。生成器拒绝已经续接的模板、`--last` 和非规范 UUID。

## 纯函数和合成证据

continuity_cli.py 提供三个小入口。

- `argv_for_turn(initial_argv, expected_thread_id=None)` 生成首轮或显式续轮 argv。
- `summarize_turn(events, episode_id, turn_index, expected_thread_id, exit_code)` 分别保留执行状态、final 存在状态、原始 usage 和未评分内容状态。
- `episode_manifest(episode_id, turn_records, anonymous_episode_id)` 固定 BASE、REPEAT、EDIT 三轮质量分母，缺席轮保留 not_run，失败后出现的 final 保留在 failed 轮。

测试覆盖显式续接、错误线程、缺线程、缺续接绑定、重连后最终完成、缺 final、缺或重复 turn.completed、异常 usage、非零退出、三轮匿名信封、重复/多余轮及业务错误正文保留。合成输出位于 SYNTHETIC_EPISODE_MANIFEST.json，测试原日志位于 offline/attempt_01/。30 方法全部通过，本子任务没有失败重跑。

匿名函数负责已知 episode 行政信封。实际业务请求/响应和原始归档沿用旧 pack_quality 的来源记录与投影规则，正式 consumer 接线时还需把这些原件接入新的三轮信封。本批合成信封没有代替真实模型匿名材料。

## 未来共同题面与配置草案

FUTURE_CONSUMER_DRAFT.json 明确一个 episode 三轮共享同一 workdir、endpoint、backend session 和原生工作 namespace。C 使用固定 `452b44d2`、138 源 `4067c864…a9f6`，增加既有普通 observe。N 与 C 都保留本 episode 内的脚本和几何缓存，工程实例在资格结束后丢弃。

T1 的 PROMPT_T1.txt 与原题逐字节一致，405 B，SHA256 为 `6a78e38a474647c0c0c49558be215864cb672932273b3e15ca6ba7f9fa02b4fc`。T2/T3 共用 PROMPT_RECHECK.txt，直接以“请重新检查当前场景。”的 UTF-8 字节前缀拼接原题，435 B，SHA256 为 `1556e86013d52b1ca222237f6e5df33d389d33e95c8e3df3bd218edb4e5549d6`。文本只增加这个共同前缀。

未来正式 episode 数量、顺序、原绝对期限和收益门仍为待冻结。工程合同的 590 秒 episode 与 30 秒工具期限分别记录。草案的模型启动开关为 false。

## 明确的集成剩余项

当前新 runtime/consumer_transport.py 提供工程 thin_turn，正式 consume 进程循环尚未接入本目录的 argv 和 parser。可以在新准备目录复用旧 consume 循环，以小范围参数化完成接线。

1. 接收逐轮输出 folder、episode 共享 workdir、expected_thread_id 和原绝对 deadline。首轮要求全新目录，续轮允许该 episode 已创建的文件。
2. 使用本目录 argv_for_turn，记录首轮实际 thread.started UUID，T2/T3 显式续接。端点和 MCP 配置随同一 owner 延续。
3. 保留原始事件及进程/工具隔离和清理检查，用 summarize_turn 复核线程和最终状态。续接失败保留失败，不生成替代上下文。
4. 将真实模型历史和后台连续性证明绑定，并把原始归档/业务投影接入三轮匿名信封。episode 结束后统一 finish。

因此目前已证明参数可解析、合成解析/分母正确，真实消费循环的接线和模型续接仍未测。未来正式启动前须完成该接线及独立复核。

## usage 与可见性

旧九次 fresh 消费只证明各自一个最终 usage 事件。它们无法确定 resume 后字段属于当前轮还是整个会话累计。本函数逐轮原样保留 usage，不求和或差分，跨轮 aggregation 为 null。重连弃流计量覆盖、provider 请求总数、实际费用、解析模型版本和 effort 保持 unknown。

本子任务只读取管理员合同、旧冻结材料和 CLI 帮助，并写入 cli/。AL 当前 context_bound=false、host_epoch=5，使用既有授权继续准备，任务同步尚不可用。
