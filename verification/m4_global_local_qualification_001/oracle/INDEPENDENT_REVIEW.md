# 独立资格审核

M4-GLOBAL-LOCAL-QUALIFICATION-001 的静态前提与三个真实资格会话均通过。固定场景有9对象、54顶点、56捕获三角，独立重建24个最大共边共面分量。其中22个矩形包含44个三角，方环与L形包含12个 unsupported 三角。合格任务集合恰为 Obj_02、Obj_06、Obj_09，各自源三角为0和1。

全场拟合的18个目标与方向组合，独立保守像素中心格上界均为1或2，包含5%相机边距、binary64区间及既有重心接受误差。真实全场构造六帧。两个开放小面保留 pixel_evidence_insufficient，盖下小面保留遮挡 unknown。

局部开放控制构造SCENE一帧，取得当前完整可读见证，实际50557个表面像素和926个对比边界像素。局部盖下控制构造SCENE一帧，目标表面像素为0，完整见证为空。盖下全六方向的几何正面积遮挡由独立Fraction射线证明及本槽精确附项共同核对，实际未构造方向单列 unrun。

三个scope分别核对原生求值点面顺序、固定资产SHA、当前 document_epoch、host_id、instance_id、局部三角号及有序几何。每个scope保存自身object_index和实际相机。跨scope对应依据是经过核验的同一固定资产几何。

静态oracle的12项纯接口反例与保存适配器的8项反例通过。保存适配器执行实际候选AST判定，覆盖比例法向、反向、偏轴、零向量及精确中心解析。帧检查器单独完成8帧的原图、数组、owner/source和像素核验。

## 保存接线修正

冻结脚本、首次失败报告和stdout/stderr均保留。独立R1按明确的最终 FRAMES_R2 文件名读取帧报告，将静态JSON中的有理中心解码为Fraction，并对公开有理比例方向核验精确正比例。原公开倾斜方向为[0,-1/3,1]，任务单位法向由独立几何得到[0,-1,3]/sqrt(10)。面积与nz门槛沿冻结几何核验。

盖下公开主字段 reason 为 finite_camera_pool_uncovered，精确 region_evidence.unobserved_reason 为 positive_area_occlusion_all_front_views，且view_reasons列出全六方向。两层原字段分别保留。该主字段的信息粒度应纳入后续消费设计。

本批验证了全场小目标取证不足和局部拟合恢复的条件。产品内全场到局部自动选择、父子见证回绑及模型任务收益由后续对应批次验证。资格后追加实际调用为0。
