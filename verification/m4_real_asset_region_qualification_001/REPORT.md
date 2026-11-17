# 真实资产局部来源资格结果

本批固定已接受的 R1 产品，完成 Yanyite 原样副本的两次后台会话。产品源码、默认安装和原文件保持原有字节。整体结论为来源、距离、缓存和状态链通过，局部图像证据不足。

## 分项结论

| 项目 | 结果 | 证据范围 |
| --- | --- | --- |
| 当前来源对应 | 通过 | 27,304 点、29,073 原生 polygon、53,264 求值三角逐行核对 |
| 固定选区对应 | 通过 | 完整 748 面、410 点，保留原生 polygon 与当前三角行对应 |
| 到 Cube 表面的距离 | 通过 | 产品与独立 binary64 域均为 0.370117193892 米，Blender float32 读回域相差约 6.39 纳米 |
| 已保存帧与原始交付 | 通过 | PNG、RGB、深度、owner、源三角与 stdio 原件对应 |
| 有效局部图 | unknown | 每幅选区像素均为零，748 个面中心均被 Cube 遮挡 |
| 移动与恢复 | 通过 | 世界 X 增加 0.25 米、恢复后旧引用均按来源代际拒绝，fresh 查询分别有效 |
| 同代复读 | 通过 | 实际公开 region_ref 复读，图像和量测缓存命中，新增 raster 为零 |
| 模型整任务收益 | 未运行 | 本批只做固定产品真实资产资格 |

## 图像缺口

Cube 原始 hide_render 和 hide_get 均为 true，visible_get 为 false。当前完整场景捕获和分析渲染仍包含它。每幅 512×512 图有 261,121 个前景像素，全部属于 Cube。Cube 的十二个三角严格覆盖闭合箱体，选区所有顶点严格位于箱体内，相机深度范围覆盖箱体。独立连续遮挡证明与逐点射线结果一致。

当前结果同时输出 status=complete、observation_status=locally_observed 和 selected_surface_pixels=0。消费者须读取可见性事实才能识别局部图像缺失。本批将图像资格记为 unknown，完整视觉任务尚未通过。

建议下一批仅处理显示参与合同。保留当前显示标志，明确图像参与对象和量测参考对象的适用范围，并为零选区像素提供明确的观察不足出口。该建议等待独立复审确定范围。

## 实际耗时与成本

| 调用 | 完整请求秒 | 新增 raster | 距离米或预期拒绝原因 |
| --- | --- | --- | --- |
| main/initial | 3.863018 | 1 | 0.370117193892 |
| main/repeat | 0.735125 | 0 | 0.370117193892 |
| state/initial | 3.606703 | 1 | 0.370117193892 |
| state/moved_old | 0.883828 | 0 | source_region_ref_capture_generation_changed |
| state/moved_current | 3.470309 | 1 | 0.370117193892 |
| state/restored_old | 0.816950 | 0 | source_region_ref_capture_generation_changed |
| state/restored_current | 3.049370 | 1 | 0.370117193892 |

两次完整 owned 生命周期分别为 9.457648 秒和 20.449018 秒，包含启动、额外来源导出、独立答案、请求及关闭。每次公开请求在原 30 秒期限内，两次会话均在原 600 秒期限内。

实际启动两个 Blender，构造四幅图，原生交付五次图片，其中一次复读使用已有帧。产品 setter 为零，夹具 matrix setter 两次，未保存 blend，模型、训练和付费调用为零。

worker 的关闭事件 status 字段沿用 unknown。对应 RPC 返回 closed，原始与最终场景指纹相等，保留的进程句柄确认退出，关闭结果经独立证据核定通过。该日志字段现象保留在生命周期报告。

离线检查按五次交付累计核查 1,305,605 个前景源成员点、1,280 条固定网格最近射线及 3,740 条选区面中心射线。全图最近遮挡范围由固定抽样覆盖，每个前景像素另经声明源三角成员与深度检查。重复交付计入上述检查分母。

## 适用范围

本次覆盖一个静态外部作者资产和一个预先指定的空间选区。手臂语义沿历史标注保留 provisional。实际数组未发生行置换，置换能力另有纯保存输入反例验证。该文件无骨骼、modifier 和动画，相关支持仍待其它实际来源验证。当前证据尚未覆盖模型自行定位问题和整任务对照收益。

SOURCE_FREEZE.json 绑定运行前 harness、独立答案代码、输入及固定 143 项安装源码。DECISION.json 给出逐调用记录，oracle/FRESH_REVIEW.json、checks/IMAGE_DELIVERY_CACHE_REVIEW.json 和 checks/LIFECYCLE_REVIEW.json 给出独立复核。runtime_archive 保存本批运行目录全部字节，CONTENT_MANIFEST.json 固定本批内容，最终 Git 提交另在审核回报中给出。
