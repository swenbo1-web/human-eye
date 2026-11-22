# M1 区域任务首包投影独立复核

2026-11-22。接受隔离工程候选 `24b8855746dfe9eeee7fa7d374bec2da86c21a2e`，直接承接 `8cf3fabc`。两处产品改动在生产启动和公开 MCP 派发。显式启用 `--region-task-evidence` 且请求及成功结果均为区域巡检时，用原简报编码。服务仍收到原业务参数。标准入口保留原完整诊断。 [产品差分](https://github.com/swenbo1-web/human-eye/commit/24b8855746dfe9eeee7fa7d374bec2da86c21a2e)

从 Git ZIP 独立核对 668 项的长度、SHA-256、唯一性和 CRC。ZIP 6,517,926 B，SHA-256 `c7049a3fd169ca8633c85a63ab26e0110d8c99dde5b0f478ecb3bd7ba5544374`。唯一候选 wheel 摘要 `2cd2bc3607fd5b8744d760f88ad23008f3faae153efa4ccd49dfa22538547572`，143 件运行源 `704742071fd1d2722b952e6fa0d4f9a497b8a33ed567ce8f510657d8c1b379fe`。冻结 466 项，SHA-256 `cf3de3e3d896330a50687ef5e970bcc1f01c5187bd316b69f1588f3f64a88620`。 [证据提交与索引](https://github.com/swenbo1-web/human-eye/tree/020159ca02607c059a3acf797ed2a3394930f290/verification/m1_region_task_first_packet_projection_001)

| 封存请求 | 标准正文 → 隔离正文 | 标准 stdio → 隔离 stdio | 同序原图 |
| --- | ---: | ---: | --- |
| P2 | 335,181 → 7,521 B | 362,123 → 19,881 B | 3,586／3,156／1,929 B |
| P3 | 335,179 → 7,521 B | 362,121 → 19,881 B | 3,586／3,156／1,929 B |

P2/P3 标准实际 RX 与基线回放逐字节相同，content 与旧正式原件精确相同。隔离三种详情输入均返回同版标准简报。原图逐张解码对照，三候选、两份完整见证、有原因的未知、六条具名挡片、同名 SCENE 的独立 scope/frame 保留。固定 CLI 三头两阶段 12/12。P3 的图引用与历史真实公共取图及闭槽文件对应。新回放直接解析并读取本次 stdio 原图块；新鲜公共 `read_images` 调用须在下一批实做。 [冻结资格结果](https://github.com/swenbo1-web/human-eye/blob/020159ca02607c059a3acf797ed2a3394930f290/verification/m1_region_task_first_packet_projection_001/evidence/RESULT.json)

实际隔离安装走生产 `main`、生产服务构造和真实 stdio，仅将宿主数据换成封存生产结果。正式 9/9 获得同进程 EOF、状态 0 和三管、线程及句柄回收。69 次请求，54 成功、15 个预期拒绝含发布期限；63 次服务调用、60 次实际取用、三次过期在取用前拒绝。联合量测、普通目标或独立选区的完整接口、无图及失败恢复沿原合同。P2/P3 单次本地 JSON-RPC 序列化 11.416→0.669、11.600→0.679 ms，整题模型收益未测。 [正式报告与分段](https://github.com/swenbo1-web/human-eye/blob/020159ca02607c059a3acf797ed2a3394930f290/verification/m1_region_task_first_packet_projection_001/REPORT.md)

隔离目录仅增加 212 B 的区域巡检特例说明。旧泛称的完整诊断句仍在，范围由追加特例界定。后续原样保留这份实装目录，按实际消费评估是否需要澄清。此次复核零新模型、Blender、构图或默认切换。旧客户端恢复 0/1 原样保留。下一批仅做[同版单对真实消费者](M1_REGION_TASK_FIRST_PACKET_CONSUMPTION_HOLDOUT_001_PLAN.md)，比较候选标准与隔离端点。
