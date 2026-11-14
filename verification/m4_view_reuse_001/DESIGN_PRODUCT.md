# 产品双owner与真实回读

本批从固定交付6e1e65c6开始，产品基线为99fa034e及141源6d4f7d36。所有实现位于m4-view-reuse-001隔离工作目录。

## 映射与首次构造

保留既有face_patch_offsets和face_patch_ids。mapping建立时按offsets准备int32全局raw ID视图，区间为每个对象原始输入三角形的连续全局编号。真实raster的第四缓冲接收这组raw IDs，原深度获胜逻辑和2/3/4tuple API保持原合同。

对raw>=0的前景显式查face_patch_ids生成patch_owners。背景raw/patch均为-1，unsupported保留有效raw且patch=-1。原RGB、depth和object owner沿同一次raster返回值保留。raw与object的关系通过offsets区间检查，raw与patch通过前向查表检查。

## 帧与文件合同

新双owner帧使用owner_schema=`active-dual-owner-v1`，triangle_id_scope=`zero-based-global-source-triangles-in-mesh-order`。owner_mapping_identity绑定上述schema/scope、既有patch_mapping_identity和face offsets，复用已有有序几何映射摘要。帧继续携带mesh_order_identity、patch_mapping_identity及pose。

owner_capabilities分别声明triangle_ids与patch_owners。内存buffers与NPZ同时保留triangle_ids、patch_owners和既有映射。NPZ追加owner_schema、owner_mapping_identity、triangle_id_scope三个小元数据项。读取路径校验相同的映射和owner合同，observe_frame默认只返回可序列化能力信息；显式include_buffers=True时返回真正加载及验证的buffers，消费者可直接复用同一份数组。

历史三/四缓冲帧缺raw时，保留原反馈兼容范围并明确triangle_ids能力为false。历史frame/ref不补写，patch不能反查raw。新schema宣称raw但数组或元数据缺失时拒绝。

## 引用与兼容

产品核心引用包含owner schema、owner_mapping_identity和本实例构造序号，缓存命中继续返回同一frame。Host覆写引用时把新owner绑定及原核心frame引用纳入构造身份。历史无owner字段的帧保留既有Host引用路径。

实际MCP full/debug帧元数据保留新owner身份与能力字段，brief-v4的区域、像素和覆盖事实不新增数组正文。新引用因owner版本而改变，旧引用及其已发布数组保持原对象与原路径。

## 触点

- active_observation_images.py的mapping、首次raster、保存、验证与observe_frame回读。
- active_observation_host.py的当前新帧引用绑定。
- live_spatial_mcp.py的full/debug帧元数据白名单。
- 必要既有mock测试把第四缓冲按实际新调用表示为raw winner，另用独立原始raw-ID raster验证真实结果。

模型调用为0。产品focused检查覆盖多对象、同patch多面、unsupported/background、近远和等深首赢、裁剪三角扇、保存后回读、legacy能力缺失与来源失效。独立安装集成与最多五个配对成本块由另一代理负责，避免重复大矩阵。
