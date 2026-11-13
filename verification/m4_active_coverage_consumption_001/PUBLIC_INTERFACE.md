# 当前场景的公共观察接口

两路都有 `execute_python`、`scene_data`、`render_views`、`read_images`，P 增加 `active_coverage`。一次工具调用可以完成普通 Python 算法、批量渲染和实际图片交付。

## Python 已有变量

- `geometry` 是完整输入字典。`geometry['objects']` 中每项包含 `name`、`vertices`、`triangles`。每个顶点是三个有理数字符串，例如 `['1/20','0','-1/100']`，三角形使用本对象零基顶点索引。
- `cameras['views']` 保存完整候选相机。每项具有 `name`、4×4 `view_matrix`、4×4 `projection_matrix`、`direction_rational`、`size_px` 及其余冻结参数。矩阵、投影与输入保持一致。
- `np` 为两路相同的 NumPy 模块，`Fraction` 为标准库有理数类型。
- `buffers[view]` 在该相机首次生成后提供三个只读原始 ndarray。`color` 为 uint8 `[H,W,3]`，`owners` 为 int32 `[H,W]`，`depth` 为 float64 `[H,W]`。行从左上角开始，owner 对应 `geometry['objects']` 的零基序号，背景 owner 为 −1，depth 是正相机深度，背景为正无穷。
- 对比边界数使用目标所属的唯一像素。水平或垂直相邻像素 owner 不同且 RGB 平方距离至少为 `24*24` 时，标记该对的两个端点，再对目标所属端点去重计数。
- `scratch` 为本会话可写 Path，`image_files` 映射当前已生成图片 ref 到 PNG 路径。普通 Python 变量持续保存，源码输入保持原字节。

## 批量操作

`render_views(names, include_images=False)` 可在普通 Python 中调用，也有同名 MCP 工具。`names` 为一个或多个候选相机名。返回每个结果的 `ref`、`view`、`size_px`、`mimeType`、`buffer_handle`、`status` 和 `cached`。

每个相机首次请求进行一次全场景光栅。重复请求复用同一 PNG 和数组，失败尝试也占用该相机，最多六个不同相机尝试。全部物体共享同一 depth/owner 光栅。

`read_images(refs)` MCP 工具批量交付实际 PNG。Python 内的 `read_images(refs)` 或 `attach_images(refs)` 请求把这些图片附到当前 Python 工具结果。`render_views(..., include_images=True)` 同样请求附图。图片顺序沿用请求顺序，每个引用标签紧接其 image content。

以下示例用调用者选定的候选相机名完成一轮批量观察。该接口允许在同一代码段前置任意独立几何算法。

```python
selected_names = [cameras['views'][0]['name']]
frames = render_views(selected_names, include_images=True)
for frame in frames:
    rgb = buffers[frame['view']]['color']
    print(frame['ref'], frame['view'], rgb.shape)
```

`scene_data({})` 返回相同的完整 geometry 与 cameras，供需要直接文字读取的调用使用。数据在第一次 Python 调用前已驻留。

## P 的主动入口

`active_coverage(include_images=True)` 可以第一次就调用。它在当前输入上计算冻结几何索引，选择候选视角，调用公共渲染，再使用实际 RGB/owner 像素反馈更新观察状态，直到当前有限池没有新的候选收益。返回 `panels`、当前生成的 `images` 和 `image_refs`。

每项 panel 包含 `object`、`object_index`、`region_id`、`status`、`views` 和 `reason`。证据项给出相机、当前图片 ref 和实际像素计数，未覆盖项附当前有限池的几何原因。默认同时附实际图片，可显式设置 `include_images=False` 获取文字事实与可追溯引用。

核心的局部观察回执确认本地新生成且可读取的 PNG。CLI 接收及模型工具结果按另一层传输回执独立计数。每个会话从空应用图像缓存开始，操作系统缓存沿用当前状态。

## 启动和私有审计

`actor.py --config CONFIG.json` 沿用 held TCP owner 与现有 stdio_attach 透传。CONFIG 包含 `group`、新的 `output`、`endpoint`、`worker_deadline_ns`、`input_manifest`，固定 `max_tool_calls=12`、`max_render_attempts=6`。原始绝对期限直接传入全部观察、图片构造和响应步骤。

私有 `OBSERVATIONS.json` 保存当前 source_inputs、所有 render_attempts、完成帧、stage、active index/steps/final_state 和错误。每帧的 PNG、NPZ、FRAME.json 和 P 的 PIXELS.json 各自保留哈希与字节。MCP 公有结果按请求输出必要事实、引用和图片，完整数组留在 Python namespace。

图片编码完成即累计 constructed 数及原 PNG/base64 字节。JSON 序列化、最终期限或发送失败独立记录。交付准备和实际 sendall 确认分别计量，CLI 接收仍由消费者原始事件核验。
