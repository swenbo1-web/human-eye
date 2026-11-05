# Radical V1 主对话独立验收记录

依据：[六模块竞争工作流与事前收益标准](RADICAL_V1_COMPETITION_WORKFLOW.md)。两端独立竞争；本文件只记录我方实现。实施者完成不等于主验收通过。

## 模块当前状态（2026-11-05，主验收004后）

代码起点：`e6192173ae252df7b657a4aa2a8ab1fa4719effd`。收益标准在实施对话开始前保存到Git；本批RB-A与TD可并行，文件责任分离。

| 模块/子项 | 状态 | 后续放行 |
| --- | --- | --- |
| RB-A 常驻数组桥 | PASS：已完成主对话独立正确性与收益验收 | 单独通过不代表RB整体通过 |
| RB-B 真实Blender采集 | PASS：原生正确性和捕获收益均经主对话独立验收 | RB整体通过本轮合同，放行BC正式推进 |
| TD 跨帧形变 | PASS：主对话独立正确性、内存和时延均达标 | 不能替代距离、图像或宿主验收 |
| BC / VG / AO / CF | 未派工 | 下一项BC；VG/AO/CF继续按各自依赖推进 |

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

## 首批结束与下一步（历史状态）

主对话已向两个实施对话反馈各自验收结果；每个候选至少独立验收一次。本批完成RB-A和TD，剩余RB-B、BC、VG、AO、CF继续按依赖管理。下一项为RB-B真实宿主采集与收益验收；先解决Blender运行环境，不能把已有数组桥通过替代原生采集，也不提前宣称整个引擎完成。

两端比较继续采用完整独立实现。本记录不包含另一端的同口径结果，不据此宣布竞争胜出。


## 环境验收 003：Blender MCP — 连接通过，RB-B收益未验

2026-11-05，已确认用户运行的Blender 5.2.3 LTS，并通过Codex配置中的同一命令、同一环境变量启动标准stdio MCP客户端，实际完成initialize、list_tools、get_addon_status和get_scene_info。旧记录的“本机未发现Blender”是受限进程检查未发现宿主进程，不能据此判断本机未安装；现已通过宿主进程与真实协议调用纠正。

- 服务包：mcp-for-blender 2.2.7；MCP SDK 1.30.0；返回9个工具。
- Blender addon：[1,8]；协议版本15与服务预期一致；up_to_date=true。
- 实际场景：Scene，Cube/Camera/Light，立方体6面，单位比例1.0；本次只请求状态和场景查询，没有请求修改或保存场景。
- 连接：127.0.0.1:9876；DISABLE_TELEMETRY=true；原有Codex配置原文保留，仅追加blender服务。
- 本机原始证据与复现脚本：`D:\human eye\.tools\blender_mcp_connection.json`、同名`.log`、`D:\human eye\.tools\verify_blender_mcp.py`。

本检查证明安装和宿主连接条件具备。当前聊天用已安装SDK完成真实MCP调用，不把配置文件写入等同于宿主已将新工具热加载到本聊天。未执行RB-B捕获性能测试；冻结的捕获＋准备总中位数降低至少20%、全变化汇总p95不超过基线1.20倍，以及主对话独立复验要求均保持。RB整模块仍未PASS，BC尚未放行。


## 主验收 004：RB-B — PASS，RB整体放行

实施对话 `01a1aa7a-e60a-7473-aa73-d341c8565136`（host local）完成后停止写入；主对话以冻结协议提交 `954f572d56e44aa3f178d2135bd050606ca402b6` 独立复验。[事前RB-B协议](RB_B_ACCEPTANCE_PROTOCOL.md)继承原有收益门，没有根据结果调整输入配比或门值。

候选直接批量读取 evaluated Mesh 的 position、corner vertex和material index属性，缓存自有米制数组，全三角路径直接建立面关联。合理基线同样预分配数组并使用批量读取，仅在需要几何/外观时通过to_mesh获取临时网格。两条路径都按相同显式变化声明运行，不做无变化强制全量读。依赖图求值包含在各步骤计时内，双方分别重放初态及完整序列，不能复用另一方完成的脏图求值。

独立种子47303，与作者31871不同；三独立Blender进程，5次预热、31次交错样本。每档两个对象；每样本是顶点、修改器、变换、无变化、外观、单位、同规模拓扑和混合变化的八步捕获＋准备总和。

| 每对象规模 | 主验收基线三进程中位数 ms | 候选三进程中位数 ms | 候选/基线，要求≤0.80 | 汇总p95比，要求≤1.20 |
| --- | --- | --- | --- | --- |
| 10,000顶点 / 19,602三角 | 31.742 / 32.742 / 32.314 | 14.812 / 15.478 / 14.960 | 0.4666 / 0.4727 / 0.4629 | 0.4743 |
| 90,000顶点 / 178,802三角 | 236.391 / 236.669 / 240.310 | 95.204 / 95.413 / 95.144 | 0.4027 / 0.4032 / 0.3959 | 0.3902 |

完整序列中位数分别下降52.7%–53.7%、59.7%–60.4%；p95分别为33.712→15.989 ms、250.901→97.912 ms。主对话从每个原始样本重新核对步骤求和、样本数量、交错顺序、进程独立性、中位数和p95，并未直接使用作者PASS标记。逐步骤结果不隐去：小档仅单位更新中位数0.549→0.604 ms，约增加10%；收益门针对完整冻结序列。

正确性共66项通过：作者5项原生测试复跑、主对话7项独立原生检查、已有54项可移植回归。主对话另覆盖父子反射/非均匀变换、独立随机网格、形变修改器、单位变化、连续shape-key动画、材质槽调序/面分配、空网格增减、同数量不同连接、对象隔离及借用生命周期。四边形与凹多边形在任何oracle/显式三角化之前首先由候选冷捕获，避免参考读取提前暖缓存。完整浮点数组与原生oracle一致，世界坐标差异约1e-15 m；索引和外观分类字段精确一致。

原始证据、重新计算的门值、命令及测前/测后相同的源码摘要见 [RB-B主验收JSON](radical_acceptance_rb_b.json)。采集器SHA-256：`f2cbeb79218e68b1506423392f77878e489fc797b001e187249b659c0aaf124d`。实现与复制量见 [RB-B实施说明](RB_B_IMPLEMENTATION.md)。复制未消失：每条完整序列RNA坐标暂存仍为0.84/7.56 MB，额外Blender临时网格由9次降至0次；Blender内部总分配/复制字节量未知。

```powershell
& 'D:/human eye/venv/Scripts/python.exe' -B verification/benchmark_blender_resident_bridge.py --blender 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' --seed 47303 --output artifacts/acceptance/rb_b_independent.json
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' --background --factory-startup --python-exit-code 1 --python verification/test_blender_resident_bridge.py
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' --background --factory-startup --python-exit-code 1 --python verification/test_blender_acceptance.py
python -B -m unittest verification.test_resident_bridge verification.test_tensor_deform verification.test_radical_acceptance verification.test_fast_kernels verification.test_fast_engine verification.test_fast_cli verification.test_fast_benchmark -q
```

决定：RB-A与RB-B在本轮明确合同内均通过，RB整体可放行BC距离核的正式推进。范围是Blender5.2.3 Object Mode、可信显式更新声明与原生Mesh组件；性能覆盖两档全三角网格，非三角覆盖正确性。用户当前GUI场景未参与写入，测试在独立后台进程执行。该结果排除场景修改命令、MCP传输、渲染、模型调用，不证明<12ms整链目标，也不替代Edit Mode、其他Blender版本或后续模块验收。

## 主验收 005：BC首审 — REWORK（基准公平性）

82项正确性/回归检查通过；独立种子79463、3进程×31配对样本的四个正距离网格主门均通过。主对话仍对算法/架构和测试边界深审，发现穷举对照找到零距离后仍继续扫描，夸大密集相交的比较收益。候选完整搜索、数值特征、面ID、更新所有权和最坏复杂度的分析、各门实际值及原始证据见[BC首审](BC_REVIEW_001.md)、[复验JSON](radical_acceptance_bc.json)。当时基准原文按原始报告SHA-256逐字节核对并保存为[历史基准快照](bc_review_001_benchmark_source.txt)。

决定：先修正测试方法，不凭已通过的主门提前放行VG；未发现既有引擎功能退化，当前不回滚无关已验收模块。作者按原输入/门值以新文件再测，失败与旧样本保留。用户在本轮修订后续工作流为“实施自测→主动唤醒→主干审计/算法架构深审/退化判断→接受继续或恢复旧方案”，主干以后不轮询等待聊天、不机械重复全套基准，有疑点才做针对性复验。
