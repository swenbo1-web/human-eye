# CONSUMPTION-RUN-PREP-001

准备材料已形成，等待根审定唯一实测窗口；本批没有启动消费者、Blender、MCP服务、native/product RPC或模型API，也没有导入产品。PLAN.json 的 execution_ready=false，runner 在任何进程、helper导入或资产复制前拒绝执行。该状态是准备阶段边界，不是某道题的成绩。

固定产品17db41c481397965a9bae3f4571c59a5a80939c9，131源01c296b5dac9c8733670b7b82886fe774fb6e50222d1b935d6ac27efa04760de；所有产品字节与原提交相同。仅新增本目录。四题材料从已交付b9336a8037d4781584b703e1aad8f24845f0a5b2的Git对象提取；4份911字节题面、真值、资产与顺序不改。资产只核哈希，准备阶段没有复制或打开。

## 当前合同及顺序

原任务书和两份根复核保留，CONSUMPTION_BUDGET_CLARIFICATION_001.md覆盖原8次工具硬门槛：8次仅观察阈值，超过不终止、不扣质量、不判无效，全部计成本。180秒从每格派发开始的原绝对硬期限保持，含资产/host启动、模型排队、MCP初始化/目录、ID发现、错误、补查、回退和最终答复。4096输出token无宿主已验证硬限，因此明确为null。

唯一固定顺序为 T01 N/P、T02 P/N、T03 N/P、T04 P/N，共8格，每格首次独立上下文；失败不补答、不替换、不改题。每格新Codex exec、新NativeSession/私有同字节资产，P另新生产服务及空state/cache。原生答内namespace与缓存允许复用；模型服务端缓存仅按真实usage另记，不能称冷模型。

8次工具不是物理RPC限额。计划使用原neutral helper已有128 execute_code上限，每格另1 close，故拟申请最多8会话、8×129=1032物理RPC的保守上界，尚未获授。每格冷链原600秒，60秒清理预留；180秒答题期限更早。没有setup/probe/oracle RPC。每次实际连接在native/HE共用账本中先登记；超过物理上限不建立新连接，已执行状态不明不重放。计量分别记录模型公开工具事件、MCP tools/call及物理RPC，不将code-mode外层动作和嵌套调用相加冒充一种指标。

## 正常入口

固定本机已安装Desktop CLI0.167.0-alpha.3.2（不是PATH首先找到的0.152.1），完整路径/SHA见entry_check/DESKTOP_CANDIDATE.json。保留先前消费者模型gpt-6.1-sol/ultra，provider仍为openai_http，tier仍default；只白名单复制该provider非凭据配置，未更换provider或登录机制。本机登录状态为ChatGPT。实际backend和当前可用性未发请求，记unexposed；失败不切API/model/tier。

普通exec以 -c 注册 native stdio MCP，两臂schema逐字相同。P额外注册 human_eye，宿主enabled_tools只开放human_eye_scene_observe，schema/description取原生产服务tools/list，服务返回的完整目录另计。模型通过函数工具调用，不读转发手册、不拼CLI/JSON协议。完整题面原字节从stdin投递，不预先提供免费ID、名称映射或目录；实际ID发现/查错/重读均在该答原期限及成本中。

native薄桥只转发完整Python到原NativeSession socket，返回原执行结果；保留bpy、math、mathutils、遍历网格、脚本、工具侧聚合及答内缓存。无筛选器、几何算法或示例解题代码。P路径为原生产入口/connector/bpy/解析；he_bootstrap保留原exact-byte loader，只有透明socket计量，没有上一批profile改网格、oracle或产品函数counter。准备阶段未启动此路径，正常注册/实际schema投递仍需在唯一批次内验证并计成本。

## 配置、注入和访问边界

ignore-user-config只跳过config.toml，auth沿用原CODEX_HOME，未读取/导出/复制auth/key内容。候选按本机schema及help准备37项覆盖，禁用已知全局HE/learning/共享GUI MCP、插件、hooks/apps/memories/skills自动指令，保留shell/view_image；仅本次进程配置，未改全局Hook、信任或权限系统。保留managed限制，不用bypass。父thread/session/tool绑定及Desktop app-tools pipe不传给消费者，API key类环境变量按名字排除，排除项的值也不读取；CODEX_HOME及正常客户端路由保持。

37项TOML和features检查只证明静态/本地命令结果，不证明exec实际完整配置、管理层或送模输入。debug prompt-input未执行，避免可能启动hook/MCP和导出系统输入。当前工具目录/上下文注入真实边界仍未验证，不能宣布干净N。若根允许唯一批次，意外HE/learning/历史事实注入、非预登记工具、源码/管理员答案读取均作为污染原件保留，不能给该对引擎归因。实际模型投递schema字节未暴露时记null，不能拿tools/list物理字节代替。

工作目录拟在LocalAppData/Temp的独立中性目录，初始只投递一题原文和正常工具；neutral资产名input.blend，无case文件名、truth/admin/旧raw/评分表或helper实现复制给work。完整Python和同用户shell仍可读账户可达文件；隐藏目录、随机路径、ephemeral或不告知路径均不是硬隔离。本批最多是非盲工程诊断。公开脚本/命令/工具参数结果须审计管理员、历史、其他格及直接绕端点访问；这不是完整底层文件追踪。不能通过削弱原生数学能力制造“盲评”。

## 图片与文本

两臂同一个可选native deliver_paths入口，复用已有ImageLedger，把消费者自己产生的PNG作为正常MCP image block返回；不增加renderer。P原image blocks也经同账本计量并保持原字节。建议冻结共同1图、每边≤768、总像素≤589824。完整Python可生成未请求的图片，桥只做发布准入；原worker render/newPNG事件必须审计构造次数。真实Pillow、相机/场景成像、host传图和模型接收均未用消费者验证；reservation不等于model seen。若根不能核实共同可达性，须在首答前冻结文字/数值子域诊断，不宣称视觉或完整产品基线胜出；N的完整原生能力仍保留。

1MiB账本包含题面、完整MCP目录、工具text/error和final，builtin shell公开输出在宿主事件后计入。MCP发布前能限额，builtin输出已经送达后才观察；不能伪称全工具发布前硬限。根需在首个消费者前确认相同实际输出配置及这个可执行合同；当前PLAN将该点和真实上下文列为待审条件，未为它新建控制层。

## 成本、失败与评分

COST_RECORD_TEMPLATE.json列初始化/目录、原生/生产socket、MCP正文/图片、模型公开usage、排队/终答/回收和管理成本。已有18,884B目录只作旧例，不是未来送模量。每层原始TX/RX保存，模型实际接收、wire、序列化和usage分栏，嵌套墙钟不相加。每个新exec的terminal usage只记一次，cached为input子集、reasoning为output子集，不累加快照。provider请求数、费用及backend未暴露即null/unexposed，不能从8答或字节猜。

消费者记录只白名单保存公开tool参数/结果、final和数值usage；丢弃reasoning/system/developer/加密内容，不保存任意stderr正文，仅字节数与状态。模型中间agent_message不归档为隐藏推理，最终公开答单独保留。真实注册、JSON事件覆盖、context、安全回收、图片/依赖和模型可用性均是唯一批次的未验证条件；该格首次失败留在原8格分母，绝不追加试答。

评分沿用冻结材料与根修正：Pro评分Agent如实标Pro Agent；无符号距离先拒绝bool/负/非有限，再做显示误差。字段正确和证据充分性分开，不凭自报complete授予全局信用；T04仅unknown为任务未完成，合理校准另列。P可不用HE，零使用不能归因引擎。只对双方正确完成配对比较速度，同时报告全四题覆盖率。8次动作观察阈值绝不进入质量/有效性失败条件。四题旧平面/提示命名的局限不变，不扩大到泛化或正式收益目标。

## 文件与命令

- PLAN.json：当前待审计划，含来源、顺序、模型/配置、预算、实际活动0、未验证项、component哈希。
- runner.py：独占actual_01和每格私有目录，普通exec/MCP、原期限监测、公共事件白名单、owner close/wait回收；准备阶段不启动。
- bridge.py / he_bootstrap.py：薄原生MCP/原生产透明socket路径。
- materials：固定Git原件和独立controller资料，绝不作为消费者附件；原件不会因补充而改写。
- entry_check：本机help/status、白名单配置、schema及能力限制。
- PRODUCT_BYTES.zip：131个原产品Git字节，没有导入执行。

准备命令：现有工程venv Python以 -I 执行freeze_plan.py；tests_bridge.py及tests_runner.py只跑stdlib非几何合成检查。未来唯一执行命令形状为同Python -I runner.py --approval <根批准文件>。仅有命令不授权；须根先核待审合同、冻结execution_ready/plan SHA、给STATE中相同cycle/token/8sessions/1032RPC并核component/hash，当前会在启动前拒绝。改合同只能在首答前，不能试完更改。

最终19项独立合成方法通过（9 bridge+10 runner）；历史合法修订累计76次方法执行、0失败，另有准备命令错误保留。新增两项验证早期BrokenPipe仍回收并记录、taskkill助手有界；进程均为内存mock。复核随后提出的原期限timer、启动前remaining、Python身份和granted状态检查也已补齐；最后终态再核原deadline，晚写不获成功信用。它们没有打开网络、启动工具后端、Blender或模型，不替代真实入口证据。原材料、entry检查和review的早期hard8措辞记录当时建议；以根补充和当前PLAN为准。全部产物提交后一次回报根，本批结束，不自行开始消费者。
