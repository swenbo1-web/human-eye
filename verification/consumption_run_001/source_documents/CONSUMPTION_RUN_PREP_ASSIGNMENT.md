# CONSUMPTION-RUN-PREP-001 — W-ENTRY

用户已要求继续本工作流。SURFACE_ENTRY_REVIEW.md与CONSUMPTION_PREP_REVIEW.md已独立接受。你的单项任务：复用现有运行设施，准备唯一一批四题8答P/N的正常MCP消费试验；本批不启动任务消费者或Blender。准备完成一次回报，根核具体计划后给实测窗口。不改产品，不新增模块/通用评测平台。

## 固定输入和归属

- 你的干净基线b821407896ce770ff9f7bc7ee42be188531175a1，分支codex/nearest-integration，产品17db41c481397965a9bae3f4571c59a5a80939c9，131源01c296b5dac9c8733670b7b82886fe774fb6e50222d1b935d6ac27efa04760de；所有产品源保持。仅写本人verification/consumption_run_001，不读写竞争分支/默认安装/全局配置。
- 已完成可只读的材料：W-ACQUISITION的b9336a8037d4781584b703e1aad8f24845f0a5b2，C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/consumption_prep_001。从固定Git提取所需版本，不合并对方在途工作。本批不得改四题prompt、真值、资产或顺序。原资产只复制到私有运行目录。
- 序列固定T01 N/P、T02 P/N、T03 N/P、T04 P/N，最多8份回答，每格首次唯一上下文；失败不补答、不替换、不临时改题/说明刷过。此项只是未来计划额度，当前模型启动额度0。

## 最短真实入口

优先本机已安装Codex正常非交互入口，MCP工具真正注册，模型用函数工具调用；禁止要求模型读长手册、手拼JSON/CLI转发协议。官方来源见根已读 https://learn.chatgpt.com/docs/non-interactive-mode 、https://learn.chatgpt.com/docs/extend/mcp?surface=cli 。本机exec --help有 --ignore-user-config（auth仍用原CODEX_HOME）、--ephemeral、--json、-c、--strict-config；这些只是候选机制，要用本机只读检查确认，不盲信选项。

复用已登录Pro能力，只核认证状态，勿读取/导出/复制auth或key内容。不要使用API key、Google、替换provider或新的付费服务。可查看版本、help、白名单设置与本地schema；不发模型提示、不创建用户聊天、不改变信任/权限系统或全局配置。宿主依赖若不可用，报告具体缺口；不为了8答搭建新平台。

P与N使用同一确切可用模型/effort和通用工具。优先保留此前已确认消费者设置；取不到真实backend信息就记unexposed，不能猜或为可用性静默换模型。P额外是当前生产HE服务，原description/schema不重写；只读试验可用正常配置的工具允许列表，但须保存实际完整注册清单和成本，不能只算正文。N不得被全局HE Hook、预观察或项目学习注入事实。仅本次进程配置隔离，不动用户全局Hook。

根只读核查发现 --ignore-user-config 仅忽略config.toml，不保证去掉全局AGENTS/skills/插件/管理层；本机存在全局AGENTS且Agent Learning启用。必须检查有效配置与实际工具/注入边界，不能仅凭该flag宣布隔离。补充只读路线将落在根review_consumption_prep/entry/ROUTE.md；其建议也须本地确认。实际P调用生产server正常执行，不带上一批三态QA的profile改网格夹具；若复用bootstrap，仅保留固定字节加载和透明线缆计量，不能附加三态oracle或产品调用counter污染正式时间。

共享native能力应保留完整bpy/Python、数学、工具侧聚合、自写脚本与单答内缓存。复用既有neutral NativeSession与真实socket；若需薄MCP桥，只做参数/原响应转发和计量，不求解、不改返回、不插入答案/示例算法。每答独立私有asset副本与新状态，同题P/N字节相同。配置与所有controller/helper要固定hash。

可选图像优先复用双方相同既有入口，记录真实可达与投递能力；不得用共享GUI/default9876。如现有设施无图像，不为本批建渲染模块，明确提交“数值/文字子域诊断”的降格方案供根冻结，不能宣布视觉/完整产品基线胜出。不要先对四题跑插件筛题。

答案材料/admin/旧raw不能注入消费者。明确实际工具/文件访问范围，禁止称fork_none或隐藏目录硬隔离；若保留完整Python意味着无硬文件隔离，提交如实的非盲工程诊断方案、公开调用的访问审计与失效规则，不制造硬盲评声明或削弱原生数学能力。不能导出隐藏推理、加密派发正文或系统提示；只收公共工具参数/结果、final和允许的数值usage。

## 预算与完整成本（启动前冻结可执行值）

建议每答从派发180秒硬终止、最多8个模型可见工具动作、1MiB实际公开文本；所有ID发现、错误、补查、回退占同一预算。4096输出token只有宿主支持硬限才采用；不支持则两臂同样标未硬限并依靠时间/工具额度，不能写假硬限。模型答数、provider请求、逻辑工具、物理RPC分开。期限自动在worker/controller执行，不能再靠根轮询导致晚答重记成功。每个冷链600秒总限与60秒回收预留；需要的session数/调用上界从8格一次计划推导并列明，根核后才给窗口。

记录初始化/工具目录与实际投递schema、采集/内部cache、wire/text/image边界、实际usage增量、错误/重试/回退、排队/终答/关闭的完整墙钟。层间重叠不相加；生产成本、试验管理成本、无法拆分分别列，费用未知记null。工具目录18,884B旧QA值仅作警示，不冒充未来送模量。

本批允许标准库语法/静态协议/合成非几何fixture检查，不启动Blender/生产capture/模型来预演四题。做一个可审的冻结计划、所需执行命令、真实接入检查、最小runner和成本记录结构；不造复杂架构。必须列出未验证条件与如何在唯一批次内计入失败分母。

最迟2026-11-08 02:00 UTC（北京时间10:00）回报，遇到可恢复准备错误在本轮修完并保留；不可恢复则按已完成范围交付。完成提交本人新增证据，工作区干净，一次回报本聊天01a1971f-eef5-7a23-a1b1-2352beb80a77，含cycle_id、HEAD、源hash、文件索引、能力限制、0消费者/0Blender确认。随后结束该批等根放行，不自行开始8答。
