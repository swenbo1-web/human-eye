# SPATIAL-TASK-QUALIFICATION-001：最薄入口与资格预检

只读核对当前 `c0134088` 实施树、`fac9b437` 产品及 M2 harness，未执行产品、Blender、模型或安装。以下为根计划建议。

## 可直接复用的路径

沿用 `verification/m2_tight_directory_001/installation/READY.json` 的 `9.7.2+dir.r1` 隔离 entry、dependency Python 和 137 源摘要 `6acb3ac7…aea0bb`，无需重建安装。使用 `measurement/owned_native.py` 的 `NativeSession`、既有 `verification/m1_task_entry_001_eval/actor.py` 的 `Peer` 和 `preflight_client.py` 的真实 runtime PID/退出核验。Peer 使用普通工具集合，不能启用 spatial-task-only，否则没有 directory。

建议**一个预先封存的新 .blend 同时放装配和远处简单控制**，一次 owned Blender、一次 Peer，会话内不改场景。这样复用现成首尾文件/几何指纹，不为两份资产切换改生命周期保护。简单控制的两个盒体不作为装配关系候选；它们仍在全场目录覆盖内。

固定资产/题意/独立答案以后，一次有限序列即可：初始化和来源核对 → 原生 evaluated 清单与资格信息 → directory → 显式 target/candidates 的 task relations → 简单控制 pair → 独立原生计算与见证核对 → 关闭并记录真实 runtime/Blender 退出。无图、geometry 默认省略。只在预登记任务确实需要而已有见证不能表达时做一个明确补读，不能见结果后反复添加字段。

普通入口示意：

```json
{"include_image":false,"query":{"mode":"directory"}}
{"include_image":false,"query":{"mode":"task","target":{"id":"目录返回ID"},"candidates":[{"id":"候选ID"}],"requested_facts":["closed_solid_relation","surface_proximity","aabb"]}}
```

现有 `correctness/run_entry.py` 的 observe 包装直接断言 `isError=false`，本资格批应改**新 QA 控制器**为先保存完整请求/回执，再分类 host 拒绝、task partial/unknown、正常结果。不能遇到第一个域外结果便丢掉后续简单控制与关闭记录。不重跑 27 会话 M2 性能矩阵。

## 先挡住选题本身的域外失败

- directory 的 `_objects` 覆盖全部 mesh，包括隐藏物体；任何实例、Geometry Nodes、未支持的曲线/体等可使整个目录拒绝，1..256 对象。首批新装配用预烘焙静态 mesh，避免意外引入来源问题。**普通 evaluated modifier 并非在 directory/task 一律禁止**；更严格的静态三角网格限制属于 surface_nearest 路线，不能混用该域来判断显式 task。
- 主路径选现有显式 target + 1..3 candidates，不换成全场 nearest。两壳总面数 ≤4096、面数乘积 ≤16384；closed-solid 另有 262144 work、16384 自交/交叉 pair 总计及 16384 ray 检查预算。仅低于 4096 面远不足以保证准入。
- 每个选中对象须为一个连通、闭合、可定向、无自交且非零体积的三角壳；不允许孤立顶点、重复/退化面或多个 disconnected shells。孔洞可存在，靠多个互不相连块拼装成一个对象则可能 `multiple_shells`。不要把 M2 的孤立顶点 fixture 原封不动拿来作精测目标。
- 新任务难点可来自非凸、不同姿态、假近邻和局部穿插；无需数千面。可预先以目标约 64–96 面、单候选 ≤48 面作为设计工作区，再逐对计算面数乘积与最坏 self/cross pair 量。这个区间只是预估，实际工作预算及 ambiguous boundary 仍以回执为准。不要靠测后减面改题直到通过。
- 稳态缓存不是准入障碍；使用新 QA 会话、固定源代，先目录再 selected 能自然揭示实际重复采集。资格结论不需要十次热循环或跨修改事件矩阵。

## 原生独立计算必须另接，不能误用旧两步基线

`measurement/sample.py` 的 native two-step **第二步仍调用产品 task**：它只比较首步目录策略后接同一产品精测，不能拿来当本批独立原生求解。

复用 `NativeSession.run` 执行一份 QA-only 原生计算脚本，禁止 import/copy 当前产品的 surface_proximity、surface_geometry、task_query 求解实现。原生读取同一 `evaluated_get(graph).to_mesh()`、evaluated matrix、单位和实际 triangulation；不能用 raw `obj.data` 与 evaluated 产品相比，也不能以 `mathutils matrix @ vector` 的 float32 舍入结果冒充产品 binary64 世界坐标。统一记录原始 evaluated 坐标/矩阵和发布算术；离线独立 Fraction/高精度答案绑定这些实际二进制输入。

独立 native 方法可利用该装配的明确几何构造、宿主库或完整的面/边候选计算；应先写明它如何证明距离下界/上界、内部重叠与孔隙。单次 BVH nearest-to-vertex 不等于任意两表面的最近距离，边-边最短也须覆盖；仅无三角相交不排除实体包含。此阶段的手写 QA 算法属于任务资格真值，不是“大模型已能原生答对”的成绩。

## 最小回报分母

固定新装配 1 个、简单控制 1 个；逐对象源域/三角数量，逐对 closed relation、surface distance、status/reason，分类与距离各自 unknown 不互相覆盖。核真实最近点在表面、距离、交叉三角/位置证据以及来源一致性；主任务需要完整集合时不得把 best-known 当 complete。记录实际执行、拒绝、未运行，保存新题无法准入或原生计算不能独立核验的结果后交回，不改产品门槛。

一次会话时间/调用/载荷可作为资格成本记录，不能当稳定收益 A/B。不要新增消费者、默认切换、Hook 或复杂场景性能承诺；资格通过后由根决定唯一后续工作。

## 最终具体计划复核（2026-11-12）

**通过；未发现执行阻塞或必须修改的口径错误。** 本结论针对根计划 `docs/SPATIAL_TASK_QUALIFICATION_001_PLAN.md` 的 G508 资格复用版本，取代上文“另造低面数新装配”的建议；本批目的就是在实际公共链核实规模缺口，不应为使准入通过而减面。

本轮只读复核了计划、当前 `task_query.py` 受理及最近分离汇总分支、`surface_proximity.py` 准入常量、M2 `READY.json`，并独立解析 G508 冻结清单：原12件确为两件256顶点/508面及十件32顶点/60面，加两个8顶点/12面控制后，14件/848顶点/1640面准确。三个面数乘积258064、30480、30480均超过16384；这属于待实机确认的预期拒绝，不是计划阻塞。

`target + 3 candidates` 与三项 `requested_facts` 可由现有普通工具受理；目录、装配、控制三次业务观察在同一固定资产会话内可执行。计划已要求 QA 在保存 partial/unknown/拒绝后继续简单控制与正常关闭，不需另开产品工具或追加审批。冻结 oracle 的容差确为 `1e-6 m`，计划也先绑定实际 evaluated 输入而非直接套名义参数；仅三候选、且独立答案均为 separated，因而最近分离与 unsigned 距离在该固定任务上口径一致，没有宣称全场最近或消费者收益。

本轮未执行 Blender、产品入口、oracle 求解或模型；实际 evaluated 绑定、三对拒绝与控制成功留给已授权资格序列，不能将本次静态可执行性通过写成业务通过。
