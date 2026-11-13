# 已封质量的连续消费001失败成本账本

质量 seal 已授权整理这次失败消耗。六份首轮内容均 complete_correct，原执行状态保持六次 failed、十二轮 not_run。以下逐集列原始观测，不据此判定连续收益。

| 集 | Outer 秒 | 首轮秒 | Prompt 至 final 秒 | 工具尝试 | CLI input_tokens | cached_input_tokens | output_tokens | reasoning_output_tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| N1 | 100.429987 | 98.472444 | 95.075460 | 3 | 35406 | 25856 | 3789 | 272 |
| C1 | 42.492474 | 39.605508 | 35.117829 | 1 | 15271 | 5760 | 1260 | 0 |
| C2 | 49.467636 | 46.571974 | 40.574163 | 1 | 15293 | 5760 | 1359 | 59 |
| N2 | 104.007244 | 102.039671 | 98.371098 | 4 | 39035 | 21376 | 3741 | 256 |
| N3 | 108.345569 | 106.274858 | 103.726562 | 4 | 39611 | 30592 | 3721 | 237 |
| C3 | 46.150338 | 43.284942 | 38.320618 | 1 | 15276 | 5760 | 1386 | 88 |

## 计量范围

Outer 使用原 FINAL_TIMING，覆盖输入检查、owner 启动、实际首轮、sole finish、关闭后验证、原件 ZIP 及 OUTER_RESULT 写入关闭。首轮使用 consumer FINAL_TIMING，覆盖输入检查、模型进程、工具、cleanup、归档及 CONSUMER 写入关闭。Prompt 至 final 为原 consumer 记录的子区间。各区间有包含关系，不能相加。timing receipt 发布范围沿原合同单列。

十四次工具尝试的名称、耗时、响应字节及原始 usage 完整保存在 LEDGER.json，逐项通过短目录原件、outer ZIP 成员和 manifest 的字节绑定。各集原 usage 同 turn.completed 事件逐值一致，cache_write_input_tokens 等全部原字段也保留。

没有实际 resume，usage 的逐轮或 session 累计语义仍 unknown，aggregation 为 null。cached 与 reasoning 子字段未再次加总。provider 请求计数、费用及不可见服务开销未测。六份 thin EXIT 继续 unknown，独立 owner close 均已确认。

## 尚未测得的共享成本

共享准备、离线检查、freeze/commit、质量打包、独立质量复核和完整端到端总耗时缺少完整计量回执，保留 unknown。原 per-episode 归档耗时已包含在 outer 区间，批次质量打包的完整耗时单列未知。既有安装回执属于复用准备来源，未归入本次新消耗。

REPEAT 与 EDIT 十二槽均未运行，耗时和 usage 不估算。旧交付 manifest 的 SHA256 与根独立来源复核一致，144 份清单成员逐字节核对通过，连同 manifest 自身共绑定 145 份文件。绑定清单见 LEDGER.json。本工作没有新增模型、provider、产品、Blender、API 或 Git 操作。
