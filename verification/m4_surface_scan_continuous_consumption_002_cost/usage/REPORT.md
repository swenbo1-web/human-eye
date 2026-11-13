# 连续消费002的终态 token 账本

质量 seal 与全部证据摘要核对一致，私有映射逐轮对应十八份完整正确、当前依据充分的答案及六个完整有效 episode。每组均为3/3 episode、9/9轮，质量门通过。十八份缺失 thin EXIT 仍为 unknown。

| 片段 | N input＋output | C input＋output | 三对 C/N 比值的中位数 | C/N 总量比 |
| --- | ---: | ---: | ---: | ---: |
| FULL | 387622 | 238238 | 0.588523 | 0.614614 |
| BASE | 148312 | 49804 | 0.329232 | 0.335806 |
| REPEAT_EDIT | 239310 | 188434 | 0.766501 | 0.787405 |

## 固定三对

| 片段 | 配对 | N | C | C/N |
| --- | ---: | ---: | ---: | ---: |
| FULL | 1 | 133942 | 78828 | 0.588523 |
| FULL | 2 | 110446 | 79570 | 0.720443 |
| FULL | 3 | 143234 | 79840 | 0.557410 |
| BASE | 1 | 52631 | 16503 | 0.313560 |
| BASE | 2 | 45042 | 16629 | 0.369189 |
| BASE | 3 | 50639 | 16672 | 0.329232 |
| REPEAT_EDIT | 1 | 81311 | 62325 | 0.766501 |
| REPEAT_EDIT | 2 | 65404 | 62941 | 0.962342 |
| REPEAT_EDIT | 3 | 92595 | 63168 | 0.682197 |

## 口径与判定

FULL 的 C 实际 input＋output 总量不高于 N，token 门通过。

每轮只取一个 CLI turn.completed 终值，逐字段核对原 consumer、usage_rows、raw_usage_events 及已封的逐轮范围证明。原 consumer 的 unknown 标签和空聚合保留，派生 scope 另列。未累加 token_count 快照，未从 input 扣去 cached、旧历史或相同文本，也未把 reasoning 再加到 output。

每个视角内部每轮只计一次。BASE 与 REPEAT_EDIT 划分 FULL，三个视角的总量不能相加。中位比由三对各自 C/N 比值求中位数，总量比由两组原总量相除，两者分列。逐轮、逐 episode、分组和配对原字段均在 USAGE.json。

时间门由独立 timing 账本复核，本文件没有据 token 通过宣称总体门通过。费用、Pro 扣账、provider 请求次数及隐藏重试/弃流范围保持 unknown。单一固定任务的三对结果不能外推所有三维场景。

本项只读现有原件，没有读取其他 session、凭据或启动模型、provider、Blender、产品、API 或 Git。输入绝对路径与 SHA256 完整保存在 USAGE.json。
