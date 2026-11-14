# M4 完整见证消费：冻结评分器独立复核

复核固定交付 `8baad59ac6da01f14e1eb87c3e1f4f0687eb2b7d` 的 `verification/m4_complete_witness_consumption_001/score_saved.py`。结论：首轮自动失败是评分器读取生产者记录层级错误，不是模型答案已被判错。可以只对同一保存证据做一个另存、版本化的读法修复；不需要重跑产品、模型、资格或渲染。

本轮没有修改作者树、源、原件、QUALITY或seal。新增产品、模型、Blender、raster调用均为0。做过一次明确标记的派生评分诊断：在内存中改两个读取位置，用原作者的保存证据/像素评分函数检查后续分支，把结果只写入本目录。这个结果不是正式重评，也不是我另写的一套独立像素oracle。

## 已确认根因

`score_saved.py:26` 只保留 `RUN_RESULT['records'][0]`，而第79行访问 `outer['execution_state']`。实际 `launcher.py:312–318` 输出的schema是 `complete-witness-single-formal-v1`：`execution_state`、`launcher_succeeded` 和 `terminal_errors` 位于顶层，records里的原route不含这个状态字段。

原静态审查套用了此前Routed额外wrapper的行级字段，未让当前生产者产物和当前消费者完整对接。这说明只检查“字段名在某个producer里出现”不足以验证层级。无需增加产品检查层，给这个读取器加一个真实保存产物的离线合同测试即可。

原QUALITY SHA仍为 `272f925f1f46b4140b7483fbeceb1ff0a2b58285d3b5c9cab6c417cbb6cb3a87`，其中 `final_quality_passed=false`、`direct_product_adoption=null` 和KeyError原样保留。这是自动评分未完成；不能写成“模型0/1答错”。

## 仅换字段位置还不完整

另一个必须一起处理的读取问题：`launcher.py:311–318` 将 `execution_state` 仅由route的outer_valid_completion决定，而 `launcher_succeeded` 还要求后置错误列表为空。假如route完成后来源/资格复核失败，顶层仍可能是completed，实际launcher却失败。

因此最小修复应保留整个RUN_RESULT，并明确这一个单槽schema及records数量。终态判定同时要求：

- 顶层schema为本批 `complete-witness-single-formal-v1`，records恰一项P1/P，原计划/实际route及CLI各1，无外层重试。
- 顶层 `execution_state == completed`、`launcher_succeeded is True`、`terminal_errors == []`，缺字段拒绝，不能默认completed。
- 原row.outer_valid_completion、consumer.valid_completion、runtime_binding.confirmed、runtime_exit.confirmed的现有要求保持。

不要给保存row补一个假字段，不要为兼容其他producer做通用多版本兜底，也不要要求thin EXIT receipt正常存在或把held exit1改判失败：当前合同明确区分已确认进程退出与缺少正常EXIT回执。

## 其余评分路径的实际检查

我完整阅读了score_saved.py以及其saved_evidence/oracle/native_evidence依赖。内存中仅将第26行改为保留run_result+选record，并把第79行状态改读顶层；其余质量、像素、引用和采用规则不变。执行在写入仅限本目录、禁产品import/子进程/网络、禁pyc写入的进程内，输出为 `DIAGNOSTIC_LAYER_FIX_ONLY.json`。

这一次对原NORMALIZED、原final/requests/frames完成全部33项检查，结果：

- final quality为true，product facts为true；没有后续KeyError或schema错误。
- direct product adoption为false，correct_with_supplement_or_recomputation为true。
- actual additional native frames为0；raw_source_read和native_computation仍被保留，缓存TOP读取没有偷偷增加raster。

这支持“修读法可完成当前保存数据评分”，不取代根对最终语义和独立像素的复核。评分器对引用片段只检查存在性，对归一化的contradictions和工具category依赖人工语义判断；当前final引述和两次原生补核分类确实一致，没有理由为了这批把分类改成direct。额外native新帧分支本次没执行，因为正式消费者只复用了产品TOP帧；该路径只能静态审查，不能声称本次已经动态覆盖。

## 最小修复的离线验收

本目录同时提供了一个窄的producer-specific终态读取器建议。用原记录的内存副本做18项控制，全通过：原件通过；缺顶层state、只在nested伪加state、failed状态、completed但postchecks失败、launcher false、errors非空、错误schema、空/多record、错误slot/group、多CLI、有outer retry、outer/consumer无效、未确认runtime binding或exit均拒绝。

这些是读取器建议的控制，不是已经部署到作者scorer的测试。实施者下一批应在其独立补充namespace做同类离线测试，再对未变的真实保存证据生成一个正式补充结果。仍使用原质量/引用/像素门槛，保留原自动失败和QUALITY_SEAL，不改prompt、产品或NORMALIZED以取得通过。

另外保留几项有意义的内容负例：将目标见证替为SCENE的partial-readable行应失败；改坏一个像素计数或当前ref应失败；native补核分类不能被改写成direct-only。可以对内存副本测试，不需要新模型或raster。当前真正已执行的控制数是18，以上内容负例是下一步建议，未在本子复核执行。

## 本轮自身错误与材料

完整派生诊断和18控制已完成，RESULT.json已写入之后，输入哈希日志收尾曾因audit hook记录了Python尝试查找但不存在的pyc路径而报FileNotFoundError。未产生作者pyc或原件修改。该错误保留在REVIEW_SCRIPT_ERROR.md及原工具记录；只修日志过滤，并另按明确的32项来源/原件生成INPUTS.json，没有重跑已完成的派生评分。

本目录的RESULT.json区分派生诊断、18项控制和未测路径；原作者scorer SHA保持 `fd6a1c455d40407e8e3b1ad8f2711689f4419c6ce187a9e3083467edcd0d4074`。这些结果允许根派一个最小只读评分修复，不支持重开模型测试、改质量标准或宣称不再需要语义复核。
