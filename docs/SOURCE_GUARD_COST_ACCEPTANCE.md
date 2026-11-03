# REVIEW-CYCLE-001：受控来源检查成本归因与单候选验收

日期：2026-11-03。本文是实施方的作者证据，等待管理员对话独立复审。只有[唯一主计划](PRODUCT_ROADMAP.md)决定下一批；本轮不继续优化第二热点，不切默认MCP/Hook，不改原资产、共享GUI或写入域。

## 判断

唯一小候选通过预登记的有限成本门及来源反例，建议将**125源派生版本**作为下一次发布差异复审对象。该建议不是默认激活或整体发布通过：owned生命周期p95增加4.74%，接近预先登记的5%上限，需要管理员明确评估。没有重采样、放宽门限或追加第二候选。

| 对象 | 固定版本与摘要 |
| --- | --- |
| 同版基线 | `2af8cfd`，`9.7.2+20261103.core.facts.r1`，125源 `dbeb471f3120bdb133b1ca1669dbbbd525e4679a9ec1949bc67fdba171182c47` |
| 唯一派生候选 | `9.7.2+20261103.source.guard.r1`，125源 `d9b01eec9ce561b9f9fe5304cc37c50aa641b1826ed3ee788501eb2f49192360` |
| wheel SHA256 | `044c411ffd8eb23a57eb054a61168dde8c53ee27977eceb4caf83992f963c1c4` |

只有`verified_source_loader.py`的条件化简和`runtime_identity.py`的版本声明改变；其余123个运行源与基线逐字节相同。数学、来源合同、core与外围策略、动作/图片预算均不变。旧78/124记录只用于定位，没有充当本轮125基线。

## 先归因，再测未插桩成本

使用实际已固定125源bootstrap的正常`serve`入口，独占headless QA Blender完成冷图1、热图3、文字3、状态3。没有将SDK普通导入当作受控入口。Python、Blender、Pillow/NumPy、entry/binding和加载集合摘要均记录；诊断wrapper增加的外部模块也保留在完整清单。

热观察有316个带文件的相关模块：62个owned、2个已见证alias、252个external。guard先做316次路径分类，再做64次最终执行见证路径解析，共380次；完整source check还包含另外4次解析。每次完整读取125源、3,605,379B，做125个文件SHA及1个总描述SHA，两个包目录实际`scandir`各一次。Python生成器的`call`事件含恢复，不把`Path.glob`的120个进入事件说成120次独立目录扫描。

插桩使耗时显著放大。owned首分类约10.40ms、external分类约42.77ms只是诊断值，不是预计节省，更不能与未插桩请求耗时相加。R1采集器把C事件误认成Python函数进入，失败结果保留；R2修复采集器，产品行为未改。R1异常JSON的786,833,426逻辑字节经过流式gzip和双重逻辑SHA/尺寸校验保留为41,536,994物理字节，只删除该重复原JSON。

## 唯一候选保持哪些保证

对owned且不是已许可namespace的模块，`internal`分类不能免除执行见证，因此省掉这个分类专用的首次`resolve()`。最终仍检查同一模块对象的执行见证，并重新解析实际origin、与冻结来源路径比较。名称前缀本身不能让模块通过。

| 固定加载集合中的路径检查 | 基线 | 候选 |
| --- | ---: | ---: |
| owned非namespace，首分类 | 62 | 0 |
| owned，最终fresh origin | 62 | 62 |
| witnessed alias，分类及最终origin | 4 | 4 |
| 外部绝对路径分类 | 252 | 252 |
| namespace | 原分支 | 原分支 |

实际入口的加载集合不同，不能宣称每次都省62次。没有跨请求缓存、stat成功缓存、词法前缀放行或全源hash删减。外部路径经symlink/junction指入引擎根仍会被发现。原逻辑未提供并发原子围栏；本候选也不新增此承诺。解释器和第三方依赖仍属外部信任基础，guard不是Python沙箱。

13项新测试与原source-loading/source-identity合计35项通过、零跳过。包含真实链接重定向、替换对象/路径、合法和无见证alias、relative路径、namespace异常、每次重新验证、同大小同mtime改写、增删/不可读与恢复。修改前12项语义也通过；新增计数断言在旧实现上准确多出62次解析，候选保留全部最终解析。两处新夹具转义和一次编辑脚本EOL预设错误均保留，没有降低断言或改候选假设。

另在独占完整clone外部固定entry/binding/source，完成8个诊断case和4次真实`-I -B` entry CLI。Windows junction在两次验证间重定向准确拒绝；源码启动前改写精确exit2、运行后连续检查拒绝且可恢复。4份合法mtime/size的恶意旧pyc没有执行，保留作负例。4次CLI包含预期拒绝，不代表4次exit0。该较小加载链初始18个执行见证、lazy导入后25，不冒称服务的62模块集合。不是用户Hook、真人表单或旧457/11矩阵重跑。

## 唯一未插桩AB/BA结果

原harness不改，小wrapper固定125对125的entry、binding、依赖和CONFIG独立SHA。8个AB/BA块，每版24热图、24文字、24状态、8冷首图，共160工具调用；owned另16次完整生命周期。全部原始槽位保留，零拒绝/unknown、零几何移动，全部进程正常退出。冷表示新进程，OS文件缓存未清空。既有内置trace不属于新增profiler。

门在结果前固定：文字/热图各至少6/8块改善、块内中位配对收益至少1ms；source-check至少改善1ms或5%两者较大值。请求尾部最多增加1ms或2%、status最多0.5ms或5%、冷启动/整轮/owned最多20ms或5%，均取较大值。此门不替代旧M1/M2门。

| 完整测量，毫秒 | 基线中位/p95 | 候选中位/p95 |
| --- | ---: | ---: |
| 文字间隙调用 | 80.287 / 85.540 | 74.552 / 80.892 |
| 热原生图调用 | 134.184 / 156.673 | 129.623 / 151.566 |
| 状态调用 | 5.780 / 6.168 | 5.788 / 6.206 |
| 冷服务启动 | 795.564 / 822.501 | 788.051 / 804.839 |
| 冷启动至首图 | 1236.744 / 1269.386 | 1226.822 / 1252.296 |
| 服务整轮，含关闭/记录落盘 | 2078.369 / 2126.892 | 2012.502 / 2042.607 |
| owned完整生命周期 | 1526.345 / 1548.072 | 1533.332 / 1621.508 |

主门通过。文字块内中位配对收益5.671ms、8/8块改善；热图5.295ms、7/8块改善。source-check对应块配对收益5.906/6.318ms。分组中位差只能辅助归因，不能相加或当精确因果占比。

owned中位增加6.987ms、p95增加73.436ms（4.74%）；配对delta的p95又是另一数值107.875ms。不能写成所有尾部改善或证明稳定因果。n=8时最近秩p95就是最大值，n=24时是第二大值；同进程3个热样本相关，未推统计显著性。此项近门代价显著保留，本轮到此停止，等待独立复审，不用重跑消掉它。

已有64张384 PNG组成32个配对，PNG原字节SHA与解码RGBA像素SHA全部相同；离线核对未追加渲染。没有优化`wire_encode`、更换算法或减少任何保证。整体模型任务速度、质量、token和USD没有新增测量，不推断费用为零。

## 发布目标、admin及最新状态回退

建议审核125派生，因其保留完整core显式模式、当前新管理器和全部安全修复，并在同125基线上有有限收益。原124安全版及125基线仍保留，可供管理员选择；不能依据“主门通过”自行发布。旧78仍是正式默认。

实际新安装的摘要：

- entry：`281d2c6647634940d49364123b1230b08968f6855b582c27559e14f012726ec3`
- admin：`9cb73f62e6933798150277a370e386819cf7243adb75e52f4e9c3ebcfeb685c5`
- binding：`e06c625405fdf5e423940b26a0b98fbdf4d359e33aaf4f76e2e7ae923c4c7f08`
- 原admin模板：`b371bd7d120e170c5ab0aef0e213e444dbf21c2030e5bd95b04b3dce5ba25c8a`，未修改。

用原迁移器同一逻辑在新独占QA完成78→新guard125→最新state→78的4组检查，3个合成已提交回执及预算消耗保持；过期reverse与未来schema准确拒绝。它们是账本测试，不是物理setter。QA新admin执行了受锁apply；实际原admin只做正式ROOT的doctor/plan，不能互相冒领。实际只读plan SHA `02db3f46c050a0b305f00baefa2bf6f5b9fad4a6a0acddee86521c119f96e9ff`，未apply，未来使用必须针对最新状态重验。

rollback使用已外部固定的旧78新manager kit，保留最新状态而不是旧备份。完整路径与文件摘要在本地`RELEASE_HANDOFF.json`。516个原保护文件保持SHA。仍缺正式用户接受、默认切换、重新连接身份/单次真实Hook及真人表单；任意未来schema/外部状态不兼容必须拒绝，不能删历史或退款预算。

历史证据分开：25组属于124新管理器代际；4组属于原125基线；本批新增4组属于guard125；旧457组原生/入口和11身份检查未重标为新版本执行。新owned16次、受控8+4、当前源2676公共回归各自说明范围。

## 交付与后续边界

166模块2676公共项，本地2673通过/3历史跳过，干净导出2663通过/13条件跳过；新Python源均与受测导出绑定。运行源码、wheel、隔离安装与全部测量pins一致。所有原始成本样本、profile失败及有意恶意pyc保留，不能当垃圾清掉。

本地证据根`verification/fixes/20261103_review_cycle001/`：`BEFORE.json`、`AUTHORIZATION.json`、`PROFILE_ATTRIBUTION.*`、`SINGLE_CANDIDATE_DESIGN.json`、`COST_PREREGISTRATION.json`、`COST_CONFIG_EXTERNAL_PIN.json`、`COST_R1/`、`COST_QUALIFICATION_SUMMARY.*`、`CONTROLLED_GUARD_R1/RESULT.json`、`RELEASE_HANDOFF.json`及公共回归记录。公开profile和成本wrapper可在固定环境重放；私有本机配置和第三方资产不进Git。

本批完成后按已核对的人类授权回报管理员对话，等待下一任务。建议下一项仅做发布目标差异复审，先裁定owned尾部代价，不自行调第二热点、core、外围阈值或扩域。Google/API、Key读取/生成、503重试和外部费用账本继续暂停，来源US$0.02预留不改。


## REVIEW-CYCLE-003 正式激活与入口验收

用户明确批准固定 `9.7.2+20261103.source.guard.r1`，接受owned生命周期p95增加4.74%的已披露取舍。本次125份运行源码、隔离安装、wheel、entry/admin/binding与001/002完全相同，没有性能调参、新算法、新来源或写域；既有广域测试按原身份复用，没有冒充本轮重跑。

本轮重新对正式项目运行doctor及plan，最新配置和完整状态仍与历史输入同字节，所以新计算的计划SHA仍为`02db3f46c050a0b305f00baefa2bf6f5b9fad4a6a0acddee86521c119f96e9ff`。这不是读取并应用旧保存计划。只读独立复核员从本轮BEFORE字节重构四份预期输出并核对全部SHA，然后原管理器以具体计划、setup锁和稳定state锁执行apply，交易manifest为applied/committed，recovery_required=false。

| 变更 | 实际范围 |
| --- | --- |
| 项目MCP | 仅human_eye_live参数中的固定entry路径 |
| 项目Hook | 三种事件、五组登记中相同entry路径替换；matcher/期限等不变 |
| connector | project_root与expected_identity |
| state | 唯一顶层config_fingerprint令牌；其他原始字节保持 |

Agent Learning、其他MCP服务、env、审批设置保持；全部回执、消耗预算、goal状态、现存review_required均保持。audit在提交点逐字节一致。随后正常状态/启动/失败观察trace触发现有last1000有界尾日志保留，活动日志的前5旧行共72,146字节被轮出；完整旧内容已在本轮BEFORE及AFTER_APPLY快照保留，不回写旧快照覆盖新trace。活动尾文件并非完整历史库。这个保留机制没有在本批改造。

| 验收层 | 本轮实际结果 |
| --- | --- |
| 配置落盘/交易 | 成功；四份输出SHA均与独立预期一致，setup锁正常释放，稳定sidecar锁原样保留 |
| 固定新版identity | 实际-I -B入口返回源d9与125文件，安装及依赖绑定通过 |
| 正式配置新MCP进程 | initialize、3次ping、2次status通过并正常关闭；一次只读observe明确返回BlenderMCP离线，未重试、未执行动作 |
| 当前桌面聊天MCP | 仍为旧进程；实际调用返回state_configuration_binding_mismatch并拒绝动作，需要重连后复验 |
| 独立QA Blender | 新建测试文件/独占随机端口，文字和原生图都测得4毫米；PNG384×384成功解码并目视核对；geometry/display保持，0产品setter、0源文件保存，进程正常关闭 |
| 真实Hook/用户消息/真人表单 | 未运行；不将手工stdin、QA或独立进程算作真实宿主触发 |
| 最新状态回退准备 | 受固定旧78＋新manager kit完成迁移前后doctor和新reverse plan，ready=true；未无故实际回退 |

旧78回退kit的87文件、新版142文件均与受信登记匹配；98份既有seal索引保留。回退计划只证明当时最新状态兼容，未来有任何新状态必须重新验证和计划，禁止覆盖历史state、退款或重做已提交动作。

Codex官方App Server提供`config/mcpServer/reload`协议，但本聊天工具没有暴露该调用；现有桌面服务使用stdio，另起服务不能刷新当前聊天。用户可在[Settings → MCP servers中Restart](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)，必要时完整重启Codex；[变更后的Hook定义需要审查当前hash](https://learn.chatgpt.com/docs/hooks)，在Review hooks或Settings → Hooks处理。未修改trust存储、未绕过真人审查。完成重连和Blender连接后，应由真实用户只读消息验证自动观察，再分别决定其他未验层。

垃圾盘点确认1,520文件、57,332,922字节：29个与保留源码逐字节相同的build副本，以及1个可再生pycache。递归删除命令被自动执行策略拒绝，原始原因仅为`blocked by policy`，因此实际删除为0。候选路径、SHA和保留原件已形成清单；未用其他路径重试绕过。旧stage失败记录/视觉/源码/依赖/wheel/安装元数据、证据、运行状态、回退材料均保留。

本地证据独立保存在`verification/fixes/20261103_review_cycle003/`：本轮doctor/plan/apply、独立审查、BEFORE/AFTER_APPLY、交易manifest、实际聊天拒绝、正式新进程、独立QA原生图/零setter、回退doctor/plan及清理清单。宿主重连和真实消息仍是后续验收，不宣称整个产品已发布或模型有巨大提升。Google/API/Key/外部费用账本继续暂停，来源US$0.02预留保持。


## REVIEW-CYCLE-003-RECONNECT 真实宿主验收

用户在来源聊天先回复“已经重连”，随后按实际插件面板位置启动Blender连接器，再提交真实三维只读原句。仍为原d9/125候选，原003记录作为当时结果保留，本次不重apply、不建QA、不手工调用Hook、不改trust或权限；99份既有seal索引保持。实际共享GUI只读观察由来源聊天执行，本实施聊天核对当前MCP身份和状态并独立重放来源消息/日志证据。

| 有限入口 | 本轮实际结果 |
| --- | --- |
| 当前桌面MCP | 实际status返回installed_distribution/source.guard.r1/d9/125、pins与identity匹配，无inflight/quarantine/unfinished_goal |
| 正式GUI只读 | 用户连接前1次观察provider unavailable；连接后1次MCP overview成功，Cube/#B0001世界bbox[-1,-1,-1]至[1,1,1]，无移动/保存请求 |
| 非三维真人Prompt | 两条普通消息“已经重连”“已经打开了”和一条问答分别实际dispatch后intent_unknown/skip，未读取场景 |
| 真实三维Prompt | 1/1正向：当前question_reply中的answer为“观察 Blender 当前场景中的 Cube，只观察，不移动、不保存。”，实际Hook自动observe为overview/complete |
| 工具前交付 | 原始source rollout为直接role=developer，不是工具输出中引用文字；2026-11-03上海12:35:14.313注入，早于后续首个模型工具12:35:38.268，共23.955秒；此差值是事件顺序证据，不是性能收益 |

正向消息wrapper为354字符/568 UTF8字节，SHA`79130396e27293a3648460edbf34dec7802b888232a1ce027f9fe702fe0f9b02`。独立从read_thread原始人类内容计算并匹配host_hook.prompt_input；format=codex_question_reply/extraction=answers_only，不能把问答原句当合成输入。实际trace`95e5f1ac021941198dd976138843c898`、request`9a4a88bb0d3f4e21a159d5ecc9312bdb`，request_origin=hook_command、tool_use_id=null，与直接developer消息及product observe/host_hook/request_trace三行对应。当前scene revision为`blender:45622a04ba88f0b00b49ae15c3b94115e1526677ec94b9d1ecbdba79c1da8874`，正文当前fingerprint为`6f3c828984fced67831b728d86414095e0dfaafd68c6546dc3ebeb1ff050ebfa`。

单物体只认证overview：pair unresolved/scene_overview_pair_required、execution_status=not_requested、execution_authority=false、image_count=0均保持。不能把这次成功写成正式GUI的4毫米双物体量测、图片、写入授权或整个产品发布。原003独立QA的4毫米/384图仍是其独立范围。当前addon协议7、服务器期待15的版本差异保留，本轮兼容fallback的有限读取成功不证明所有新版addon能力。

五条当前Hook命令与全局五条trusted_hash记录均已只读核对。Prompt的实际执行证明此次未被信任门拦截；未独立重构当前定义hash算法，不由旧.hook-trust或单纯登记推断所有hook受信。四个动作Pre/Post只匹配transform/clearance_segment，本轮没有对应动作调用，保持未触发/未验；真人写操作表单亦未验。官方宿主日志的generic hook/started与completed仅带targeted_connections，不能单独归因HumanEye，直接用户SHA、product事件和developer输入为本轮关联依据。

### 已确认的遥测缺陷与下一项

本次MCP与Hook实际正文均为当前Cube，但对应request_trace.annotations写入了历史场景fingerprint`d21fef06…8143d4`及2对象/16点/24面，而correlation.scene_revision是当前Cube。只读代码审查定位：overview为清旧pair而runtime.import_state，其重新校验历史router session时，_validated_scene向当前trace重复annotate；last-write-wins覆盖fingerprint/规模，返回包装仅恢复当前route.scene_revision等字段。当前最后历史session恰与旧fingerprint及2/16/24一致。

这是实证的日志元数据污染，尚未修复。实际当前正文、只读状态与工具前注入门保持成立；不能用错误annotations作当前资产来源/规模、精确成本归因，也不据此外推其他动作安全。本轮运行源码固定，记录后交来源审查，后续另做最小遥测修复及反例，不静默改日志或重标旧验收。相比原003状态，动作sessions、goal_segments、消耗预算、quarantine和inflight保持；新增读取仅更新router观察缓存。

本次证据位于独立兄弟目录`verification/fixes/20261103_review_cycle003_reconnect/`，含实际桌面status、真实来源消息、正负Prompt、直接developer注入及首个后续工具原始行、输入SHA绑定、当前Hook定义/信任记录、遥测限制、最终state与seal。原003封存未追加。Google/API/key/付费试验仍暂停，来源US$0.02预留不变；垃圾清理仍为策略拒绝后的0删除，没有绕过。


## REVIEW-CYCLE-004 请求场景遥测修复候选

来源复核003-RECONNECT三项有限入口通过后，按既有持续修复授权仅派发P2最小修复。正式d9/配置/trust/用户GUI不变；新候选`9.7.2+20261103.scene.trace.r1`，revision`v21-scene-trace-owner-20261103`，125源`a045a800256f4767271308d239c735177f992ce3408d927d42bde5f1d4b60d8f`。运行源只改auto_router、scene_delta和revision三个文件。

_validated_scene新增内部_annotate_scene选项，默认True保持原当前捕获行为。只有router导入历史场景与scene_delta规范化detached target/base传False；False仅绕过最后场景revision、fingerprint和对象/点/面计数写入，不关闭完整校验、规范化、哈希、scene.validate/hash span或错误。增量传输也会先校验当前再旧base，是同一根因的第二覆盖路径；没有改复制、架构、缓存、精度或性能门。

公共反例放在既有test_production_service_telemetry.RequestSceneOwnershipTests：先合法双盒历史2/16/24，再切临时host当前单盒1/8/12。oracle用夹具原始规范JSON SHA与原数组计数，不调用生产验证器或trace构造答案。冻结最终11项在旧代码9失败2通过，MCP/模拟Hook正文原本正确而trace旧指纹；修复后相同11项全过。另覆盖16历史、正常pair、status无捕获、捕获失败、无效当前场景、取得有效捕获后的查询拒绝、旧base delta、坏历史指纹、真实router.before_action产生的非空pending保留，以及validate/hash计时。

早期测试R2中单位错误预期文本与“preview会持久化pending”的测试夹具假设错误已保留；修正夹具后冻结R3，未把这两项当产品缺陷或放宽生产判据。最终R3的9失败均是当前场景注解被旧值覆盖/未知被伪填；2正常对照通过。11项不单独宣称覆盖真实committed预算，另使用冻结真实账本副本及既有安全回归。

11个相关模块共234项本地通过，无skip（已包含新增11项，不能再相加）；干净公开副本同样234项全过，无skip，包含production-service/live-service/telemetry-runtime/image-trace/live-hooks/telemetry/router/host-runtime/verified-source/goal-segment-telemetry/scene-delta。保留原动作不确定、日志失败不可重试、来源约束、数值和碰撞门；不机械重跑旧广域或真人写表单。干净公共副本结果与最终wheel/隔离安装pins见本轮封存记录，分开记账。

实际新固定-I -B入口连接自建后台Blender独占随机端口，对冻结的真实16历史会话及账本副本分别执行MCP和--probe Hook；该Hook明确为manual_probe，不能算真人宿主新版本验收。两条实际路径均正文/trace当前revision与fingerprint一致、1对象/8点/12面；当前Cube bbox±1，0产品setter、未保存源文件，场景/显示还原，所有子进程正常关闭。完整动作sessions、goal_segments及预算与原副本一致，router历史scene/fingerprint/pending和16个ID保持，仅可过期观察/场景缓存更新。

QA首轮checker误从observation内部读取顶层scene_capabilities的fingerprint，产品两个原始响应本已正确；改checker后离线重验原记录通过，再于独立QA_R2完整运行两路径通过，旧失败保留。QA_R2的MCP完整生命周期1034.029ms、模拟Hook1005.352ms，provider启动到关闭2703.542ms；外层等待进程并落盘的完整wall另存QA_R2_PARENT。只有单次正确性调用，不构成性能比较或模型耗时收益。

当前正式旧d9固定manager对独占候选QA最新完整状态执行doctor/plan，ready=true，reverse计划SHA`3b7e7a1a9b578103773325f46cfe13bb1ed1b4d8fbb174138014e3d263fc628d`；未apply或实际回退。最初QA目录未位于.human-eye、第二次缺注册expected_identity均按预期拒绝，修正隔离测试注册后成功，原错误记录保留。当前正式配置/状态没有迁移，未来任何状态变化仍需重新生成计划，不能复用这份QA计划。

独立只读审查确认最小diff未弱化任何验证，计时保留、oracle独立、11项旧失败准确；作者实际运行与独立审查分栏。范围仅本次MCP/Prompt观察、历史restore与detached delta。OwnedScheduler._discover仍可能在外部场景变化拒绝动作时重验较早envelope而覆写外层遥测，未扩修或认证；不能宣称已建立所有Python helper的通用当前场景ownership。

本批独立证据根`verification/fixes/20261103_review_cycle004/`保留旧反例/夹具错误、候选回归、BUILD/安装/实际QA、原始帧/Hook、冻结账本、正常关闭/完整成本、兼容计划和保护清单。旧seal、003真实输入/旧错误trace全部原样保留。候选可以交来源复核，正式默认不切；Google/API/Key/503/外部账本仍暂停，来源US$0.02不改，垃圾删除审批拒绝不绕过。


## REVIEW-CYCLE-005 正式激活 scene.trace.r1

004及追加勘误经来源独立复核后，用户最新明确更正为“批准安装新版本”，覆盖误选保留候选；本批只激活已验收的scene.trace.r1/a045。Git基线001743bb、125执行源、原安装、entry dcdbb830…93ae、admin b09c84ef…65e7、binding3f4671ae…9d3e、wheelf3cbc8b3…7258保持，不重包或改源码。004摘要错误entry保留，使用追加勘误和实际target_runtime_entry作为依据。

先归档最新完整正式state142362B/config/audit/锁，保存原d9及旧78回退材料校验。真实新entry以-I -B运行doctor/plan，明确钉住旧d9 entry281d2c66…26ec3与旧build；旧d9 manager也先实际只读验证当前状态。新计划SHA`675720c75efd78d50e1768e97073ad77bdd166a7d96582183dca59d95198a52d`，只读复核员不调用build_plan，直接由BEFORE字节重构四份after并逐SHA匹配，再由根唯一写入者受setup/stable-state锁apply。

四份实际after与独立预期一致，manifest为applied/committed/recovery_required=false：

- 默认human_eye_live参数中一处目标entry替换；其余MCP、AL、env、权限不变。
- 三事件五组Hook只替换entry，matcher/timeout等保持；不自行改平台trust存储。
- connector只改project_root/expected_identity。
- state只改唯一顶层config_fingerprint令牌，原动作sessions/goal_segments/所有预算回执、unknown/pending/review_required字节保持。

活动audit本身有既有last1000保留策略。BEFORE到提交后快照间的一次正常旧进程status使活动日志轮出1旧行、留下1000旧行并新增1trace；原完整日志已归档，不把这个保留动作说成迁移丢失账本或最终活动前缀完全相同。事务本身没有audit写入。102份旧seal索引保持。

| 本轮实际层 | 结果 |
| --- | --- |
| 目标落盘 | 受锁成功，具体计划及四输出匹配；备份manifest正常提交，稳定锁保留 |
| 新固定identity | actual target_runtime_entry.py返回a045/125/installed_distribution及固定入口绑定 |
| 正式config独立新MCP | initialize、3ping、2status、1次真实GUI overview，7帧均正常，退出0；关闭174.555ms |
| 当前观察与遥测 | Cube bbox±1；独立重建内容寻址完整mesh，canonical SHA与正文/trace一致，1对象/8点/12三角面，不再出现历史2/16/24 |
| 观察语义 | observation complete，execution not_requested，0图/0移动保存命令，无双物体量测或动作授权 |
| 当前桌面MCP | 实际仍持旧d9配置，返回state_configuration_binding_mismatch/stale_configuration_snapshot，disk与state匹配、allow_action=false、automatic_retry=false |
| 新版真实Hook | 尚无a045宿主事件；本轮批准消息是旧d9实际Prompt正确skip，不借003旧真人或004模拟结果标新版本通过 |
| 最新逆向兼容 | oldd9固定manager对最新正式state doctor ready=true，逆planSHA266f49f8d1bbe17563513cd048c5fb5aee692af869a96620a0408715806377e2，未apply |

新观察trace`d2aa997557bc4bf6a6e82d0a97c8807d`、request`43a90214c4ee4807bb660784d238078e`。从保存scene_memory的frame/object/geometry blobs直接重建完整当前scene，独立canonical JSON＋SHA为`6f3c828984fced67831b728d86414095e0dfaafd68c6546dc3ebeb1ff050ebfa`，revision为`blender:45622a04ba88f0b00b49ae15c3b94115e1526677ec94b9d1ecbdba79c1da8874`。不调用生产_validated_scene生成答案。MCP观测单次约134.801ms只是一次请求，不与旧版比较，不当作整任务/模型收益。

当前宿主工具没有reload/reconnect入口，实际桌面app-server为stdio且无可用控制socket；官方存在config/mcpServer/reload协议不等于本聊天能调用，另起server不能刷新当前连接。最短剩余操作是重连human_eye_live或完整重启Codex，随后核对真实新身份、state健康和实际Hook。新Hook定义已指a045，五条持久trusted_hash仍是旧记录，未拿到新定义计算hash，不能先验认定受信或未受信；只有平台界面提示时审查变更后的HumanEye定义。已有升级批准无需重复。

所有独立部分完成后回来源复核；若还需宿主动作，只报告具体剩余层。004同源码234本地/干净与两隔离路径证据复用，未机械重跑。OwnedScheduler外层旧envelope限制、四动作Hook、真人写表单、正式GUI图片/双物体与整体模型价值未扩验。Google/API/Key/503/费用账本继续暂停，来源US$0.02预留保持；垃圾删除仍为0。

本轮证据独立在`verification/fixes/20261103_review_cycle005/`，包括批准更正、全最新快照/锁、具体doctor/plan/apply/backup、独立复核、实际旧桌面拒绝、正式新进程原始帧与重建当前scene/trace、最新回退plan和最终保留记录。回退计划只对应当时最新状态，未来必须重验，不能恢复旧state、退款或重做committed动作。
