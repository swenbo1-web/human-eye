# 凹槽六格匿名几何质量独立复核

本次独立评分结论：六格均 **complete_correct，13/13**，合计 **78/78**。最终答案没有 unknown、缺项或错误确定结论，未发现额外无依据的几何宣称。该结论仅针对匿名质量，不评路线采用、时间、usage、成本或收益。

指定实施提交为 `4a90bbe95ef46c6666050ef1a1096fc6719c3b97`。读取范围为该实施树 `verification/m4_grooved_rail_consumption_001/runtime/handoff_01/public`、根消费合同及其引用评分段；未读取分组映射或其他评分者结果。本报告以实际 public 文件 SHA256 绑定输入；原始档案/提交一致性的全量审核由父任务另行处理。

| 匿名格 | 关系 | 距离 | 4 mm 判断 | 合法最近见证 | 唯一最近者 | 结论 |
|---|---:|---:|---:|---:|---:|---|
| answer_05363860e6cd01e3 | 3/3 | 3/3 | 3/3 | 3/3 | 1/1 | complete_correct |
| answer_199cffa37be50d12 | 3/3 | 3/3 | 3/3 | 3/3 | 1/1 | complete_correct |
| answer_1e64fe6d4aa9d4b6 | 3/3 | 3/3 | 3/3 | 3/3 | 1/1 | complete_correct |
| answer_2c2752bff20d064c | 3/3 | 3/3 | 3/3 | 3/3 | 1/1 | complete_correct |
| answer_3f52891e54cefc9d | 3/3 | 3/3 | 3/3 | 3/3 | 1/1 | complete_correct |
| answer_553b560ed3826c4e | 3/3 | 3/3 | 3/3 | 3/3 | 1/1 | complete_correct |

`RESULTS.json` 为每格列出全部 13 项状态、最终坐标、距离误差、见证证书索引、工具结果定位、过程业务错误，以及全部 public 文件的内容哈希。

## 独立几何计算

`score_geometry.py` 不导入或运行产品、Blender 或消费者代码。它从实际快照的 binary64 世界坐标构造精确 `Fraction(float)`，独立遍历每对 24×4 个三角形，共 288 对；比较双向顶点—三角形、所有边—边候选并检查边—三角形相交。所得三个全局最小平方距离均与 oracle 的有理数 **完全相等**，不是通过容差近似认同。

随后独立检查每个 Target 顶点在候选中及每个候选顶点在 Target 中的精确射线奇偶，退避穿过边/顶点或共面射线。所有顶点均在另一实体外部，且边界最短距离严格为正。这里使用已冻结 oracle 的嵌入闭壳资格作为输入前提；不声称重新执行了完整自相交资格审核。

| 对象对 | 独立真实距离（m，显示值） | 关系 | ≥4 mm | 真最近点特征 |
|---|---:|---|---|---|
| Target—Part_A | 0.0052500005143693625 | separated | 是 | Target 三角形 16 面内点—Part_A 顶点 0 |
| Target—Part_B | 0.002750000356851723 | separated | 否 | Target 边与 Part_B 边的内点 |
| Target—Part_C | 0.008500001624148858 | separated | 是 | Target 三角形 7 面内点—Part_C 顶点 0 |

Part_B 严格小于另两者，唯一最近。B 的同一合法见证可落在 Target 三角形 10 或 23，以及候选三角形 0 或 1；评分没有要求固定三角形编号。A、C 的候选顶点也各属于多个三角形。

每个使用的精确点对都附有有理数坐标、合法非负重心坐标、所属三角形和全局最小平方距离证据；这同时证明表面归属和全局最短性。通过结论不依赖“接近表面＋点间距相近”两项必要条件。

## 完整精度与最终舍入

四格 `05363860…`、`199cffa3…`、`2c2752bf…`、`553b560e…` 提供 binary64 完整精度见证。每一坐标分量均与独立精确最近点相容，误差不超过该分量的半个 binary64 ULP；最终文字坐标与工具记录也逐分量符合 1e-6 m。

`1e64fe6d…` 与 `3f52891e…` 的工具 stdout 仅输出小数点后 12 位见证，不能称其为原始完整精度坐标。本次直接构造并验证精确全局最近点，证明该点位于各工具坐标的 ±5e-13 m 舍入箱，以及最终每坐标分量 ±1e-6 m 误差箱内；因此这两格也有充分的合法最近见证。

六格最终文字的三对坐标和距离一致，实际误差如下，均远小于合同 1e-6 m 门限。

| 对象对 | 最终距离绝对误差（m） | 两端坐标最大分量误差（m） |
|---|---:|---:|
| Part_A | 4.856306373e-10 | 3.882407546e-10 |
| Part_B | 3.568517231e-10 | 4.989981117e-10 |
| Part_C | 3.758511419e-10 | 4.725788493e-10 |

## 过程记录与额外宣称

`answer_2c2752bff20d064c` 的首次请求包含不被接受的 `nearest_witness` fact 名，业务响应为 `status=error`、`tool_outcome=unknown`、`executed=false`、`execution_status=not_executed`。该错误完整保留在结果中。其第二次请求去除该 fact 名后返回测量结果，最终 13 项全部有依据；不能因最终正确抹去首次拒绝，也不能把已解决的过程 unknown 当作最终缺项。其他五格没有此类业务错误记录。

`answer_553b560ed3826c4e` 先输出 mathutils 变换的较低精度包围范围，后在计算距离前重新使用 NumPy binary64 世界变换；评分依据后续实际用于答案的见证和几何计算。没有据早期包围范围判定最短距离。

所有用于评分的 owner 输出文本均在对应消费者 `item.completed` 事件中找到相同文本，不把仅由 owner 产生但未确认送达的输出当作消费证据。最终 13 项之外，六格均未宣称全场无碰撞、壳体无自交或最近点对唯一。关于“全程只读/未移动/未保存”的程序行为陈述不增加几何分；观察到的代码与之相容，不能据本几何子审证明不存在一切瞬时修改。

## 来源与复现

| public 来源 | SHA256 |
|---|---|
| scoring/ACTUAL_SNAPSHOT.json | `6bb073b9aa29e7eecc5aa74ad2330cbb8fb5c5e06c79e70bf71091a33470ff52` |
| scoring/TRUTH.json | `2d072197f67f2d9860cb2ceb86c2782a7d4d2c3a71f1ed6d8be2487afc0eaa74` |
| scoring/SCORING_CONTRACT.json | `ac2d535d0addafd54cc7dd290baecf9fcdb13988a50bf04b04f3ec34e5d26215` |
| INDEX.json | `0d15bde51a73b56a17dc2962f0538ee4c72f5a5539c684c4ae9cfbe1e7dc94f9` |

全部答案的 SHA256 均与 public INDEX 记录一致；三份评分材料与 INDEX 哈希一致。离线脚本包含平行面、共面嵌套、非共面穿越、内部边—边最近点、四面体内外奇偶五项解析自检；均通过。运行命令：

```powershell
& 'D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe' -I -B -X utf8 'D:/hefe/verification/fixes/20261112_m4_grooved_rail_quality_review/geometry/score_geometry.py'
```

盲审限制：首次全文读取 public `TRUTH.json` 时，意外呈现该文件自带的资格阶段时间元数据；没有读取六格消费者时间、usage、成本、分组映射或别的评分结果，资格时间未用于判断。其后仅按几何字段读取。工具名称及业务内容本身仍可提示路线，故本审查不声称完全双盲。
