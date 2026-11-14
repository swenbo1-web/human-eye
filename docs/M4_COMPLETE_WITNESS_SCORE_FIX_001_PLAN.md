# M4-COMPLETE-WITNESS-SCORE-FIX-001

唯一目标：修复完整见证验收的离线评分器与实际生产者的字段绑定，让同一批已保存证据得到可复核的补充自动评分。没有新模型、产品观察、Blender或raster调用，不修改产品、题面、真值、阈值、归一化答案或原始结果。

## 固定输入和原失败

原交付 `8baad59ac6da01f14e1eb87c3e1f4f0687eb2b7d`，产品仍为d12c7ab2及141源d8ad7003…9f02。输入目录为实施树 `verification/m4_complete_witness_consumption_001/`，运行原件 `D:/he_complete_witness_001/`。原自动 `admin/QUALITY.json` SHA `272f925f1f46b4140b7483fbeceb1ff0a2b58285d3b5c9cab6c417cbb6cb3a87`、质量seal SHA `93b0dde406a185bdb60c7921eb1f7d3f697e45e493763130d304828fdfdd30d9` 永久保留。

原scorer读取 `RUN_RESULT.records[0].execution_state`；实际schema `complete-witness-single-formal-v1` 将execution_state写在顶层。旧Routed外层包装曾给逐槽记录增加同名字段，静态准备把它误套到当前原始route上。新修复绑定当前生产者，不增加跨版本猜测或默认completed。

## 最小代码改动

在新目录 `verification/m4_complete_witness_score_fix_001/` 保存可读的派生评分器及测试，仍沿唯一实施分支提交。原冻结scorer及helpers不写。新评分器明确自己的版本/源码身份，依赖原固定真值、像素读取和语义判据；把新输出写到新目录，不能覆盖原QUALITY。

读取完整run_result后，明确检查当前schema、恰一条P1/P记录、planned_routes=1、actual_routes=1、actual_CLI_processes=1及outer_retries=0，顶层execution_state为completed、launcher_succeeded为true且terminal_errors为空。保留原row.outer_valid_completion、consumer.valid_completion、runtime_binding与原已接受的runtime_exit确认条件。正常thin EXIT回执缺失继续与真实持有句柄已退出区分，不另要求它变成exit0或伪造回执。

顶层launcher检查是必要的：当前生产者在post_route_checks失败时仍可能保留execution_state=completed，但launcher_succeeded=false并记录错误。因此只替换一处字段取值不够。实现可以是一个小reader/谓词，不新增通用schema框架、运行时检查层或新的进程包装。

除此以外，完整性、可读像素、来源引用、覆盖集合、unknown和direct adoption的评分逻辑保持不变。明确记录派生diff/AST差异与旧函数哪些部分一致。不得为了将本次改为direct=true而重新分类tool2/tool3，也不得向NORMALIZED补答案。

## 仅对已有数据验收

先用真实保存的RUN_RESULT和CONSUMER做一次离线终态读取与评分，跑到内容判定，不能只搜源码里是否有字段名。根的独立诊断已表明终态字段修正后原内容路径可完成，预期本次补充结果为最终答案正确、实际产品事实采用、direct-only=false且存在原生补核。预期不是允许硬写的答案，全部由实际原件计算。

在根外的新派生测试目录或内存副本制作必要负例：顶层state缺失/failed、launcher失败或postcheck错误、记录缺失/多条/错slot、原row或consumer有效性/绑定/退出证明为假，均不能通过。另把目标见证改为真实SCENE部分可读行，即使其像素计数达标也必须在完整性检查失败；不存在的引用同样失败。原始运行文件不改，负例标记为人工派生控制，不计为新模型样本。

派生评分器的正常读取与负例必须都保持0新产品/模型/Blender/raster/网络执行，使用已有字节。输出存在时不得覆盖；原件与seal前后哈希一致。若出现另一项真实语义或读取问题，保留并回报，不悄悄放宽规则或重跑消费者。

## 交付和后续规则

分别呈现原自动失败0/1、根独立语义正确1/1，以及本次派生自动评分实际结果；补充通过不把历史首轮改成通过。原生读取/全幅像素重算仍计为补核，不能解释成产品纠错或纯直接消费。

将本次真实生产者输出作为以后同reader的离线回归样例。对更换生产者/包装的评分器，在启动昂贵消费者前运行该离线接口检查；不为它增加新的模型预热或通用防御层。

提交最小派生代码、输入/输出哈希、负例分母和结果、所有失败及版本差异到现有实施分支。回报根 `local/01a1971f-eef5-7a23-a1b1-2352beb80a77`：**M4-COMPLETE-WITNESS-SCORE-FIX-001_READY**，然后结束等待独立复核。本批没有新的模型能力或性能试验；Google/API/key、默认配置、原资产、共享GUI及专家线保持原边界。
