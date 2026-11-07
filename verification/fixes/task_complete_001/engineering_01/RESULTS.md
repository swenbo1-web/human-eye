# TASK-COMPLETE-001 ENGINEERING-01

工程验收完成，提交一个产品候选。新增模型消费者为 0，后续 P/N 消费者及整体成本收益交主线另行复核。

## 候选

产品初版提交为 `fea80e7e23aef6defdb55616d0043a7169345f1c`，测试／记录修正提交为 `67ae7633cc39520da72a4f314ddf41b93b246eba`，两者产品字节相同。新来源为 130 源／`b0b4e1d3fa96a0b9c9676863fc7565215f82557a2936f247a5a4abd5b911103a`。隔离安装版本为 `9.7.2+task.complete.1`，实际加载自该新 venv 的 purelib，`source_kind=installed_distribution`。

产品仅改 `geometry_safety.py` 和 `task_query.py`。按请求见证使用一次既有带见证遍历替代标量遍历，仍核原三角表面、点距与 1e-9m 发布精度。精度不足时保留已知标量／关系，见证单独 unknown。两项输出需求进入缓存参数及版本。SAT 证据复用已有向量／度量，注明 A 的脱离向量、非最近方向／非全局最小深度、world_apply_verified=false，SAT 源码未改。正交路径已有严格零容差判定，直接复用。

## 定向检查

固定六模块实际运行 110 个唯一方法。首次 109 成功，1 个新增正交微穿插测试错误地把认证 escape 度量等同最小重叠厚度，实际为 -.025m，错误预期为 -2^-32m。只修该测试语义预期，产品保持原候选字节，唯一必要重验该方法 1 次通过。

首次结果写盘还因 failures 含 TestCase 对象产生序列化错误，`UNIT_RESULT.json` 为部分原件，明确不可按完整 JSON 使用。原 `targeted.stderr.log`、部分文件和派生 `UNIT_FIRST_SUMMARY.json` 保留首错，`UNIT_RECHECK.json` 保存单项重验。没有重跑六模块或全项目。

覆盖原表面点／交换／非轴旋转、触碰零方向、容差内真实重叠、真实大坐标见证发布不足、既有正交／多组件、需求缓存及新 revision 绑定，关键路径用函数调用计数断言。测试 helper 采用精确有理或 Decimal 独立小几何预期。

## 一次隔离 control 三状态

复用旧 control 同字节 blend、patch 和获证 truth。在一个后台 Blender 中，每状态实际执行一次既有 observe CLI，requested_facts 为 surface_clearance／solid_relation／nearest_witness。

| 状态 | 标量 m | 必要证据 | CLI bytes | CLI wall ms |
| --- | ---: | --- | ---: | ---: |
| initial | 0.009999997913837433 | 原表面点与 +X 方向 | 1482 | 445.8990 |
| unchanged | 0.009999997913837433 | 同点／方向，缓存命中，当前采集 | 1482 | 247.2476 |
| changed | -0.004999998956918716 | 穿插与已算 SAT 数值依据 | 1643 | 238.0245 |

前两状态 observed。changed 保留 partial，nearest_witness 为 unknown／no_surface_witness_for_escape_metric，relation evidence 提供 `convex_sat`、严格零容差穿插、A 的 escape 向量 `[-0.004999998956918716,0,0]`。该向量没有充作最近方向、内部点或已执行动作。

三次实际查询共 4607B CLI stdout、4601B MCP 文本、931.1711ms CLI wall。每状态查询本身提供问题所需信息，模型是否仍补查尚未测。QA 操作者另外进行了 3 次 native 网格回读和 1 次固定顶点更新，均单列在 RESULT 与原始协议中。

后台实测累计为 3 次 selected capture、2 次 pair measurement、2 次 shared paired SAT、1 次完整 witness traversal、0 次 scalar surface traversal、0 次 fallback SAT／full capture。unchanged 不重算 pair，changed 生成新指纹。计数包裹原函数，无数值替换。更底层 PT／EE／点积总调用数和完整因果观测税未测，计数发布成本包含于实际 CLI／外层时间。

一次构建、一次新 venv、一次离线安装和一次安装身份只读检查完成。外层 wall 分别约 0.8104s、4.0089s、1.5239s、1.7669s。control 启动至清理内部 2.9727s，外层 3.1114s，CLI 时间为嵌套范围。首次定向外层 3.6161s、单项重验 0.4376s，完整实施从 01:30:15.5113058 UTC 开始，封存时刻和整体投入见 OUTCOME。

## 原件与收口

`MEASUREMENTS.json`、`INSTALLED_IDENTITY.json`、`control/RESULT.json`、逐状态真实 CLI／COUNTS、product／broker／worker 原件及构建 wheel 供复核。`EVIDENCE_INDEX.json` 只索引主要原件。新 venv 和构建 source zip 留在本地，Git 不重复封存整个安装目录。

service launcher 与实际 Blender worker 均 exit 0，watchdog 已回收，forced cleanup 为空。清理复查已知 PID 和本轮路径匹配为空，完整未观察进程树／句柄未测。无共享 GUI、默认安装、原资产、Google/API 调用或旧 usage 修复。旧失败与原件保留。本批完成回报后结束，工程结果不替代主线的实质优化机会评估和后续固定消费者对照。
