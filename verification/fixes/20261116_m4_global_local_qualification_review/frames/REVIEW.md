# 保存帧与公开交付复核

2026-11-16。作者提交 99f939513111637b76a1d486622b4841cad9ccda，产品固定 ccb608aa83de4b0e6671da89e0c8f387bd3f800e，141 源摘要 7d2d4352f462c64a46e6fccf447c6f030c08b96e95517a3b2b6776ed50b69a6a。

复核者参与了本场景的原始资格设计。本次自写离线检查器，未参与作者资格执行或其 saved_frames 检查器实现。结果属于项目内部复核。AL 自身旧 assignment 已过期，parent 已为本次 312a5056-6564-4416-82d2-c11af3fc81fe 登记；该情况已回报根。

## 实际复核结果

自写 review_saved.py 对现存运行原件执行 644 项检查，通过结果保存在 RESULT_R2.json。未导入产品或作者 checker。新增 live、Blender、raster、模型和付费调用均为 0。

| 范围 | 独立复核 |
| --- | --- |
| 公开交付 | 3 次实际 stdio TX/RX、3 个 full JSON、8 个 native PNG，与 same-producer full 原件及缓存 PNG/NPZ 一致 |
| 全场 | SCENE、BACK、LEFT、RIGHT、FRONT、TOP 共 6 帧。Obj_02 每帧 1 surface；Obj_09 为 1、1、2、2、1、1 surface；两者均不可读 |
| 局部开放 | 1 个 SCENE，Obj_02 实际 50,557 surface、926 contrasting boundary，readable=true，公开 covered |
| 局部遮挡 | 1 个 SCENE，Obj_06 实际 0 surface、0 boundary，readable=false，公开 unknown，主原因 finite_camera_pool_uncovered |
| 数组与几何 | 8 帧共 2,097,152 像素位置，701,991 前景像素。实际 owner、全局 triangle、对象内面行、patch 映射与当前 native capture 对应 |
| 深度与射线 | 所有前景像素均具有原源面交点，最近深度与保存深度最大误差 4.2633e-14m，全部通过额外 1e-10m 检查 |

真实 RGB 图片也已目视检查。开放局部图为中央完整灰色四边形及深色背景，遮挡图为盖盒表面。保存图像只说明本次实际视角内容。

## 1263 个数值模糊像素

独立重建作者的 1e-8 重心/近等深带，得到完全一致的 1263 个像素。全场 333，局部开放 465，局部遮挡 465。

所有模糊像素仍受实际源三角成员关系和最近深度约束。独立路径中跨对象归属差异为 0。全场 SCENE 有 2 个同对象不同 patch 的并列边像素，坐标为 (255,279)、(255,291)，均属于域外大箱体 Obj_08，保存面行为全局源三角 37，独立浮点并列选择为 32。它们在明确的模糊带内，保留精确 triangle tie ownership 未证的限制。

局部开放目标的 465 个模糊像素保持同一目标 patch，来自同一矩形的源三角 8、9 的内部对角线数值带。全部目标像素在更严的 1e-12 重心余量下具有实际原三角交点，源深度误差最多 7.1055e-15m。完全去掉这 465 个像素后仍有 50,092 个 surface 和 922 个对比边界，均显著超过 16/4 可读门槛。此数值带无法改变本次可读正控制的结论。

全场水平目标的单像素落在其内部源三角对角线上，倾斜目标的实际像素没有落入该带。全场两者的实际计数与独立小像素上界相容。盖下目标在所有保存帧中都为 0 patch-owned 像素。几何完全性及六方向遮挡由根的独立几何复核共同验收。

## 当前来源、索引与缓存

原 native WIRE 作为数据解析，恢复 resident resources 和本次 capture，未执行其中代码。恢复出的真实源顶点及源三角顺序逐对象等于同会话 raw_sources 原件。绑定的 document_epoch、capture_state、revision、对象顺序和 host/instance 与这些原件一致。

全场 Obj_02 为 object_index=6，局部为 1。全场 Obj_06 为 2，局部为 1。两个对象各自的对象内源三角行仍为 [0,1]。Obj_02 对应全场全局源行 [40,41]，局部 [8,9]。Obj_06 对应全场 [12,13]，局部 [8,9]。每个 scope 的 offsets 独立核验，未用全场 object_index 解释局部数组。

本次 host_id 和几何 roi_id 在全场与局部间稳定，各会话的 instance 数值也恰好一致。各自 document_epoch、capture_state、binding 和相机身份均按本会话核验。当前产品尚未发布内部父子取证关联，跨会话相同数字未被当作该能力。

8 份 PNG 与 8 份 NPZ 均实际保存在各会话 product_state.json.active_observation 子目录，其 SHA256、数组逐字节元数据、patch/owner 映射摘要、frame_identity 和 host image_ref preimage 全部核对。8 个公开 native image block 解码后逐字节等于相应 PNG。

三个会话均没有 product_state.json 本体。实际保存的图像缓存文件与该状态文件分开核对。ReadContext 归档保存了当次 retained selection 元数据；本次不推断进程结束后仍有可调用的内存状态。

源码确认 live_service._bind_read_result 在核心摘要生成后追加 runtime_source_sha256、source_status、disk_status、source_check_scope 四字段。独立检查器先验证四字段真实值，再从摘要 preimage 排除它们。原核心 source binding 与完整 camera binding 哈希均正确。

## 失败记录与范围

首次自写检查器遗漏 NDC 视锥域，在局部盖盒覆盖整幅时失败。review_saved_initial.py 和 INITIAL_FAILURE.md 保存该失败，修订只限制现有 published projection 的有效 NDC 范围。原始响应、图像、数组、产品和作者失败记录均保留。第一次通过结果 RESULT.json 也保留，RESULT_R2.json 追加摘要 preimage 与更细数值带归因。

当前复核证明固定场景的局部开放正控制确实恢复可读证据，真实盖板仍产生 unknown。自动选择、内部全场到局部关联、完整任务耗时、模型消费与收益尚待候选验收。

## 最小跨尺度建议

仅对任务合格且至少一个方向几何完整、当前像素不足的区域触发局部拟合。按源对象合并焦点，用当前冻结几何和既有六方向原语取得首个可读局部见证，通过 host/instance、对象内源面集合及当前 generation 回绑全场区域。几何全遮挡区域保留原因并结束同方向细化。预算与结果直接计入原观察，避免为一次局部取证另启完整 owned 生命周期。

全场原语已具备局部拟合所需信息。本次证据支持优先补这一小段衔接，后续具体接口与验收由根统一制定。
