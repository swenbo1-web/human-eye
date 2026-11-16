# M4 全场到局部观察的固定产品源码复核

本复核针对安装目录 `D:/he_m5_observe_measure_001/B/product`，产品提交为 `ccb608aa83de4b0e6671da89e0c8f387bd3f800e`，141 源文件摘要为 `7d2d4352f462c64a46e6fccf447c6f030c08b96e95517a3b2b6776ed50b69a6a`。本文记录实现合同。独立几何资格由本批 Fraction oracle 判定，源码本身不构成几何期望答案。

复核者曾编写部分产品接线及当前 saved checker。此作者关联保留，整个工作属于项目内部复核。

## 六个有限方向

`active_observation_host.py` 第 23–30 行固定 SCENE、TOP、LEFT、RIGHT、FRONT、BACK，目标至眼睛的原始方向依次为 `(4,-4,3)`、`(0,0,1)`、`(-1,0,1)`、`(1,0,1)`、`(0,-1,1)`、`(0,1,1)`。每张图为 512×512 正交投影。单边留白参数为 0.05。

全场拟合见同文件第 211–263 行。设全场顶点包围盒中心为 c，单位视线方向为 d。TOP 的 up seed 为 `(0,1,0)`，其他方向为 `(0,0,1)`。right 是 `normalize(cross(-d, seed))`，up 是 `cross(right,-d)`。以所有全场顶点相对 c 的 right/up 投影绝对值最大值为 h0，实际半画幅为 `1.1*h0`，完整 span 为 `2.2*h0`。每个方向独立拟合 span，中心共用。

`attention_rendering.py` 第 158–171 行使用全场几何确定眼睛距离和远端。眼距为 `max(.1, max((v-c)·d)+.1, span)`。near 为 0.08 米，far 为 `max(.081, max(camera_depth)+max(span,.01))`。`scene_rendering.py` 第 60–90 行构造 look-at 矩阵和正交矩阵，XY 投影系数均为 `1/half_span`。

局部拟合由 `blender_host.py` 第 575–683 行实现。局部目标真实顶点决定同一个目标中心及各方向的 XY span。眼距、near/far 则使用全场保守包围盒计算的有界深度。该路径包含向外舍入和已发布矩阵的精度检查，精度不足有独立 `active_observation_target_camera_numeric_insufficient` 出口。它的最终浮点矩阵可与全场路径存在末位差异。

本批应使用每个实际 scope 的 published matrices 复算像素界。不同新会话的 instance、capture state 和目录摘要分别绑定，不能要求它们跨会话相等，也不能虚构产品已提供跨尺度父子关联。

## 源数据和目标范围

`active_observation_host.py` 第 131–202 行把真实 host ID、实例 ID、原始捕获顺序、document epoch、revision、capture state 和 scope 纳入来源摘要。全场 scope 为 `complete_scene_meshes`。显式目标 scope 为 `target_observation_meshes`。目标目录、完整场景实例、保留/剔除对象和目标相机计划分别绑定。

同文件第 273–342 行发布对象源三角面的完整划分。`patch_support.regions` 中的 `triangle_indices` 是对象内零起始的捕获三角面行号。目标路径只把目标的区域计入 coverage，其他保留对象明确为 `occluder_only`，仍参与深度遮挡。被剔除对象保留在完整目录语义中。

捕获源面来自 evaluated mesh 的 loop triangles。它与任意原生多边形、原生顶点或 M6 局部修复域的对应关系需要另一层明确映射。本批固定资产通过原始与 evaluated 点面顺序的独立核验建立该对应关系。

## 栅格和可读阈值

`attention_raster.py` 第 22–84 行先裁剪到 NDC 三轴闭区间 `[-1,1]`。屏幕坐标为 `x=(ndc_x+1)*511/2`，`y=(1-ndc_y)*511/2`，采样点为像素整数索引加 0.5。重心权重下限为 `-1e-10`。正 camera-depth 严格更近时更新，等深保留先提供的源面。无背面剔除。

同文件第 86–184 行按实际 mesh 顺序及其原始 face 顺序处理所有保留三角面，共用一份深度缓冲。背景 RGB 为 `(18,22,30)`。对象统一基础颜色 `(180,190,205)`，光向量为归一化 `(0.4,-0.5,1)`，表面明度为 `0.45+0.55*abs(n·light)/|n|`。RGB 最终截取为 uint8。

`active_observation_images.py` 第 179–267 行按实际 patch owner 统计表面像素和对比边界。边界需要四邻域 patch owner 不同且 RGB 欧氏距离至少 24，边界两端都计入。正面区域只有实际表面像素至少 16 且对比边界像素至少 4 才 readable。位置框为实际 patch-owned 像素的 inclusive bounds，锚点选最接近框中心的实际像素，等距按 row-major。

`active_observation.py` 第 608–705 行把几何完整候选与实际 readable 图像结合，才形成 covered 的 complete witness。`pixel_evidence_insufficient` 与 `positive_area_occlusion_all_front_views` 有不同来源。未实际构造的方向保持 unrendered，不可作为实际图像证据。

## 归档数组与当前图像绑定

`active_observation_images.py` 第 36–175 行和第 333–425 行定义实际 frame。

- `color` 为 uint8 `[512,512,3]`。
- `depth` 为 float64 `[512,512]`，背景为正无穷，前景为正有限 camera-depth 米值。
- `owners` 为 int32 `[512,512]`，对象索引对应本 frame 的捕获 mesh 顺序，背景为 -1。
- `triangle_ids` 为 int32 `[512,512]`，其 scope 为 `zero-based-global-source-triangles-in-mesh-order`。
- `face_patch_offsets` 为对象面数累加的 int64 数组。局部面号为 `triangle_id-offsets[owner]`。
- `face_patch_ids` 把每个全局源面映射到 patch。非支持面为 -1，仍可赢得 RGB/depth 和 raw triangle owner。
- `patch_owners` 为 int32 `[512,512]`，有效值指向 `patch_roi_ids`。背景与非支持面均可为 -1，应通过 raw triangle owner 区分。

patch mapping 摘要使用版本、排序 ROI IDs、按捕获顺序的完整有理顶点/原面列表及每对象 face→patch 数组。owner mapping 摘要再绑定 owner schema、raw triangle scope、patch mapping 摘要和对象面偏移。PNG 解码必须与保存的 `color` 数组逐元素相等。

同文件第 384 行的 frame identity 绑定 scene/candidate、owner 映射、view、序号与 PNG 哈希。`active_observation_host.py` 第 451–456 行进一步构造 host image reference，绑定当前 host binding、view、PNG、patch mapping、owner schema/mapping 和 frame identity。

`live_spatial_mcp.py` 第 1360–1435 行把同一 producer 返回对象投影成 full 文本和原始 PNG native blocks。公开 binding 省略完整 camera specification，归档 full 保留它。公开 frame metadata 也省略 pose 和逐数组元数据，但保留其哈希和来源。因此 checker 必须同时核实际 stdio 返回、同 producer full 原件及 PNG/NPZ，不能把后台原件存在直接算成已交付。

## 独立验收接口

`checks/saved_frames.py` 不导入产品模块，不调用产品几何、遮挡、栅格或 MCP。它从原始 native wire 中以数据方式恢复 resident resources 和当次 capture，核 loaded host source payload，再绑定一次 public full 请求的实际 TX/RX 与 same-producer archive。每个源文件和原件都记录 SHA256。

像素验收直接解码 PNG/NPZ，重算全部 patch surface/boundary/readability，检查对象、全局源面、局部面与 patch owner 映射。另一条数值路径从 published camera 的逆矩阵发出正交世界射线，与原世界三角面作平面交点和 Gram 重心判断，验证实际 winner 的来源、深度及更近面。它只读取保存数组，不生成另一张图像。

射线检查的三角边缘和近等深数值带单独报告。对该带内像素只声明可接受的源面交点及最近深度集合，不声明已证明精确的浮点 tie ownership。几何遮挡及完整见证仍由独立 Fraction oracle 判定。

每个 scope 的三个合格小面的实际矩阵投影按 Fraction 精确计算，另加本批独立 oracle 冻结的 `2^-16` 像素向外分析余量，再统计可能包含的 pixel centres 上界。这是像素数量上界，不是可见像素数量。

初稿 CLI 使用 `--session D:/he_m4_global_local_001/sessions/global --eligible <本批 STATIC_QUALIFICATION.json> --output <checks 下新的结果路径>`。同样用于 local_open 与 local_covered。可选 `--capture` 只用于交叉核对外部导出，它必须逐字段等于本 checker 自己恢复的当前 capture。输出采用独占创建，保留失败和修订记录。
