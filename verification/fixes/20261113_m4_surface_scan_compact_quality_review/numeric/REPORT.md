# 九匿名答案独立数值与完整性评分

2026-11-13。**未发现最终答案的真实数值或集合质量缺陷。九份内容均 complete_correct；按冻结合同，主分类是 7 complete_correct、2 execution_failure，不能汇报为九格全部通过。**

只读取 `quality/public/` 的 42 文件、固定 r2 匿名包与根计划。没有打开 private、cells、runtime、usage、分组映射或其他评分者输出；没有运行作者评分程序，没有启动 Blender、模型或 API，没有更改作者树及 Git。

## 独立依据

- r2.zip SHA-256：`5d2ca81f18285da1fff1a05b9c0c03deb97966f57db86fa022c8ecc0b091f54f`。42 个公开文件逐字节匹配包中相应成员。
- 精确 truth SHA-256：`a0f14b1a48601590445ce5e2d13bb34f56647caa2acedf3eeac97b32e8a656c7`。
- 实际几何快照 SHA-256：`f8a578f78004a21e611c76d47506c5290f6015e7343e67b3b094a9e54da9884b`；truth 的 snapshot 绑定一致。
- 题面 SHA-256：`6a78e38a474647c0c0c49558be215864cb672932273b3e15ca6ba7f9fa02b4fc`，与根固定计划一致。

新写标准库解析器统一展开普通三列表、逐对象 `对象：距离` 分组表及明确声明距离为零的分组表。无零值声明的表不自行补零；只将匹配表计入匹配集合，正文中的“最近未匹配对象对”另核，不误作额外匹配。九份最终文本都已独立通读，不以工具内容替代 final。

逐一使用 `Fraction(binary64(0.002))²` 核 276 对精确平方距离的阈值成员，得到 71 对，其中 43 个确切零、28 个正距离。每个最终数值按十进制原文解析，使用 **[max(0, d−0.000500001), d+0.000500001] mm 的精确平方区间**与真值比较，不依赖有舍入的 oracle sqrt。RESULTS 的十进制误差只是可读诊断，判分使用上述有理数区间。

本轮复用固定 SHA 的既有精确 oracle，**没有重算全部三角形对最短距离**。额外独立检查了快照 24 对象、530 顶点、978 三角面，所有坐标有限、没有空三角网格；用有理数叉积核 978 面均非退化。

## 逐答结论

| 匿名答案后缀 | 主分类 | 最终内容分类 | 正确匹配 / 应有匹配 | 缺漏/额外/重复/错距 | 最大距离误差 mm |
|---|---|---|---:|---|---:|
| 11a4c8ec025d6a16 | complete_correct | complete_correct | 71 / 71 | 0 / 0 / 0 / 0 | 0.000000493361 |
| 3990a6a4bf660eee | **execution_failure** | complete_correct | 71 / 71 | 0 / 0 / 0 / 0 | 0.000469684868 |
| 4a4a77418ce1424c | complete_correct | complete_correct | 71 / 71 | 0 / 0 / 0 / 0 | 0.000000493361 |
| 4c4c0fa03baa1ee8 | **execution_failure** | complete_correct | 71 / 71 | 0 / 0 / 0 / 0 | 0.000000493361 |
| 89dab9e90194dcbf | complete_correct | complete_correct | 71 / 71 | 0 / 0 / 0 / 0 | 0.000000493361 |
| 9297e204cfb1d7f7 | complete_correct | complete_correct | 71 / 71 | 0 / 0 / 0 / 0 | 0.000000493361 |
| 9ee63c86af8ff66d | complete_correct | complete_correct | 71 / 71 | 0 / 0 / 0 / 0 | 0.000000493361 |
| bb2c246d257d7867 | complete_correct | complete_correct | 71 / 71 | 0 / 0 / 0 / 0 | 0.000469684868 |
| dccb27e1bc47c94f | complete_correct | complete_correct | 71 / 71 | 0 / 0 / 0 / 0 | 0.000000493361 |

总计 **639 / 639 匹配行正确**，各答案显式以毫米表示，非零值满足至少三位小数，所有零值对应精确零距离。各自明确说明全场检查完整；`4a4a…` 的原话是“扫描状态为完整”，与“检查完整”同等有效，不强求固定措辞。

两 failed 格公开 INDEX 均记录 stream disconnected / response decoding transport error，`consumer_valid_completion=false`。即使最终文本存在、与 CLI 文本一致且内容正确，也不更改这两格执行状态，不替补、不排除分母。9 格均开始、9 final 存在、7 completed、2 failed、0 not_run。

## 额外确定性陈述

未发现额外确定性错误：

- 24 网格对象、978 三角形、276 无序对、71 匹配、43 零/28 正值、205 非匹配与固定答案一致。
- 写出 164 个界限排除、112 个保留、41 个实测非匹配的答案，其统计与真值一致。
- `3990…` 指出的最近非匹配 `Obj_002 — Obj_008` 及 `3990…`、`bb2c…` 给出的约 2.250 mm 均符合固定精确真值（约 2.24999897182 mm）。没有错误把该对象对列为 ≤2 mm 匹配。
- 声称全部 276 对另行复核的答案，公开业务回执中确有对应全量计数与一致性输出。此核查只支持其额外方法事实，不将“必须全量重算”加为评分条件。
- “不存在空网格、退化三角形、非有限坐标”与实际快照独立检查一致；“1 Blender 单位 = 1000 mm”与快照单位一致。
- 各答案均保留表面距离与实体穿入/包含的区别，没有把表面非匹配推为实体无碰撞。
- 公开来源记录的资产 SHA、初末文件 SHA、终态几何一致性相符，支持当前固定来源；这是作者原记录的交叉核对，不是本轮重跑写保护，也不能证明没有恢复原状的瞬时修改。

## 评分过程及限制

最终自写校验 **453 项通过，0 失败**；其中含解析器关键边界自检和固定输入绑定。评分证据是逐行 639 数值/集合记录，不能把断言条数当作 453 个独立场景。

保留 `ATTEMPT_01_RESULTS.json` 和 `ATTEMPT_01_CHECKS.json`：第一版解析器只找“检查完整”，漏掉 `4a4a…` 的同义“扫描状态为完整”，曾产生一项提取失败与 temporary incomplete。逐字人工复核后扩展等价声明识别并补自检，未改变合同。这是复核解析器问题，不是答案缺陷，不能将初次分类留作正式质量结果。

有限匿名如实保留：工具名、schema、原始业务文字可能揭示路径；审阅公开业务数值来源时，一段原生 stdout 内顺带出现了 elapsed 数值。没有访问私有耗时/usage/分组映射，也没有使用该值或推测组别参与判分。本报告不分析采用率、机制优劣、时间、token 或费用。

自身 AL 句柄仍显示旧子 assignment，已读取新父任务 `60f80757` revision 1；按父 Agent 明确的新派单执行离线评分，没有借根句柄、没有覆盖父任务，不称旧 assignment 已归属新阶段。

此次只封数值/内容质量。精确全三角求解、原始私有来源重绑、成本和组别比较均未运行或由其他阶段承担。两个执行失败会影响正式同质量收益门，不能用“内容九份正确”绕开。

复算命令：

```powershell
& 'D:\hefe\.human-eye\releases\9.7.2+20261028.support.discovery.r1\.venv\Scripts\python.exe' -I -B -X utf8 'D:\hefe\verification\fixes\20261113_m4_surface_scan_compact_quality_review\numeric\score.py'
```

输出：`RESULTS.json`、`CHECKS.json`、九份 `answer_*.json` 逐行指标、`INPUT_HASHES.json`，以及审计实现 `score.py`。
