# 紧凑扫描候选的输出合同

本候选修改 `surface_scan` 的 MCP 展示结构。省略 `response_detail` 和显式 `brief` 使用同一紧凑表示，显式 `full` 使用已有详细结构。其他观察模式沿用原默认展示行为。

## 客户端读取

紧凑结果带 `display_encoding="surface-scan-task-table-v1"`。客户端应按该版本解释表格，或者显式请求 `response_detail="full"` 使用详细结构。依赖原默认 `matches[i].objects` 的外部 JSON 客户端需要适配这项结构变化。

| 字段 | 含义 |
| --- | --- |
| `objects` | 本结果匹配端点的原 ID、名称及端点附加字段，各 ID 记录一次 |
| `object_table_scope` | `matched_endpoints_only`，对象表只覆盖已交付匹配的端点 |
| `object_reference` | 从零开始的对象表索引，作用域为本结果来源绑定 |
| `match_columns` | 行内六个值的列名 |
| `matches` | 按原匹配顺序交付的表格行 |
| `match_metadata` | 对每一匹配都存在且值相同的逐行说明 |
| `match_exceptions` | 按 `match_index` 合并的逐行差异说明 |

六列依次为 `object_a`、`object_b`、`object_a_ref`、`object_b_ref`、`distance_m`、`distance_mm`。可读名称用于显示，对象索引用于恢复原 ID。同名对象继续按索引独立对应。当前基准有 24 个场景对象、22 个匹配端点，对象总数继续读取 `coverage.objects`。

`distance_m` 保留原始值，投影继续交付原匹配集合及顺序。`distance_mm` 为阅读提供派生毫米值，超过 binary64 毫米范围时使用精确十进制整数字符串。成员判断沿用原米制测量与阈值。带符号零和极小正数保持其数值区别。

恢复逐行说明时，先复制 `match_metadata`，再合并该行索引对应的 `match_exceptions[].metadata`。见证状态、方法、未知原因和未来附加字段按此规则保留。见证世界坐标由详细结构提供。

## 状态和详细观察

原状态、覆盖计数、未知项、来源范围、全局 binding、trace 和执行权限继续交付。`delivery` 继续描述 reducer 原始交付范围，上游截断仍保持原 partial 与 `delivery.complete=false`。紧凑投影只处理上游已经交付的行。

显式 full 发起一次新的当前场景观察，可复用已有计算缓存。组合两次响应时需要核对场景和来源 binding，trace 是请求级标识。full 提供的是该次当前观察的详细证据。

工具错误保留详细错误正文。投影不支持的结构、保留字段冲突、对象 ID 内容冲突或可恢复的展示异常，会交付原详细结构。完整值首先通过原严格 JSON 序列化校验，非有限原始值继续触发原错误路径。响应中的 `display_encoding` 可用于识别是否采用紧凑结构。

## 验证范围

本批验证封存响应的语义恢复、相关入口与回归，以及固定合成 BASE/EDIT 的五次普通 installed MCP 观察。10 KiB 正文目标针对本次固定基准，包含对象表、说明和来源。实际模型上下文呈现、模型往返、token、完整任务收益和外部 JSON 客户端覆盖留后续验收。
