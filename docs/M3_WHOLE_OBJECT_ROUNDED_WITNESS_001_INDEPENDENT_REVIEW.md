# M3 斜面精确来源独立复核

2026-11-22。`ae14344ea3aa654c710f2329bd4aa4423f7af9c4` 的精确来源通过目标工程验证，独立准入因闭壳关系回归暂缓。证据 `a1dac20030ea2b6546c24bbb9e89a266681929ef` 的 ZIP 含 2,425 件、4,957,133 B，摘要 `76fe1fff4f1fb880f69186f095cbe1e228ca639b0d8e499b47789bf0dd81abda`。独立核对 Git ZIP 全成员集合、长度、SHA-256 和 CRC。产品、证据远端均与提交一致。 [工程报告及原件](https://github.com/swenbo1-web/human-eye/tree/a1dac20030ea2b6546c24bbb9e89a266681929ef/verification/m3_whole_object_rounded_witness_001)

21 对象装配的 210 对保留原距离、方向、状态及显示点。202 对的严格来源保持，8 对的精确世界点对恢复，真实树留出 N02→N03 保持三角 38/3、99 个节点，候选正文 2,470 B。五个新增病例的冷、热原回包共报 20 个端点。逐一按原捕获三角做有理归属核验，均精确在面内，舍入后与原显示点一致。实装 stdio 56/56、固定 CLI 回放 84/84。隔离证据 RTT 中位冷 17.698→15.677 ms、热 9.896→9.367 ms，标准端冷 14.519→17.429 ms、热 9.223→9.283 ms。五个附证冷样本的精确检查和投影中位为 51.3 和 14.0 μs。各臂串行封存回放时钟仅作诊断。原套件两版都是 121/122，同一旧替身漏参数。 [公开回包及用量](https://github.com/swenbo1-web/human-eye/blob/a1dac20030ea2b6546c24bbb9e89a266681929ef/verification/m3_whole_object_rounded_witness_001/REPORT.md)

另用同一解释器分别加载基线和候选的已安装模块，逐字节核对 `surface_proximity.py`、`surface_geometry.py` 与 `task_query.py` 后运行单位闭壳斜交。A 为原点单位立方体，B 平移 `(0.75,0.4375,0.125)`，两版均为 `penetrating`，证书 `transverse_boundary_interiors`，三角 6/4。基线 `_closed_solid_fact` 交付 `local_evidence.point_world_m:[1.0,0.4375,0.25]`，候选交付 `[[1.0,0.4375,0.25],[1.0,0.4375,0.25]]`。共享 `_publish_points` 改成同时返回显示点对和精确点对，旧 `surface_geometry` 调用直接取了第一组，随后闭壳和 `spatial_relation` 回退照样公开这一字段。独立用当前已安装 `task_result`、`SpatialSceneCache` 及网格对象复核了四种正向关系事实组合，均复现。原工程矩阵的标准端冷、热样本只测了单项距离，未覆盖成功穿透定位。 [差分](https://github.com/swenbo1-web/human-eye/commit/ae14344ea3aa654c710f2329bd4aa4423f7af9c4)

保留本批原通过记录和独立兼容拒收。下一项只做[闭壳定位兼容恢复](M3_WHOLE_OBJECT_ROUNDED_WITNESS_COMPAT_001_PLAN.md)。已初核另一装配的 BVH 留出 N02→N04/N05，当前可用精确来源，距离 0.09927311939755278／0.392124534572486 m，待恢复后再决定是否进入消费对照。
