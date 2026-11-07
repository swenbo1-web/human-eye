# TASK-COMPLETE-001-CONSUMER-01

本轮已完成固定 control 的 N→P 三状态对照，六份公开回答全部保留。根按已有独立 truth 与实际响应核对，六答的关系、距离、方向及当前性均有相符几何依据。主线独立评分待复核。

**“P 三问各一次 observe，且无需追加 native”的目标未达。** P 实际选择三次 observe 加两次 native，补读发生在 unchanged_current 和 changed_current。每问仅执行一次，无重答。

## 调用、文本和时间

| 量 | N | P |
|---|---:|---:|
| 消费者 native | 6 | 2 |
| 消费者 observe | 0 | 3 |
| 公开调用 | 6 | 5 |
| broker 公开 wire 字节 | 15,037 | 10,763 |
| 响应重建 CLI stdout UTF-8 字节 | 12,727 | 8,700 |
| 保存的 final_text UTF-8 字节 | 2,154 | 2,188 |
| 已记录 thin wrapper 合计 ms | 473.6645 | 719.8739 |
| broker 调用合计 ms | 285.8405 | 559.9222 |
| 链启动至回收 s | 303.7421 | 318.6604 |
| 三问报告时长合计 s | 175.045 | 120.344 |
| QA 更新次数 | 1 | 1 |
| 消费者失败 / 自动重试 | 0 / 0 | 0 / 0 |

CLI stdout 字节由保存的公开响应及既有交付格式重建。纯 CLI 进程启动至退出计时、宿主工具包装交付字节和模型实际消耗字节均未测。thin wrapper 包含 broker、worker 与部分落盘，其末端仍在 audit 发布及 stdout 交付之前。各层时间分别报告，嵌套时间分别保留。

两链各拥有完整600秒上限，包含启动。六问报告时长依 N→P 次序为61.514、51.338、62.193、34.064、41.823、44.457秒，均小于150秒。链 wall 包含根的调度、上下文恢复和响应收集等待。P 第一答完成至根保存公开 final 的间隔约91.35秒，本轮单对数据未建立因果性速度收益。

## Token

| 计数 | N | P |
|---|---:|---:|
| Input | 224,065 | 228,279 |
| Cached input 子集 | 196,992 | 218,240 |
| Output | 6,080 | 3,531 |
| Reasoning output 子集 | 1,873 | 1,250 |
| Total | 230,145 | 231,810 |
| Input 减 cached input | 27,073 | 10,039 |

白名单 cumulative 差分与两链末次累计完全相符。Cached 与 reasoning 已包含在对应 input 与 output 中。六问设置均可见为 gpt-6.1-sol、ultra、openai_http。初次累计快照中 N cached input 为0，P 为18,048，缓存条件不同。费用、provider 请求数、真实后端和 Pro 身份未测。根与审计助手 token 未纳入消费者比较。

## 三状态证据

| 状态 | N | P |
|---|---|---|
| initial | 当前求值网格与表面覆盖证明间隙约0.010000 m，方向 +X | 一次 observe 返回严格最近点、精确间隙及 A→B 方向 |
| unchanged_current | 重新读取当前网格、连接、变换和修改器，确认旧计算适用 | 当前 observe 绑定与事实一致，另补一次 native 网格检查 |
| changed_current | 四个目标顶点变化，共同严格内点及实际表面交点证明穿插 | 先读当前 native 网格，再 observe，报告穿插、零表面距离与 SAT 的 A 脱离证据 |

P 第三次 observe 的 nearest_witness 为 unknown，原因为 no_surface_witness_for_escape_metric。其 surface_clearance 为负的脱离量，语义为 certified_separating_translation_not_global_minimum。消费者指出该调用缺少最近见证，并以当前 native 网格给出相交点，零距离处方向未定义。此次响应为 partial，传输和脚本均成功。两次 native 补读的因果动机未单独测量。

三次 observe 的 exact_pair_count 为1、0、1，中间一次 pair cache hit。每次仍执行当前 selected_objects 捕获，均为2对象、16顶点、24三角面。changed_current 的修订与指纹变化已在响应中保留。

## 固定输入与清理

产品固定在 b4bcf3961e2c9b7068883d501072d83d1dbcdaeb 对应的130源 / b0b4e1d3fa96a0b9c9676863fc7565215f82557a2936f247a5a4abd5b911103a，沿已有 engineering_01/venv 普通入口运行。QA 适配提交为 f002f9a1db96d75a870f1c5f51f34c5479264aa3，diff 与源哈希已保存。场景、patch 和独立 truth 沿用已授权字节。

首链启动前剩余1,651.0382秒。两次 QA 更新各成功一次，操作者当前几何额外读取为0。两链均正常关闭，launcher 与 worker 的退出码均为0，watchdog 已加入，forced_cleanup 为空，已识别的8个本轮进程均已消失，原文件与保护文件校验保持一致。

## 证据入口

- answers 下六份 FINAL.json 保留公开 final，各 ATTEMPT.json 保留派发记录。
- ANSWER_CHECKS.json 保存根的逐答核对与原始响应路径。
- COSTS.json 保存逐调用成本、计时边界、缓存与 unknown 原因。
- METADATA.json 与 USAGE_SUMMARY.json 保存六轮白名单设置、时间与 token。
- chains 与 runs 保存实际请求、公开和完整响应、worker 事件、QA 回执及退出记录。
- PROVENANCE.json、qa/ADAPTATION.diff、CLEANUP.json 和 EVIDENCE_INDEX.json 保存来源与封存索引。
