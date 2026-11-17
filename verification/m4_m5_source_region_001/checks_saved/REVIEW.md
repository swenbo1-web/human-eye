# M4-M5-SOURCE-REGION-001 保存证据复核

## 结论

六个正式槽和状态槽的独立保存验收通过。三对正式任务共十二次公开请求，逐次验证当前源、区域取景相机、全场遮挡、原生图片字节、距离、最近点及原始行号映射。三对成本准入由根代理单独评估。

首次 qualification_R0 的源几何、距离、见证、图片字节和实际像素归属验收保留。根复核发现该版本使用全场相机，区域仅有13个像素样本。追加的区域相机检查准确拒绝 `camera_common_center_exact_selected_bbox`。正式 pair1_R0 使用修正后的 R0F，是首次通过局部取景验收的槽。首次失败、原保存检查器和实际原件均已归档。

## 固定资产与答案

资产 SHA256 为 `b9cf3671bc8cd5b88ed23118f229a6e753eda40802d35a3ad297961e0a9edcf9`。场景包含11个对象、64个顶点、62个三角。保存前与重开后逐行一致，原始 vertex、polygon 和 evaluated triangle 行序均与固定世界坐标配方对应，矩阵为单位矩阵，单位为米。

Obj_07 的前四个源三角构成非共面凹 L 区域，后两个源三角组成连接斜翼。有理数预检通过坐标界和达到界的显式点证明下列答案。

| 范围 | 到 Ref_B | 到 Ref_C |
| --- | --- | --- |
| 所选四个源三角 | 5/4 m | sqrt(137)/4 m |
| Obj_07 全部六个源三角 | 1/32 m | sqrt(2305)/32 m |

Obj_07 沿世界 X 平移1/4 m后，所选区域到 Ref_B 为 sqrt(5)/2 m。实际状态槽得到1.118033988749895 m，恢复后得到1.25 m。整对象控制实测0.03125 m和1.5003254855197254 m，最近点位于原始源三角第4行。

## 源、相机与图片

索引域为当前 evaluated capture mesh 内的对象局部三角行。公开 region_ref 包含 document_epoch、host_id、instance_id、capture_generation、完整场景 ordered geometry 摘要和源三角集合。复核程序从原 WIRE 解析当前捕获和驻留资源变换，逐行比对固定场景，并独立重算 region_id、几何摘要、相机与 owner/frame/image 引用。

区域相机以六个所选顶点的 AABB 中心 `(35/8,35/8,17/16)` 取景。独立 Fraction 投影验证全部所选顶点落入每个公开相机的 NDC 范围，按所选顶点的 right/up 对称投影范围核原有1.1倍 half-span padding。六个相机均逐一检查完整11对象的88个 AABB 角点深度。SCENE 的实测取景跨度为1.1667261889578036 m。

正式图像四个所选源三角分别拥有8427、13108、1869、2808个像素，共26212个。SCENE 全场前景40651个像素均有明确的最近源交点。独立射线复算覆盖每幅512×512保存帧，检查全场最近深度、对象 owner、源三角 owner和光照 RGB，并将 PNG 解码结果与 NPZ 的 RGB 数组及公开 native image 原字节逐一核对。

可见性结果表达实际源三角像素样本。距离量测覆盖全部所选源三角，包含图中未显示的部分。原始 polygon、vertex 与 evaluated triangle 的行序对应在本批固定资产上取得逐行实证。

## 复用、状态与控制

每个正式槽首次选择 Obj_07 前四面量测 Ref_B，第二次实际请求使用首次公开返回的 region_ref 量测 Ref_C。两次 region_ref、frame_identity、image_ref 和 RGB/depth/object owner/triangle owner/patch owner 原数组 SHA 均相同。六个正式槽跨 R0F 与 R1 的这些原数组也完全相同。

状态槽十一条请求通过。原默认 active 路径交付六张当前原生图并逐张通过全场射线复核。区域重复与 B/C 切换复用原帧，区域子集变化取得对应的新引用。移动和恢复后的旧引用分别准确返回 `source_region_ref_capture_generation_changed`，各自对应零原生图、零成功 producer archive和零 raster事件。两次当前选择成功，恢复后的 ordered geometry 与初始一致且绑定当前 generation。状态槽实际 raster事件总数为10。

仅本批拥有的测试副本执行两次固定矩阵 setter。保存的回执及完整场景捕获支持移动和恢复检查，product setter为0。末尾两个原 task 路径整对象控制使用全部六个源三角并交付纯文本结果。

## 优化计数和字节生命周期

三个 R1 正式冷请求均记录 fresh_payload_reuses为1、frame_array_decodes为0。热请求两项均为0且 frame_reuses为1，generation_work保留冷请求的1/0计数。状态槽四个新帧请求与两个复用请求的实测计数遵循相同规则。

正式帧的私有压缩 archive payload为231254字节，发布后 retained encoded payload为0。该数值覆盖 immutable compressed payload长度。BytesIO 分配器开销和进程峰值 RSS尚无量测。R0F的一次数组解码由冻结源码的成功验证路径推导，原始 R0F运行未预先设置该计数器。

## 复核关联与留存

夹具与独立 oracle由同一委派代理编写。oracle导入固定的历史独立数学和射线辅助程序，产品实现导入数为0。根代理另行复核冻结来源，并发现和纠正首次漏验的局部相机要求。

构造器固定的 TASK 原件使用作者选择的 full detail。根代理实际正式请求使用默认 brief，状态重复请求使用 full。独立检查将两种公开投影与同一次 producer archive交叉核对，TASK_REQUEST_BINDING记录该选择。冻结检查器保留，后续相机、计数与真实 trace字段接线通过单独 adapter追加。

QUALITY_REVIEW记录汇总结果和直接来源 SHA，THREE_PAIR_QUALITY记录三对质量等价，state记录十一条状态请求及原错误。每个正式槽的独立复核和 stdout/stderr均已保存。本代理新增 Blender进程、实际 raster和模型调用均为0。
