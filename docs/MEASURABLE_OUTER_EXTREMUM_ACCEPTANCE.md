# REVIEW-CYCLE-002：可测外围极值与core隔离的原生反例

日期：2026-11-03。本批只有一个新增纯构造QA资产，运行源码、安装和wheel保持原版本。本文是作者证据，交管理员独立复核，不宣称模型收益、通用资产资格或发布通过。

## 固定边界

- 运行源仍为125文件，SHA `d9b01eec9ce561b9f9fe5304cc37c50aa641b1826ed3ee788501eb2f49192360`。
- 固定安装`9.7.2+20261103.source.guard.r1`；wheel SHA仍为`044c411ffd8eb23a57eb054a61168dde8c53ee27977eceb4caf83992f963c1c4`。没有新build、安装、算法或版本声明修改。
- 新注册原始SHA：`7b1ba80835ca2d9c0c53e3e42058fcf5ecf77a1485c6764a623db08cacc4230c`，在数值预检和产品调用前固定。
- 旧`outer_dominates_mixed18`的外围`metric_resolution_insufficient/not_realized`保持原文件和seal。本例是另一个提前登记的中等变形，未回填旧结果。

## 单一几何与独立预期

12顶点、4原始三角、2个根骨；单位1米、保存帧1、mesh/rig世界矩阵均identity。仅单Armature顶点组LBS，无DQ、包络、动画或其他modifier。世界core闭框固定`[-0.25,0.25]^3`，选择原生`CoreAnchor/head`；不是由被测报告反推box。

| 区域 | 面ID | 登记与实际状态 | 指标 |
| --- | --- | --- | --- |
| core | 0、1 | identity，可测 | 两主伸长与面积比均1 |
| core | 2 | 三顶点无权重，unknown | `unweighted_vertex_source`，该行指标为null |
| 外围 | 3 | 可测、当前全部x≥1 | 主伸长1.5、1；面积比1.5 |

外围参考两边为`(1/4,0,0)`、`(0,1/4,0)`；仅第二顶点由独立根骨平移`(1/8,0,0)`，变形后两边为`(3/8,0,0)`、`(0,1/4,0)`。相应映射为`diag(3/2,1)`，奇异值与面积比解析确定；全部坐标为可精确表示的dyadic数。

独立Fraction精确SAT和NumPy QR/SVD在产品前首轮确认：core成员`[0,1,2]`，外围`[3]`，外围可测且两项最大值显著高于core。按既有数值模型估计伸长误差约`0.0002805294`，距0.01门约35.65倍；面积误差约`0.0007014023`，距0.02门约28.51倍。没有改精度门、核心或尺度；这些是输入算术模型余量，不是物理精度认证。

## 三次实际正式入口

先冻结完整几何/骨权/帧/core/成员/计数/四极值/见证范围与停止规则，再由独占headless Blender构造并保存一份自有fixture。期望的求值坐标没有写进mesh；实际求值由骨骼LBS产生。

预登记的3次`-I -B small_skin_source_entry.py`分别为：

1. `--anchors-only`：取得实际目录和稳定anchor引用。
2. `--triangle-query [3]`：直接取得产品B2外围行，确认不是只有参考数学将其判可测。
3. `--core-query`：按原raw policy SHA和原source合同取得正式core报告。

三个调用的live PID/epoch/source SHA各不相同，不能混用。每个packet分别核对实际entry/profile/scene/binary/worker/module/math/runtime pins、握手与first/second捕获。目录稳定字段独立重算；跨调用只有同一固定文件、profile、source_ref和完整几何/骨权/姿态绑定相等。core真值直接从**core自身**完整捕获算出，再读取core报告比较，不拿目录或外围调用的捕获冒充。

原30秒/16请求/512KiB边界不变。三个调用共6次实际inspect快照；一个QA资产，不是三个资产或真实作者样本。另有1个QA authoring Blender进程，产品各使用1个worker，没有共享GUI或原资产操作。

## 实际结果与反例有效性

正式外围行：`state=measured`、`principal_stretches=[1.5,1.0]`、`area_ratio=1.5`。该调用whole-mesh摘要仍为partial，因为core面2无权重；不能把全局partial误判成所请求外围面不可测。

正式core结果：

| 字段 | 实际值 |
| --- | --- |
| 完整成员 | `[0,1,2]` |
| measured / collapsed / unknown | `2 / 0 / 1` |
| 全部unknown原因 | `unweighted_vertex_source: 1` |
| 四个core极值 | 全为`1.0` |
| 四个core见证 | 全为面`0`，在允许集合`{0,1}`中 |
| 本地audit | 3个完整core行，含面2的null指标；成员/摘要/来源/发布哈希一致 |

若错误地使用global/primary替代core，最大主伸长及最大面积比都变成1.5。对真实报告做此两项变异，checker准确拒绝`measurable_outer_facts_max_principal_stretch`。另将数值仍为1的最小主伸长见证换成外围面3，也准确拒绝；因此不是靠数值相同侥幸过关。

错误选择平移骨可能保持相同成员与事实，本checker额外直接绑定注册世界box、half和CoreAnchor/head对应ID。新增13项负例还覆盖capture/audit交换、unknown/null/省略、布尔值冒充计数或ID、实际输入或注册改变，以及外围unknown不能提升为realized。合成测试首轮source digest夹具误计capture_id的9个错误保留，修正测试packet编码后没有放宽预期或改变产品。

## 期限、退出、输出与成本范围

core stdout与报告对象的canonical ASCII＋单LF完全一致，并对应PUBLICATION及CORE_AUDIT字节数/哈希；REPORT文件本身是另一种UTF8序列化，未混作相同原始字节。raw policy SHA针对原CLI输入，解码重编码的sidecar只比内容。

目录与triangle旧模式stdout含独立operational envelope，没有伪称这两者也有core PUBLICATION。每次都检查完整源、角色、单位置姿态、成员与readonly审计。成功路径按固定源码先关闭worker、核对退出再发布；另外用Windows只读进程查询观察到worker已退出或PID已不存在，未发送任何信号。记录stdout在原cap deadline前接收，父端完整wall也小于30秒，不单靠publication.elapsed推断最终接收期限。

| 单次完整父端wall，含进程、关闭、接收及记录落盘 | 毫秒 |
| --- | ---: |
| 目录 | 3276.823 |
| 外围面查询 | 3467.770 |
| core查询 | 3881.865 |

每类只有1次，无性能比较或模型时延含义。产品0几何setter、0原文件保存，fixture保存后SHA保持。没有图片、模型试验、Google调用、Key读取/生成、503重试或外部费用账本读取；来源US$0.02预留不变。

验收器复查另修两处真实误接受：退出记录现在必须严格绑定capabilities的实际PID；来源验证元数据必须是固定6字段、有限replay误差、精确atol=2e-5和整数0动画计数。原放宽atol=.01并重算出版哈希的绕过、wrong PID等反例及旧文件保留。三份原始实际记录均正确，使用原数据重新验通过，没有新增产品调用或修改runtime。selection/source_ref/catalog、INPUTS与无失败/撤销文件也显式核对。

## 验收范围与出口

4个相关模块共49项，本地和干净公开导出分别全部通过、无跳过。没有机械重跑2676项旧广域、457组原生、25/4迁移、11身份或owned性能试验；运行源同字节的旧证据按原范围复用，未冒领为本例执行。新增模块列入便携测试选择，只表示未来全量可包含，不代表本批跑了新增后的全部2689项。

公开重放资料：`verification/fixtures/measurable_outer_extremum_v1.json`、`build_measurable_outer_fixture.py`、`measurable_outer_checker.py`、`test_measurable_outer.py`。独立checker消费已有受信捕获，不是新的生产准入服务。

本地原始证据位于`verification/fixes/20261103_review_cycle002/`：`BEFORE.json`、`PREREGISTERED.json`、`ANALYTIC_PREFLIGHT.json`、`fixture_r1/`、三次调用的EXECUTION/STDOUT/SNAPSHOTS/REPORT、`core/readback/CORE_AUDIT.json`及PUBLICATION、`ACTUAL_RESULT.json`、独立truth/check记录和相关回归。失败、旧not_realized与新realized分栏保留。

该预定缺口在一个有限原生案例上补齐，不扩展任意角色/动画/病变语义或证明整体模型提升。本批交付后回报来源管理员并结束；若无新明确缺陷，下一出口是用户对固定版本、已披露成本及正式激活的决策材料，不为填满循环另起模块。
