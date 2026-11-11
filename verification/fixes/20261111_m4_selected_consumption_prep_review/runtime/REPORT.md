# Selected geometry consumption：运行器准备独立复核

**结论：运行器子审通过，足以支持根复核者在其他分项通过后发出本轮唯一 GO；没有发现需要扩改运行器或补跑产品的阻塞。** 本轮尚未执行任何正式消费者，也没有创建 GO / STARTED。

固定实施提交：`13f3b279f2a57581e3cebd032d64ec9e2bfdb0ae`。
固定 PLAN SHA-256：`bd8af1e9619ccf9dad8c43a3ecf17eb240843f5b76f4ca9390b8a283ecc00096`。

## 最小复用差异

独立读取新旧文件字节，不依赖作者 reuse=true 标记。

- actor 原字节相同：`d1b71de84efb57d6c5df6301789817327b8c1669e1f945d817991db78b5b7f7e`。
- consumer_transport 原字节相同：`69e5fdbc701b95ae9af02b4039c465a6818d42e03178fb86ccab5c7c895cbb31`。
- driver 的 10 个顶层函数逐一比较 AST，仅 `arm_runtime`、`go_contract`、`preflight_inputs` 因新外部分组和 cycle 改动。`prepare`、`finish`、`snapshot_binding`、`run_models` 及 read/save/load 均相同。
- 独立重新生成 driver 和 pack_quality 的 unified diff，与保存 diff 完全一致。pack_quality 仅静态核复用差异，零启动包装保真由另一子审负责，本轮没有重复执行。
- 正式 backend 是原 accepted_native.py，字节摘要 `13887e30d9f08309102e17704b91603325df13c490bdcc6bcda8b74ac01c59b8`。没有 setprofile / qa_profile_schedule，也没有沿用上批 23 请求的固定 profiling worker。

## 实际 PLAN 与九格映射

逐项核验 PLAN 中 31 个 dispatch 引用实际文件摘要，全部一致。实际计划为 sgc01…sgc09，外组 N/P/G、P/G/N、G/N/P，各三格。

| 外组 | actor/transport 内组 | 安装来源 | 插件是否启动 |
|---|---|---|---|
| N | N | P 仅供共同 dependency Python | 否，entry/install_root/source 参数为 None |
| P | P | e077 / 137 源 53db / lr.r1 | 是 |
| G | P | 00b13060 / 137 源 4eb / sg.r1 | 是 |

无进程调用实际 `arm_runtime` 验证了 9/9 映射、外组保留、slot 不变及 READY 文件与 PLAN 深等值。P 与 G 使用相同 actor 路径；二者工具定义与安装来源是候选差异。

新旧 PLAN 的 15 项控制值完全相同：模型 gpt-6.1-sol、medium、consumer 450 秒、全格 570 秒、actor 启动 40 秒、32 次工具尝试、128 物理 RPC、1 MiB 文本响应、30 秒工具预算、256 KiB 单次原生代码、1 张初图、0 新图、0 工具图、0 协调方重启/替补，以及同一 CLI 字节。actor/transport 的对应实际常量和设置已读，不只比较了 PLAN 标签。

实际 prompt、初图、scene、catalog、camera、directions 与旧共同输入逐字节一致。实读初图并验证 metadata；用惰性输入生成真实 argv，不启动 CLI。相同惰性路径下 P/G argv 完全相同，N 仅工具能力配置不同；三组都携带同一 `--image` 路径和请求模型。共同 ChatGPT 登录路由、关闭 Hook/记忆/无关能力的设置一致。当前账户权益、resolved model/effort、provider 图像接收仍待正式记录，不由本次静态检查推断。

## GO 与实际入口

实际正式函数是 `runtime/driver.py::run_models()`。**直接执行 driver.py 的 __main__ 只做 preflight_inputs 并写准备回执，不会运行九格。** 不能把那个 CLI 当正式派发入口。

本轮真实代码纯验证的 GO 最少需要以下四项，必须写在本批根目录 `GO.json`：

```json
{
  "task": "M4-SELECTED-GEOMETRY-CONSUMPTION-001",
  "authorized": true,
  "plan_sha256": "bd8af1e9619ccf9dad8c43a3ecf17eb240843f5b76f4ca9390b8a283ecc00096",
  "max_consumers": 9
}
```

这是合同示例，本审查没有落正式 GO。根可同时记录冻结提交、发令人/实施人、审查报告摘要、P/G 来源、固定次序、一次矩阵和完成回报要求等审计字段。不得改 PLAN 来写授权状态，否则会改变其绑定摘要。

实际 GO 检查核 cycle、明确 authorized=true、PLAN 摘要、max9、sgc01…09、固定次序、每格 task/round、图片预算及 P/G 来源/共同 dependency 映射。`run_models` 在这之后核 actor/transport/driver、31 输入和 CLI 字节，然后用独占 `STARTED.json.open('x')` 建立单次执行标记，再进入 prepare/consume。已有 STARTED 时不能重新运行或删标记重启。

本轮实际执行结果：当前内存 GO 被纯合同接受；历史真实 GO、authorized=false、错误 PLAN、错误 max、G 错绑 P 来源共五类均拒绝。另在真实 `run_models` 上仅替换 read(GO) 为历史真实 GO：它只读 GO 和 PLAN，随即报 `wrong_consumption_GO`，在任何模块 load、写文件或进程启动前结束。所有外部进程/socket/signal/文件写入尝试均为零。

根发 GO 后，一次正式调用可沿用下列导入方式（**本轮未执行**）：

```powershell
@'
import runpy
entry = runpy.run_path(
    r'C:\Users\Administrator\.codex\worktrees\m4-single-pass-acquisition\hefe\verification\m4_selected_geometry_consumption_001\runtime\driver.py',
    run_name='_sgc_formal_control')
entry['run_models']()
'@ | & 'D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe' -I -B -X utf8 -
```

结束仍按固定规则交匿名质量包后停止，费用/机制解盲遵循根流程。本子审没有执行 packer、产品安装、smoke 或模型消费；不替代其他子审的评分和 smoke 原件验收。

## 本轮实际证据

`review_runner.py` 独立执行退出码 0；`RESULTS.json` 记录映射、拒绝理由、共同控制和惰性 argv；`INPUT_PINS.json` 固定实际读取字节。实际消费者、Blender、产品进程全部为零，实施原件未改，GO / STARTED 始终不存在。先前默认性能与生产准入未决不因准备审通过而关闭。
