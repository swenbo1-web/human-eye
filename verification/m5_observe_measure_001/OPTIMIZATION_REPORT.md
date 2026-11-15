# M5 唯一优化复核

本轮沿初版资格的实际计数，只复用本次 M4 已计算的几何 ID。生产改动限于 active_observation_host.py 和 live_service.py。初版源码快照、安装和资格原件保留。

原资格 task_source_prepare 为 7.1598 毫秒，包含两次额外 geometry 解析与两次必需的原面顺序摘要。候选从同次 M4 MeshEntity 取得不可变 ID 元组，随现有 ReadContext 结果保存和命中。最终选择摘要在真实别名补全后计算一次。父 scope、真实 ID、instance、对象序号、完整源面顺序及缺口补读校验保持。

定向纯检查 52 项通过。旧 task 35 项、service 5 项与 brief 6 项通过。V1 与 V2 的合成 binding、facts 和 task_result 结构完全相同。独立折面原件经过真实派生 helper 和 M3，两个非共面源面完整保留，等距换面序及改坐标均使旧源引用失效。

旧 service 模拟函数缺少新增私有 callback 参数，原运行的两项错误保留在 LEGACY_SERVICE_V2_INITIAL.json。新命名空间副本仅补模拟函数参数与 callback 数据，验收断言原样保留。该差异属于测试接线适配。

候选纯执行的额外 alias 解析为 0，已有 alias 复用为 2，顺序摘要为 2，规范化为 1，M3 surface pair 为 1，定量新增 raster 为 0。冷暖、普通观察后附项、附项后普通观察、无图、代际变化、绑定冲突和私有数据泄漏检查均通过。

实际初版两对象数组包含 296 顶点、515 面和 808 边。顶点与面为 13,284 字节，加边数组 6,464 字节后为 19,748 字节。两个记录的差异来自统计口径，实际复制次数仍未知。

候选时界须将 task_source_prepare 和 task_source_finalize 相加，再与初版 source prepare 比较。当前仅证明重复操作被删除，实际收益等待根对冻结安装进行一次资格验证。默认观察增加既有结果缓存中的小型 ID 元组，尚未测量实际分配与复制成本。

生产源码保留原换行格式。live_service.py 原为 CRLF，使用 cr-at-eol 规则检查通过，默认 diff 检查会将新增行的 CR 记为尾空白。

本报告作者同时实现了 M5 接线、这次优化及产品纯检查。实际质量与资源核验由根及其他代理独立完成。此代理新增 Blender、MCP 进程、场景 raster、模型和安装均为 0。
