# M4-ACTIVE-IMAGE-CONSUMPTION-001 静态审查边界

计划 SHA256 为 `8477d53bdc9807c718b370fe9f3cc811906b5069653555e64e32b8020e28a427`。审查方不启动真实 CLI 模型、provider、付费 API、Blender 或 renderer。准备阶段只审源码、封存 schema/prompt 和本地协议原件。

## 盲性与两路合同

- 两路同一共同题面和 view-a、view-b 呈现顺序。输入 PNG 原字节相同，公开内容只出现 opaque refs、媒体类型、尺寸和实际 image blocks。
- consumer 可见 prompt、schema、示例、工具文本、错误和路径不带 BACK/SCENE 来源标签、owner/ROI/深度、预期答案、管理员计划或旧报告。
- 两路保留同一通用 Python 能力和通用 read-image 能力。P 的主动观察实验出口最终使用同一个 PNG→MCP image content helper。缺少 bpy 时不公开 execute_blender_code。
- 固定 CLI 0.152.1、gpt-6.1-sol、medium、现有 Pro 登录与服务设置，两路各一个新会话和用户轮次。单路最多四工具请求，启动前固定原始 450 秒绝对期限，所有工具和异常继续使用该期限。
- 每路实际执行一次。普通单路失败可继续另一独立路，共同传输接口确定无效则停止剩余路，原失败与未运行保留。

## 三层证据

1. 服务端构造层从真实 PNG 字节、严格 base64 和正确 MIME 核 image block，记录 SHA、尺寸、数量、原 PNG/base64/JSON 字节及实际请求顺序。
2. CLI 接收层使用本批真实 CLI 工具事件，绑定实际 raw MCP 响应及 image 内容。无模型 fakeCLI 和本地 stdio 检查只证明本地协议接线，无法代替真实接收层。宿主未暴露 provider 内部请求时记录未观测。
3. 回答消费层独立核实际最终回答及工具代码。如果模型通过 Python 像素统计推导答案，则记录计算正确和视觉消费未证。自称看见或路径文本无法单独证明视觉参与。

## 本地协议与正式成本

- 本地允许核封存图片 SHA/解码、两出口 image blocks 逐字节相同、标准 MCP response 经 stdio/TX/RX 保真、refs 和顺序、真实内容计数。准备错误记录后可在真实调用前修接线。
- 本地 fakeCLI 只覆盖消费者解析、计数和失败分支，记录其替身身份，禁止把其结果算为真实 CLI 已接收。
- 正常交付共四 image blocks，原 PNG 载荷 13,398 字节。多发、失败及部分交付按实际累计。已有图片生成成本继续留在原账本。
- 读取/编码、文本/PNG/base64/线上 JSON、工具数量、CLI 原始 usage 和完整运行/回读时间分别保存。未知内部轮数、价格、图片 token 记未测。
- 本批结果只判传图链与消费层，不据这两次推出插件优于原生的任务收益。

最终静态结论待实现作者停更后绑定具体源码与公开材料。本批真实运行后仅回读本批原件作最终判定。
