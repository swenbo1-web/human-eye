# 工具结果绑定候选

`consumer.py` 派生原 `archive_turn`，每次结果绑定都调用公共 `result_contract.bind_tool_result`。请求工具名、完整参数、JSON-RPC 请求与响应 ID、attempt 原始顺序及条目数量一并核对。分类保存在新的 `BUSINESS_SOURCE_BINDING.json` 和 `ARCHIVE.json`。

`driver.py` 派生原 `common_image_faults`，所有业务工具结果复用同一 matcher。图片构造、响应序列化、实际发送、渲染账本和来源故障继续采用原检查。普通业务错误得到 `tool_error` 分类。

实际消费入口复用原函数 code、defaults 和 closure，并创建独立 globals 浅副本。固定三处接线分别连接新 archive、新 consumer/共同核查以及新 route。`CONNECTIONS.json` 列出根冻结后应核验的实际指针。完成门、顶层流错误门、原始 stdout 和持有进程句柄路径沿用原函数。

## 离线调用

准备好原 owner 文件快照及真实 CLI completed 工具事件后，由统一验收器调用以下入口。输出目录使用本批新目录。

```python
archive = candidate_consumer.archive_turn(
    new_output_directory,
    {"audit_dir": str(owner_snapshot_directory)},
    first_owner_attempt,
    actual_completed_tool_events,
)
faults = candidate_driver.common_image_faults(
    {"tool_calls": actual_completed_tool_events},
    owner_snapshot_directory,
)
```

JSON-RPC request/response ID 属于同一层。CLI item ID 按原事件保存。候选重放保留原业务错误正文、六槽答案和实际费用记录，N3 原顶层流错误继续进入严格失败门。

本批新增 Pro、provider、CLI、actor 服务、Blender 和光栅均为零。旧正式验收仍为 4 通过、2 失败，完整三配对收益条件保持未满足。
