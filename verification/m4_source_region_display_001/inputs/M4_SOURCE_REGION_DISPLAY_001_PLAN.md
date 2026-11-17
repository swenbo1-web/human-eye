# M4-SOURCE-REGION-DISPLAY-001

2026-11-17。修复真实Yanyite资格已确认的source_region图像参与及零区域像素反馈。一项端到端正确性修复，复用当前宿主捕获、通用帧、来源绑定和M3，新增模型/训练/付费调用均为0。

## 固定反例和目标

起点828d1265a3434fd1b5fb97e4759acaedd9253bc0，产品2292c3d79e9996fb29b0c3351102998923113d56、143源8d8d3d60e99b5e039e6711c168f95d648124e96eea03b0a061b2796c5a690600。新namespace为verification/m4_source_region_display_001，runtime为D:/he_m4_source_region_display_001，候选安装隔离。

真实原件Yanyite_Appearance.blend的SHA为614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d，目标及ARM748面/410点保持固定。原文件Cube的hide_get/hide_render为true、visible_get为false，但其全部12三角进入分析图，五次交付的选区像素均0。当前顶层complete/locally_observed和observed_samples掩盖了这项证据不足。

本批source_region图片采用捕获时active view layer的有效可见网格合同。以宿主实际visible_get(view_layer=捕获层)的结果决定图片参与，记录hide_get、hide_viewport、hide_render等原始标志供解释。图片scope明确为该view layer；hide_render和viewport专用状态各按实际来源标明。

完整几何捕获继续提供量测、来源和源面编号。隐藏Cube作为明确reference的表面距离仍使用其真实12三角，预期选区距离保持0.37011719389236364米。本批改进的是当前图像取证与消费者反馈。

## 必要接线

### 宿主当前显示快照

每次当前捕获提供active view layer身份、逐对象host_id/instance_id、有效viewport可见布尔及解释标志，形成小型display snapshot和稳定摘要。快照从当前宿主读取，O(对象数)，同次读取复用，不为这些布尔字段重新展开网格。

当前驻留signature已有hide_viewport/hide_render，hide_get及有效visible_get尚未覆盖。显示切换必须使快照更新，即使顶点、面和矩阵保持。resident命中、delta编码/解码和非resident普通捕获都按实际来源传递该快照，避免缓存带回旧可见性。

### 图片参与与源索引

source_region通用帧沿完整源对象及完整三角offset保留owner映射。图片阶段应用参与掩码，跳过不可见对象的绘制。掩码与帧identity、image_ref、相机及image scope绑定，输出清楚列出参与/未参与对象及依据。

使用现有栅格与帧原语完成，保留完整源索引空间，测量继续从原capture及所选面取数。旧默认观察、矩形region_task、距离和执行相关路径按当前各自合同回归。

当前完整场景generation仍沿已有host/region_ref契约。显示改变后原ref若按现generation失效，给出原原因，fresh选择更新。图片key包含当前display身份，几何代际未变化时同样区分不同显示状态。恢复相同display/geometry且原binding仍有效时可复用对应旧帧，实际构造据实计数。参考对象参数切换和同态复读按原规则复用图片。

### 零样本的直接反馈

include_image=true且区域没有任何实际源面像素时，visibility.status为unknown，observation_status明确evidence_insufficient，顶层给partial并保留已测量的task_result。原因区分目标未参与当前viewport与已参与但没有当前像素，附实际选区计数和当前图片范围。

有实际选区样本时交付observed_samples，完整曲面可见性继续按现证据表示unknown。include_image=false沿image_not_requested和正常量测路径。原始MCP JSON、默认brief及full同样表达这一结果，缓存也保持相应状态。

## 验证矩阵

产品实现前固定输入、条件、输出和单一修复范围。当前真实source和旧错误图片保留。采用以下实际状态序列，全部在拥有的未保存副本执行。

1. 原Yanyite状态，Cube隐藏、角色可见。fresh source_region使用当前visible snapshot，Cube不参与图片，继续参与量测。原SCENE相机及选区不改，记录角色实际可见样本。
2. 同态public region_ref复读，brief/full交叉核对，新增构造0。全部图片/显示/来源及距离对应当前状态。
3. 将Cube的viewport临时显示，角色保持可见。图片再次出现Cube遮挡，选区0像素，返回明确partial/evidence_insufficient，距离正确。
4. 恢复Cube隐藏，当前图片恢复参与集合与对应结果，证明图片缓存没有跨显示状态复用。
5. 隐藏角色目标并请求其区域，量测来源继续按完整capture处理，图片明确selected_region_not_displayed或等义原因，保留真实状态。
6. 恢复角色显示，完整显示标志和几何恢复，当前请求及重复请求正确。

隐藏/显示使用夹具的view-layer对象状态控制，保存完整前值并恢复。四次fixture可见性setter、产品setter0，不保存blend。原件/副本文件与全部顶点面矩阵前后核同。

根纯离线探针已按原SCENE和当前53264三角验证，排除隐藏Cube后，源面35618、35619、35620的中心均在视窗内且精确无遮挡。预检在verification/fixes/20261117_real_asset_region_review/geometry/VISIBLE_BODY_PROBE.json，实际像素仍由本批验证。若实际出现其它自遮挡或采样不足，保留unknown及原因，几何和视角保持固定。显示规则、连续遮挡及图像有用性分别核定。

## 纯回归与原件检查

有限纯/mock控制覆盖viewport和render标志不一致、对象/collection可见性的宿主结果、缺失当前显示来源、显示变化而几何generation不变、图片mask保持全局源索引，以及同态缓存、foreign/saved帧和producer proof。缺失当前显示来源时按事实给出图像unknown，已有几何量测可继续。

保留旧source_region的冷/热测量、stale ref、局部相机和M3源见证回归，以及M4旧默认/region_task、图片构造额度、原期限、取消和受控源字节回归。纯控制使用合成帧时把编码成本另列。

独立核当前宿主visible标志、参与掩码、原对象及源面offset、PNG/RGB/depth/owner、源样本与默认brief/full反馈。图像最近遮挡采用固定16×16网格加748选区面中心的射线抽样，全图另核声明源成员和深度；抽样分母与全图范围分别记录。

## 实际预算与收口

最多2个fresh owned、8次实际raster、0额外Blender准备、0模型/训练/付费调用。每请求30秒、每owned600秒原期限。第一会话检原状态及复读，第二会话检上述显示切换与恢复。实际构造失败、不可交付图片及额外恢复均累计计入8次。

记录捕获/显示读取/掩码、几何准备、栅格、validation/编码、缓存、公开交付和完整owned成本。当前反例旧图没有选区证据，新图的质量变化和新增成本分别验收。这是正确性与能力修复，性能结论按实际窗口记录。

完成固定提交/安装、当前显示合同、原反例及新正常/拒绝路径、源映射、距离、图像、实际状态恢复、完整成本与所有失败/unknown/未运行。回报M4-SOURCE-REGION-DISPLAY-001_READY一次后结束本批，待根独立复审。M6另线、Google/key暂停，正式默认部署和原资产保持既有流程。
