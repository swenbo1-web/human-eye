# T2 / T3 资产、独立真值与任务评分复核

结论：**几何与oracle通过；正式消费者GO前需解决一个题面/评分精度不一致。** 独立数学重算支持T2唯一最近1/256米、T3唯一最近1/128米，全部候选都有有效下界和实际表面见证。没有更改题目、资产、评分或产品，也不建议扩大本批任务。

固定准备提交 `82e976cd425fae9703399148a8938bd6099d486f`，产品固定 `7411ac7`。审查对象为实施工作树的 `verification/m1_task_entry_001_eval/tasks/T2` 与 `T3`，不是根旧源码。自身AL句柄恢复为parent_read_only，未借根句柄或写父任务。

本轮独立执行的是Python标准库Fraction纯数学核算、文件哈希与JSON比较；未导入作者exact_geometry/生产算法，没有运行Blender、产品或模型。保留完整逐候选结果于 `T2_T3_INDEPENDENT_MATH.json`。已检查保存资产SHA、实际快照SHA、前置FREEZE的源/题面哈希及评分绑定相符。实际快照来源由既有后台Blender导出记录提供，本轮没有重新从.blend导出，所以不把作者导出执行冒称本轮执行。

## 实际坐标与覆盖证明

逐对象以Fraction重算所有局部顶点乘实际matrix_world再加平移，精确等于快照的native-world坐标；单位为1米。两题均为dyadic精确坐标、单位旋转/纯平移、无父级/修改器、非退化三角形，所有顶点都被面使用。不存在名义构造距离与实际保存浮点网格的差额。

T2使用与作者裁剪面积方法不同的平面有向边界链核算：把实际三角面按所在平面分组，验证组内法向符号一致、内部边抵消后的有向边界与期望矩形/C形边界逐区间完全一致，且总有向面积一致。这确定完整平面覆盖，无遗漏或重复覆盖。所有全局有向边有唯一反向伴边，实际体积为3/4立方米。目标实表面正是三个矩形体内部不重叠并集的外边界；八个候选也逐面核实为各自实际AABB的完整盒面。

随后用三个体积单元对每个候选求轴区间分离平方和下界，再检查达到最小界的点分别属于目标与候选的实际三角形（精确重心系数非负、和为1）。体积集合界不高于表面距离，实际表面见证达到该界，所以每对全表面距离精确成立，不是只验证oracle给出的赢家。

## T2逐候选结果

| 候选 | 精确表面距离平方（米²） | 含义 |
|---|---:|---|
| Mesh_097A63 | `1/65536` | 唯一最近 |
| Mesh_B19194 | `1/16384` | 严格更远 |
| Mesh_662CF6 | `9/65536` | 严格更远 |
| Mesh_2E2F54 | `13/65536` | 严格更远 |
| Mesh_A89EE8 | `1/4096` | 严格更远 |
| Mesh_A7A7A6 | `25/65536` | 严格更远 |
| Mesh_A9E055 | `9/16384` | 严格更远 |
| Mesh_3307B2 | `49/256` | 严格更远 |

唯一最近 `Mesh_097A63`，距离 `1/256 m = 3.90625 mm`；第二名为 `Mesh_B19194`、1/128米，平方距离差3/65536米²。赢家实际见证可取 `(2,1/8,0)` 与 `(513/256,1/8,0)`。

中心排序反例确实成立：目标与 `Mesh_3307B2` 的原点/实际AABB中心重合，中心距离0，但表面距离7/16米，远非最近。原点由各自AABB中心设定，故这里只证明“原点/AABB中心排序”失败，不泛指所有可能的质量重心定义。独立遍历全部顶点对还发现：顶点法选 `Mesh_2E2F54`（平方距离1037/65536），而真正赢家的最小顶点对距离平方为1281/65536；因此T2也会误导纯顶点对近似。

T2有8候选，其中3个候选与目标AABB重叠、下界为0，必须结合凹部实表面排除。仅按全局AABB距离排序不能得到正确答案。C形闭合拓扑确实不同于旧齿状/梳状资产，不是只改名字。

## T3支撑界、完整等号集与逐候选结果

实际目标全部位于z≤0，所有候选位于其各自z≥正值的半空间。对每个物体遍历全部三角形与支撑平面的接触：无整三角形躺在支撑面；平面内的全部边组成连续线段，8个支撑顶点/7条边覆盖[-1/4,1/4]，不存在断口或遗漏的平面等号点。

独立对支撑边两两求精确线段最近点，检查点属于原三角形。得到的上界逐项等于从全部实际顶点的x/y/z极值导出的AABB距离下界，因此每个候选都已完成全表面距离证明；折带其余所有三角形不能越过该半空间界。

| 候选 | 精确表面距离平方（米²） | 最小顶点对距离平方（米²） |
|---|---:|---:|
| Mesh_8CC127 | `1/16384` | `129/16384` |
| Mesh_696772 | `5/65536` | `5/65536` |
| Mesh_879214 | `5/65536` | `261/65536` |
| Mesh_79F58B | `25/262144` | `1049/262144` |
| Mesh_A83E57 | `9/65536` | `521/65536` |

唯一最近 `Mesh_8CC127`，距离 `1/128 m = 7.8125 mm`。目标z=0等号线为y=0、x∈[-1/4,1/4]；赢家z=1/128等号线为x=0、y∈[-1/4,1/4]。达到下界还需x/y相等，所以唯一最近点对正是 `(0,0,0)` 和 `(0,0,1/128)`。两者都不是实际顶点，位于支撑边内部；快照的相邻支撑端点跨过0，精确三角形成员核算通过。

纯顶点对法确实会选错物体：它选 `Mesh_696772`，距离sqrt(5)/256米，约8.734640537毫米；真正赢家的最小顶点对距离为sqrt(129)/128米，约88.73毫米。所有顶点对均比真实7.8125毫米更远，不能用顶点采样代替表面距离。

必须保留另一事实：**T3五对的AABB距离全部恰好等于真实表面距离，且中心排序也恰好选中真正赢家。** 它只证明顶点对近似会错，不证明AABB排序或中心排序会选错。采用保守AABB界、再补能达到界的实际边见证，是合法且高效的原生解法；评分不得因它没有枚举所有三角对或没有调用插件而拒绝。

## 空间代表性与工作量

T2目标原始28三角面经过一次1分4中点细分成为112面，实际几何完全不变；208总面及10752潜在三角对不是新增空间机制。T3折带有真实的多平面折弯和无顶点的最近边特征，但沿带宽均匀细分不改变表面，更多远离最近点的折带面主要增加工作量；其轴对齐半空间提供很紧的界。

因此这两题是小规模、受控的非凸完整覆盖/边内部表面距离任务，适合本轮M1自然选入口与正确消费的筛查。它们不是大型资产、高密遮挡场景、旋转变换压力、视觉发现或所有复杂场景能力验收。不要以潜在三角对数定义实际算法工作量；允许原生根据可证明的几何结构直接求解。

## 题面与评分

两份PROMPT都只给真实目标名字、全场其他网格、表面最近、并列集合、毫米单位及只读要求；不泄漏赢家/模式/工具/构造/私有角色。目标名字及排序为不含角色的标识，没有从名称直接推出答案的证据。T3开放面完全符合无符号表面距离题，不要求闭合实体分类。SCORING_CONTRACT对T2/T3要求正确全场集合、单位、有效全覆盖依据，T3不强制提供最近点坐标，与实际难点一致。有效下界+表面见证即可，不能新增“必须用完整三角枚举”之类门槛。

**需在开跑前解决：题面未告知1微米输出精度。** PROMPT只说“以毫米给出最小间隙及依据”；SESSION_RULES也没有精度要求。但SCORING_CONTRACT要求每个最终陈述距离误差≤1e-6米。例如T2回答3.91毫米，误差3.75微米；T3回答7.81毫米，误差2.5微米，均是符合题面常见展示方式的四舍五入，却会被现评分判错。不能在结果出来后再临时决定是否接受。

根应在正式消费者前选择并统一冻结一种口径：所有组共同题面明示所需精度；或者预先定义可接受展示舍入与实际工具证据的对应规则。只需对齐题面/评分说明，不需改变几何、算法或样本，也无需为此重新做Blender几何验收。本复核没有修改这两项，等待根对该差异作明确处理。

数学truth中的suggested_answer_tolerance_m为1e-5而最终评分选1e-6，本身不使精确oracle错误；关键仍是最终对模型可见的任务要求应与判分一致。

## 文件绑定

- `D:/hefe/verification/fixes/20261111_m1_eval_ready_review/T2_T3_INDEPENDENT_MATH.json`：`a42d42764ac3518f960a4b111412f5d4579d8708f878301f1e66bbb325caadb7`
- `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001_eval/SCORING_CONTRACT.json`：`56792e94240c715bb92c16c6a2f66fe9602a72889a0ed9996fd752618ecd8f9a`
- `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001_eval/SESSION_RULES.txt`：`1cba377e467f9e2af4ac1a1ed9e09ef851be39ef9a9577edaeeea75cefdfaeb1`
- `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001_eval/tasks/T2/SPEC.json`：`91eb3429b90a99ed8bc015edf89de490c025b7a15a13d3b309f5947d29c32136`
- `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001_eval/tasks/T2/PROMPT.txt`：`c2c5afc6ce329d96268c9ee58701f6f659b8cd6a190cc46e65cc219484913a6f`
- `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001_eval/tasks/T2/TRUTH.json`：`6cef7ce5e55e1512955446de583f93dfc95a0c7ba86fc0fa8f22d133ea926264`
- `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001_eval/tasks/T2/FREEZE.json`：`16e5650cb2f38ae79b6a7fc6e99a1130aa6bef2980c98e333f40ec66551ffb38`
- `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001_eval/tasks/T2/certify.py`：`90ea48e68924ddd8f8ec36361a84d1f60166626da68e8b51ddb42d31d3799b54`
- `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001_eval/tasks/T2/exact_geometry.py`：`c8d122bcc152ad5e89ba30c48d79845553560a1834ae39fd2120b34ecaca6a15`
- `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001_eval/tasks/T2/build_asset.py`：`5f2aa240ed58eb2e039c5158bf67a5db0121551abe1179447a4234822631cc8b`
- `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001_eval/tasks/T2/export_evaluated.py`：`2b0d396ab3f426b80d56e445d6fde5d2c095c95902b8647932f37a754e4e9811`
- `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001_eval/tasks/T2/assets/evaluated_mesh.json`：`904260c4ab32fa49090ac05fa3e5903ed42d946cc35c393aa2bdd8bf0a68e774`
- `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001_eval/tasks/T2/assets/scene.blend`：`5a9e3cccfe3a3d72bac0f9d3d8fea23a6e3ee1115ec7e97c3984900e60d8fce4`
- `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001_eval/tasks/T3/SPEC.json`：`b7708857b2de23a7dd1fed8cb46f25e8effc4b499ebe0fd7eed5864012def843`
- `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001_eval/tasks/T3/PROMPT.txt`：`2b144904aaf1eac33231e9744ef3c3558e89234415d4b46f47ec76fadf1c081d`
- `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001_eval/tasks/T3/TRUTH.json`：`a4a2a7a1286b87cd9246b00ab7f037244bd9728439406f24ae204a6e43a8f6c3`
- `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001_eval/tasks/T3/FREEZE.json`：`e472f5e61fb68abf65ef08c5b1e1f0d1825c29f7d41704ee5ee5e935208da81a`
- `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001_eval/tasks/T3/certify.py`：`38fdc9334cb8f491dd789535cdb69cf02d595d1568f30375ab17debdc9bca483`
- `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001_eval/tasks/T3/exact_geometry.py`：`c8d122bcc152ad5e89ba30c48d79845553560a1834ae39fd2120b34ecaca6a15`
- `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001_eval/tasks/T3/build_asset.py`：`5f2aa240ed58eb2e039c5158bf67a5db0121551abe1179447a4234822631cc8b`
- `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001_eval/tasks/T3/export_evaluated.py`：`2b0d396ab3f426b80d56e445d6fde5d2c095c95902b8647932f37a754e4e9811`
- `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001_eval/tasks/T3/assets/evaluated_mesh.json`：`426cd1678540b70a750be9f4ad844b77096c236079f4c66fe72a7cc424b5c2b2`
- `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001_eval/tasks/T3/assets/scene.blend`：`7fb7d648644d35c8e1c07c6be7f5ff741b4b32230f0e3eb18a461330b6f90d4c`

## 根复核决定（本报告完成时）

根已接受隐藏精度问题，决定在正式消费者前统一公开误差要求≤0.001毫米，并要求输出至少保留到0.001毫米；不放宽评分，不改T1/T2/T3资产或7411产品。共有规则和各组实际模型输入须重新冻结并记录新哈希，不能继续宣称原SESSION输入字节未变。本审查尚未收到或核验这项修正后的输入，只记录已确定的处置；几何证明可沿用。

T3易由紧AABB下界加实际边见证求解的事实已向根明确报告，并作为固定解释边界保留，不因后续原生表现好而改题或否定这种正确解法。根另行处理运行器计时起点问题，不属于本T2/T3几何审核的执行或结论。
