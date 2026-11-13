# 成本组件的独立交叉复核

本轮依据已封质量结论和002-COST计划，只读同批原件。`recheck_components.py` 从十八份 CLI 唯一终态、六个外层原始整数时界及十八个 consumer 时界独立重算，再与 usage、timing 组件对照。组件一百一十五项及主账二十二项检查合计一百三十七项通过。

| 主门 | 独立复核 |
| --- | --- |
| 质量与执行 | N、C各3/3完整有效episode，各9/9完整正确且当前依据充分 |
| 完整episode时间 | 三对C/N比值的中位数为1257127904/2049220255，约0.613466，满足≤0.70 |
| 实际input＋output | N为387622，C为238238，C不高于N |
| 固定任务总门 | 三项均通过 |

token三对中位比为0.588523，总量比为0.614614。两个数使用各自明确的分母。每轮只取一个经封存范围证明的终值，cached、cache write与reasoning分别保留为报告子项，没有再次加入input或output，没有扣除重复历史。

BASE与REPEAT＋EDIT的token中位比分别约0.329232、0.766501，时间中位比分别约0.378030、0.755440。优势在BASE更大。三个时间配对的REPEAT与EDIT各自均低于原生组，当前数据也支持后两轮的收益。

BASE与REPEAT＋EDIT的时间口径采用consumer完整轮次区间。登记EDIT及轮间管理间隙在timing组件另列，并计入FULL。FULL主指标始终使用外层时间，全部准备、启动、关闭、后验和原件收口按其已记录范围保留。视角之间有包含关系，不能再把这些总量相加。

十八份thin EXIT继续unknown，独立owned关闭与CLI/readers结束按质量seal分别保留。共享准备/打包、费用、Pro扣账及不可见重试缺少完整计量时继续unknown。单一固定任务的三对结果只支持本任务门槛判断。

复核脚本首版误将timing组件的布尔时间门按含passed的对象读取，触发TypeError。已按实际字段修正并重算通过，首版脚本和错误记录保留于 `ATTEMPT_01_SCRIPT.py`、`ATTEMPT_01.json`。

原件和组件SHA绑定见 `COMPONENT_CHECK.json`，usage逐轮及全部分区见 `usage/USAGE.json`。本子任务没有读取其他聊天、session日志或凭据，没有新增模型、provider、Blender、产品、API或Git操作。

主 `LEDGER.json` 的六个episode、十八轮 usage/timing 逐值对应组件，三个视角的全部九个配对原始时间和token值、精确比值、中位比及四项门结论均对应独立复算。root 的 `RECALC_CHECK.json` 与主账实际 SHA256 绑定一致。费用及项目总投入仍为 unknown。
