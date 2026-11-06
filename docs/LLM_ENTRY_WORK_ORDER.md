# 大模型接入实施：极简常驻路径

2026-11-06，本端`codex/aggressive-v1`。用户已授权自动分模块推进，实施自测完整交付后主动唤醒主干。此为新接入模块，不重开已验收六模块，不与另一竞争端合并。

## 已完成和当前阶段

引擎采用c2dcf1d已验收的17个生产源字节（BC为76b25），参考[整体验收](ENGINE_V1_ACCEPTANCE.md)。根侧已完成旧报告/旧传输/新契约三路审查，选定[极简接入架构](LLM_ENTRY_ARCHITECTURE.md)。没有新入口收益、模型可用性或宿主部署PASS。

第一阶段交付可执行的最小接入候选、精确工具/交换合同与有限功能预检，主干随后审查并冻结正式收益实验。不要只写建议，也不要未经冻结跑正式性能/模型评估或把预检数据宣传成收益。

## 实现范围

允许新增以下文件，不改已验收内核/旧plugin/默认配置：

- `human_eye_llm_stdio.py`：标准库纯字节全双工relay，不import旧plugin或engine，不处理JSON。
- `human_eye_fast/llm_entry.py`：实际工具协议、最小session/ticket编排、一次最终内容封装。
- `human_eye_fast/blender_llm_bridge.py`：显式start/stop、主线程nonblocking socket与timer、当前连接/缓冲生命周期。
- `examples/blender_llm_entry.py`：显式配置绑定、启动/关闭说明或示例，不做全仓扫描/网络安装。
- `verification/test_llm_entry.py`、`verification/test_llm_transport.py`：真正有意义的语义/边界验证。
- `verification/llm_entry_fixtures.py`、`verification/llm_entry_reference.py`：精确的新交互场景与同责薄B/现有桥L；复用原积分夹具，不复制几何内核。
- `docs/LLM_ENTRY_API_DRAFT.md`、`docs/LLM_ENTRY_PROTOCOL_DRAFT.md`：把下列未定项写成可执行合同。
- `artifacts/llm_entry/preflight_001/`：初始/修改后的源身份、全部实际输出、失败记录、运行命令和环境。

确有需要的额外辅助脚本放该artifact目录。若无法不改已验收模块实现，先给主干精确seam/diff及理由，不自己扩大。`pyproject.toml`、README、Git、根侧架构/工作单/报告及用户`docs/RADICAL_V1_SPEC_REVIEW.md`由主干独占；不要stage/commit/push、切分支或改其他聊天成果。

## 必须落实的简化

外部只传少量操作参数/变更声明与必要结果，mesh/索引/模型全部留在Blender。常驻会话、持久TCP、纯字节relay、Blender单次parse、末端PNG单次base64。热路径不经旧execute_code、源哈希、源码compile、router进程、文件IPC或图片落盘。

不得无条件新增prepare/commit模型确认往返。明确step按已有图真实V→本地预测→执行/回读→真实A→after返回；after的V留到实际看过后，next按需。预测比较可独立请求。此新反馈时序有真实行为差别，B/I必须同序，不能直接借旧after图标签。

AO原bytes尽可能原样放入文本；必要MCP文本转义如实计费。不重复同时返回完整TextContent和structuredContent，不为“零copy”宣传而手写危险的任意JSON拼接或第二套事实生成器。before图不重复发送时，明确跨消息引用/新上下文重新取得/缓存责任；没证明消费者可恢复就不能删。

单client串行episode、明确对象/目标/参考/部署来源。NONE/dirty等由明确变更合同负责，目标拓扑变化仍按原API新建session；不加全场景扫描弥补并发编辑。错误输出如实携带既有write_status/Outcome，无自动重试、回滚或旧版fallback。

## 第一阶段有限预检

1. **先登记**：保存代码/输入/命令/设备及本阶段案例清单，明确协议版本profile、候选工具schema、反馈/图片/pending票据所有权、旧桥L与最薄B的实际职责。协议版本按实际客户端能力确认；模拟客户端只证明该profile实现，不证明当前宿主已支持。
2. **CPU语义及真实管道/socket**：验证分片/合包/UTF8跨包、partial send、通知无返回、双向原bytes一致、EOF/close；stub验证调用次序和实际A/真实V绑定、错误已写状态、公开图像/观察引用不丢失。主线程pump不能使用sendall；不在Blender内启动线程。无需为了测试低风险文档写大量镜像单测。
3. **最多两个独立Blender功能进程**：一个后台进程验证同handler及原新API对接；一个独立factory-startup窗口进程验证真实GUI事件循环/GPU/主线程dispatch，窗口隐藏且不操作用户现有GUI。两进程串行，各最多6个预登记功能任务，覆盖NATURAL Translate、SECTION relative shape（非单位/父变换）、真实V/A和after新图、显式predict-only/observe、无模型F/NONE及空面/已达目标、关闭/EOF。可组合控制，精确映射到案例。保留运行过程所见时序，但不做5+31正式计量、不比较收益、不挑配置试到更快。
4. 图像只通过新协议的实际内容解码核对源PNG/绑定，独立读取真实RNA/Outcome；不能只引用私有probe或只验证文件存在。若新时序需要像素标签，来自本次实际图的冻结独立评分，缺标签保持unknown。首轮不是正式模型消费。
5. GUI预检不能由background工作循环冒充。如果当前机器无法在独立隐藏进程提供必要GPU/event loop，保留失败并回传具体阻塞；不要改用户GUI/旧addon/宿主配置，不自动加进程重试。失败涉及计量/输入/范围时按既有工作流先回报，未失败的独立CPU工作可继续。

## 正式验收草案必须精确到可执行

把根侧架构里的1往返/0整mesh等结构门、I/B≤1.05、同责现有桥L的≥20%热调用中位改善目标，落实到固定场景、输入、图像/反馈、新旧语义及计时边界。若比较无法公平成立，应在正式成绩之前说明；不能用旧不同能力接口、额外防御链、弱化的B或省next流程制造收益。

至少分engine-direct、direct-handler和wire-entry；固定3进程、5预热/31配对原则、创建/执行交错、真实timer等待/idle CPU/完整buffer峰、原始bytes/codec/RPC计数、冷启动与schema分账。给出有依据的资源/空闲CPU不退化门及可验证计量方法。终端MCP客户端实际可见图片和真实模型闭环另外列资格，计量脚本成功不等于产品可用。未知provider token/费用标未测，不调用付费模型API、不寻找或复制凭证。

I/B的1.05门比较同一relay/pump/IPC上的候选与合理手工薄编排，二者最终内容和职责相同；engine-direct/direct-handler只作独立绝对成本分账，不作为带GUI调度与传输的I的1.05分母。L是通过原addon合理承载同一新会话/同一MCP结果的薄包装，不是旧全场景产品，也不故意每call重建会话或加旧guard。

## 回传与后续

完整交付后停止改写源和原件，主动一次发消息到主干host=`local`、thread=`01a1a993-669e-7632-98c2-a75754546eef`，包括精确文件/源摘要、命令、全部成功/失败和未运行项；该发送由用户先前明确授权。主干不轮询等待。根侧复审第一阶段后再冻结正式批次和必要优化对比，不自动开启第二轮寻优。不要触碰当前大模型宿主MCP注册，真正部署作为后续具体可复核阶段执行。
