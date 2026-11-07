# TASK-CONTRACT-001 R1

修复初版证据归属错误。产品仅将 pair_relation 负值 fallback 的 method 从 strict.measurement_method 改为 strict.clearance_method，复用原 strict 结果及度量范围。几何内核、求解、缓存、工具说明均没有源码变化。

新产品为130源 / 14c22c391b83eb4cb7d4c6523a13d4e36d0609293a502c0a4f40a0ee0a0e3d88。独立安装位于本目录 venv，版本9.7.2+task.contract.r1.1。原 c839 安装与全部初版原件保留。

## 实际组合反例

B为中心(0,0,0)和(0,3,0)的两个分离单位盒，A为中心(1−2^-32,0,0)的单位盒。独立重叠预期为2^-32，即2.3283064365386963e-10m。

修改前先运行真实几何，并包裹原分类函数记录同一次 strict 测量内的两次固有调用。正容差结果为不穿插 / convex_components_sat，零容差结果为穿插 / convex_components_escape。负 signed_clearance 正确，但初版 pair_relation 错标 convex_components_sat。COUNTEREXAMPLE_BEFORE.json 保留 c839 来源、原始 strict 和这项错误投影。

R1对保留的真实 strict 结果重新投影，不重算几何，method 变为其实际 clearance_method，即 unrounded_all_surface_features_or_certified_escape，escape_distance 保持独立预期。COUNTEREXAMPLE_AFTER.json 明确这份后记录的范围。新增正常 service 入口测试另行使用同一真实夹具，验证求值和投影路径。

## 必要定向与安装入口

一次固定定向运行6项，6/6通过，无错误、失败或跳过。包含组合反例、既有正交/多组件、单凸容差内真实重叠、显式 nearest unknown 和证据不足。原96项及两项测试夹具修正历史保留，R1没有重跑该清单。

一次R1构建、新venv离线安装及显式身份检查完成。测试、构建、安装、反例后投影与真实 control 绑定使用同一新 pin。沿正确五份QA helper运行原控制脚本，一个后台Blender会话做3次pair_relation observe和1次QA更新。R1三次均measured/observed，实际stdout仍为1158/1158/1268B，当前绑定与更新后变化通过核验。

实际累计3 selected capture、2 pair、1 witness traversal、0 scalar、2 paired SAT、0 fallback、0 full capture、3 content encoding。R1额外native读取0。本批总计observe为6、QA更新2，消费者答案0。真实Blender仍为原control，组合反例由必要定向中的真实分析网格覆盖。

## 成本、清理和时间

工具说明由547增至959 UTF-8 B的412B增量沿用独立复核记录，R1没有重新措辞。4607→3584B的22.21%仅指相同边界下的返回正文。工具说明发送频率/缓存、模型补查和总净收益未测。

launcher及worker均exit0，worker已回收，watchdog退出，forced_cleanup为空。识别PID及R1路径匹配Python/Blender均无残留。原资产和保护文件校验一致。

本次turn从2026-11-07T03:23:04.261Z起，10分钟截止03:33:04.261Z，原新实验截止03:29:27.767Z、原工程03:39:27.767Z和路线04:06:11Z继续有效。全部实验在03:27:09Z前完成，封存前缀时间见MEASUREMENTS.json，最终完整投入由host完成时间确定。

RESULTS、MEASUREMENTS、COUNTEREXAMPLE_BEFORE/AFTER、UNIT_RESULT、INSTALLED_IDENTITY、control/RESULT及原始CLI/audit/QA/worker记录为主要证据。EVIDENCE_INDEX索引主要原件。交协调根差异深审收口。
