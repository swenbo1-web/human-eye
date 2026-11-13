# FIX2 实际三轮与关闭后验收复核

2026-11-13。只读原件复核通过，1304项检查、648份输入。新增live、Blender、模型、API和Git操作均为零。

固定准备1511af696b564a0b261b70d5f0562325daa1f2a7。实际仅一个全新C、三次业务，N新增零次。执行3成功/0失败/0未运行，资格3通过/0失败/0未核验。

| 轮次 | 实际匹配 | 新kernel | 捕获序号 | thin实际PID |
| --- | --- | --- | --- | --- |
| BASE | 71 | 112 | 2 | 2964 |
| REPEAT | 71 | 0 | 3 | 20616 |
| EDIT | 72 | 10 | 7 | 19072 |

三个独立thin进程都经原stdio_attach和完整initialize/通知/list/业务链，正常EOF退出且backend_close_requested=false。owner、Blender、产品runtime、session和endpoint跨三轮保持，原始TX/RX与owner请求返回逐项一致。

原业务started_ns/ended_ns固定，宿主事件按started_ns+elapsed_ns完整落入各自窗口。三轮先完成收集，唯一登记EDIT位于REPEAT之后，原actor前态及精确姿态回读通过。BASE/REPEAT用INITIAL，EDIT用登记回读；初末几何仅含Obj_008登记Z变化，原资产文件保持。

唯一finish、产品runtime退出、Blender回收和worker终态确认后，才进行三次事实验收与sequence。九帧WIRE含唯一qa_advance和末尾唯一close，尺寸、sendall及JSON完整。较早轮次资源只引用当时及之前的捕获，BASE/REPEAT绑定相同、EDIT失效。

完整episode为5.0941225秒，含后台启动、三轮收集、登记编辑/回读、关闭、后验核验及RESULTS写关，均在原590秒内。各实际工具均在30秒内，计时发布单列。后验阶段约94.0775毫秒。

59份冻结准备及369份外部输入保持原字节，覆盖固定actor、consumer、资格、worker和产品证据。原001及FIX1两个C失败和各两轮未运行继续保留。此前原N三轮仅作为固定工程证据复用。

这份复核核对真实来源、请求回执、资源/资格报告对应、时序、分母和关闭，没有重新求解全部几何真值，也没有执行模型消费。实际模型续接、记忆保持、usage范围、费用和连续任务收益仍待正式阶段。rich来源缺失字段及通用close事件unknown与独立关闭确认分别保留。

RESULTS.json保留逐项标签、输入摘要、三个原窗口、后验窗口及原始成本。verify_lifecycle.py只读原件并仅在此postrun/lifecycle目录写派生输出。
