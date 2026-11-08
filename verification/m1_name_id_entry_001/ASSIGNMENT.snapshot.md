# M1-NAME-ID-ENTRY-001：只修首调用可发现性

固定基线c77111f7076b4a1720a98e8c0f8f8af43feb1c34，产品17db41c/131/01c296b5。003独立质量已冻结双方4/4，根成本复算P四题446.1977786秒、N391.4187119秒；完整账本仍由W-ACQUISITION同批核对。七次HE错误已逐TX/RX确认全部发生在名称到ID阶段，schema与校验一致。四组均先选插件，不能归因模型拒用。见review_run003/USABILITY_REVIEW.md。

W-ENTRY在本人codex/nearest-integration分支做一个描述候选：将现有human_eye_scene_observe description首部的含糊说明替换成合法且可照抄的名称→ID→surface_nearest短例。先用占位名称：

```json
{"session_id":"read-1","include_image":false,"query":{"mode":"task","objects":[{"name":"<object-name>"}],"requested_facts":["aabb"]}}
```

明确该返回的binding.objects[0].object_id可供下一次surface_nearest的focal_id使用，并紧接最短合法nearest示例。identity/object_identity不是合法fact。只使用通用占位符，不能放本次对象名、答案或资产结构。以替换压缩原说明为主，最终description UTF-8字节不得超过当前1471B，不追加长教程、信任口号或让模型忽略核验的指令。

仅修改live_spatial_mcp.py中的这段说明及运行身份所需的既有摘要更新；保留其它事实语义的必要说明。inputSchema、selector/FACTS集合、工具名、错误语义、支持域、源绑定、获取次数、几何结果和执行权限完全不改。不新增identity别名、新工具、学习层、格式压缩器或求解路径；不做原生补查去除实验。本候选只针对七次入口错误，不承诺完整收益已达标。

验证复用已有相关离线检查，不新增测试框架或为文案镜像写新测试。核两个示例符合当前已有校验，返回ID路径用003真实aabb包作只读依据；核descriptor/schema除description之外逐字段不变及字节变化。使用项目既有来源生成/核验方式，无新Blender/CLI消费者/MCP服务/RPC/付费，原源码和旧001/002/003证据保持。若来源身份需同步既有文件，列明必要差异，不顺手整理其它模块。

直接实施、必要验证、本人分支提交，一次M1_NAME_ID_ENTRY_001_COMPLETE回报根，附候选提交/源码摘要、最小diff、旧新description字节、实际检查及未运行项。结束等待根深审；没有本批新增模型实测授权，不用已完成003工具预授权自行再开试验。每条后续改动必须以实际新失败为依据，不连续写多个文案候选刷题。
