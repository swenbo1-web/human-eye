# Radical V1 主对话独立验收记录

依据：[六模块竞争工作流与事前收益标准](RADICAL_V1_COMPETITION_WORKFLOW.md)。两端独立竞争；本文件只记录我方实现。实施者完成不等于主验收通过。

## 首批派工前状态（2026-11-05）

代码起点：`e6192173ae252df7b657a4aa2a8ab1fa4719effd`。收益标准在实施对话开始前保存到Git；本批RB-A与TD可并行，文件责任分离。

| 模块/子项 | 状态 | 后续放行 |
| --- | --- | --- |
| RB-A 常驻数组桥 | PASS：已完成主对话独立正确性与收益验收 | 单独通过不代表RB整体通过 |
| RB-B 真实Blender采集 | 待实施/待真实环境验收；本机未发现Blender或bpy | RB整模块未通过前不正式推进BC |
| TD 跨帧形变 | PASS：主对话独立正确性、内存和时延均达标 | 不能替代距离、图像或宿主验收 |
| BC / VG / AO / CF | 未派工 | 按依赖及验收结果推进 |

主对话至少执行正确性复跑、收益重测、计时边界核查和不同种子/变换补充案例，并保留原始数据及候选文件摘要。通过、返工、待验均须列明确证据。

## 已创建的实施对话

标准冻结提交：`c31f78af3868a4a8a44ce8fac41323a414fdbd0b`。两对话使用本端相同checkout，但文件责任独立，Git由主对话统一管理。

- RB-A：`01a1aa0e-8c2e-7e61-a14c-8c70c6382322`，host `local`，常驻数组桥实施。
- TD：`01a1aa0e-efc4-76f2-9ba2-eeccfe50ce19`，host `local`，跨帧形变与内存收益实施。

主对话使用对话状态和最终报告接收反馈，随后在同一候选源码独立复跑，不以实施报告代替验收。

## 主验收 001：RB-A — PASS

主对话在两个实施对话作者基准结束后串行复测。独立种子97813与作者20261105不同，3个独立进程，每进程5次预热、31次交错样本。基线为常驻预分配缓冲与批量全量刷新；候选dirty取行计入耗时。无Blender调用。

| 网格 | dirty基线/候选，各进程中位数，要求≥2 | full候选/基线，各进程中位数，要求≤1.20 | full汇总p95比，要求≤1.20 |
| --- | --- | --- | --- |
| 10,000顶点 / 19,602面 | 6.729 / 6.924 / 6.594 | 0.998 / 0.996 / 0.998 | 1.0034 |
| 90,000顶点 / 178,802面 | 14.963 / 14.763 / 14.664 | 1.002 / 0.994 / 1.007 | 0.9945 |

主对话从原始样本重新计算所有门，未直接使用作者PASS标记。两档世界坐标最大绝对误差均小于1e-12 m；无变化时数组视图保持身份，无顶点/拓扑写入。共享顶点、多对象、全量/dirty/变换/外观/拓扑替换与释放由测试覆盖。

独立组合测试54项通过：原fast36项、RB-A5项、TD9项、主对话额外4项。主对话检查包含不同种子的逐面QR/SVD、随机变换、1e-7/1e8尺度下排名、桥接→形变刚体快照；见 [主对话补充检查](../verification/test_radical_acceptance.py)。

原始样本、重新计算的门值、代码摘要与范围在 [RB-A独立验收JSON](radical_acceptance_rb_a.json)。命令：

```powershell
python -B verification/benchmark_resident_bridge.py --seed 97813 --output artifacts/acceptance/rb_a_independent.json
python -B -m unittest verification.test_resident_bridge verification.test_tensor_deform verification.test_radical_acceptance verification.test_fast_kernels verification.test_fast_engine verification.test_fast_cli verification.test_fast_benchmark -q
```

决定：数组子项收益达标。RB-B真实Blender采集仍PENDING，RB整体尚未通过，不提前放行BC正式推进；TD是此前已独立派工的并行模块。

## 主验收 002：TD — PASS

独立种子61847与作者29017不同。20,000/100,000连通面、各16帧，3进程×5预热×31交错样本；在RB复测结束后串行运行。完整逐面摘要在1e-11容差内与语义正确的全张量基线一致，见证ID与独立完整排序一致。

| 面数 | 候选额外峰值 / 基线，要求≤0.50 | 候选/基线各进程中位数，要求≤1.25 | 汇总p95比，要求≤1.25 |
| --- | --- | --- | --- |
| 20,000 | 10,961,632 / 67,531,264字节，0.1623 | 0.8362 / 0.8491 / 0.8766 | 0.9803 |
| 100,000 | 54,721,632 / 337,611,264字节，0.1621 | 0.8928 / 0.9793 / 0.9563 | 0.9570 |

额外分配峰值下降约83.8%，同时所有时间门通过。内存是tracemalloc单次调用额外峰值，排除已有输入，并非RSS或GPU显存。主对话从每进程原始值重新计算所有门；测前测后候选源码摘要相同。

[TD独立验收JSON](radical_acceptance_td.json)保留样本、运行环境、数值差异、源码摘要与判定。正确性与原fast回归已包含在前述54项独立运行中，无源码变化后不重复扩大测试。

```powershell
python -B verification/benchmark_tensor_deform.py --seed 61847 --output artifacts/acceptance/td_independent.json
```

决定：TD模块通过本批预先定义的可移植完整摘要与内存收益验收。并不证明16帧100,000面满足12ms；本机候选此规模中位数约0.88–0.91秒，属于不同输入与计算范围。

## 本批结束与下一步

主对话已向两个实施对话反馈各自验收结果；每个候选至少独立验收一次。本批完成RB-A和TD，剩余RB-B、BC、VG、AO、CF继续按依赖管理。下一项为RB-B真实宿主采集与收益验收；先解决Blender运行环境，不能把已有数组桥通过替代原生采集，也不提前宣称整个引擎完成。

两端比较继续采用完整独立实现。本记录不包含另一端的同口径结果，不据此宣布竞争胜出。
