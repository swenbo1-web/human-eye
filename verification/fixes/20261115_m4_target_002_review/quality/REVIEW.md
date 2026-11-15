# M4-TARGET-ACQUISITION-002 保存质量独立复核

2026-11-15。复核输入为固定最终交付 `71a505135ecf202c0e8572fb01bbe21c410342e2` 的保存原件，脚本独立编写于本目录，不导入作者 checker 或产品模块。新增 Blender、raster、产品请求、模型消费均为 0。

通过本轮检查。`review_saved.py` 最终运行 1393 项检查全部通过，分母为正式 12 槽、6 对、18 张原 producer 帧，另有缓存 3 阶段和旧 peripheral 2 槽。检查数量不是独立场景样本数。

- 从原 native WIRE 回复解码宿主 packet，按实际 resource revision、矩阵与单位重建采集坐标。捕获文件和 WIRE 请求/响应均核原字节 SHA。所有实际读取对象逐点逐面比对根冻结几何。正式目标及其后续定量回读的坐标、面序、源对象和场景代一致，capture-local mark_label 按各自选择范围处理。
- 正式主场景的全部 6 槽均为 2 支持、1 完整、1 未知，实际构造 SCENE。target-only 全部 6 槽为 2 完整，实际构造 SCENE、LEFT。每对实际 camera plan、两区域位置/朝向/状态/原因、六方向几何分类和完整见证一致。每个完整见证指向已交付且可读的 producer pixel row，且对应方向几何 complete。
- 18 张正式 PNG 与 response image 的 base64 原字节、NPZ RGB 一致。NPZ 的 face offsets、所有前景 source triangle ID、object owner、ROI patch owner 均从已核网格顺序与目标源面 0–511/512–513 独立重建。按冻结对象名和对象内面序归一后，6 对的全像素 RGB、depth、asset owner、source-local face、patch 均一致。
- 像素可读性重新计算实际像素数、包围范围、中心最近 anchor 和行优先平局规则。独立四邻域向量化实现重算 RGB 平方距离阈值 24² 的边界对比数，并核对可读门限。
- 主场景实际捕获 A 14 对象、B 6 对象，控制 A/B 各 1 对象。缓存初始/移入/恢复的完整数 1→0→1，source revision 1→2→3，三个当前 binding 各异。Far11 从排除转为保留遮挡后再排除。中间态 depth 与 asset owner 实际变化，恢复后的所有归一 buffer 与初始相等。
- 缓存控制的实际 Far11 点坐标逐点匹配 `(z+9/8,y−1/8,67/32)`。move/restore 收据各为 289 点赋值，矩阵前后均 identity。这覆盖几何顶点变化失效，实际 matrix setter 路径未运行。
- 旧 peripheral 的 A 接受原件与 B 新记录，目标 1 支持、0 完整、null witness、全部实际帧和六方向分类一致。独立用 Near 原始 x 及 LEFT 方向推导遮挡三角的双直角边均为 x，面积 x²/2，得到 `73786983304225/9223372036854775808`，为严格正值，与原报告一致。

正式未构造 TOP 等方向的像素维持未运行。本轮未重新执行相机、渲染器或重建全部六方向遮挡答案。保存分类的 A/B 一致性、已有根冻结几何答案及旧 Near 独立正面积证明共同构成本轮几何结论。产品源身份、完整归档和性能门限由根的其它独立复核覆盖。

质量范围内未发现阻止接受本候选的缺陷。后续同状态复用应继续传递源对象与对象内面序，避免重新根据屏幕位置反查目标几何。
