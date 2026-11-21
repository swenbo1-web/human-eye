# M1 指定源面原图引用独立复核

2026-11-21。候选 `470a36f111cd5e96845569c258f464d4bbcf2824` 由 `30c9cfc1` 直接派生，只改 `live_spatial_mcp.py`。接受隔离工具序列化及当前同机文件读取，后续只补一次自然最终回复诊断。[工程原报告](https://github.com/swenbo1-web/human-eye/blob/8d12736d95a82d0598cc1a3f2373b572e9aa57e1/verification/m1_source_region_final_image_001/REPORT.md)

- 143 件运行源在 Git、wheel 和隔离安装逐项同字节。候选沿原路径读取和校验原 PNG，实际图片块构造成功后才考虑附加路径。需要完整见证、一个实际图块、唯一匹配的构图记录、同一选区帧指纹和当前服务的绝对源区目录。只新增 `images[0].local_image_path`。独立复放两隔离安装，full、无图、全场、部分结果四路相等，12 个失配和路径控制通过。
- 真实 P2 冷生产记录与热简报的候选回放均从 **9,748 B 增至 9,920 B**。同一 **2,870 B** RIGHT PNG、帧及量测证据不变。固定 CLI 三种头长及两阶段完整保留正文、路径和原图。两次文件重读为 0.130／0.143 ms，追加正文为 172 B。
- P2 结束后保存的原图文件已实际读取，`view_image` 返回同一字节并有一次预制展示。Codex 文件面板记录仅为 `queued`，确认打开与用户点击均为 0，自然模型最终附图实测为 0。历史 N1 的 `native-image:` 可从封存注册表解析，直接给本机文件工具未打开。当前原图与封存线包匹配，原 P2 文本和封存 4/5 保持。

当前证明了同机工具结果提供了一条可读取的原图路径。是否有正常模型把它用进最终答复要另测。自然答复给出的有效引用、宿主实际读取或展示、真人点击分别留证。此结论限本机已核文件与场景，跨宿主无同级证据。[原宿主回执](https://github.com/swenbo1-web/human-eye/blob/8d12736d95a82d0598cc1a3f2373b572e9aa57e1/verification/m1_source_region_final_image_001/checks/HOST_OPEN.json)
