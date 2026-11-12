# 凹槽导轨资产的独立资格核验

资格结论为 **passed**。

仅对已保存资产进行标准库离线分析。几何判断使用实际 binary64 世界坐标的 Fraction，零产品、Blender 和模型运行。名义间隙仅在实际求解结束后交叉核查。

## 实测闭壳

| 对象 | 点 | 三角 | 边 | 自身三角对 | 检查 |
|---|---:|---:|---:|---:|---|
| Target | 14 | 24 | 36 | 276 | 通过 |
| Part_A | 4 | 4 | 6 | 6 | 通过 |
| Part_B | 4 | 4 | 6 | 6 | 通过 |
| Part_C | 4 | 4 | 6 | 6 | 通过 |

自体检查仅允许交集落在合法共享拓扑顶点或边，非法额外交叠拒绝。互体 288 个三角对独立计数，含共面相交。包含关系另用双方全部顶点的有理射线奇偶检查，保留方向、命中三角、参数及避退化记录。

## 实际真值

| 对象对 | 关系 | 间隙毫米 | 至少 4 毫米 | 最近特征 |
|---|---|---:|---|---|
| Target / Part_A | separated | 5.250000514369362 | 是 | 通过 |
| Target / Part_B | separated | 2.750000356851723 | 否 | 通过 |
| Target / Part_C | separated | 8.500001624148857 | 是 | 通过 |

限定三个候选的最近者为 Part_B。每个三角对保存精确距离平方、全部同值最小候选、三角 ID、重心和边参数。

平方根采用整数平方根构造 70 位小数外向区间，并将最终 Decimal 两端重新转为 Fraction，验证 lo² ≤ min_sq ≤ hi²。

A 通过全部实际支撑三元组核实在 Target 凸包内，同时以实际局部凹截面核槽空域。材料分离的主证据为实际世界几何的相交及有理射线检查。A 须保持槽底面内点，B 须保持非平行边的严格内点，C 须保持端盖实际材料内点。

矩阵和顶点未吸附回理想值。实际矩阵的 binary32 表示变化以及世界 binary64 求值残差独立保留。局部截面属于交叉核查，未替代世界全集距离和实体判定。

## 资格检查

- PASS all_input_design_checks
- PASS algorithm_synthetic_checks
- PASS four_valid_closed_shells
- PASS 288_interbody_and_294_self_pairs
- PASS three_material_pairs_separated
- PASS A_in_actual_hull_and_groove_void
- PASS A_vertex_floor_face_interior
- PASS B_nonparallel_edge_interiors
- PASS C_endcap_actual_material
- PASS nominal_crosscheck_within_1e_minus_6_m
- PASS threshold_yes_no_yes
- PASS unique_nearest_Part_B
- PASS input_hashes_unchanged

离线分析窗口为 876.329 毫秒，文件发布窗口另存 RUNS.jsonl。此处是资格制备成本。

[完整真值与证书](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_transfer_001/oracle/TRUTH.json) [独立算法](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_transfer_001/oracle/exact_geometry.py) [离线入口](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_transfer_001/oracle/exact_oracle.py) [来源 SHA](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_transfer_001/oracle/SOURCES.json)
