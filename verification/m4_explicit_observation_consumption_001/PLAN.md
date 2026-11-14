# M4-EXPLICIT-OBSERVATION-CONSUMPTION-001

唯一目标：在当前隔离工具链上，用一个真实Pro消费者确认产品观察入口能否被调用，以及返回事实能否用于完成同一巡检和定位任务。它是调用与消费资格，不是第二轮收益A/B，也不证明自发采用率或自动Hook路由。

基线交付 `21b2871df70c5fedde4a916c67983ee40c626f89`，产品仍固定 `7d42bb939c7881a98fe322c10c216398f6c7aecc`、141源 `96d7da8c50680a73f251496406c9f0bbbf6b38bd4dfe848c931e45f094343b76`。新内容只放现有实施分支的 `verification/m4_explicit_observation_consumption_001/`，旧六槽及其0/3采用、全部费用/失败记录不改。

## 已知问题与单变量

旧正式三P都没有调用active_observation，真实模型没有消费当前v3结果。tools/list、局部approve配置和fake P已通过，仍不能替代一次真实模型调用。旧实验明确关闭Hook，因此不能称自动Hook故障。共同题面与通用工具说明详细介绍原生算法，ACTIVE主要描述内部入口与brief格式，这可能影响选择，但没有因果证据。

本批不修改工具描述、工具顺序、产品源码、输出格式、相机、几何、评分阈值或Hook。只给原公共题面加一段明确的首步指令，区分“可调用并能消费”与“此前没有自行选择”。保留全部P公共原生工具和相同审批配置，不通过隐藏原生工具来制造成功。

原题面SHA `3f848a42070580ad479e3de6507b9ffe09c59b9651c784c17608f0d752c1205a` 逐字节保留为后缀，前缀固定为：

> For this diagnostic, first call the available active_observation tool with include_images=true. Use its returned current-session facts and images to complete the inspection below. Use the other tools only when additional evidence is needed. If that tool is unavailable or fails, report the actual failure; completing the task through native tools alone does not establish this diagnostic's observation-entry qualification.

不提供ROI答案、正确数量、正确位置或旧会话解法。旧题面的全部可达面巡检与三位置问题不变；域外剩余不能硬归入支持矩形。允许用原生工具补证据，真实补查与重算全部计成本。

## 复用执行链

沿用消费001的实际产品安装、bridge/native_tools、图像helper、consumer/result_contract、stdio、句柄回收和输出归档。设置与旧P相同：同一CLI实际二进制、请求模型/推理/档位及Pro登录，Hook/rules/skills/memories保持原实验配置。Google/API/key继续暂停，不改全局配置、正式MCP或用户资产，也不管理专家线。

只增加必要的新批入口和路径配置。新绝对runtime、独立会话/输出/图片构造账本；沿旧入口参数传入新prompt与新输出位置，不能误调用旧六槽run_batch、旧main或复用旧输出目录。新执行源及实际指针链、141产品与依赖、原题面后缀、新前缀、评分规则在执行前固定提交和摘要。旧脚本/数据从原只读位置复用，不复制一个未经核对的旧函数闭包来冒称新入口。

准备以只读源码、参数和路径核对为主，不再运行已通过的N/P fake、重渲染资格或旧协议矩阵。本次新的路径适配若需要无模型接线验证，仅允许一次无图的无害普通Python读取（如42）；它不算真实模型或产品观察资格。任何本地准备错误保留，修正后固定来源再开始唯一正式槽，不在启动后换源码。

## 一个真实槽

只执行一个fresh P Pro消费者、一个用户轮次，450秒原绝对期限、12工具尝试、最多6次真实raster尝试（含失败和再次构造），正常产品观察预计3张。真实消费者会话1个、用户轮次1个；provider实际请求次数不可观测则未测，不把会话数写成模型请求数。不自动另开会话补测；不存在N对照或配对收益分母。准备新raster为0，全部实际图像构造/编码成功即记消耗，交付失败不能退还。

原生读取、批量图片及自己的会话变量继续可用。模型内部普通错误按原合同允许在同一窗口恢复，记录首次调用及全部恢复，不能把后续成功写成首轮成功。若入口始终未被调用、真实拒绝、无可用工具、图片/文本缺失、期限或额度触发，则保留该诊断结果并结束，不外层重试或放宽配置。

## 必须分别验收的三层

1. **真实调用。** CLI模型事件出现active_observation调用；服务端实际收到；当前安装产品生产者执行，记录source/prepare/coverage/raster与返回结果。只有fake或工具列表不算。
2. **真实交付。** 实际stdio返回、CLI工具事件及图片块与生产者同源结果一致。记录完整v3字段、图片数量/引用和所有可观测截断迹象。CLI收到不能冒称已查看provider内部输入；provider内部定义/截断不可见就保留未测。
3. **正确消费。** 模型最终或明确引用的本槽证据满足原完整巡检及三位置任务。逐项记录答案依据来自产品事实还是原生补查；不能只凭答案正确就认定用了产品。首次获得足够产品事实后是否仍整体重算，也从实际调用和可见输出分析，不猜测模型心理。保留当前视角遮挡、其它视角已覆盖、背向有限池未知及域外剩余。

使用原冻结评分规则和独立几何/像素参考。新输出布局如需归一化，转换器只映射实际当前内容，保留逐项原文/文件出处，不能补答、伪造产品ROI或吞掉未知。先做质量检查，再展开完整成本。

## 交付与下一出口

保留原始CLI stdout、MCP请求/结果/图片、产品执行及捕获重放次数、全部工具与raster意图、源码身份、真实进程终态及完整生命周期时钟。实际input/output/cached usage分别保留，工具外等待不统称纯推理，provider内部次数/现金费用/图像token不可得则未测。正常退出和旧thin exit1/EOFunknown合同分别呈现。

本槽时间与旧六槽可以列原值供定位，不能计算或宣称新的原生/插件收益；显式首步指令也不能记为自发采用成功。即使很快通过，本批也不自动扩大到六槽、不改Hook、不顺手改metadata。

结果将决定唯一下一项：调用失败则修具体调用链；调用成功而事实不足则修具体交付缺口；调用与消费都通过，下一项才转向可选入口呈现与选择设计。显式成功不确定旧0/3的原因，不代表自动路由故障已被证明。不能跳过这一判别直接推断几何引擎无价值或全局自动路由已损坏。

无论通过或失败，提交本实施分支，向根 `local/01a1971f-eef5-7a23-a1b1-2352beb80a77` 回报 **M4-EXPLICIT-OBSERVATION-CONSUMPTION-001_READY**，附准备/最终Git、三层通过/失败/未测、模型实际工具序列、产品事实引用、全部成本与失败，然后结束等独立复核。本批已有M4连续推进授权，无需重复询问。
