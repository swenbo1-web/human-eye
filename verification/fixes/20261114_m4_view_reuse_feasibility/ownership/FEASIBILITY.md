# M4 重复 SCENE：原三角形所有权的最小补齐方案

结论：适合做一个小修复。复用已有帧记录；首帧保留原三角形 winner，再由现有映射生成 patch owner。无需新缓存框架、单点求交器或修改 raster 内核。本轮仅静态阅读和已存 NPZ 离线核对；新增 product/model/Blender/raster 调用均为 0。

## 固定输入与实际核对

产品来源摘要 `6d4f7d363aaa48081eff7db467fff20665419172560f19b3a4ccb0fbb46c900f`。读取时作者 HEAD 为 `3689ab0726fb05f1dd45e7f8fd628c3081d6835a`；本次两份关键产品文件与 `D:/he_consume_001/product` 安装副本逐字节 SHA 相同。输入的绝对路径、长度和 SHA256 全见 `INPUT_HASHES.json`。

核对 P1 已存 product SCENE 与第四次 native SCENE：pose、PNG SHA、color/depth/object-owner 全部一致。产品仅保存 `patch_owners` 和多对一 `face_patch_ids`，没有原 winner。区域 72 的可见像素确实来自原三角形 34 和 35，不能把 patch 72 当作原三角形编号；查询像素 `(109,247)` 对应原三角形 35。以保存的 native 原三角形编号查产品 `face_patch_ids`，整幅 512×512 结果与产品 `patch_owners` 逐元素相同。此项是已有结果离线核查，不是新实现回归。两份现存数组背景 sentinel 都是 -1。

## 为什么现存数据不能直接恢复任意原 winner

现存 RGB/depth/object owner/patch owner、来源三角形集合可直接复用。patch 到 raw triangle 是一对多，metadata 没有记录同 patch 中哪一个三角形赢得某像素。单点几何测试可以重新计算候选，但要复现裁剪、像素中心、边界 epsilon、深度严格小于和同深度先到先得；当前没有这一公共单点实现。为本次复用增加求交器比首帧保留 winner 更复杂，且不能称作“读已有 raw ID”。

## 推荐实现

`attention_raster.py:45` 的 `_raster_triangle` 用同一个 `nearer` mask 写深度、颜色、对象和 caller 的 face ID；ID 不参与判赢。`rasterize_attention` 的第四数组已经可以保存任意合规 int32 face ID。

1. `active_observation_images.py:89/262` 继续使用当前 mesh 顺序和 `face_patch_offsets`，每个 mesh 准备全局递增原三角形编号（与 native_tools.py:172 的定义相同）。每代准备一次。
2. `render_view:300` 首帧照常只调用一次现有 raster，传上述编号作为 `face_patch_ids`，将第四结果明确命名为 `triangle_ids`。对前景执行现有扁平映射 `patch_owners = face_patch_ids[triangle_ids]`，背景保留 -1。未纳入 patch 的前景原三角形仍可有 raw ID，其 patch 保留 -1。
3. 保留这两个数组。`_validated_patch_buffers:117` 当前会丢弃额外字段，需明确保留可选 `triangle_ids`；NPZ 保存、元数据、`observe_frame:379` 加载时一并支持该可选字段。原 buffer 顺序和意义不能替换。
4. native adapter 的 `active_observation:380` 当前登记 by_ref/by_view，却不填 buffers；新帧登记时用同一记录提供 color/depth/owners/triangle_ids，并另保留 patch_owners。`render_views:341` 的 fresh-only 合同需由负责接线者明确调整为同有效帧复用、显式 fresh 才重建。不能用旧版本 fresh-only 文案宣称已实现复用。

### 旧合同和历史文件

无需修改 raster 签名或 2/3/4 元组返回规则；现有 caller 和 patch-only 输入保持原行为。产品旧三缓冲 whole-object patch fallback、旧四缓冲 patch 文件仍按原规则读取；新增 raw 字段是可选能力。旧 NPZ 没有 raw 时只提供其真实已有的图像/patch 能力。若调用方明确需要完整 native raw 合同，允许正常构造一次新帧并缓存，或明确返回能力缺失；不得从 patch ID 伪造 raw，也不能改写历史 NPZ/构造账本。本次六槽冻结结果不重跑、不追溯改分。

## 成本与备选

当前 renderer 允许 64..512 的正方形帧。新增常驻 `int32[512,512]` 为 **1,048,576 B = 1 MiB/帧，三帧 3 MiB**；原四数组为 4,980,736 B/帧。全局 source-ID 列表另需 4T 字节（该场景 T=3337，即 13,348 B/代）。查表 O(P)；简单布尔索引实现还产生短暂 mask/gather，最大约 2.25 MiB，不应误称零开销。新增 hash/NPZ 写入及压缩后大小尚未测。raw 不进入模型文本，交付稳定 frame handle 即可。

备选是 raster 内额外写第五个 raw 数组，省查表却增加 raster 函数参数、每个 winner 的写入和调用合同面。本次优先不改内核的查表方案；除非定向测量证明查表成为显著成本，不再另做一轮内核优化。

## 最小验收

同输入首帧仍一次 raster；随后同 SCENE 连续请求 3 次，raster 和已构造图片计数均不增加，raw/patch/PNG/depth/object-owner 与首帧一致。保留显式 fresh 的真实计数。用多对象原序、同 patch 多三角形、裁剪/共面边界和未支持 patch 前景核对 raw ID；scene/camera/mesh-order 改变后不能命中旧帧。旧三/四数组文件继续可读，但不宣称含 raw。记录首帧额外耗时、内存、NPZ 和重复请求节省；本报告不声称端到端收益已经验证。

离线复核脚本为 `inspect_saved_frames.py`；结果为 `SAVED_FRAME_FINDINGS.json`。未修改产品、作者 worktree、安装或正式试验目录。
