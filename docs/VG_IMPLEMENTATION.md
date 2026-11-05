# VG 主动视觉实施

2026-11-05。夹具、质量门和正式采样沿用 [VG 冻结协议](VG_ACCEPTANCE_PROTOCOL.md)。以下接口、着色和计时边界在首次评分前冻结。

## 公开接口

`VGRenderer` 持有一个 Blender GPU 上下文中的绘制资源和两台独立正交相机。`prepare(meshes)` 接收 RB 输出的 `{object_id: ResidentMesh}`，按显式事实更新构建共享 GPU 网格批次和原生 `BVHTree`。`observe(prepared, witness, *, target_ids, frame_id, scale_length, mode="NATURAL", method="active", audit=False, relation=None)` 接收 BC 的 `SurfaceDistance`。`fixed` 使用世界空间 `normalize(1,−1,1)`，`active` 使用正交环带原生射线选择局部方向。全局方向相同。`close()` 释放相机和 OffScreen。

`Observation.png` 是可消费的 1024×512 PNG。`Observation.metadata` 绑定源对象、帧、米制单位、BC 面 ID 和见证、实际相机 RNA、GPU 矩阵、视口、所选方向、探测射线数和投影间距。`selection.probes` 按搜索次序列出实际测试方向、逐方向射线数、连续通过的孔径采样数和通过确认的目标数。`SECTION` 记录平面和 `<=0` 保留侧。`audit=True` 额外获取叠加前底图用于开发期评分。零距离显示 `ZERO_GAP` 或调用方已有的 `CONTACT`/`INTERSECTION` 关系，采用场景相对宽度，省略正距标线。

正距局部宽度等于 `32g`，中心等于两个 BC 见证的中点。两个视口各 512×512。相机位于场景外，近远裁面包含所有源几何，世界米制 GPU 矩阵与 Blender 单位相机 RNA 配对记录。剖切使用过中点的 `t` 平面和 GPU 半空间裁剪，针对所有局部图几何，全局图绘制原始网格。主动搜索使用同一半空间约束原生射线，选择实际成像轴向能留出空隙且两侧目标有表面命中的方向。候选由固定视向在见证正交平面的投影生成，算法没有夹具标签输入。

## 两方法共用的像素规则

Blender 自定义 GPU 批次使用不透明、无光照的 RB 基色，`GPUOffScreen` 采用线性 RGBA8。材质色直接映射为 `round(255*c)`。深度测试 `LESS`、开启深度写入、关闭混合与面剔除、无抗锯齿。几何颜色和背景不经过显示变换。A 为 `(0.82, 0.24, 0.15, 1)`，B 为 `(0.16, 0.60, 0.90, 1)`，障碍为 `(0.36, 0.40, 0.45, 1)`，背景为 `(0.08, 0.10, 0.14, 1)`。底图判色各 RGB 通道固定容差 1 个字节，仍需逐像素的原生射线归属和冻结的深度判定。HUD 标识目标颜色、源/局部关系、未取整米制距离和模式，叠加后 PNG 才是公开产物。

## 计时边界

热态从已捕获事实和已准备的两方共用批次开始，包含主动方向及其原生射线、相机和 section 设置、实际 GPU 矩阵及元数据、全局和局部绘制、HUD、GPU 完成和同步读回、行序转换与 PNG 编码，直到返回字节和元数据。磁盘、额外审计底图读回及评分在热态以外。一次正式观察总会重新绘制并编码。场景构建、RB、BC、GPU 初始化、场景准备和双方首次观察分别记录。正式采样不并行争用同一个 GPU。

## 实现与复验

- 以固定方向在间隙正交平面上的投影为起点，按离起点角距递增的顺序探测 16 个环向候选。每个方向探测间隙中央、沿见证轴与横向各偏移一像素的 3×3 孔径。通过孔径后用两端附近的原生首命中确认目标表面。找不到满足两项的方向时，仍沿搜索所得最佳方向作一次观察。评分读取实际像素和独立原生射线。
- 所有源三角面进入一个位置与颜色批次和一个 Blender 原生 BVH。剖切用相同世界半空间裁全部局部片元。主动剖切方向垂直于见证轴，候选的原生探测从该平面进入保留侧。半空间后方仍保留遮挡与深度。
- 相机 RNA 存储单精度位置。正交相机通过实际 `shift_x/y` 补偿长取景距离下的亚像素中心漂移，记录平移后的投影矩阵及实际 GPU 矩阵。两个 512×512 视口共用一个 1024×512 RGBA8 OffScreen。BLF 在 GPU 上绘制 HUD，同步读回后交 Blender ImBuf 进行 PNG 无损编码，压缩设置为 15。
- 后台实测 Blender 5.2.3 LTS 的 `gpu.init()`、自定义批次、同步读回和 `imbuf.write_to_buffer` 可用。记录的是 NVIDIA GeForce RTX 3060 的 OpenGL 后端。路径使用自己的批次与相机，没有调用依赖 VIEW_3D 区域的 `draw_view3d`。可参照 [GPU API](https://docs.blender.org/api/5.2/gpu.html) 和 [ImBuf API](https://docs.blender.org/api/5.2/imbuf.html)。
- `pilot_001` 保留首次 24 例试测。长槽中有两个观察的连续见证间隙被顶盖遮住，数学中心线擦过屋顶边缘却没有像素中心余量。`pilot_002` 验证横向采样后的修复，并确认两方用相同的无损 PNG 压缩设置。两次试测均保留原始记录，五对热样本仅供诊断。
- `author_001` 保留加入逐方向公开记录前的三进程正式结果。`author_002` 使用同样的几何和评分，对包含完整公开字段的交付源码重新采样。

正式运行命令如下。

```powershell
& 'D:\human eye\venv\Scripts\python.exe' -B 'verification/benchmark_raycast_saccade_gpu.py' --blender 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --output-dir 'artifacts/vg/author_002'
```

正式输出、源码摘要、三进程逐例分数、原始时序、相机、底图和 HUD 由 [run.json](<D:/human eye/human-eye/artifacts/vg/author_002/run.json>) 索引。运行日志和 PNG 也位于同一个输出目录。
