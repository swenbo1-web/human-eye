# 全场相机、几何光栅与可读性

六个完整正交相机已经冻结。全部 28 对象、200 个顶点、276 个三角形参加同一 depth/owner 光栅。每张为 512×512，统一采用全场 world AABB 中心，分别按 right/up 投影的最大绝对值构造对称方形范围，再在每侧增加原对称 span 的 5%。TOP 的 up seed 为 +Y，其余为 +Z。候选方向均表示目标到相机，光轴方向取其反向。

固定产品 452b44d2、138 源 4067c864…51a9f6 的安装字节已逐项核对，实际导入模块另有摘要。相机直接复用 `_attention_camera`，光栅直接复用 `rasterize_attention(return_owner=True)`。同一个 RGB/depth/owner 缓冲保留所有遮挡物。全场统一对象色为 `(180,190,205)`，图像没有标签或其他叠加。当前交付通道为几何光栅。

## 已存图像与边界检查

六张 PNG、六份 RGB uint8 / depth float64 / owner int32 的压缩数组及相机 metadata 均已保存。PNG 共 15,735 字节，npz 共 136,752 字节，原始三缓冲数组载荷共 23,592,960 字节。载荷计数只描述数组存储。

`INPUT_CHECK.json` 的 74 项检查通过，包括全场顶点闭 frustum、near/far、公共输入绑定、PNG 与数组逐像素对应，以及 owner/depth 前景对应。产品 `_clip_polygon` 的六个 NDC ±1 边界控制原样保留，向外一 ULP 控制排空，新增几何容差为零。该检查新增 raster 调用为零。

## 动态 ROI 的像素证据

`assess_readability.py` 只将共同 scene 输入实际 `discover_regions`，得到 6 个 Region，随后使用已有全场缓冲生成 36 行像素证据。每个 Region 使用实际 object_index 对应 owner，从原产品 `_readability_evidence` 取得可见表面像素和对比边界像素。

| 视图 | 达到 16 表面像素、4 对比边界且 front-facing 的 ROI 数 |
| --- | ---: |
| SCENE | 2 |
| TOP | 1 |
| LEFT | 2 |
| RIGHT | 3 |
| FRONT | 3 |
| BACK | 3 |

达标项有 340–792 个表面像素、72–110 个对比边界像素。阈值沿用 24 RGB 对比距离。当前其余项像素为零。`READABILITY.json` 单独记录这些像素事实。连续几何完整性由 coverage index 独立计算，状态更新取其与可读集合的交集。模型纹理识别能力仍待后续验证。

像素评估耗时为 105,562,100 ns，覆盖动态发现、mesh 构造、六份已有缓冲加载、原图摘要和 36 次证据 helper。运行期禁止全部相关 raster 入口，新增全场 raster 和 solo footprint raster 均为零。

## 实际交付接口与计量范围

`assess_readability.receipt_for_view(index, view_name, assessment)` 读取实际 PNG、核对摘要和 scene/candidate/camera/ROI 绑定，返回绝对图像路径及 `actual_common_depth_owner` 证据。CoverageState 使用它单独判定已交付覆盖。

六图 preparation 函数的既有测量窗口为 832,584,900 ns，涵盖输入读取、依赖摘要、相机、mesh、光栅、PNG/npz 和逐图 metadata 发布。解释器/import 与最后 `RASTER_RESULTS.json` 自身写关未测。输入检查的耗时另有记录。各段按其原时界解释。

新的 Blender、模型和 API 运行均为零。公开输入、冻结相机、产品依赖和实际光栅的摘要分别保存在 `CAMERAS.json`、`DEPENDENCIES.json`、`RASTER_RESULTS.json`、`INPUT_CHECK.json` 和 `READABILITY.json`。
