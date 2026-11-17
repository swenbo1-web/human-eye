# M4-REAL-ASSET-REGION-QUALIFICATION-001 独立复核

2026-11-17。来源、局部表面距离、缓存、状态恢复和生命周期通过。真实局部图像资格保持unknown，确认隐藏Cube参与绘制和零样本反馈两个相连缺口，下一批按单项显示参与合同修复。

作者交付828d1265a3434fd1b5fb97e4759acaedd9253bc0，产品2292c3d79e9996fb29b0c3351102998923113d56，143源8d8d3d60e99b5e039e6711c168f95d648124e96eea03b0a061b2796c5a690600。产品差分为0，安装仍D:/he_m4_m5_source_region_001/R1/product，原用户blend SHA614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d。

## 当前来源和距离

独立几何215444项检查通过。四份fresh导出逐点/面核27,304顶点、29,073原生polygon、53,264求值三角及748面/410点区域。静态原生点面与求值同行对应，原生polygon到当前三角行映射完整。实际capture按宿主binary64矩阵与单位运算重建，和产品有序几何摘要精确一致。

Cube为真实闭合轴对齐箱体，区域全部严格处于内部。以六个边界面的连续表面下界及达到点，独立答案为0.37011719389236364米，方向+Z。源顶点24331及区域三角48160/48161属于原生polygon26521。初态和恢复的Cube参考成员为三角0，移动后为三角1，均在Cube polygon0内，原件各自保留。

Blender float32世界读回域的答案为0.3701171875米，和产品binary64运算域差6.392363638e-9米。两种坐标运算范围分别验算，该差异未被容差合并。量测值为到Cube边界的表面距离，选区实体内含由另一独立证明成立。详见[几何复核](../verification/fixes/20261117_real_asset_region_review/geometry/REVIEW.md)。

## 实际图像缺口

当前Cube的hide_render/hide_get为true、visible_get为false，完整采集保留它，分析栅格也绘制它。五次实际交付的每图261121个前景像素全部属于Cube，选区像素0，748个选中面均未见。Cube顶面和源区域顶点射线的严格内交余量证明连续选区遮挡，相机near/far也包含该箱体。

公开结果同时给complete、locally_observed和visibility observed_samples。默认消费者需要深入读取0样本才能发现图像未提供选区证据。这一反馈属于待修复的观察不足语义，当前图像质量没有通过。

独立交付348项检查覆盖7个原TX/RX、5次native PNG和4份构造帧。保存数组、源offset、PNG/RGB、depth和owner对应一致。按五次交付累计覆盖1,305,605个声明源成员/深度/RGB点，固定16×16最近射线1280条、748面中心射线3740条。实际数值计算复用两个唯一几何/相机组，独立计算点/射线分别为522242/512/1496，原交付分母和复用计算分母都保留。连续全选区遮挡另有闭箱证明。

缓存复读实际使用首个public region_ref，frame/binding/facts/mapping和量测一致，新增构造0。两次stale原样拒绝，新增构造和native均0，成功归档INDEX保持，后续fresh请求正常。[交付复核](../verification/fixes/20261117_real_asset_region_review/delivery/REVIEW.md)保存原状态与检查分母。

## 身份、成本和退出

身份成本1107项检查通过。321个Git路径、274份原始运行文件100,678,626字节零排除归档，原目录保留。143源Git/wheel/完整RECORD/安装和4份实际内嵌host/residency源码一致，实际执行字符串与worker摘要对应。四份fresh导出及其独立答案的冻结完成时刻均早于相应请求。

实际2owned、7公开请求含5成功/2stale、4构造/5native、4fresh导出、2fixture矩阵变更/恢复、0产品setter。额外Blender准备、模型、训练和付费调用均0。两owned为9457.6476和20449.0181毫秒，合计29906.6657毫秒。最慢公开请求3863.0180毫秒，全部在原30秒请求和600秒owned期限内。

两个native与两个MCP持有进程句柄均确认退出0，reader、pipe、handle关闭，初末场景指纹、原件和副本文件摘要相等。worker通用关闭事件仍记unknown，对应wire closed响应、实际退出及指纹分别保存，未改写原日志。[成本复核](../verification/fixes/20261117_real_asset_region_review/cost/REVIEW.md)保留各层嵌套时界和关闭证据。

删除的本批自生pyc删前大小/SHA只有收据，原字节无法重hash。根未执行清理。独立checker各自的参考三角固定假设、错误回复可省略归档字段、清单字段名修正均留档。实际数组没有发生行置换，置换能力仅保存输入控制被验证。根及同行新增live Blender、MCP、生产raster、图像编码、模型和付费调用均0。

## 下一修复的依据

根另做一次纯离线可实现性探针，保留原SCENE相机和角色几何，只排除隐藏Cube。对748个面中心先作浮点预筛，再按源行顺序固定前三个候选，用Fraction实际相机XY/depth及全53264角色三角核遮挡。源面35618、35619、35620中心均在视窗内且精确无遮挡。该结果证明有可获取的局部几何证据，实际新像素仍待修复批验收。

[M4-SOURCE-REGION-DISPLAY-001](M4_SOURCE_REGION_DISPLAY_001_PLAN.md)使source_region图片按当前捕获view layer的有效可见性绘制，保留全几何量测和原源编号。图片当前display快照参与来源及缓存，零区域样本直接交付partial/evidence_insufficient，已测量事实保留。测试包含隐藏Cube的正常状态、显示Cube的遮挡、隐藏目标、恢复和同态复读。

本真实资产无骨骼、modifier和动画，自主定位及完整模型收益仍未运行。M6继续按另一管理线推进其提案机制。当前工程结果明确关闭来源与量测资格，将后续投入转向实际图像缺口。
