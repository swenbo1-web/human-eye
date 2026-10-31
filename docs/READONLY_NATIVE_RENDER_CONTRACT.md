> 文档角色（2026-10-31复核）：本文保留专项合同及当时验收记录，“源码候选/未安装/下一步”等描述只代表所述阶段。当前正式版本与已交付状态见 [PROGRESS](PROGRESS.md)，现行排期仅见 [唯一主计划](PRODUCT_ROADMAP.md)，设计取舍见 [架构分析](ARCHITECTURE_ANALYSIS.md)。本标识不扩展本文原有支持域，也不重标历史测试。

# 锁定资产只读证据与渲染状态回读候选

当前SDK候选已推进到 `9.7.2+20261031.multiscale.candidate.r2`（5e24/77源，未激活）；当前生产仍b77/76。新增共同多尺度只读图和actual-RNA审计，保留旧图像API并校正XY方向元数据；实际MCP/Hook尚未适配，详见当前总推进计划。最新尺度/取景/真实故障验收见本文末尾“2026-10-31 边界实测与原生取景修复”。以下先保留d89阶段历史结果，不当作当前完整支持域。

候选版本 `9.7.2+20261031.readonly.render.candidate.r1`，77运行源码，build `sha256:d89f8623cb83683e931be94c1a26437e8912e88c5c7c02145d9f0252f3bc0cae`。当前聊天仍运行已核验的b77/76；此前27c候选和生产入口保持，本候选仅在独立SDK目录测试。

新增三个无参数typed只读入口：`capture_readonly_evidence`、`native_render_state`、`last_native_render_audit`。入口验证固定worker、PID、共同QPC协议和各自专用协议；不注册为模型工具，不接受JSON权限或路径。

锁定静态资产通过显式只读生产者取得完整原始姿态证据。只有transform lock这一项可读条件与严格生产者不同；原始/求值网格、拓扑、身份、单位、静态矩阵等证明仍执行。默认 `capture_evidence` 继续拒绝锁定场景，动画、约束、变形等其他不支持条件也不能借只读标志放行。只读证据明确不签发执行权限，原生及自动写入口仍零移动。

每次真实截图均记录owner私有before/after：原相机及data身份、矩阵和参数、scene/global对象与camera数据清单、active与全selection、helper改动的render/shading属性、image/view可写RNA scalar/enum/array，以及明确的image颜色管理子节点与scene display设置。恢复按颜色管理依赖顺序执行；单项恢复失败不能跳过其余清理。完整约定状态及原生几何都恢复、审查记录匹配新sequence/view后，公共接口才返回PNG。失败记录留私有侧并停止后续动作。

该状态范围是“helper赋值及明确隐式依赖的标量、相机资产、选择状态”，不包括任意外部插件、操作系统/GPU状态、渲染结果缓存或所有RNA指针图。没有宣称任意Blender全局状态事务。

| 实际验收 | 结果 |
| --- | --- |
| 回归 | 1360运行，1359通过，1既有Windows符号链接权限跳过；20新增方法包含在内 |
| 独立合同 | 新20加相关旧65，共85通过；旧测试断言保留，仅同步fake协议和独立失败fixture |
| 标准与真实锁定 | A2/C2各一：标准目标各4次真实移动到0.0010000057573859179m；锁定资产默认严格入口拒绝、typed只读完整，两组零移动 |
| 密集场景 | 20个mesh（目标/底座+18背景箱体），两组共同公开数学/自动入口均4写到同1mm，原生保护字段保持 |
| 前景遮挡 | 3个mesh，两组均完成同1mm；SCENE图蓝色像素启发式0，XY/XZ仍为正。实际截图已检查；这不是分割真值或遮挡比例标注 |
| 完整回读 | 8case × 3view，共24份真实审查before=after；含与临时相机同名的原camera/data、EXR_RGBA16、517×293/73%、非默认曝光/gamma/shading、多选及非目标GreyBase active |
| 引擎切换 | 扩展四case原设置CYCLES，真正生成Workbench图后实际回读恢复CYCLES |
| 分组一致 | 四种场景的A2/C2公开初始geometry/task/三viewRGBA完全相同；诊断、RNA身份、路径不进入公共图像结果 |
| 生命周期 | 8个新factory fixture、16个自有进程全部exit0回收；8个输入blend字节保持 |
| 独立原生审查 | 1588条细粒度核查，不当作测试方法或模型试次数；逐setter链/原预算/路径/非目标/局部网格/13矩阵保护值复算 |

本轮成功路径有真实Blender恢复证据；强制渲染失败、after不可读和恢复错误路径目前为hostdouble测试，不能称已在真实Blender刻意触发。原有回执丢失与混合预算证据保留在上一阶段，不与本批样本数相加。

新候选未替换默认MCP。真实模型试次、训练和上传均0，公共评测formal资格继续false。下一批优先检验不同尺度、极端视角与真实故障恢复边界，再做固定launcher/安装和受预算约束的模型对照。场景仍限静态刚体箱体/原支撑面及世界Z终态，不推广为通用旋转、扫掠或任意资产。

证据：[本轮目录](../verification/fixes/20261031_v21_readonly_render/)、[标准/锁定](../verification/fixes/20261031_v21_readonly_render/owned_work/core_001/RESULT.json)、[密集/遮挡](../verification/fixes/20261031_v21_readonly_render/owned_work/expanded_001/RESULT.json)、[独立审查](../verification/fixes/20261031_v21_readonly_render/acceptance_work/FINAL_REVIEW.json)。


2026-10-31 边界实测与原生取景修复（取代上一批“尚未触发真实故障”的当前状态；旧结果按当时版本保留）：

新候选 `9.7.2+20261031.native.framing.candidate.r1` / d16 / 77源，当前生产仍b77/76。SI顶点先换回BU，Python double局部投影计算全深度相机/裁面，真实RNA参数回读与全顶点frustum检查通过才进入render。使用本次fresh native而非episode初始几何。截图临时归一pixel_aspect为1、关闭border/crop，8个新增依赖字段纳入private状态及消费者完整审查，之后恢复原设置。全部layer关闭在进入render前拒绝，避免d89真实AV崩溃。

实测d89的毫米BU三图单色、千米BU空白，虽然A2/C2图片相同也不算合格。修复后两个单位的目标三view均可见；mm/km/standard共6case、24截图、12进程通过，三pair公开query/task/初始RGBA exact；standard两arm各4setter到1.000005757mm，动作后XZ/SCENE图随姿态变化、仍可见且两arm最终RGBA exact。20m深度的XY远红标记由0变7744颜色像素；原border/crop报错现输出384完整图，原状态exact恢复。颜色阈值仅启发式，不是分割真值；深长场景XZ/SCENE仍可能subpixel，不宣称全场景可读。临时相机frustum检查由实际代码执行，未把参数全量写入持久化raw，不冒充独立重算完整证明。

故障证据分层：d89默认worker真实零面积border引起bpy RuntimeError，状态恢复且五路冻结；新d16禁用layer预拒绝、worker正常回收且audit恢复。受控render_post删除原相机属于越界资产丢失，检测恢复失败并清理临时资产，不宣称找回已删资产。Python verifier一次异常注入驱动真实bpy forward+rollback两setter，原pose/deadline/limits保持，仍冻结；不是自然Blender故障。早期原生AV及harness异常回执保留为失败，不能计通过。

1372方法回归中1371pass、1既有WinError1314权限skip，12新增方法包括单位协变/全视锥/真实RNAclamp/fresh输入/无layer预拒绝/新增审查字段；旧两个测试assertion AST完整保留。独立53相关方法通过。真实模型试次、训练、上传和provider调用均0。

新增未修边界按顺序收敛：原生binary32零位移预拒绝并保持预算；共面代表triangle编号变化时仍固定原triangle witness；384全景长宽比/深度场景共同多尺度观察。100m/100km固定world-Z的1µm要求可能不可达，不能改容差拿通过。之后固定安装与模型收益对照。

证据：[尺度/视角/故障目录](../verification/fixes/20261031_v21_scale_fault/)。


2026-10-31 共同多尺度观察SDK验收与产品接入缺口：

当前SDK候选 `9.7.2+20261031.multiscale.candidate.r2` / 5e24 / 77源80文件，生产仍b77/76。新增带独立capability的 `native_look_multiscale(view)`；旧native_look五字段公图、旧冻结ABC _NATIVE不改。新cap可用时common A2/C2同增只读工具，返回全景、可选局部图与18字段公开SI取景/裁切说明。budget_scope明确每call最多2×384²=294912px，原episode截止不续；没有宣称episode/token硬总图片额度。

先计算公开focal投影最小边法向宽度（最多64v/128tri），全景不足12px、zoom至少2且最多4096、预计局部至少32px才考虑追加。局部span约4倍特征宽，预计96px。普通可读场景不做central ray也不附图；候选只用一条正交中心视线对全部已捕获原生网格求最近hit，明确focal优先才追加，遮挡/不确定/超4096tri预算则跳过。单样本不是完整可见性证书。ROI只裁屏幕，不删/隐藏资产；所有已捕获native顶点继续参与深度安置和裁面检查。

每张图都保存owner私有actualcamera RNA矩阵/尺寸/clip/全部顶点depth/中心和轴的独立可复算记录。两帧必须同fresh完整native，逐帧约定render/camera/选择状态恢复；rawPNG SHA绑定privateaudit，公开图剥text/EXIF/path等metadata而IDAT/解码RGBA exact。整个bundle验证完并通过最终截止/状态门后原子发布，第二失败不给部分成功。该范围不包括任意外部插件/GPU状态/RenderResult缓存；隐藏collection、曲线及任意非捕获资产不泛化为全部Blender场景保证。

真实首r1在XY被orientationguard拦住，0移动、状态恢复。独立factory探针发现mathutils的legacy相机XY实际180度roll；r2只修纯basis/公开canonical轴为-X/-Y，不改camera quaternion/Euler/阈值。45纯场景/单位组合相机输入exact、renderer AST不变；真实r1legacy与r2标准两arm三view像素exact。原r1失败SDK/回执保留，未重标成功。

1427方法回归中1426pass、1既有WinError1314 skip，14host/planner加18entry新方法包含在内。16主case、8pair公开task/query/plan/RGBA exact，48新工具调用返回80帧（48全景+32局部）；标准/密集只发全景。长1000:1及20m深度的原blue0全景得到可辨局部形状；局部端部裁出窗口有明确标识，不称完整对象。partialSCENE的蓝启发式像素8→7468，20m前红箱仍有1930像素；完全中心遮挡SCENE不追加。颜色阈值和bbox均非分割真值，斜杆minbbox不是其真实横截宽度；这也不能证明图像可精测1mm。

两故障分别为真实fixedworker无enabledlayer预拒绝（六个模型route停止、无成功bundle）及owner Python第二attempt前注入（真实首overview后整个bundle失败，0setter/state/native/deadline保持），后者不是自然第二次render失败。含r1失败/r1legacy/16main/2fault共20sceneattempt、40自有进程exit0回收；另1factory朝向probe进程回收。20输入blend原before/afterSHA均持久化重比。成功物理render共90：80主帧、6r2legacy、3r1legacy和1故障中未发布overview；不能把90都当80主bundle或模型样本。

最终CPU规划探针12组、每法41交错warm样本，普通/密集较旧frame-only最大额外median约0.0338ms，全部case约0.1149ms；不含RPC/renderer/元数据输出成本，不宣称端到端加速。困难视图实际多付一张图的渲染与模型输入成本。

当前LIVE_MCP_TOOLS_SCHEMA仍4tool，production/Hook没有新SDK入口；仅打包核心不能让其自动进入当前聊天。下一步先做独立只读观察lease（不重绑/重置动作episode、不签动作权限），再接实际MCP/Hook、显式来源/能力协商和include_image=false，随后固定launcher/安装事务/真实3D消息验收。未来视觉收益对照须给原生模型合理手动取景及同像素预算，不能拿旧三枚固定视角当普通模型上限；当前共同SDK同API用于输入等价，不是巨大模型收益证明。模型/provider/训练/上传0，formalfalse。

证据：[本阶段报告](../verification/fixes/20261031_v21_multiscale/REPORT.md)、[安装缺口](../verification/fixes/20261031_v21_multiscale/owned_work/INSTALLATION_GAPS.json)。


## 2026-10-31 产品只读观察协议

新增 `typed-native-readonly-observation-v1-20261031`。宿主提供 `native_observation_capabilities()`、`observe_readonly_native(request_id, focal_id, reference_id, expected_capture_revision, deadline_ns, view)`、`last_readonly_native_audit(request_id)`。能力响应严格8字段，绑定宿主源码SHA、进程及系统QPC；固定Process worker还核验子进程PID。旧受信adapter以None表示未支持，Socket仅将严格supported:false映射为该sentinel；声明新能力的坏字段/错误不会触发成功降级。

每次观察持有不超过30秒的独立期限，保留128个未过期ID，到期才清理、满时拒绝；新host实例通过Blender driver_namespace共享去重/观察隔离。它不建立、续期或重绑动作episode，不读取或清空动作ledger，不补原预算，不返回setter权限。完整同次响应为evidence/overview/detail/plan/observation五字段；私有审计绑定fresh capture/native revision、对象身份、相机/渲染/几何恢复和期限。恢复无法确认会隔离观察通道。诊断getter不返回历史图像。

实际MCP保持原4工具，在human_eye_scene_observe的query.native_visual选择mode=auto|projection|multiscale和view=SCENE|XY|XZ。默认auto仅在已有目标对、无显式投影标注、受信能力协商成功时选择原生；旧宿主/单对象等按明确reason返回投影。projection以及include_image=false不探测能力，文字Hook仍传文字，不触发图片渲染。已进入原生观察后失败即失败，不用投影掩盖。blocked观察路径不渲染原生。

每call最多两张384图、294912像素、16MiB PNG，plan仅公开一次。MCP图像走原生ImageContent，JSON不重复base64；渲染审计、进程ID和宿主路径不进入visual_delivery，原生PNG/plan不持久化到动作授权缓存。现有显式投影缓存保持既有语义。所谓原生图是Blender原渲染并在返回后删除私有PNG元数据，公开前后RGBA一致。局部图是有意窗口裁切，仍保留真实所有场景网格和深度遮挡；一条中心射线不是全可见证明。

78源81文件SDK候选ed296569，只读观察lease独立于动作episode；新8-key能力、完整同call证据/恢复/实际RNA/PNG验证，MCP仍4tool经observe.query.native_visual接1/2原生图；默认auto、projection与无图不probe；文字Hook零图零render。1468回归1467pass/1既有权限skip，41新增方法；7真实产品case/14进程exit0已wait回收，13成功只读call交付17原生图，另6预期拒绝；raw/public RGBA exact，默认BlenderMCP随机端口链通过。独立控制场景仅1次授权-.5mm动作，观察前后原账本exact、原动作过期仍读但拒写；7个输入文件SHA保持。run001验收器失败保留，额外2进程启动，其worker无returncode仅确认不在进程表，不能称总16均reaped。当前b77/76仍在用，新SDK未固定launcher/激活；Hook是模拟handler，未验真实新版本用户消息；模型/provider/训练/上传0。

当前候选及协议实测见[报告](../verification/fixes/20261031_v21_readonly_product/REPORT.md)。固定launcher、安装CAS/旧writer隔离和新版真实用户消息仍待完成。


2026-10-31 只读身份门与固定发布：

已安装78源/87文件固定发布readonly.product.r2，build6acbe816；新配置真实MCP进程身份兼容，当前旧聊天b77已被statefingerprint拒绝，须重启后再核加载。安装验收发现r1只读observe遗漏原身份/source检查，r1拒装保留；r2仅复用既有_identity_rejection并更新revision，几何/渲染/动作/预算算法未改。1470回归1469pass/1既有Win1314skip；r2私有admin11case19CLI、11role合同、两组serve/Hook真实哨兵12拒绝/0TCP/0state。固定serve→默认Socket实际3场景/10子进程通过，5native观察7MCP图片，R1/R2七图RGBA exact；独立有限axisbox4setter从4mm到约1.000002mm，原4步/4mm/10s预算内，观察后ledger exact/重放0setter。独审source+mini14+plan25+after55通过。四文件CAS/备份已提交，state仅顶层绑定token改变，历史/原预算不重置；五组Hook结构保留同指新r2。用户global model/effort期间变化仅记录，安装不覆盖，验收相对freshplan快照。未触用户GUI/共享9876；Hook为模拟固定命令，真实用户消息仍待验；模型/provider/训练/上传0。

观察、预览、移动与有限动作段共享现有身份/source准入；status保留无host诊断。只读租期仍不重绑动作episode或返还预算。局部图窗口和源像素机会不等于模型成功率提高；当前模型试次仍为0。见[本阶段报告](../verification/fixes/20261031_v21_readonly_fixed_release/REPORT.md)。

本轮激活后独审时global配置与freshplan快照相同；随后另记录本项目五条Hook的trusted_hash变化。安装器不写回或恢复这些信任哈希，操作者未归因，不以此证明真实用户消息Hook已运行。全部历史审查保持原时点边界，不声称global全轮或直到收尾字节不变。


2026-10-31 当前聊天重启、真实消息入口与纯默认PNG边界：

r2当前聊天实际加载6ac/78/installed且身份兼容，无旧stale；本轮真实UserPromptSubmit非3D重启消息正确skip，随后用户完整问答答案经answers_only触发真实自动文字观察，gap=0.004000001586973667m，0移动/0图片/0能力探测，场景与原动作历史保持。纯默认PNG首次原生观察发现恢复失败：重复赋相同PNG触发Blender把无效空linearcolorspace名变sRGB，恢复空值TypeError，原生通道正确隔离且没有伪装投影成功。原r2默认PNG不计图片通过。隔离候选只跳过alreadyPNG setter，三视角初测+4格式3视图双arm共24 typed native调用回归：候选12/12成功，旧默认3次预期失败，21成功帧actualRNA/PNG复核，9组已初始化原/候选RGBA exact；未修改源码或安装。下一P0正式合入/全相关回归/新固定发布，不再重复已通过的重载与真实文字Hook。测试服务已STOP，5个自有Blender均exit0/wait，默认端口已释放。探针漏禁bytecode产生r2内2新pyc，清理遭blocked by policy拒绝后未重试，原87发布文件字节保持、实际89文件如实记录。模型/provider/训练/上传0。

24项新纯解析合同单独记录，未声称已包含原1470回归；24实际native调用也不是24个模型试次。自动文字Hook、已初始化配置原生图、纯默认PNG失败、隔离候选分别按实际证据判断。见[本阶段报告](../verification/fixes/20261031_v21_r2_restart_acceptance/REPORT.md)。


2026-10-31 默认PNG正式修复与当前工具验收：

已正式合入同值PNG setter guard并安装r3/d2a4508d，78源87发布文件。原源码真实红测defaultPNG三view失败、其它九初始化配置通过；新完整1508回归1507pass/1既有Win1314skip，包含新2个真实RNA方法及完整36项structured prompt模块。真实固定serve→默认Socket四profile13次native/13MCP图通过，12管理进程exit0/wait，四输入SHA保持，默认空linearcolorspace名经三view+repeat始终空，13帧恢复/PNG/RNA复核，历史12组RGBA exact，0setter/0动作episode，无新增bytecode。独立source/min14/plan25/after55与13图离线复核通过。四文件CAS/备份36627ce795a04bb19239d1c2a8afc3c8已提交，安装state仅绑定token改变。实际当前聊天工具已由6ac/78切到d2a/78兼容，不需用户重启；随后root在空闲9876独占只读新factory上实测当前native SCENE/XY两图成功，raw/public/RNA/空name恢复均过，无图零能力探测/渲染，0移动，原动作历史保持。该桥已关闭，输入SHA及两个额外Blender exit0/wait回执齐，未触用户GUI。原r2及两份策略拒删cache完整保留，没有新清理尝试；新r3仍精确87文件。模型/provider/训练/上传0。

修复仅跳过alreadyPNG赋值，恢复比较、隔离、几何、动作预算与截止均保持。安装器本身不承诺热重载；本轮依据实际当前工具已加载新身份和图片，不要求重启。纯解析、实际RNA、MCP图像及模型试次分别计数，不从像素一致性推断模型收益。见[报告](../verification/fixes/20261031_v21_default_png_release/REPORT.md)。


2026-10-31 只读宿主重连与能力缓存收口：

只读重连已合入并安装1c51f537/78源87发布文件。仅LiveSpatialService.observe进入5命令只读串行域；完整64hex文档epoch改变时失效正/负cap缓存，同epoch不加RPC；legacy无可靠epoch则每次图像重探，保留旧capture准入。仅_connect返回socket前的OSError/TimeoutError不毒化本次只读连接；当前调用仍报错且绝不重试，下一次独立观察才可恢复。已发送/响应未知/JSON或nonce错误仍原poison，closed不复活，动作绑定/总预算/截止/账本/inflight/宿主render隔离不重置。1526相关回归1525pass/1既有Win1314skip，含15新transport与3service方法；独立真实未监听端口/并发writer/close三项通过。同真实service经canonical MCP跨三个owned Blender进程：新source与固定entry各6图，首cap各1、warm各0，离线一次失败后下一独立调用恢复；无图0cap/0render。旧r3同矩阵复现B旧PID图拒绝及离线poison后C全拒，不能算候选成功。15/15管理进程exit0/wait，0setter，3输入SHA保持。实际16render/14公开PNG；旧负例B两raw-only拒绝图补审，旧arm原budget2误标实际4的验收器偏差保留；两candidate各6均合原预算。独立mini14/plan25与旧writer隔离、dirty unknown/CAS拒绝通过。私有admin11case19CLI、11角色合同与12零连接边界通过。四文件CAS安装只变状态绑定token，原两条goal历史保持，新固定入口stdio身份通过；11旧release及22旧封存阶段完整保持。这证明只读可用性修复与新鲜证据，不证明模型三维任务收益；用户GUI、非空动作跨重启继续执行、真实新用户Hook均未据本轮冒认。模型/provider/训练/上传0。

流程为原状态锁→只读域→fresh capture epoch→必要时新cap→原inline PNG/PID/epoch/恢复验证。失败当前call不重发，下一独立call只在确定零发送时可继续。稳定可信epoch保持warm零额外cap RPC；不对无可靠epoch旧桥作此性能承诺。已关闭/毒化/同宿主quarantine保持。本轮当前聊天status实际触发旧配置fence并拒绝执行，需重启后复核，不把fresh stdio当当前聊天热重载；没有连接生产Blender。固定entry真实图片属于独立owned链。见[报告](../verification/fixes/20261031_v21_readonly_reconnect/REPORT.md)。


2026-10-31 有限只读依赖链收口：

原生只读依赖绑定已安装4d2d68ff/78源87文件；原bootstrap全源pin已有保障，本批关闭另bridge根只比host.py及有效pyc错配的有限加载缺口。host字面commit gateway/deadline两个SHA，保留host_source_sha256原host字节含义和八字段V1；只读scope capture/typed模板核构造快照并编译同份bytes，cap绑定loader实际编译hash，helper固定sibling/hash/256KiB上限后编译已验bytes，warm仍核源漂移，clock独立于action缓存；默认worker初载host/clock同样覆盖。无新增RPC、回退投影、动作授权或预算/截止/unknown重置；无图不触发新增helper加载/cap/render。scope外旧capture/apply/supervision模板及legacy episode loader保持，不宣称任意同进程篡改或全部native/action加载链已绑定。1544相关回归1543pass/1既有Win1314skip，18新方法；首两完整回归均因worker示例副本未同步失败并保留，已snapshot/diff后同步examples/blender_worker.py，第三完整回归通过，runtimefreeze未变。独立7组pyc/漂移/snapshot探针、mini14/plan25通过。真实fixed MCP四候选arm交付8图，old正常2图，三类旧pyc反例0图；6份真实3.13有效pyc参考执行被现场证实，实际渲染入口=完成=公开10，17管理进程均exit0/wait。另defaultworker独立2次启动：第一次验收器capture键误用objects导致0render/健康退出，第二次按meshes修正后SCENE/XY两图通过，2child均exit0/wait；合19管理进程其中11Blender，实际12render/12验证图，MCP10和worker2分开记。新旧正常两view RGBA exact，输入SHA/87发布文件不变，0setter。局部clean-source模板96对照样本的paired median额外capture+.696ms、cap+.638ms；非整任务时延，cap p95更高且有76ms离群/并行验证干扰，明确不承诺性能不退化或提速。接受此有限正确性成本，不把零RPC当零CPU。四文件CAS只替换状态绑定token，原两条goal记录保持；12旧release和23旧seal完整保持。当前聊天与fresh stdio分开记录。用户GUI/复杂独立资产/模型三维收益未由此验收，模型/provider/训练/上传0。

这是来源与恢复正确性验收，正常图片像素保持，不把它当成模型视觉/任务收益或速度提升。后续优先进入复杂资产与GUI验收。见[报告](../verification/fixes/20261031_v21_readonly_dependency/REPORT.md)。


2026-10-31 重启核验与复杂资产质量诊断：

当前聊天实际已加载4d2d/78、readonly.dependency.r1且身份兼容，不再需要为本次安装重启。运行时、安装、五组Hook与生产状态本批均未改。106项针对性installed回归通过。新建6个独立静态Blender场景：断开槽组件、真实凹洞、23对象nearest、25um薄片、闭壳完全遮挡、1000m/BU凹洞；实际12个Blender进程exit0/wait，12张SCENE/XY原生图由SDK service交付，非当前聊天MCP或GUI图。量测/nearest/penetration、raw/public RGBA和actual RNA恢复经离线独审。

原run001六case全部在收尾状态断言失败：验收器将合法变化的router.sessions观察缓存误当动作历史，图片汇总因赋值太晚误记0；原failed、原计数和预注册字段误名均保留，离线审查重数12图，没有重启Blender或重渲染。完整before state中runtime.sessions未保存，因此不称整state字节相等；已保存完整可比较差异及动作字段。不能把离线事实通过写成原预注册整轮通过。

质量新发现：25um精确文字保留，但目标自身轮廓足够大使planner不补图，任务间隙仍是亚像素；闭壳图只显示外壳，几何穿入证据不等于看见内部目标。另同边界8v/65v126tri纯规划反例发现复杂焦点直接失去ROI机会，尚非真实产品图反例。下一批优先任务相关接触特征取景/质量说明，再低成本复杂焦点机会筛查；保持原2张384²、完整遮挡与原期限。模型试次仍0，GUI与任意复杂网格尚未验收。

证据：[本阶段报告](../verification/fixes/20261031_v21_complex_quality/REPORT.md)。


2026-10-31 任务间隙取景候选：源码/SDK候选7a88d58d、78源81文件已验，生产仍4d2d/78且未激活本候选。新增readonly专用V2只处理严格8v12tri外向轴盒、单轴正间隙、其它轴足够重叠、最佳正交gap小于1px；保留原overview，gapZ补XZ、gapX/Y补XY，预测局部至少32px才追加。每call仍最多2张384²，producer三ray与consumer独立三ray共享6F<=4096预算，支持scene F<=682/V<=4096；全部几何参与原生render/depth，三sample不代表完整可见。大坐标局部绑定、共面射线和binary32相机定位不成立即保留旧V1，renderer实际guard不放宽。旧V1/common/action规划和renderer函数AST保持。

完整1568方法中1567pass/1既有Win1314skip，含24新方法。真实5pair10SDKarm实际13帧（旧5/新8），3新增局部gap几何投影均96px、连续PNG核心94/95/94px，且通过独立实际camera-ray/PNG判据；25um SCENE/XY转XZ，0.4mm侧pair转XY，普通4mm与闭壳仍1图，五全景RGBA exact。15Blender+10SDK进程均exit0/wait，完整STATE_BEFORE/AFTER、FINAL_CAPTURE与即时计数均在断言前持久化，原上阶段失败不改。独审46纯组+3camera组和16实际组通过；离线MCP full/brief十投影保留新plan/方向/图片，不能当真实MCP进程验收。普通planner配对median额外约.074ms，microgap约.216ms、side约.253ms；不含validator/RPC/render，更不证明整任务加速。

本批真实矩阵首次全通过；预启动ray审图器纠错、开发期两个validator反例和独审器工作量边界建模错误全部保留。新SDK尚未固定入口安装，旧consumer不能冒认为理解innerV2；下一批先固定发布/兼容与实际MCP，再推进复杂焦点和GUI。正式模型/provider试次仍0。[报告](../verification/fixes/20261031_v21_task_gap/REPORT.md)；[合同](TASK_GAP_NATIVE_CONTRACT.md)。


2026-10-31 task-gap固定发布：7a88/78源87文件task.gap.r1已安装。私有11admin/19CLI、11roles与12零连接哨兵拒绝通过，35fixed子进程正常wait（负例预期非零）。实际fixed入口→默认Socket私有三scene（旧sealedfactory输入的新副本）交付6MCP图/4nativecall，thin正常+warmbrief各2图，ordinary与occlusion各1图；raw/public/RNA恢复及与已验SDK像素exact、0setter，3Blender+3frontend全exit0/wait。独审17兼容、47MCP、25plan、79安装后检查通过。V1/V2旧新消费者边界明确，8cap非任意V2兼容证书；旧consumer拒V2准确，新consumer接受旧V1。四文件CAS备份527d9f17bc7f4169acdaffcffd2be9da，state仅config_fingerprint，原goal历史/foreignsettings保持；fresh配置stdio7a88兼容。实际当前聊天仍被stale配置fence拒绝且无新identity，需重启再核验，不把freshstdio当热重载。生产GUI/真实新Hook未据本轮冒认。

同时准备用户明确授权公开GitHub仓库human-eye。公共干净源码85模块1493run中1480pass、13skip（10旧frozen基线、2Blender opt-in、1Win1314），原source-only首轮37个缺历史/fixture错误保留；恢复公开routingfixture后过门，不称所有197测试都无需历史。源码字节固定，Git禁止换行转换，机器状态/凭据/附件/大型验证历史不上传。正式模型试次0。[本轮报告](../verification/fixes/20261031_v21_task_gap_release/REPORT.md)。
