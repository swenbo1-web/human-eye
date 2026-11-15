# 默认区域的源面绑定

本候选修改 `human_eye_plugin/live_spatial_mcp.py` 的同一主动观察投影路径。每个已验证区域行增加 `source_triangle_index_ranges`，采用对象局部、零基、两端包含的区间。

原 `object_index` 继续引用本结果的 objects 表。顶层一处简短语义说明将范围与本结果 binding 关联。产品不按中心、法向、包围盒或“两三角一面”的假设生成面号。

## 版本与准入

存在并通过原 patch_support 全部分区与来源验证时，简报为 `active-observation-brief-v5`。源映射缺失时沿原版本投影，不声明新列。原验证拒绝及外层全量回退路径继续承担错误处理。

原 helper 的唯一内部调用接收 `(compact_patch_support, region_counts, region_ranges)`。公开 full 响应与原始 patch 映射保持其来源结构。几何、像素、选帧、缓存和图像输出使用既有入口。

## 两个候选

初版保存为 `product_candidate_01.py`。它在既有验证后，增加一轮源映射遍历生成范围，并增加一次结果行追加遍历。

追加优化保存为 `product_candidate_02.py`，与最终产品文件逐字节一致。范围在原验证循环已有的 indices 集合上构建，计数和范围在同一个结果行循环中追加。该版本避免再次读取原始源面序列。排序仍用于规范化任意输入顺序，每个支持区域一次，沿现有 unsupported 范围编码语义处理不连续编号。

两版本的实际公开值完全一致。定向验收由另一个执行者负责，工程测量记录于 `ENGINEERING_REPORT.json` 与 `ENGINEERING_SORT_COUNTS.json`。
