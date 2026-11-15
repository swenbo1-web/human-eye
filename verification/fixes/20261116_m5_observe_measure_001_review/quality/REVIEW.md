# M5-OBSERVE-MEASURE-001 独立质量与状态复核

2026-11-16。固定作者最终交付14c8c6b8206dcaecc373bc9aa895cda1d622eee3，产品ccb608aa83de4b0e6671da89e0c8f387bd3f800e。本目录独立编写check_quality.py，只读取原WIRE、capture、producer、公开响应和图像缓冲，不导入作者checker，不执行产品或Blender。

质量与实际状态控制通过。最终837项证据检查，分母为8个正式工程槽、5个状态请求。核对6个正式实际帧、状态控制6条帧引用，其中状态NPZ实际为4个不同文件，初始full和缺失对象请求复用了已有帧。

## 当前来源与公开事实

- 解码原native RESPONSE.bin中的标记packet，按resource revision复用局部点面，使用实际matrix与scale独立重建世界网格。逐项核原TX/RX和保存capture摘要，所有原始WIRE重建capture与保存capture完全相等。
- 正式及状态父捕获均保持target_observation_meshes声明。全部实际观察网格逐点逐面对齐根冻结世界几何，矩阵变更态仅目标X增加0.25。父绑定的场景代、真实object_id、instance与定量对象映射一致。
- B的默认brief及状态full所交付task_result与同producer原件逐字段相同，原普通task公开facts及binding也等于其producer事实。父binding/source_binding、whole_objects语义、完整有序源三角集合与世界几何SHA均独立核对。
- 对每个已观察定量对象，按原始有理顶点、绕序三角规范化独立重建geometry:标识，结果与定量source对象的标识相同。图像对象索引映回真实host对象和实例。补读Far11没有被伪装成图像对象，observation_object_index与geometry_id均为null。
- 六主槽的相机、六方向分类、实际选视、完整/未知状态一致。主任务仍2支持、1完整、1未知。task-only两槽仅有普通定量结果，图片为0。

## 距离与合法见证

原Near所有顶点都位于x=a，a=0.004000000189989805；原目标全部点x≥1。该支撑平面给出距离下界1−a，当前发布最近点位于两对象真实源三角内并达到下界，故主距离为2138893713/2147483648，即0.9959999998100102米。矩阵X+0.25时同一证明给出1.2459999998100102米。

Far11位于x=12，z∈[0,1]。目标竖面的全部点x=1，距离至少11；目标水平面z=2、x≤2，距离至少sqrt(10²+1²)。当前见证[2,0,2]与[12,0,1]分别精确位于源三角上，达到sqrt101。补读确实只含Far11的289点、512面，与同代父捕获一致。

检查允许合法的非唯一见证。全部发布点使用Fraction平面及重心坐标核对源三角归属，点间距离与发布distance一致，A→B方向和单位长度成立。每个fresh B主请求只求解一次surface pair，定量追加raster为0；状态初始full命中已有测量缓存，surface_pair_count为0且result_cache_hit为true。

## 图像与真实矩阵变化

逐帧核PNG/NPZ原字节、公开image块、RGB解码、当前parent binding和source revision。由原对象顺序及face offset把每个前景triangle ID映回对象和局部源面，再独立建立目标两片的patch映射。三对全像素RGB、depth、归一对象owner、局部源面、patch owner相等。实际区域表面像素与四邻域RGB距离24的对比边界数重新计算，全部readability字段与门限一致。

五状态的距离依次为原主距、原主距、sqrt101、原主距+0.25、原主距，完整区域数1/1/1/2/1。初始、变更、恢复的revision为1/2/3，parent binding各异。两个fixture回执的真实matrix分别从identity变为X+0.25、再恢复identity，293个世界点逐点符合矩阵，原全场fingerprint恢复。恢复后的全部归一图像buffer与初始相等。

恢复后的几何内容scene_revision可以与初始相同，当前来源还需capture_state的instance_id/epoch/revision。脚本按这个同代组合选择父捕获，验证任务和帧绑定均为当前代。旧绑定没有作为恢复态当前binding返回。

## 本轮脚本修正与范围

三个独立脚本准备错误分别保存在check_quality_R0/R1/R2.py和ERROR_R0/R1/R2.md。R0误以为binding.objects直接含geometry_id，改为真实host/instance映射并独立重建geometry标识；R1误把缓存命中也要求新求解一次，改为核其result_cache_hit；R2只按几何scene_revision挑父捕获，改为连同generation核对。这些修正使用同一保存材料，未改变任何作者记录或产品行为。

本轮新增真实产品请求、Blender、raster、模型和API均为0。未独立重新运行几何求解器或光栅器，几何距离使用上述固定资产解析下界与精确见证证明；图像检查使用全部实际保存帧。M5更广曲面任务、真实模型消费与总体性能由后续验收处理。
