# A 资源基线复核

本次只读取已关闭的 A 资格，样本数 1。复核作者也参与编写本批 harness 和被动归档层。

- 第二次 task 的 to_mesh、三角化、资源构建、资源顶点/面读取和世界变换增量均为 0。资源转发 0，新增资源数组 0。同一 resident 资源及修订号保留。
- 第二次仍有真实 capture_task，TCP 请求 1505 字节、响应 2634 字节，host.capture 54.948 毫秒。capture_cache_hits 为 0，选中场景包重新组装。
- Active 的 ReadContext 未保留 normalized tuple。Task 此时新增 2 个 mesh、296 点、515 面的 normalized tuple，数组元数据合计 13284 字节。复制和分配次数未测量。
- Task facts 为 100.0657 毫秒，scene.validate 为 2.5829 毫秒，其内嵌 hash 为 0.5853 毫秒。各级跨度有嵌套关系。
- 连续业务为 974.2059 毫秒，完整会话含结果 fsync 为 3401.953 毫秒。两个完整 client.call 为 784.5417 和 189.6567 毫秒，server 回写时界为 782.8491 和 172.6425 毫秒。
- 两响应原始 stdio 分别为 12451、1671 字节。LF 编码文本分别为 12450、1670 字节，差值来自实际 Windows CRLF。
- MCP 持有句柄 exit0 且已关闭，Blender owned Popen exit0 且已 wait/reap，全场初末指纹一致。Worker close 的通用事件仍为 unknown，独立保存，关闭回包和 Popen 证据已核。

优化依据是复用当前 observation 来源，省去第二次 host RPC 和所选场景重复绑定。独立 surface-proximity 求解仍须执行一次。后续 B 和正式样本决定完整收益。

所有原件和安装源的字节数、SHA256 见 JSON input_pins。只读脚本未启动产品、Blender 或 raster。
