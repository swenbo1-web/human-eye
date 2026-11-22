# M1 区域任务原图路径消费独立复核

2026-11-22。现场 QA/QB 2/2，正式 A1/B1 2/2，各 7/7，最终两图闭槽各 2/2。两边都真实启用证据端点，自然显式 `full` 返回区域简报。首包 7,397／7,955 B，三张 PNG 同序同字节共 10,337 B。A 首包无地址，第二调 `read_images` 新给两条最终地址并重传 5,682 B；B 两条原答链接均来自首包，未重交原图。路径直接采用和省一次专门读图成立。 [原答与正式报告](https://github.com/swenbo1-web/human-eye/tree/8e31dfdaa318571252ac5697fc2d76198e8c3d0b/verification/m1_region_task_witness_image_path_consumption_001)

从 Git ZIP 核对 956 个唯一成员的长度、SHA-256 和 CRC。ZIP 7,494,082 B，SHA-256 `398837f68607033a1023bdf5fd381f626388a5e1c1c045409bce778442ec47aa`；冻结 644 项、摘要 `2603bef2b95266730b0329552b072895771fd476e812f0ab189df1904493b490`。固定同资产 `f5469ae8`、A `24b88557`、B `1535d08a`，四槽均正常关闭。预检以构造／实际交付分开评分，两路线和错帧坏路径已核。 [原件索引](https://github.com/swenbo1-web/human-eye/blob/8e31dfdaa318571252ac5697fc2d76198e8c3d0b/verification/m1_region_task_witness_image_path_consumption_001/RAW_INDEX.json)

B 两次实际普通 Python 调用同时想复验 PNG 和计算几何数值，两次均被其既有边界拒绝，零输出、零新图或事实。双方各一次真正 Blender 几何复核。A/B 业务 3／4，实际构图 3／3。CLI 输入加输出 44,315／56,771（+28.11%），输入扣 CLI cached 后加输出为 26,395／26,435（+40）。完整槽 63.515／80.263 s（+16.748 s），工具间区段 16.432／39.076 s。A 补取图实测派发至 CLI 35.230 ms，B 两个错误回复 18.490／44.042 ms。阶段账本支持主要可见时差在工具之间，单对无法隔离路径字段、模型选工具和时钟波动的因果份额。计费、内部时钟与真人点击未测。 [完整分段](https://github.com/swenbo1-web/human-eye/blob/8e31dfdaa318571252ac5697fc2d76198e8c3d0b/verification/m1_region_task_witness_image_path_consumption_001/evidence/COSTS.json)

区域路径消费按单对收口，保留隔离能力和真实整题结果。下一项针对另一条已证实大包，[无图选区量测首包](M1_SOURCE_REGION_NO_IMAGE_MEASUREMENT_PACKET_001_PLAN.md)。不动图路径、诊断接口与正式默认。
