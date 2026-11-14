# M4 REGION LOCALIZATION CONSUMPTION001：入口、采用和生命周期独立复核

复核对象：作者交付 `21b2871df70c5fedde4a916c67983ee40c626f89`，批次 `verification/m4_region_localization_consumption_001`，外部原件 `D:/he_loc_001`。本复核只读取原始文件并运行标准库离线检查；新产品、CLI、模型、Blender、raster、benchmark 调用均为 0。作者报告与以下独立检查分开。

**结论：三次 P 正式会话都未调用产品入口。当前证据证明本地工具列表和批准配置正确、准备阶段下游产品链可运行；没有证明真实模型已经收到完整工具定义、实际调用过入口或消费过产品事实。不能把这轮当成产品定位事实的模型消费验收，也不能把 0/3 直接解释为路由缺陷或模型不信任。**

## 本轮实际检查

`audit.py` 从正式 CLI 原始 stdout、真实 stdio TX/RX、actor REQUEST/RESPONSE/RECEIPT、退出记录以及封存副本重新核对。692 份输入参与检查，1584 项文件/协议/状态一致性判断通过，0 项失败。这是离线判断数量，不是 1584 个产品测试案例。详见 `RESULTS.json`、`CHECKS.json` 和 `INPUTS.json`。

| 正式槽 | execute_python | render_views | read_images | active_observation |
|---|---:|---:|---:|---:|
| N1 | 6 | 1 | 1 | 0 |
| P1 | 7 | 0 | 0 | 0 |
| P2 | 8 | 1 | 0 | 0 |
| N2 | 7 | 1 | 1 | 0 |
| N3 | 8 | 1 | 1 | 0 |
| P3 | 6 | 1 | 0 | 0 |
| 合计 | 42 | 5 | 3 | 0 |

P2 的第 2 次、N3 的第 3 次 execute_python 是业务错误；两者之后都出现成功工具调用。没有 active_observation 调用尝试，因此没有该入口被拒绝、执行报错或返回事实后被忽略的正式样本。六槽的产品 observation/replay 记录均空，均实际构造了 6 个视图。

三 P 的真实 `tools/list` 回复都列出 active_observation，回复原字节 SHA256 同为 `7f82345427e8c1d16485b786006814f400a70b81d9818c34ea415e0959c95901`。实际 CLI argv 为四个公共工具及 P 的 active_observation 分别配置 `approval_mode='approve'`。桥接代码将 P 的该名称直接分发到当前 observation service，未发现将其过滤或禁用的分支。以上证明到本地 MCP/CLI 交界处；封存没有 provider 最终请求中的工具定义，故不把本地注册扩大成模型一定看到。

## 实验实际测了什么

所有槽的实际 argv 都有 `--ignore-user-config`、`--ignore-rules`，且 `features.hooks=false`，技能、记忆及其他宿主能力也被共同隔离。本轮测的是“可选 MCP 工具在独立环境中的自发选择”，没有运行真实默认 Hook 自动观察。需要改善的可能是工具可见性、任务契约、说明或事实消费；本轮不足以支持重写自动 Hook。

公共 prompt 字节一致，公共工具 schema 一致，原始几何与缓冲计算能力共同可用。它详细定义了原生三角形合并、像素与边界计算，并提供 persistent Python、NumPy、Fraction 和 own algorithms 的路径。P 的新增 schema 则只简述当前安装引擎、brief-v3、region locations、pixel facts、图片及缓存，未明确说明它能一次完成区域发现、视图选择和覆盖汇总。公共 prompt 也没有点名该产品入口。这是可以核对的呈现差异，足以形成待验证假设，不能单凭文本或 3 个结果认定其造成了零采用。双方公共能力足够强是实验条件，不是违规，也不能把 P 走公共工具的结果归因到产品算法性能。

六个 CLI 均有 fallback model metadata 和 skip_host_skill_discovery 警告；原始 stderr 也存在宿主快照/结束刷盘信息。当前没有证据把这些共同警告单独关联到 active_observation 的隐藏或拒绝。

## 准备阶段的证明范围

本地 fake N/P 都先收到预定 ValueError，再返回 `42`，最后 N 返回 1 张当前图片、P 成功调用 active_observation 并返回 3 张图片。P 的 active/replay 记录各为 1；准备及正式 P schema 相同。

`static_review.py` 核对准备与正式冻结的 1552 个共同条目：唯一改变是 `freeze_sources.py`；该变化与作者保留的 `FREEZE_GENERATION_NOTE.json` 一致。bridge、launcher、native_tools、fake_cli、bootstrap、公共 prompt 的准备/正式/当前字节一致。正式新增的冻结条目主要为已关闭的准备证据。详见 `STATIC_REVIEW.json`。

因此 fake P 支持“同一下游传输和产品分支可达”。fake_cli 自行产生 thread/tool events 并直接发起 RPC，替代了真实 CLI/provider/model；它不能证明真实模型的工具可见、工具选择、输出理解或回答正确性。其正常 EOF 也不能覆盖正式槽的不同结束状态。

## 生命周期和绑定

六个正式槽为六个不同的新 thread，均一轮、同一冻结 prompt、原 450 秒期限，无恢复旧 thread 或重跑槽的记录。CLI 原始 tool ID、名称、参数、返回内容与真实 stdio 和 owner 请求/回执逐项匹配；最终输出与本槽 final、线程和终态对应。

六槽 CLI 和 actor 进程均 exit 0，actor close 成功、线程停止、管道/句柄关闭；thin runtime 的保留进程句柄确认已退出，六槽 exit code 均为 1，EXIT 回执均缺失，正常 EOF 保留 **unknown**。这符合本批已接受的退出契约，但只能写“退出已确认”，不能改写为“全部正常 EOF”。

## 唯一建议的下一项

先做 **1 个真实 Pro 新会话的显式入口与事实消费资格检查**：保持当前产品、场景、工具 schema、CLI 和模型设置，在诊断指令中明确先调用 `active_observation(include_images=true)`，再使用其当次证据回答已冻结的定位问题。保留真实 tools/list、调用/回执和答案绑定；需要原生补算时如实记录。此诊断不计作自由选择采用率或端到端收益胜出。

- 出现 missing/denied/协议执行错误：修对应入口，保留原错误。
- 工具成功而事实缺失、解释失败或答案错误：针对具体缺失/消费问题修最小一处。
- 工具与事实消费都成功：确认下一轮应研究入口说明和任务契约；不能倒推前三次零采用的确定原因。
- 即使明确指令也没有调用尝试：继续定位可见性/工具选择证据，不先断言路由故障。

本阶段不重复六槽、不更改全局 Hook、不扩大算法或数据场景。先把“能否调用”“是否自发选用”“事实是否可用”三个问题分开，才有依据选下一处优化。

复核过程有一次只读命令误查 `inputs/bridge.py` 和 `inputs/launcher.py`，路径不存在；随后读取了批次根目录的真实文件。该命令未启动任何产品行为、未改变作者证据，也未计作通过项。
