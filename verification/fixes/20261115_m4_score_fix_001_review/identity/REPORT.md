# M4 完整见证离线评分修复：身份与分母独立复核

固定作者提交 `b0e2fcfe90b7b535105e24dff9c34b36c27a26af`，基线 `8baad59ac6da01f14e1eb87c3e1f4f0687eb2b7d`。结论：新增交付身份、冻结输入、原件与真实回归样例一致；保存结果支持报告中的离线调用分母。没有发现改写原始失败、替换原样本或漏计新模型样本的证据。

本次仅读取文件字节、Git blob、源码及保存输出，没有导入或执行作者 scorer、harness、产品或模型。只写本目录。`check_identity.py` 首次执行 **3396/3396** 项断言通过，运行错误及未通过断言均为0。此分母主要是文件/来源/保存结果检查，有重叠，不是3396个功能场景。

## 身份与原件

- 基线后变更恰为 **182** 路径，全部在新 `verification/m4_complete_witness_score_fix_001/`；181条manifest记录加manifest自身，完整集合与当前实际目录相等。182个固定Git blob与工作字节一致，作者树检查时干净。
- **2524** 冻结路径全部按真实文件重算SHA256通过。
- 原namespace和运行根 `D:/he_complete_witness_001` 的 **338** 项执行前/后快照相等；当前实际文件集合及逐项摘要也相等。
- 两个fixture分别与原 `formal/RUN_RESULT.json` 和 `formal/P1/c/CONSUMER.json` 逐字节相同。真实thin `exit_code=1` 没被改成0，退出确认仍沿旧合同。
- 原QUALITY SHA256仍为 `272f925f1f46b4140b7483fbeceb1ff0a2b58285d3b5c9cab6c417cbb6cb3a87`，`final_quality_passed=false`、`direct_product_adoption=null`。
- 原NORMALIZED仍为 `7bb03e3df6a52fa158b689b00c0ce32d5cabe7edf8fb2ad8df2fee26f5f1ef33`；原quality seal仍为 `93b0dde406a185bdb60c7921eb1f7d3f697e45e493763130d304828fdfdd30d9`。旧评分器及原模型final/请求/图像都在未变的保护或冻结集合内。

## 实际离线分母

| 保存执行 | 数量 | 核对结果 |
|---|---:|---|
| 首次真实原件 `main` 入口评分 | 1 | exit0、无read overlay，输出SHA与补充QUALITY一致 |
| 主回归正例 | 1 | 同一真实原件，33项内容检查通过，direct=false |
| 主回归终态反例 | 18 | 每项实际FULL_SCORE与TERMINAL、错误字段、exit1及注册CONTROL相符 |
| 主回归内容反例 | 2 | 实际SCENE partial和错误ref均按注册内容错误拒绝 |
| 输出独占辅助 | 1 | 预期FileExistsError，sentinel前后摘要及实际文件相同 |
| 合计评分入口 | **23** | 1首次正例 + 21主矩阵 + 1辅助 |

21次reader直接预检单列，不再加为模型样本。保存目录恰有一个 `regression_01`；21个CONTROL/RESULT/FULL_SCORE/TERMINAL/READ_OVERLAY都完整，21份stderr为空，无未运行主案例，实际结果与顶层账本相符。终态反例的exit1和辅助FileExistsError是预期拒绝，不是未报告的意外失败。

本次补充QUALITY为 `f3475509ee2118a3d86187627bdf19ab22f46a88ab0abd32d0cfbff475f2babe`，33项内容检查全过；quality=true、direct_product_adoption=false、correct_with_supplement_or_recomputation=true。原失败0/1、先前管理员语义正确1/1、本次补充正确1/1都属于**同一个原模型样本**；新增模型样本为0。

## 执行范围证据

实际 `regression.py` 在进入评分前安装审计hook，拒绝其列举的网络/子进程操作、隔离产品目录代码执行以及结果目录外的文件写入。保存 `blocked_side_effects=[]`。脚本只使用已有fixture、原JSON和图像数组；人工控制以三个精确JSON读取点的内存副本进入评分，原件没有被修改。入口计数在循环实际调用前增加，并与每例保存结果一致。

首次正例的 `POSITIVE_RUN.json` 记录 `scorer_entry=main`、`read_overlay=false`、`exit_code=0`、`blocked_side_effects=[]` 和相同源码/reader/output摘要。该正例的audit包装未作为独立脚本存于namespace，本项未读取运行命令正文；本项依据保存回执及所读评分代码核查，不把它称为独立全系统网络监控。没有重放这个入口以提高检查计数。

据已读代码、保存执行记录及未变的原件，本轮评分/回归没有新增产品、模型、Blender或raster调用，网络执行记录为0。Git同步与本次读取Git不是评分器网络执行。现金、模型时间、token收益均不属于这轮离线修复的新测量。

## 边界

本项不重新判定三维几何真值，也不证明额外原生补核“必需”。它只确认该补核在原轨迹和评分分类中保留；答案语义及新reader是否保持原判据由另一项独立源码复核负责。完整内容评分在此次子复核未重新运行。

原评分器作者参与作者侧跨作者审核的关联在POSTRUN_REVIEW中披露；本项为另行读取实际字节的身份/分母复核，没有把作者侧检查数字当作自身执行结果。

材料：`RESULT.json`含分组与3396条断言；`INPUTS.json`记录本次实际读取的文件长度和SHA256；`check_identity.py`为可读独立复核脚本。
