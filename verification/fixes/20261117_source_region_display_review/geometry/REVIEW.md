# M4-SOURCE-REGION-DISPLAY-001 几何与显示域独立复核

本轮检查通过。作者固定提交为 `aa45f033ce662b7453dda77084b36da34640f558`，读取时作者工作树 HEAD 与该提交一致且工作树干净。产品固定提交为 `29f35a77`。本轮仅执行独立离线程序，检查原生导出、实际 wire 捕获、完整服务回包及显示夹具回执。

## 实际验证

- 独立程序 `review.py` 共通过 526 项断言，输入路径、字节数与 SHA256 均保存在 `RESULT.json`。作者 checker 和作者通过计数均未作为通过依据。
- 核验全部 6 份 fresh 原生导出。角色始终为 27,304 顶点、29,073 原生多边形、53,264 求值三角形，Cube 始终为 8 顶点、12 三角形。每份导出的原生、求值、矩阵、父级、修改器和动画字段均与上轮独立核验的固定原件逐项规范序列化一致，原生与求值数组一致。
- 748 个源三角形、410 个源顶点和紧凑三角形到原源顶点映射完整一致。748 个源三角形到原生多边形映射重新核验。8 份实际服务结果的源行、紧凑索引及完整捕获数组均与上述原件一致，隐藏 Cube 仍保留于完整几何与参考目标。
- 8 份实际结果的 6 个相机规格均逐项等于上轮固定规格。每个会话内 camera identity、geometry identity 和 ordered geometry SHA 在四次显示变化中保持一致。
- 由完整 Cube 六面覆盖和选区线性坐标界重新独立得到最近距离 `3333719312994125/9007199254740992 m`，转为 binary64 为 `0.37011719389236364 m`。8 份结果均等于该答案。最近源点为 24331，属于源三角形 48160、48161，对应原生多边形 26521。参考三角形为 Cube 行 0、原生多边形 0。最近方向为世界 +Z，世界见证坐标逐值一致。
- 全部 410 个选区顶点严格位于闭合 Cube 内部，三角形的凸组合保持内部关系。正距离表达选区曲面到 Cube 表面的无符号距离。内部包含关系应随测量结果一并理解。
- 6 份 fresh 快照的 SHA 重新计算通过，实际捕获快照的 unsigned SHA 重新计算通过。逐对象 host ID、instance ID、`visible_get`、`hide_get`、`hide_viewport`、`hide_render` 与对应 fresh 状态一致。
- 图像参与掩码按完整对象顺序分别为普通 `[true,false]`、Cube 显示 `[true,true]`、目标隐藏 `[false,false]`。Cube 在显示阶段仍为 `hide_render=true`，其 `visible_get=true` 正确驱动当前活动 view layer 图像参与。
- 四个显示夹具分别执行 Cube 显示、Cube 恢复隐藏、目标隐藏、目标恢复显示。实际 fresh 状态、四份回执及 fingerprint 链一致，最终完整显示层快照等于初始快照。每份回执记录一次夹具 `hide_set`、零产品 setter、零资产保存。已读取固定夹具实现，状态变化位于其 `_apply_display_step`。
- 6 份正样本回包记录 35,452 个选区像素，状态为 `locally_observed`。Cube 显示和目标隐藏两份回包均为零像素、`partial/evidence_insufficient`，分别记录 `selected_region_displayed_without_pixels` 与 `selected_region_not_displayed`。8 份回包仍保留 `complete_surface_visibility` unknown 和空 complete witness。像素值在本分工中核对实际回包，独立 PNG 与 ray 结果由交付同行另行验证。

## 源码域核对

已读取 `source_region.display_state`、`prepare_region`、`observe_region`、`measure_region` 和固定夹具显示实现。显示参与源为捕获时活动 view layer 的 `visible_get(view_layer=...)`。测量仍把完整选区与完整参考 mesh 交给现有曲面求解器，显示 mask 进入图像路径。源码与实际八份完整捕获均保留全几何、原对象顺序和源三角形索引域。

公开显示 scope 为 `active_view_layer_effective_viewport`，本批 fresh 快照的具体 3D viewport 为 null。此验收覆盖活动 view layer 的对象参与状态，Local View 等具体窗口上下文语义留待独立需求与样例。

## 复用与未运行

- 上轮独立程序和输入原件先固定 SHA，再比较本批全部几何字段相同，复用此前完整原生多边形/求值矩阵核验。当前重新计算了闭箱六面界、最近点和源面/原生多边形归属。
- 上轮无 Cube 的纯离线相机探针已证明同一相机下至少三个固定选区三角形中心可见。本轮完整相机与源几何相同，复用该存在性结论。完整曲面可见性继续记 unknown。
- 本分工新增 Blender、MCP、raster、图像编码、模型、付费 API 调用均为零。完整新 live 生命周期、PNG、ray、模型消费、性能收益与费用均未运行，由对应分工或后续任务验收。
- 本轮独立脚本执行未发生失败。前批独立程序的 R0 错误及更正记录保持原封存。

## 身份记录

本轮使用自身 Hook 句柄 `2177bc02fec34553b8a2f368baf24a95` 恢复 Agent Learning 上下文。当前父任务为 `eed67225-f61c-4c6d-a712-2c4c4a40e74c` rev1、epoch747。AL 返回的历史子 assignment 仍关联旧任务 `d718d092-1718-414a-85bf-d636c6bc9f09`、epoch740，并显示 current=false。按当前父任务明确委派范围执行只读复核及本目录写入，未借用其他句柄或改写父任务。

## 复现与结果

运行 `C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe -I -B -X utf8 D:/hefe/verification/fixes/20261117_source_region_display_review/geometry/review.py`。

- 独立程序 SHA256 为 `5c59b2b255229ebcd6d00c9a4b6b3714d277fb99d438f8d0d29d75d45ff57afa`。
- RESULT SHA256 为 `818b579630e37b7be8c9ee0fb9fe298602cffcd76768b1adc1f226e3e87ac56f`。
- 通过范围内未发现实质缺陷，失败项为 0，未运行项如上。
