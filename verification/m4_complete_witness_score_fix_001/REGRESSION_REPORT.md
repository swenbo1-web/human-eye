# 派生评分器离线回归结果

本报告由离线registry和harness作者整理，依据根已执行的唯一回归结果。仅读保存的结果文件和控制记录，没有重新运行评分、产品或模型。

固定准备 Git 为8d69825，FROZEN包含2524项来源。主矩阵21/21通过，输出保护辅助检查1/1通过，未运行项和非预期失败均为0。对实际保存结果另做19项读取与一致性核验，全部通过。

## 真实正例与历史结果

根先对原真实RUN_RESULT、CONSUMER、原NORMALIZED和原保存帧执行一次完整派生评分。实际结果为final_quality_passed=true、product_current_facts_correct=true、direct_product_adoption=false、correct_with_supplement_or_recomputation=true。回归矩阵中的同字节正例也通过完整内容判定。

三个结果分别保留。

| 判定 | 同一原模型样本的结果 |
| --- | --- |
| 历史首次自动评分 | 0/1，execution_state字段异常，原件及seal保持 |
| 根独立人工语义复核 | 支持正确1/1 |
| 本次派生补充自动评分 | 1/1，存在原生补核，direct=false |

本批没有新增模型样本。原tool2的原生源读取及tool3的全幅像素重算分类保持。补充评分没有将其改为纯直接消费，也没有覆盖历史首次自动失败。

## 反例与精确原因

18项终态控制全部经真实reader及完整scorer入口拒绝，返回码1。每项失败字段与registry逐字匹配，没有借其它错误通过测试。

| 终态控制 | 精确失败字段 |
| --- | --- |
| 顶层state缺失或failed | RUN_RESULT.execution_state |
| launcher为false，原completed保持 | RUN_RESULT.launcher_succeeded |
| postcheck错误，原completed及launcher=true保持 | RUN_RESULT.terminal_errors |
| records缺失、空或多条 | RUN_RESULT.records |
| slot/group错误 | RUN_RESULT.records[0].slot / group |
| schema错误 | RUN_RESULT.schema |
| planned/actual/CLI计数为0 | RUN_RESULT.planned_routes / actual_routes / actual_CLI_processes |
| outer_retries为1 | RUN_RESULT.outer_retries |
| 原row无效 | RUN_RESULT.records[0].outer_valid_completion |
| consumer无效或绑定/退出未确认 | CONSUMER.valid_completion / runtime_binding.confirmed / runtime_exit.confirmed |

真实fixture的held-handle退出确认保持原值，原runtime_exit.exit_code=1。正例继续通过，reader没有增加exit0要求。

W01使用实际SCENE第一条readable目标行，37917个surface pixels、924个contrasting boundary pixels、原ref与真实owned anchor都保持正确。独立保存测量再次确认readable=true且complete=false，终态检查通过。完整scorer精确拒绝target_actual_complete_view与target_index_frame_consistency，证明达标的可读像素仍不能替代完整性。

W02只将目标ref换成不存在的人工控制ref，原TOP、计数、owned pixel、身份和支持原文保持。终态检查通过，完整scorer精确拒绝相同的两项目标见证检查，没有其它内容错误。

## 次数与输出保护

| 调用类型 | 实际次数 |
| --- | --- |
| 主矩阵直接terminal reader预检 | 21 |
| 主矩阵完整score入口 | 21 |
| 输出保护辅助score入口 | 1 |
| 根独立首个完整score入口 | 1 |
| 完整score入口总数 | 23 |

reader预检次数单独列出。21个主案例包含一个真实正例、18个终态负例和两个内容负例。18个终态负例在reader处早退。23次均为对同一份已保存样本的离线入口调用，不是23个模型样本。

输出保护辅助检查只使用新测试目录。实际完整评分尝试写入已存在的sentinel时收到该路径的FileExistsError。其前后SHA均为66de088fa2a2b9642fedc6c034c3b2511005d7a3b8a580696ccaedfb52c6e27e。辅助检查按预期拒绝计为通过，分母1与主矩阵21分开。

## 原件与边界

harness前后对原namespace及原runtime内338个文件逐项SHA比较，全部相同。原QUALITY SHA仍为272f925f1f46b4140b7483fbeceb1ff0a2b58285d3b5c9cab6c417cbb6cb3a87，原质量seal SHA仍为93b0dde406a185bdb60c7921eb1f7d3f697e45e493763130d304828fdfdd30d9。没有guard阻止的副作用记录，新增模型、产品、Blender、raster和网络调用均为0。

fixtures仅保存真实生产者RUN_RESULT与CONSUMER的完整原字节及其provenance。内容评分依赖原hash绑定的helpers、真值、原NORMALIZED、原工具与帧。反例通过三个精确JSON读路径的内存深拷贝构造，原数据和来源SHA函数未替换。

报告JSON包含实际每项验证、输入输出SHA、真实partial测量和精确错误。REGRESSION_REPORT.json SHA为79d110733416663e74f4145344390ab5c588c431d94804d572eb292e28c7a264。补充结果只覆盖当前绑定的single-formal生产者和这一个固定案例，后续更换生产者仍需先用真实保存fixture进行离线接口回归。
