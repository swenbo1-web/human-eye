# M5-HARNESS-RECOVERY-001

两个真实零模型恢复会话通过。参数拒绝之后，成功与 partial 回复、有效距离、unknown 及当前图片均经 Owner、普通 Python 薄绑定和真实 MCP 完整交付。两组公开请求与 service 归档分别关联，实际序列均为 `[1, null, 2, 3, 4]`。

本批验收对象为测试桥恢复能力。原 M5 模型消费批继续按受干扰结果封存，M5 模型任务收益保持待证。

## 固定版本与最小迁移

管理员计划 SHA256 为 `4e37508e0fa047c13b832bd2f9c6b03442d0493f062da1fbe00d3f83bb627ee2`。起点为 `baf8799d9e1cb411d39da58c28171b00ac76f12f`，实测前固定提交为 `046e1772959af7c3c297ac2678ac3845ae27abc5`，冻结 68 个直接输入。

复用候选源 SHA256 为 `371049158c7370a0e29e30992e5b1fe2cd6d6ba726688e77017ca44c27f94318`。迁移后的 runtime 为 `b658da7d89e833cd90dfa65aad95516fc9a98b5936174e940da074ec8ab77810`。关联核心 correlate_archive 和 public_request 的 AST 与候选一致。

迁移内容包括新 NAMESPACE、HERE、EXTERNAL、账本和归档根、会话标识及原始 600 秒时界。旧字段 consumer_deadline_ns 在当前零模型流程中沿用名称，其值为本次 600 秒绝对期限。额度按全批 2 次 owned、12 次 raster、0 消费者和 0 付费 API 执行，公开请求保持 30 秒预算。

| 产品 | 固定来源 | 原隔离安装 |
| --- | --- | --- |
| A | c309d7e4302518cd5f7d1c3966e7c7fa338ea128，141 源摘要 776b0f0914e116fece16d2b3875ee16ffebf4896a7e394861287ffaa6fe025be | D:/he_m4_target_002/B/product |
| B | ccb608aa83de4b0e6671da89e0c8f387bd3f800e，141 源摘要 7d2d4352f462c64a46e6fccf447c6f030c08b96e95517a3b2b6776ed50b69a6a | D:/he_m5_observe_measure_001/B/product |

固定资产 SHA256 为 `2d7c48f01665588bd7cfc93280ea50b559f4dc08196738c504ea56c88c75a164`。每组使用一个 fresh owned 场景副本，所有请求按顺序执行。

## 两组真实交付

| 内部公开请求 | service 索引 | 原 isError | 实际结果 |
| --- | --- | --- | --- |
| 初次观察 | 1 | false | 默认 brief 与当前 PNG |
| target/candidates 仅请求 surface_proximity | null | true | 原参数拒绝，INDEX 字节保持 |
| objects 请求 surface_proximity | 2 | false | observed，距离和见证有效 |
| objects 请求 surface_proximity、closed_solid_relation | 3 | false | partial，距离有效，closed_solid_relation 为 unknown |
| A 再观察、B 联合观察 | 4 | false | 当前图像正常注册，B 实际交付 task_result |

每组四次外层 execute_python 承载五次内部公开请求。第一外层同时执行观察及预期拒绝，外层 Python 成功返回，拒绝本身的原 JSON 和 isError=true 标记分别保留。后续两个合法回复实际到达调用层，正常产品回复提供服务可用证据。

partial 中的 surface_proximity 继续为 measured，closed_solid_relation 保持 unknown，原因为 closed_solid_too_few_faces。实际米制距离为 0.9959999998100102，最近点与 A→B 方向经当前完整源面核对。最后一次 B 联合结果绑定当前观察来源及 whole_objects 量测范围。

初次观察每组构造一个 raster。最后一次观察均复用当前帧，frame_reuses=1、新 raster=0。PNG、帧注册、实际源面、对象实例和来源链按本槽原件核验。后台 SERVICE_RESULT 按对应公开投影核对，外层原 JSON 另与原 RPC 返回逐条比较。

## 独立验收与范围

独立 QUALIFICATION.json 首次执行通过，会话 2/2、外层成功交付 8/8、原 public JSON 与错误标记 10/10，失败与未运行均为 0。374 个输入字节 pin 和预算物理原件复核一致，原预期和冻结源保持。

迁移检查 17 项、变化处纯控制 26 项、源比对 20 项及独立归档控制 16 项分别通过。覆盖连续拒绝、service 序号空缺、缺失或多条记录、前缀改变、跨调用窗、跨槽与内容 SHA 改变。旧 104、19、96 项验证按原证据引用，历史大清单保持直接封存引用。

本批实际为 2 次 owned、2 次 raster、0 消费者，待结算为 0。所有真实进程、读线程、管道、持有句柄及源文件关闭情况以 RUNTIME_REVIEW.json 为准。源文件和场景副本保持只读使用。

运行原件审计 1148 项通过，失败项为 0，包含 545 个输入 pin。两个会话的 actor、产品 MCP 和 Blender 均由实际进程及持有句柄确认退出 0，reader、管道及句柄关闭通过。源文件保存检查与初末几何指纹一致性通过。旧通用 worker close 的 unknown 状态独立保留，实际进程关闭证据另行核对。

根另外核对 51 项原始交付、时界和额度，逐条将普通 Python 标记中的原 JSON 与原 RPC 公开 JSON 比较，确认拒绝及后续回复均原样到达。DECISION.json 的 accepted_harness_recovery 为 true，管理员独立复审待完成。

## 实际开销

完整 A 会话为 4606.0515 毫秒，B 为 4094.1011 毫秒。窗口从根检查与启动前开始，涵盖真实工具、回复和图片交付、所有进程关闭及结果发布。两项仅记录当前恢复序列的实际投入。

消费者模型任务与付费 API 均为 0，协调和审查代理费用未测。注册前的计划阅读与初始委派未计量，注册至封存的可观测投入由最终账本另列。Agent Learning 当前聊天仍待 host binding，登记 pending，未借用其他句柄。Google/API/key 保持暂停。

根对话曾在实测前中断，恢复时实际启动与 raster 仍为 0。注册至本地判定的墙钟间隔为 10704.785 秒，包含中断及后续继续的等待，活跃工作与空闲时间未单独划分。两个真实会话的完整开销按各自原时界单列。

本次范围为两个固定安装、同一固定资产和单一同步 Owner 调用序列。并行请求、其他资产和真实模型任务的覆盖仍待对应验收。

候选与迁移 runtime 作者承担运行审计，另一代理复核迁移源和变化控制，独立验收代理编写预期及读取本次实际回复。根负责冻结、真实执行与原始交付判定。作者关联保留在各报告中。

## 唯一下一建议

复审通过后，沿主线选择一个具有独立答案的全场发现能力缺口推进，并以当前对象及源面引用衔接 M6。原 M5 模型消费批继续保持封存。
