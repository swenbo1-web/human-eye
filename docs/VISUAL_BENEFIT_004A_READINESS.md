# VISUAL-BENEFIT-004A 准备验收

本批已完成六题资产、P/N 协议、通用原生通道、实际产品观察适配器和无模型集成核验。**正式消费者为 0，尚无模型任务收益结论。** 基础设施可交回复核；产品并非六题全部支持。004B 只在本批独立复核后按同一冻结题集运行，不因拒绝、超时或负收益换题。

## 固定范围

- 产品基线：`50f20d56f95e5672b213e1247ea00fae9c3a1ee0`。
- 129 个运行源码文件的 SHA-256：`6a5375fb5d5577e8de05c043db7523263cf96ad8386ee524a04beb25feb9f382`，本批未改产品、安装、默认配置或阈值。
- 六题规格 SHA-256：`f109ea3d64dc7b87d5010317c086008ff3d29129861bb9f049b1ba7a6c67f4e8`。含两题遮挡、两题小特征、一题全景足够、一题外图无法看到内部。独立解析真值和规格先封存，随后只构建一次，支持检查后未重造。
- P 使用实际现有观察工具组合，允许同等通用原生回退；N 使用模型自己编写的普通 bpy/Python，可调整视角、本地计算和保留状态，不接入 Human Eye 或预制任务求解器。
- 双方同一资产字节、公共问题、对象目录和新鲜初始图；不向模型提供正确对象对、core、最佳视角、私有真值或本批支持检查结果。

## 实际支持结果

所有六题的 P/N 新鲜公共初始图像素和对象目录一致，12 个支持检查进程均正常关闭，原始文件及初始 PNG 保持不变。支持批完整外部耗时约 22.44 秒；这是准备成本，不是模型完成任务耗时。

| 场景 | 实际产品配对路径 | 保留的限制 |
| --- | --- | --- |
| V01 | 三个 native 方向均仅全景；projection 成功 | 全景足够的判定按整对象特征宽度，不能当成关键间隙已可读 |
| V02 | 三个 native 方向均仅全景；projection 成功 | 未证明投影重叠问题已被模型正确理解 |
| V03 | 三个 native 方向与 projection 均拒绝 | `geometry_resource_limit`；保留题目，原生回退仍可用 |
| V04 | SCENE 遮挡守卫保留全景；XY 输出全景及局部两图；XZ 仅全景 | XY 的 `projected_detail_gain` 是投影机会，不是实际任务 ROI 或模型质量收益 |
| V05 | 三个 native 方向均仅全景；projection 成功 | 不因全景已够而强制额外观察 |
| V06 | 三个 native 方向与 projection 均拒绝 | `reference_pair_geometry_unknown`；外部不透明图片不能证明内部表面，完整几何仍可读 |

无配对的 auto 在六题均生成现有 analytical projection。配对检查使用操作员真值只是探测 API 支持范围，**不计为模型自主识别**。该批没有把六题图片发给任何模型。现有 native 与 analytical Q4 attention 是不同路径；native 成功时 analytical attention 的 `image_not_requested` 不表示 native 没有图。投影分支本次均未应用新的注意力转移。

## 真实图片和生命周期核验

独立 calibration 场景完成了普通 bpy 读、语法错误后在原期限内恢复、渲染与同进程状态保留。P 通过真实 `LiveSpatialMCPServer`、`LiveSpatialService`、`BlenderMCPHost` 取图。最终 owner broker 让 P 多次调用复用相同 service/host/coordinator，N 保留自身 Python namespace；未刷新期限或重启 worker。

最终 r2 校准的 N 768² 图与 P 384² native 图实际进入宿主 `input_image`，事件 `call_b9a346314631430b9d8224cb1a7b612b`，块序号分别 1、2。PNG 字节、当前运行、事件、块和原始 600 秒窗口均有绑定；不是路径、API 回执或 helper 自报看到图片。证明位于本地 `verification/fixes/20261104_visual_benefit004a/qualification/BROKER_R2_HOST_IMAGE_BLOCK_PROOF_FINAL.json`。

P 的 calibration native 图未保留材质颜色，而普通原生图保留颜色；此为实际限制，未改产品或将资产 object.color 改造为产品更有利的输入。双方公共初始图仍相同。六题后续需靠真实消费判断该限制影响。

首轮 broker CLI 的 `UnboundLocalError`、原失败及清理记录保留；修复后增加真实 TCP/隔离 CLI 回归，r2 通过。早期在 120 秒窗口外查看存档 PNG 只算静态传输核验，不算期限内观察；最终 r2 才补齐期限内宿主图片证明。初版按图片哈希匹配时曾匹配到旧运行同字节 PNG，最终凭当前事件及块序号排除旧运行，旧提取记录亦保留。

## 冻结的后续比较要求

每题原始 600 秒在 broker 入口、资产读取与复制前开始，含初始渲染、模型工作、调试、失败、回退和关闭。48 次公共请求、数据 262144 字节加控制 98304 字节；超过或截断不得当作已完整交付。每次图片显示均计预算：8 图、每边至多 1024、单图至多 1024²、累计至多 4×768² 像素，重复图及失败/未知交付不退预算。渲染构造和实际显示分账，不能将未审计的构造计成零。

共计划 12 个新鲜消费者，六对中 P/N 各先行三次。允许在原窗口内修复脚本，禁止重启消费者/worker、续期、修答案或额外筛选成功样本。评分绑定 case/run/asset/task，缺项、unknown、不支持、超时和拒绝保留固定分母；自由区域描述保留盲审。给定面/对象后的正确查询不等于模型已自主定位。实际宿主证据与模型自报使用图片分开；图片出现或答案正确都不能证明视觉机制因果贡献。

usage 只采用宿主可观察增量，图片专属 token、美元和进程峰值 RSS 未公开则记未知；不由 PNG、像素或局部算法时间推算完整收益。准备阶段没有正式模型调用或收益成绩，原 USD 0.02 预留未动。

复核补齐了公共证据引用映射：已收到的文本为 `text:<request_id>`，实际显示图片为 `image:<request_id>:<reservation_id>:<image_id>`。两组采用相同规则；公共符号不构成成功或已交付证明，controller 仍须核对原始宿主事件和合同。首次冻结快照保存在 `PRE_EVIDENCE_MAPPING_REVIEW`；原计划也保留不覆盖，最终复核候选位于 `final_protocol/FORMAL_PLAN.json`，用 `visual004_protocol.py --root <004a根目录> --output-dir <004a根目录>/final_protocol --verify` 验证。未改题目、阈值、产品或资产。

## 验证与清理

六个新增验证模块共 133 项测试，普通模式与 `-O` 均通过；最初 126 项记录、补证据映射后的 `ALL_TESTS_002_*` 及最终 `ALL_TESTS_003_*` 都保留。产品摘要仍为原 129 文件固定值。代码和 README 纳入本地验证提交，私有场景、真值和原始记录保持本地，不推送。

垃圾盘点只确认两个缓存目录中的 13 个未跟踪 `.pyc`，共 1517748 字节。针对这两处的校验后逐文件删除命令被自动策略以 `blocked by policy` 拒绝，未执行删除，未换通道绕过。`CLEANUP_RECEIPT.json` 保存候选文件、哈希和拒绝；归档、失败、发行环境、附件及资产全部保留。

本批后的架构验收按 [模块收益路线](MODULE_BENEFIT_ACCEPTANCE_ROUTE.md) 区分实际入口和合同。完成视觉批次后才选一条普通 Live 连续任务链，依据分账选择一个机制，不同时扩展产品域。
