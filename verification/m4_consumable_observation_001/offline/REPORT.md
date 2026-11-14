# 产品投影零光栅验收

候选提交为 `99fa034ee6074a9b674c1bb05b3328b91e9d93fe`。本轮产品改动位于 `active_observation.py` 和 `live_spatial_mcp.py`，分别增加当前状态的巡检/见证事实及默认v4投影。

## 已实现

- 核心short_facts保留原覆盖、世界向量和像素行，新增inspection与region_evidence。每个covered面引用实际登记顺序中的首个完整、正向、像素合格见证。
- inspection给出注册池、已观察/未观察计数、尚有几何候选的区域数、无完整几何候选及像素不足计数，显式区分prediction、仍需观察、有限池耗尽与证据不完整。
- 未观察区域按既有classifications分组视角原因。默认v4以去重视角组和既有pixel行索引连接区域，位置、法向、owned anchor与图片沿原表查询。
- 旧输入继续采用v1/v2/v3，full/debug保留完整事实。公开结果仍为一个JSON text块及原生图片。

一次short_facts仅调用一次既有覆盖summary。现有receipt像素遍历同时供原observations与新见证，现有view_masks/classifications供计数与未观察理由。实现过程使用元数据与实际状态。

## 固定保存结果

输入为显式消费001实际保存的SERVICE_RESULT、anchors实际保存的CoverageIndex元数据及原独立几何真值。覆盖索引仅从既存元数据重建，receipt仅回读原PNG作状态重放。

| 验收项 | 结果 |
| --- | --- |
| 支持区域 | 138，逐区域对应 |
| 当前完整可读见证 | 115，全部同时满足独立几何完整与实际像素门限 |
| 有限池未观察 | 23，22无正向候选，1正面积遮挡 |
| 尚有未观察几何候选 | 0 |
| 域外余量 | 源三角形48保留 |
| 上次漏报面 | BACK完整见证，468表面像素、84边界像素 |
| 原点+Z面 | SCENE为正向零像素，首个确定性完整见证为BACK，owned anchor为[419,224] |
| 点击与底面问题 | 原世界位置、像素对应及有限池unknown均通过 |
| 视角理由组 | 2组，供23个未观察区域复用 |

readable=true但几何不完整、仍有未观察候选、prediction-only、像素不足、scene/camera重绑定和patch映射失效的状态检查均通过。新投影对计数、见证引用或未观察分组冲突保留完整输出回退。

## 执行记录

| 记录 | 结果 |
| --- | --- |
| REPO_RESULT_01 | 保留失败。验收脚本错误限定原点见证必须LEFT，实际按既定receipt顺序选择BACK |
| REPO_RESULT_02 | 171项检查通过，19项既有零raster测试通过 |
| REPO_RESULT_FINAL | 同上，补齐实际Python/NumPy/Pillow和模块来源记录 |
| INSTALLED_RESULT_01 | 首轮通过171项检查与19项既有测试，实际模块路径均位于D:/he_consume_001/product |

首次验收的固定LEFT假设已修正为任意当前合格见证，产品仍按原确定性登记顺序选择。所有历史失败原件保留。

既有子集包括active_observation_brief的6项、patch_delivery的5项、region_delivery的5项、纯世界向量编码的3项。真实几何/index/observe_capture/raster入口均安装拒绝守卫，守卫调用数为0。

本轮新模型调用为0，新光栅为0，实际observe_capture为0。未运行实际采集、几何/index构造、Blender、renderer相关旧用例及真实模型消费。正式槽由根任务执行。

## 字节与时钟范围

相同保存状态的旧v3公开JSON为42,049字节，新v4为44,873字节，增加2,824字节。新格式保留原字段和原生PNG内容，附加见证索引及分组摘要。独立投影CPU耗时未单独测量，沿用scope_and_facts和完整MCP交付时界的既有范围。

## 来源摘要

- active_observation.py为 `3d73af68f8ab715a7c84873fc1d4dc2ba23334ec00e6d29bc634eede6630eb30`。
- live_spatial_mcp.py为 `d8b62cef7d9a60d08bb22e3534b1bb7ab2562f05777bff2ee9a46e77c87a80e7`。
- 离线脚本为 `a624c3724607fcdbb4b8efb79379d3d66a3809c87541b8dce67c22a31ae5299a`，支持显式product-root。
- 仓库最终记录为 `ad501e58b66976fd9a361ea014971210f9a5b14785ab409c37c84d4dac183bb2`。
- 隔离安装首轮记录为 `98acf8b1d8a0c228eb260f7388f1891fb9e9ee6e6d8cb036f072eb40514e2759`。

产品源和离线脚本已停更。后续真实消费及安装交付资格按根任务唯一正式槽验收。
