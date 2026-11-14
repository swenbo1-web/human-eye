# 离线评分修复：独立语义与控制复核

结论：本批修复符合固定计划，未发现阻止接受的新增缺陷。它修正了生产者状态的读取层级并检查顶层失败情况，原内容、来源、完整性及采用规则保持。原自动失败与补充通过属于同一个模型样本；补充结果为最终正确、产品事实正确、直接采用为false、发生原生补核。

固定目录为 `C:/Users/Administrator/.codex/worktrees/m4-view-reuse-001/hefe/verification/m4_complete_witness_score_fix_001/`。派生scorer SHA256为 `b444ffa6f3528ca1e775ccd6fb617b808b47ae2cf326f8ebcdb9863655f99600`，reader为 `b6e095a866c7fa498f700bf856d04d75aed5701c8cf44d31d4eef9c5b1f2afde`。原scorer摘要仍为 `fd6a1c455d40407e8e3b1ad8f2711689f4419c6ce187a9e3083467edcd0d4074`。

## 本轮实际做了什么

独立脚本 `review_saved.py` 完成132项检查，132通过、0失败，读取126个实际文件并记录长度和SHA256于INPUTS.json。这132项包含AST、保存产物与七次小reader执行，是有重叠的审核断言，不能当作132个几何场景或新的模型样本。本轮没有运行完整scorer或作者回归生成器，也没有产品、模型、Blender、栅格或网络调用，只写自身证据目录。

| 范围 | 本轮独立动作 | 结果 |
| --- | --- | --- |
| 内容规则 | 显式撤回新增终态读取、输出限制及元数据后比较AST | score、main和load的保留部分逐节点一致 |
| 作者21控制 | 逐个读CONTROL、TERMINAL、FULL_SCORE、RESULT和READ_OVERLAY | 原控制、精确错误、退出/质量和三处JSON替换均一致 |
| reader定向运行 | 原件正例、假nested状态、completed但后检失败、bool伪计数、多record、未确认退出、空来源证明 | 7/7符合精确字段预期 |
| 真实补充评分 | 阅读无read-overlay的main调用回执并绑定输出哈希 | 原33检查全过，direct=false且补核=true |
| 原件 | 原producer fixture逐字节对比，以及原QUALITY摘要与内容 | fixture相同，历史失败保留 |

未重新执行完整21项评分矩阵。这里对作者21/21的确认来自实际保存的每项输入变体和评分产物、回归实现审查及当前源码身份，不冒充本轮独立重跑。作者的独立正例1次、主矩阵21次和输出独占1次合为23次离线评分调用，仍只有一个原始模型样本。

## 读取修复没有偷换评分规则

`terminal_reader.py` 对当前schema、单P1/P、计划/实际route和CLI各1、无重试、顶层completed、launcher成功、空错误列表以及原row/consumer有效、来源/持有退出确认作检查。它没有把nested state或缺失状态默认成completed。顶层state已完成但postchecks报错时仍拒绝。实际原件中的持有退出证明继续按既有条件接受，没有新加exit0要求。

AST复核不是只比较函数名：独立脚本逐项保留并列出从新score中撤回的节点，只恢复原outer读取及valid_final判断，删除明确新增的reader调用、提前终态拒绝、输出目录检查和两个身份字段；随后整个score AST与旧版相等。main仅撤回输出范围检查及身份元数据后也相等。因而完整/可读、当前引用、coverage、unknown和native/direct分类没有在本次改动中放宽。

原冻结helpers及NORMALIZED仍被使用。新输出增加来源身份并采用exclusive创建，原scorer、QUALITY和原答案没有改写。其来源身份字段属于元数据记录；输入冻结与原件核验仍由本轮运行/验收流程承担，不将元数据存在夸大为独立安全能力。

## 内容反例确有针对性

W01把目标见证换为实际SCENE行，37917表面像素、924边界像素和真实ref/anchor保持，readable=true而complete=false。实际产物同时报告`target_actual_complete_view`和`target_index_frame_consistency`失败。完整性这一项独立失败，不能因第二项索引不一致就把它说成只测试了引用。W02仅替换为不存在的ref，其他TOP事实保留，也按同一完整见证及索引绑定判据拒绝。两项中产品本身事实仍被评分为正确。

反例是NORMALIZED在内存中的人工变体，不是假装模型真的给过这些错误答案；所有原文和图像读取仍用原件。原回归函数只拦截RUN_RESULT、CONSUMER、NORMALIZED三个JSON路径，未替换oracle的几何/像素计算、source hash或实际图像。

## 采用结论的边界

实际保存轨迹分类仍为`raw_source_read`及`native_computation`，没有新增原生帧。因此可以说“最终答案正确，模型做了原生补核，未达到纯直接消费”。

作者final里的“当前结果仍依赖模型补充计算”容易被读成已证明这一步不可缺少。当前没有去掉补核的反事实实验，只有发生补核的事实；管理员此前又核对首次输出已含任务所需字段。因此应采用报告正文的“存在原生补核”，不把依赖或必要性当成已证结论。

归一化source quote存在性仍不等于自动理解引用的全部语义，native分类仍有人工作者解释参与；这是原合同的已知范围，本轮未扩大或掩盖。native新帧分支本例未触发；没有再次运行几何光栅器、模型或性能实验，因此也不产生新的速度/费用收益结论。

本批无需增加通用schema层或再跑模型以验收这个离线接口修复。语义规则保持、保存控制和七个定向reader检查已支持当前范围的接受。
