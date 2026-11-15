# A 主输入独立核查

实际记录来自 `D:/he_m4_target_001/qualification/A_peripheral_02`，产品来源为 `b7868c46119b2f5dcb3ca426e78a2ac9bb45b51167a01d323516c7707eb81e76`。本核查读取该次原始 capture、TCP bootstrap、公开结果、audit、PNG 和 NPZ，没有执行新的观察、Blender、模型或 raster。

## 已核内容

- 14 个对象的当前实例、完整世界顶点和原局部三角顺序与冻结资产一致。独立重构的 source、geometry、camera 和完整 binding 摘要均匹配实际公开结果。
- 目标为 `M4_Far_00`，完整源面范围为闭区间 `[0,511]`，共 512 面。目标处于平面 x=1、0≤y,z≤1，正面方向为 -X。
- 保存数组的对象 owner、局部面范围、patch 映射及 offsets 一致。实际 MCP 图片与保存 PNG 字节相同，PNG RGB 与 NPZ RGB 一致。图片引用和 owner 绑定由当前原始几何及实际文件独立交叉验证。
- 已有 SCENE 图片的可见目标像素为 91559，达到颜色对比门槛的边界像素为 1127。边界框为 `[120,23,390,487]`，锚点为 `[255,255]`。独立逐像素统计与公开结果一致。SCENE 为背向，readable 保持 false。

## 独立遮挡答案

六方向中，SCENE 和 RIGHT 背向，TOP、FRONT、BACK 为 edge-on，只有 LEFT 的方向 `(-1,0,1)` 朝向目标正面。目标四角完整位于实际 LEFT 相机视锥内。

原场景的 `M4_Near` 位于 x=d，其中 d 精确为 `8589935/2147483648`。其单三角形满足 y≥0、z≥0、y+z≤1。目标点 `(1,y,z)` 沿 LEFT 到该平面时变为 `(d,y,z+1-d)`，因此目标上的遮挡区域满足 y≥0、z≥0、y+z≤d。

其严格正面积为 `d²/2 = 73786983304225/9223372036854775808`，与实际 audit 中的面积完全一致。独立源三角形摘要为 `db02fb1c4e51d43aeb0e6db3db83017076ef712986070af2398b89f642616737`，与实际 first_blocker 一致。x=0 的 `M4_Focal` 只产生零面积边界接触。

六向 complete 均应为 false，实际分类逐项相符。公开 inspection 保留 covered=0、无完整几何候选=1，目标仍为 unknown，原因为 `positive_area_occlusion_all_front_views`，没有完整见证。

## 收口与局限

按冻结输入和既有完整见证标准，主输入判定为 `not_realized`。B、正式性能矩阵及其他控制均未运行。

输入资格预审没有在冻结目标前确认六个方向中存在完整无挡见证，原有 Near 小三角已阻断唯一正面方向。这项规划不足应保留记录。

本核查验证当前保存数据和独立解析遮挡答案。没有重建整幅 raster，brief 也没有交付原始完整 frame 字典或生成时 NPZ 摘要。保存 NPZ 的当前摘要、元数据、实际 PNG 和图片引用已交叉绑定。结论限定在此固定输入和已检查的 A 路径，尚无 B 性能结果。
