# M4-M5-SOURCE-REGION-001 独立复核

2026-11-17。接受修正后的区域观察/量测能力和当前R1的一次NPZ解码复用优化。初始R0局部相机失败、early候选发布窗口失败及原始成本保留。正式质量和性能比较使用R0F与R1。

作者交付de884a2a44557fb3d01407c5e7c2883cc4aa749c。保留产品2292c3d79e9996fb29b0c3351102998923113d56，143源8d8d3d60e99b5e039e6711c168f95d648124e96eea03b0a061b2796c5a690600，隔离安装D:/he_m4_m5_source_region_001/R1/product。根及三名复核者读取固定原件，独立检查程序分别归档。

## 能力及原相机漏验

source_region接受当前对象内源三角集合或region_ref，观察保留全场遮挡，量测只用完整选中三角并复用既有M3。通用SceneObservationImages已从矩形门控提取。原生/求值来源一致性当前只由本批11对象64点62三角资产证明。

20份成功区域结果及2份整对象控制独立验算通过。数学检查11215项，包括源成员、精确距离及500组平面/反绕序/段/点控制。前4面到B为5/4米、到C为sqrt(137)/4米；整对象6面因未选斜翼而分别为1/32和sqrt(2305)/32米。每个最近点的原源三角/顶点集合由另一套Fraction Gram成员算法重算，compact反向映射正确。

私有holder只保留内核已计算的exact点对，并清除前次遗留值。独立控制核origin+point/factor与公开世界点一致，原点映回源面，无新增最近点求解。

初始R0产品7f71b352的SCENE跨度49.7803米，只有13个区域像素，六向均不符合选区局部fit。作者内部复核先发现这一漏验，本轮从原件独立复现。R0F产品f14f1553改用现有目标拟合helper，固定原布局和门槛。

修正后中心为(35/8,35/8,17/16)，SCENE跨度1.1667261889578036米。18份修正结果的六相机均按选中顶点拟合，选中点XY及全11对象88个AABB角点深度通过。原R0失败未进入正式同质量比较。

## 发布窗口与解码复用

34项独立proof控制与3项发布窗口对照通过。当前R1先以NumPy编码生成不可变BytesIO字节，固定SHA后写盘并核首次读回，成功后才建立producer私有proof。后续validate每次仍读取PNG/NPZ字节核摘要，再核原frame对象、相机/路径/来源元数据及完整当前buffer/mapping内容。

原producer的同一frame可复用数组，foreign实例、保存帧、浅深副本、路径或元数据变化进入原解码。alias修改原数组、dtype/shape和owner/mapping变化被完整路径核对。旧Active默认继续解码。

独立拦截首次NPZ读盘并替换为另一有效archive。旧默认在后续校验拒绝，封存early候选错误接受，当前R1在frame返回前以actual_frame_array_bytes_required拒绝，原反例确实复现并由当前实现关闭。[算法复核](../verification/fixes/20261117_source_region_review/algorithm/REVIEW.md)保留源码、对照及失败。

本轮proof控制使用合成buffer，生产raster为0。最终成功运行6次PNG/10次NPZ编码及28次decode，另一次自检失败前缀重建3次PNG/3次NPZ及25次decode，未完整profile该失败进程。纯距离重放和这些编码单列于独立报告，正式实测成本保持原件。

## 图像、源引用和状态

交付检查1610项通过。25次原TX/RX、26个native图片块和17份唯一构造帧逐项核同。七个双请求会话的第二请求确实使用首个原public返回的region_ref测C，图像、区域准备和当前源身份一致。

三对R0F/R1选中相机、PNG及全部NPZ数组相同。通用曲面帧的矩形patch数为0，patch owner全为-1，仍有当前RGB/depth/object/triangle owner。四个选中面分别8427、13108、1869、2808像素，共26212。独立逐前景射线核10种唯一组合覆盖17原帧，修正局部最大深度残差2.4869e-14米，额外1e-10米检查通过且重建模糊数为0。根另查看了原13像素与修正局部图。

实际可见源面样本与完整曲面可见性分别交付，complete_surface_visibility保持unknown。该边界与当前量测覆盖完整所选集合一致。

状态槽11请求的构造为[6,1,0,0,1,0,1,0,1,0,0]。A世界X+1/4及恢复逐点核实，区域到B分别为sqrt(5)/2和5/4米。两次旧ref原样拒绝，各0native、0构造、成功归档INDEX不变，后续当前请求正常处理。恢复后几何相同，引用仍绑定当前新代。[交付复核](../verification/fixes/20261117_source_region_review/delivery/REVIEW.md)记录全部当前source/camera/frame/nearest witness对应。

## 身份与同质量成本

身份成本4506项检查通过。1550个namespace Git路径及7份产品修改准确闭合，1375份运行原件29,929,015字节零排除归档。R0、R0F、R1三代各143源Git/wheel/完整RECORD/安装以及16份实际host/residency内嵌源码吻合。

8owned加1准备进程共9次实际Blender，25请求含2次预期stale错误、17次构造、26次图片交付、0模型/训练/付费调用，pending0。原30秒请求、600秒owned期限、held process/reader/pipe/handle关闭与源文件指纹通过。准备进程780.6547毫秒，8个完整owned合计20,020.0798毫秒，各层嵌套时间分列。

首个修正pair1_R0实际运行R0F，同时承担修正后的局部资格；它完成后才冻结FIRST_CORRECTED_HOTSPOT并实施唯一优化。正式R0F/R1的harness pins相同，R0到R0F的harness枚举接线变化已披露。

| 配对 | R0F两请求服务ms | R1两请求服务ms | R0F完整owned ms | R1完整owned ms |
| --- | --- | --- | --- | --- |
| 1 | 174.2804 | 165.4777 | 2349.8276 | 2286.1356 |
| 2 | 170.6616 | 164.3280 | 2257.3856 | 2262.4334 |
| 3 | 217.8623 | 172.6677 | 2389.5400 | 2314.5535 |

两请求服务配对下降中位5.0509%，三对均更快。完整owned中位改善2.7105%，第二对慢5.0478毫秒，保留该回退。R1三次冷请求实际fresh_payload_reuses=1、frame_array_decodes=0，热请求图像复用；R0F的一次decode由冻结成功源码路径推导，原运行没有预设计数。每张正式图临时压缩payload为231254字节，发布后保留0，分配器及峰值RSS未测。

这些结果符合本批预登记同质量与真实重复工作下降条件。后台负载、完整模型收益、供应商费用、根/协作模型用量及全任务CPU/RSS未测。[成本复核](../verification/fixes/20261117_source_region_review/cost/REVIEW.md)保留原时界和独立算式。

## 证据限制与下一项

作者fixture与原oracle为同一作者，本轮独立数学和射线核查补足当前范围。TASK原件为full，正式两版实际REQUESTS均为默认brief，状态另核full，差异保留。旧schema及8帧预期失败、检查器字段假设、相机漏验和early发布反例均完整保存。

一份已删除自生core pyc的删前摘要只有收据，所引历史Git是另一较早字节，当前按receipt-only记录。另外三份可由所引Git核字节。根与同行没有执行清理。独立checker自己的对象顺序、字段及decode时点假设错误亦留档。

下一[M4-REAL-ASSET-REGION-QUALIFICATION-001](M4_REAL_ASSET_REGION_QUALIFICATION_001_PLAN.md)使用用户原Yanyite静态文件副本。根核当前原件SHA与M6旧保存导出相符，27,304点/53,264三角，既有410点/748面区域的原生/求值对应在保存证据中成立。文件无骨骼和modifier，因此下一批只验真实静态来源和入口。fresh读取、实际参考Cube几何、图像域及量测仍待执行。

M6最新005–007报告已读取，006–007固定幅度校准阶段收口，其新机制由外线管理员决定。本线继续提供真实当前源数据和局部观察/量测基础。正式默认部署沿既有验收流程。
