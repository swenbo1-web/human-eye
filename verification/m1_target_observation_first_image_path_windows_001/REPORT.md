# M1 目标观察首包原图路径 Windows 复验

**工程验收通过。** 正常目标观察首包与上轮正常线包逐字节一致。上一轮的 `SLOTS` 反例现在省略路径列，两张原 PNG 和整件量测继续交付，回包与同输入的无路径基线逐字节一致。

固定方案 `45e458b285193f8c7b99919fd04338455c98398e`。产品候选 `95fd44bb8c4b6b992d8849f38ffbe5d778b0ac5a` 自 `a9183d02eca6153995828dbc47d39ce00a346946` 直接派生。唯一变更是目标观察在现有一次 `resolve(strict=True)` 后严格比较原生路径字符串。共享校验的 `source_region` 继续使用原来的 Path 比较。143 件 Git、wheel 与隔离安装逐件一致，实际工具目录 5 项一致。运行源 `eaccba2ec88abc035c62841a765f99ecae5f50e34dd8e7867b09dc17cb6d9dc9`，wheel `e0f603f2279df4d9e08c844ad3b191449b69799c54737f2b0c178f6ef22f4fbe`。

同一个封存 P1 第 2 调生产记录与实际请求经过隔离安装的真实 MCP 派发。正常回包只有 LEFT 的见证图带本机路径，SCENE 留空。此前闭槽后的实际文件读回 2,526 B LEFT 原图，SHA-256 `4a69c9a0c955be1527564d9df02db9fbfcdbad95bfd836deb7fd6afd04c75157`。两张原图依旧按 SCENE 2,580 B、LEFT 2,526 B 交付，M09→M03 的整件距离 234.375 mm、世界 +Z，点对及来源绑定一致。

| 线包 | 正文 | CRLF 回放线包 | SHA-256 |
| --- | ---: | ---: | --- |
| 此次正常目标观察 | 8,726 B | 16,456 B | `1b633b584220d6440813934903b487b8dbbdf35cf1bf00909c0d4845e6746acf` |
| 此次旧别名输入 | 8,478 B | 16,204 B | `d3ffd9e4c290d180a1c139c3e5f180c7b396f94b6a0b9cf568c9127751de8215` |
| 上轮实际别名失败 | 8,726 B | 16,456 B | `65d3f6509a0409410a97463990b7f2539abe5fa5595d2cba1b74e7bf91778d13` |

原正常回包与上轮同 SHA，去掉原失败回包中唯一新增的路径列后，与本轮别名回包相同。别名回包仍是正常 MCP 结果。目标反例 12/12、兼容 6/6、固定工具头及结果与历史双阶段 6/6。无图、无完整见证、全场、full、`region_task` 与 P3 `source_region` 均经原合同核对。上轮 11/12、准入 0/1 属于上轮候选，原失败线包和装配 N1 5/5、P1 4/5 保留。

60 次交错热文件系统配对中，路径投影中位 0.346 ms、p95 0.366 ms，启用路径的完整候选序列化配对中位增加 0.351 ms。原 P1 第 3 调实际重交 433 B 正文及 2,526 B 原图，MCP RTT 16.623 ms，派发至 CLI 17.036 ms，前一回包到此调相隔 7.747 s。这些数值分别来自本轮离线复演和历史现场槽。

实际构建和隔离安装各 1。新增 Blender、构图、模型、替补、资产重建、Google、额外 API 和付费调用均 0。模型自然在最终答复附图、调用减少和用户打开保持未测。验收范围为固定只读首包工程接线。

- [逐项回放](checks/REPLAY.json) · [字节对照](checks/BYTE_CONTROLS.json) · [路径实测](checks/PATH_COST.json) · [隔离安装](install/PRODUCT_RUN_BINDING.json)
- [本轮正常线包](checks/CANDIDATE_DISPATCH_RX.bin) · [本轮别名线包](checks/CANDIDATE_ALIAS_DISPATCH_RX.bin) · [上轮失败线包](../m1_target_observation_first_image_path_001/checks/CASE_ALIAS_DISPATCH_RX.bin)
