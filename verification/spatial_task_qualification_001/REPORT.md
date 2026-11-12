# SPATIAL-TASK-QUALIFICATION-001 资格核验记录

日期为 2026-11-12。资格批完成，装配业务状态为未完成，简单控制通过。管理员深审待完成。

## 固定来源与任务

产品为 fac9b4373575d653cc96f39f1dcb225300cd5977，137 源摘要为 6acb3ac7f014a590a279994f44be07c581af53a2da4dafae8dba9cd58eaea0bb。复用隔离安装 9.7.2+dir.r1，准备提交为 a4f830be。来源文件与安装的137项源字节已经核对。

资产复用既有 SCALE-DIAG/SCALE-OPT 合成 G508，原12件精确绑定后，在私有副本添加两个边长2米的控制立方体。实际为14对象、848顶点、1640三角面，单位米、frame 1、subframe 0。派生资产 SHA256 为 27f197a8cc312832382ae06cb633cbf846f20a1a22797909a15dfda8513ade46。

这是既有合成资产的资格复用。真实用户资产覆盖、新未调参任务泛化与模型收益均待验证。业务分母固定为1个装配任务、1个简单控制、14对象目录、3个装配对和1个控制对。

## 逐项业务结果

14对象目录全部完成，范围、中心和来源已逐项匹配实际 evaluated 快照。装配请求的4个AABB均可测。

| 对象对 | 独立距离区间 mm | 独立4mm判定 | 产品实体关系 | 产品距离与定位 |
|---|---:|---|---|---|
| Target / Peer_000 | [3.000005904956, 3.000005904956] | 不满足 | unknown | unknown |
| Target / Competing_001 | [4.999987091380, 4.999987091380] | 满足 | unknown | unknown |
| Target / Near_003 | [12.000011060800, 12.000011060800] | 满足 | unknown | unknown |

三对独立闭壳关系均为 separated，登记三候选中唯一最近件为 Peer_000。产品的 nearest_separated_complete=false、nearest_separated_ids=null，3项4毫米要求均无法由本次产品事实完成判断。unresolved_distances 为空对象，unresolved_relations 仍有3项，最近判断按完整状态解释。

独立证书的实际三角见证使用世界米，下面坐标按展示精度舍入，原始有理重心和完整数值保存在 ORACLE.json。

| 候选 | Target见证位置 | 候选见证位置 |
|---|---|---|
| Peer_000 | (0.9579902934, 0.2961424935, 0.2400656858) | (0.9562832083, 0.2984078721, 0.2410423923) |
| Competing_001 | (0.9500806551, 0.3173591895, 0.1770311146) | (0.9472355263, 0.3211348034, 0.1786589513) |
| Near_003 | (0.8985557830, 0.2785324174, 0.1770311157) | (0.8917274499, 0.2875939225, 0.1809379376) |

简单控制的产品结果为 separated、距离1.0米，公开见证为 (11,-1,-1) → (12,-1,-1)。独立 Fraction 核对确认两点均在实际三角表面，点距精确为1米。独立证书采用 (11,0,0) → (12,0,0)，对应另一组合法见证。

## 实际拒绝层

| 装配对 | 面数 | 理论面数乘积 | 16384乘积门 |
|---|---:|---:|---|
| Target / Peer_000 | 508 × 508 | 258064 | 超出 |
| Target / Competing_001 | 508 × 60 | 30480 | 超出 |
| Target / Near_003 | 508 × 60 | 30480 | 超出 |
| Control_A / Control_B | 12 × 12 | 144 | 通过 |

三装配对的面数总和与顶点规模均在原4096准入范围内。实际 selected capture 已成功交付4对象、576顶点、1136三角面、1704边。公开拒绝原因分别为 surface_geometry_work_limit 与 closed_solid_geometry_work_limit。固定源码 surface_proximity._admit 的乘积预检及 surface_geometry 的错误映射与回执一致。

现有 observe.task_work 诊断中，每个装配对的 surface validated_faces、triangle_pairs、aabb_bound_tests 和 feature tests 为0；closed node/leaf/pair/ray 等已发布计数为0、work_units为1。这些值与前置准入拒绝相符。底层未插桩调用和其它内部访问量为 unknown。精测调用入口计数为 surface 3次、closed 3次，不能把入口次数当成完成的精测对数。

控制在同会话随后完成，closed work_units=708、validated_faces=24、self_pair_tests=108、node_pair_visits=33、leaf_pair_visits=132；surface triangle_pairs=144、intersection_tests=104，使用共享准备。

## 成本与生命周期

以下均为单次归因窗口。完整工具时间采用实际 Peer 请求到回执，桥字节包含所在消息封装。

| 阶段 | 耗时 ms | host RPC | 桥TX B | 桥RX B | 可见事实文本 B | 已返回见证值 B |
|---|---:|---:|---:|---:|---:|---:|
| QA evaluated快照 | 54.9257 | 1 | 2912 | 127753 | QA原件 | QA原件 |
| 目录 | 57.4132 | 1 | 88787 | 6697 | 6448 | 0 |
| 装配精测 | 45.9290 | 1 | 1555 | 70247 | 5374 | 0 |
| 控制精测 | 37.3674 | 1 | 1573 | 3603 | 3087 | 76 |

完整宿主通信共5 RPC，包含QA快照1次、业务3次、关闭1次。TX为94844 B，RX为208362 B，合计303206 B。关闭请求17 B、响应62 B。产品stdio全序列TX 1647 B、RX 42288 B，含4条元数据消息及3份元数据响应，元数据阶段host RPC为0。

目录首请求中的宿主源码建立费用已经包含，完整压缩源码与封装保存在 raw wire。QA原生脚本额外显式执行14对象的 to_mesh/三角化并导出实际数据，这部分单列为QA成本。产品目录实际14次to_mesh、848次目录顶点forward、0三角化和0完整网格resource数组；装配采集新增4次to_mesh/三角化，控制新增2次。

| 单独窗口 | 耗时 ms |
|---|---:|
| owned Blender启动 | 1068.6467 |
| 产品启动与元数据 | 1313.3557 |
| 正式快照精确绑定 | 26.2717 |
| 关闭与计量发布 | 295.7640 |
| 完整owned会话 | 2992.0426 |
| 正式独立证书重放 | 539.2215 |
| 派生资产构建进程 | 2755.9164 |

各窗口按自身时界保存，启动子阶段、QA与完整会话存在嵌套关系。完整工程协调、token、模型质量与费用待计量。原始退出凭据确认 owned Blender 及实际 Python runtime exit0，runtime retained handle 已关闭，正式序列没有重放。

## 失败、未运行与解释范围

准备阶段有两项QA harness缺口，经测前审查修复并保留历史。完成旗标增加3份实际响应及无transport/harness异常要求，退出检查增加 exited 和 handle_closed。公开 unknown、tool isError 与RPC错误响应均可被保存，装配未知后仍继续控制与清理。正式harness错误与执行异常均为0。

资格完成的出口为可复现的实际能力缺口。装配的距离、实体关系、定位、3项要求和三候选最近判断均记业务未完成。独立答案通过、目录通过或控制通过，分别保留各自分母。模型消费者、M2性能复跑以及新的几何补查次数为0。

原12件和控制均与正式实际快照直接精确绑定，本轮未发生重索引。保存的纯绑定反例覆盖1 ULP变化、单位、矩阵、面方向、逻辑ID、缺失对象以及合法重索引。距离验收采用原1e-6 m证书范围，实际支持面与见证上下界远窄于该上限。单次工具耗时仅作此批归因线索。

## 唯一下一改动建议

推进 M3 成对精测的实际工作量准入与距离 BVH 改造。保留现有尺寸、数值位宽、期限与已发布unknown语义，复用已有整数几何、BVH及query-local准备。将理论面数乘积的预先拒绝改为实际 node、leaf、特征与谓词工作预算，距离遍历采用严格 lower > best 的安全剪枝并保留相等情况。

闭壳自相交、跨物体边界与射线查询各有已有预算和剪枝，须随同核对、计量并共享准备。距离模块当前仍先做全笛卡尔双循环，再逐三角AABB排除。仅取消乘积门会暴露这层成本，直接套用只筛相交的 candidate_pairs(pad=0) 会漏掉正距离最近面。

后续候选需要同时验证距离界的数值安全、非唯一见证与并列最近、分类型预算以及准备复用的一致性。尺寸放行后仍可能触及真实工作预算，G508完成度需要用候选实际验证。本批交付源码定位和最小方案，下一实现由管理员深审后定批。

## 证据入口

- ROOT_PLAN.md、WORK_ORDER.json 与 INSTALLATION_BINDING.json记录任务及来源。
- assets/DERIVED_MANIFEST.json 与原件记录派生过程。
- entry/run_01保存3业务请求、完整回复、实际 evaluated 快照、21项绑定、raw wire、trace和退出。
- oracle/formal_replay_01保存正式独立证书。
- verify_saved.py与SAVED_VERIFICATION.json重算支持界、有理见证、公开控制见证和raw字节。
- SOURCE_ANALYSIS.json、HARNESS_REVIEW.json、POST_RUN_REVIEW.json区分测前定位与实际后验核对。
