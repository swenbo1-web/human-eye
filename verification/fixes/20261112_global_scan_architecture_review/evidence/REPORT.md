# 非指向性任务既有实测：只读证据审查

日期：2026-11-12。范围：`D:/hefe/docs`、定向定位的 `verification/fixes` 记录及实施树 `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe` 的已存材料。实施树 HEAD 本次实际读取为 `a44a6138b9d354ecc98a4fbd76095f0536d6973f`。未运行产品、Blender、模型、API、几何测试或旧评分器；未改产品、默认配置、资产、Git 或实施者文件；只新增本报告。当前凹槽资格任务不受此建议影响。

本审查采用 learning-worker，子 assignment 只读父任务；没有写父任务状态。证据搜索发生过一次过宽的 Markdown 递归输出截断，之后改为文档索引和明确文件，不以截断输出作结论，也未扫描全目录 JSON。

## 1. 结论

**当前最明确的收益是已给定对象集合后的空间事实消费；无指定目标、要求发现全部异常的整场观察尚缺正式端到端验收。** 这不等于所有“全场”任务都没有进步：M1 的给定目标、遍历其余候选的 nearest 已有正确消费和正收益。必须分开三个范围：

1. **指定对象对/候选集合**：任务预先告诉模型 Target 和三名邻件，插件把已实现的求解变成可直接回答的事实。最新 M4 属于这一类。
2. **指定目标、未知邻件**：任务告诉目标名，要求它与场景其余对象的全局最近距离。COMPLEX-005 discovery 和 M1 T2/T3 属于这一类；后者改善了入口与依据交付。
3. **未知目标、全场发现**：任务不给目标/问题数量，要求发现全部相关异常并交代未检查范围。28 网格 M4 有目标选择，但仍给了精确位置条件和三个邻件角色；它不是全部对象对的异常普查。上述记录都不能替代第 3 类召回验收。

旧负收益和新正收益必须保留各自任务版本。20261103 AB001 用 ultra、严格引用输出合同、逐 SDK 冷启动和单样本；20261111/12 M4 使用 medium、新交付合同/入口、三次重复。不能把 721 秒到 29 秒直接称作同题产品加速，也不能把不同批次的 48 秒到 67 秒称作性能退化。

## 2. 本轮核实了什么，哪些仍是历史报告

本轮直接读取并核实：实际冻结题面、模型/预算配置文件、明确文件中的样本汇总、实施树 HEAD；对 COMPLEX-005 已存质量成本 join 的各组 `input_tokens.observed_sum + output_tokens.observed_sum` 进行算术复算；从 D48 已存几何 JSON 数组计数得到 **48 对象、1536 顶点、2880 三角面**。首次计数字段误用了不存在的 `vertices` 得到 0，已按文件实际 `vertices_local/vertices_world` 修正，两者都是1536；没有改输入文件。

本轮没有从 Blender 重新取几何、重新判断任何答案或重新验证全部归档摘要。因此下文“正确率”“独立真值/调用内容已审核”等是**既有作者运行及既有独立复核报告**，不是本轮新增质量样本。已存 join 与根复核文档相符，不等于本轮完成了原始逐事件再审。

## 3. 实验脉络与可比结果

### 3.1 20261103 AB001：图像辅助选目标，旧完整流程负收益

原题要求从四个同形框架中按三个空间条件选出目标，再识别三邻件并分类、给出局部依据。共同初图 1 张，无新局部图；28 mesh/32 对象。旧候选 `56ed427`，两路实际暴露 `gpt-6.1-sol/ultra`，每路一个新消费者。

| 已存结果 | 原生 A | 引擎辅助 B |
|---|---:|---:|
| 完整墙钟，含准备/失败 | 547.556 s | 721.432 s |
| 目标/关系正确 | 1/1、3/3 | 1/1、3/3 |
| 人工有效局部依据 | 3/3 | 3/3 |
| 顶层工具调用 | 8 | 23 |
| input+output，实际累计 | 407000 | 1459044 |
| 工具文字字节 | 121176 | 211734 |

引擎辅助路线包括 4 个 SDK owned-worker 尝试（2 成功）、编码 bootstrap 失败和原生补查；冻结自动引用匹配为 0/3，但人工几何证据为 3/3。它说明整条交付链额外工序可吞掉求解价值，不能把全部慢因归给几何算法。旧记录没有显示质量或效率优势。

证据：

- [RUN_CONTRACT.json](D:/hefe/verification/fixes/20261103_spatial_perception_ab001/admin/RUN_CONTRACT.json:14)：旧模型继承条件及单场景范围；`:56` 固定产品。
- [SUMMARY.txt](D:/hefe/verification/fixes/20261103_spatial_perception_ab001/admin/SUMMARY.txt:5)：成本、质量、调用；`:20` 失败尝试；`:24` 归因限制；`:25` ultra。
- [RESULTS_ANONYMOUS.json](D:/hefe/verification/fixes/20261103_spatial_perception_ab001/admin/RESULTS_ANONYMOUS.json:1)：本轮实际读取 lane_results A/B 的模型上下文及宿主 usage，与摘要相符。
- [PERF000_NATIVE_WORKFLOW_AUDIT.md](D:/hefe/docs/PERF000_NATIVE_WORKFLOW_AUDIT.md:99)：既有后续审计保留 AB001 负收益且禁止移作新候选成绩。

### 3.2 COMPLEX-005：48 对象 nearest 没有被插件实际解决

冻结题面是“**以名为 Target 的网格为目标，在其余全部网格找三维表面距离最小对象**”，要求 1e-6 m 精度和候选覆盖；它没有预选邻件，但已经指定目标。48 对象/47 候选，低面数合成场景。请求 `gpt-6.1-sol/medium`，图像 0；N 为原生，H 为实际旧安装 `9.7.2+20261103.scene.trace.r1`/125 源，C 为当时 `df016079`/137 源；每题每组 3 次。

| 同批任务 | 路线 | 正确 | 完整格中位 s | input+output 合计 | Native / observe 调用 |
|---|---|---:|---:|---:|---:|
| 指定旋转带孔装配 | N | 3/3 | 96.0695 | 146765 | 12 / 0 |
| 指定旋转带孔装配 | H | 3/3 | 84.3781 | 116089 | 9 / 0 |
| 指定旋转带孔装配 | C | 3/3 | 55.7478 | 78250 | 2 / 5 |
| Target 全场最近 | N | 3/3 | 103.4952 | 174209 | 13 / 0 |
| Target 全场最近 | H | 3/3 | 91.4130 | 122071 | 10 / 0 |
| Target 全场最近 | C | 2/3 | 78.0390 | 87777 | 7 / 1 |

九个 nearest 会话最终全部走模型自编原生代码。C 唯一 observe 在第18格因缺 session_id 被拒，随后原生答对；错误第07格没有调用插件，原生把 Near_017 伪交点误判零距离，既有独立真值为 Peer_000 约3毫米。五次初始伪交点中四次自纠、一次保留。9/9 遍历47候选，但只有8/9真正解对。**遍历完整不等于几何正确；C更短的时间/token不能作为质量保持的收益，更不能当插件求解性能。** H六格正式会话均未使用插件，H/N差值也不是旧引擎算法收益。

这批的“指定题强、未知邻件题弱”首要证据是有效入口/自然采用与回退计算，而非“非指向几何算子本身慢”。工具 schema 较难调用只是有证据的机制之一，不足以把所有差额归因给一次错误。

证据：

- [PROMPT_DISCOVERY.txt](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/native_plugin_complex_004/PROMPT_DISCOVERY.txt:3)：实际固定问题；005 PLAN直接绑定此文件。
- [005 PLAN.json](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/native_plugin_complex_005/PLAN.json:115)：模型与预算；`:138` discovery资产和提示绑定。
- [005 REPORT.md](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/native_plugin_complex_005/REPORT.md:31)：质量/完整时间；`:42` 调用；`:51` 失败机制；`:73` 规模与外推边界。
- [FINAL_QUALITY_COST.md](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/native_plugin_complex_005/private/FINAL_QUALITY_COST.md:18)：伪交点与遍历/有效解决的区分。
- [FINAL_QUALITY_COST.json](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/native_plugin_complex_005/private/FINAL_QUALITY_COST.json:10917)：本轮直接读取 discovery 三组全样本 usage 并复算；N input/output行11270/11312，H行12138/12180，C行13006/13048。不是只取成功子集。
- [D48.json](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/scale_diag_001/fixtures/D48.json:1)：本轮只读数组计数。

### 3.3 M1：给定目标 nearest 已有后续正收益，不能略去

`7411ac7`固定产品、三道题×N/C/S各3次，共27格，均请求 sol/medium。N普通原生、C普通接口、S同一求解内核的精简任务入口。T1给三个候选；T2给非凸目标名字、8候选；T3给开放表面目标名字、5候选。没有图像。

| 完整任务中位 s | N | C | S |
|---|---:|---:|---:|
| T1三候选 | 80.742 | 27.619 | 24.545 |
| T2非凸目标全场最近 | 77.931 | 82.831 | 36.856 |
| T3开放表面全场最近 | 71.549 | 72.232 | 33.706 |

既有独立质量27/27正确。各组9格 input+output 为265250/393912/146861；调用为29/36/15，C错误10次、S零错误。S首次有效和最终采用均9/9、原生调用0。此前005的“插件未被实际用来解全场nearest”已有有限后续修复证据，不能继续写作当前所有入口均失败。

S六个T2/T3仍在 complete nearest后再问一次关系，主要为已计算却未交付的见证；不是重新求全局最近。后续 nearest-evidence候选据此补第一次结果的必要依据。该收益仍未证明全场无目标发现、所有异常召回或视觉取景。

证据：[M1正式复核](D:/hefe/docs/M1_TASK_ENTRY_001_FORMAL_REVIEW.md:9)、[每题时间与采用](D:/hefe/docs/M1_TASK_ENTRY_001_FORMAL_REVIEW.md:23)、[二次取证](D:/hefe/docs/M1_TASK_ENTRY_001_FORMAL_REVIEW.md:41)、[TASKS.json](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001_eval/TASKS.json:72)、[T2实际提示](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001_eval/tasks/T2/PROMPT.txt:1)。费用未暴露；S未缓存input仅比N少约1%，不能把总token降幅当费用降幅。

### 3.4 M4含目标发现的完整观察：最近一次仍有净收益缺口

复用28网格设备场景，但新合同移除旧AB001强制JSON、SHA手抄与引用拼写。共同初图真实经CLI输入；未新增图片，不能据此认定模型视觉使用或主动扫视。

| 批次；每路线3格 | 完整正确 | 完整中位 s | input+output合计 | 调用 |
|---|---|---|---|---|
| BASELINE N / P | 各3/3 | 52.6611 / 53.7364 | 140862 / 177907 | 7 / 9 |
| LOCAL N / P0 / P1 | 各3/3 | 48.3034 / 48.9575 / 47.4155 | 143762 / 172454 / 172370 | 7 / 9 / 9 |
| SELECTED N / P / G | 各3/3 | 75.947 / 73.746 / 67.174 | 147942 / 167637 / 157270 | 7 / 9 / 7 |

三行是不同批次，不能跨行相减推版本效果。最新 SELECTED 的G相对本批N时间−11.55%、token+6.31%，净收益未过门；相对P时间−8.91%、token−6.18%，未达预定至少一项10%门。G确实少了同集合形状补查、三格均自然采用，但更大单次交付和schema成本同时存在。

真实步骤解释了为何弱于指定对象题：所有baseline先原生读取全28对象范围/中心，由模型筛目标和邻件，再问插件关系，再原生补框架孔形/参照形态；P1局部交叉见证只填一个信息缺口，未替代整体孔形与参照。G把56顶点/100三角与关系同次交付，调用9→7，但N也是7，G工具字节比N多49.52%。已有事实被信任和采用；“模型不信任所以完全重算”不是这批的主要解释。

G owner工具执行合计0.618805秒，只占完整201.185718秒约0.308%；这是本轨迹的局部优化上界，不能把其余时间全叫模型推理，也不能泛化到大场景算子。当前最缺的是少做完整流程中的工作，而非继续在此题追毫秒。

证据：[实际新TASK.txt](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_observation_baseline_001/input/TASK.txt:5)（三位置条件、三个角色；并非全场问题普查）；[BASELINE复核](D:/hefe/docs/M4_OBSERVATION_BASELINE_001_REVIEW.md:19)、[调用阶段](D:/hefe/docs/M4_OBSERVATION_BASELINE_001_REVIEW.md:49)；[LOCAL复核](D:/hefe/docs/M4_LOCAL_RELATION_CONSUMPTION_001_REVIEW.md:11)、[实际机制](D:/hefe/docs/M4_LOCAL_RELATION_CONSUMPTION_001_REVIEW.md:25)；[SELECTED复核](D:/hefe/docs/M4_SELECTED_GEOMETRY_CONSUMPTION_001_REVIEW.md:15)、[采用及载荷](D:/hefe/docs/M4_SELECTED_GEOMETRY_CONSUMPTION_001_REVIEW.md:38)、[局部时间](D:/hefe/docs/M4_SELECTED_GEOMETRY_CONSUMPTION_001_REVIEW.md:46)。

### 3.5 最新 M4 −57.93% / −45.01%：真实有限收益，题目明确给三对

产品固定 `e836e03f`、137源；题面明确 Target、Peer_000、Competing_001、Near_003，要求三对分离/距离/见证/4毫米判断及**仅此三候选最近者**。请求sol/medium、零图像；资格资产为保留原12对象的G508加两个简单控制，重点Target/Peer每个508三角面，任务仍不要求从14对象发现全部问题。

N/P各3/3正确；完整中位68.825/28.952秒，input+output累计91958/50567，尝试8/4（P含一次错误）。P三格原生调用和原生重算0，直接自然使用空间事实。P局部handler反而更慢（合计11.1823 vs 2.2603秒），所以收益来自用已有求解替代模型写代码/补证的整题工作，不能声称内核快58%。

证据：[正式题面](D:/hefe/docs/M4_SPATIAL_FACT_CONSUMPTION_001_PLAN.md:22)、[G508资产范围](D:/hefe/docs/SPATIAL_TASK_QUALIFICATION_001_PLAN.md:29)、[最新正式复核](D:/hefe/docs/M4_SPATIAL_FACT_CONSUMPTION_001_REVIEW.md:17)、[自然消费和局部成本](D:/hefe/docs/M4_SPATIAL_FACT_CONSUMPTION_001_REVIEW.md:34)。这些属于已封存实验的独立复核结论；本审未再次运行。

## 4. 对两份用户优化方案的证据校正

只读查阅 `D:/下载/CODEX_HOOK_OPTIMIZATION_PLAN.md` 和 `PERF010_V21_OPTIMIZATION_PLAN.md`。这两份是建议/预测来源，不是执行授权或新增实测。

- CODEX_HOOK方案51/57/105/228行的18–28秒、首轮将开放题转指定题、55%–70%提速是预期，现有消费结果没有验证这套Hook链。
- 其126行把005的参数拒绝与原生伪交点并列，可作问题线索，但不能写成同一失败链：005错误格07根本没调插件；唯一discovery参数拒绝在最终答对的18格。
- AABB重叠只能产生待精测候选，不能表示“物体穿在一起”；Top-K邻接可以帮助排序，不能保证全部异常召回。不应靠把开放问题截成K对来宣布已完成原问题。
- PERF010方案P0任务入口方向得到M1支持；其中局部性能估计不能覆盖未测的全场发现、视觉或完整费用。当前目标应是一条有覆盖证明的发现→精测→必要证据路径，Hook只是未来交付入口之一。

## 5. 当前真正缺少的全场证据

1. **缺无目标、未知问题数的召回分母**：已有nearest覆盖是围绕一个目标的候选覆盖；已有28对象任务是条件选一个目标+三个角色。尚未见固定当前产品对全场全部相关关系的漏检率、误报率和unknown率。
2. **缺候选发现的端到端归因**：原生目录+模型筛选不能记为插件发现；目录快也不自动意味着发现成本快。需记录目录构建、候选剪枝/覆盖、实际精测和最终报告分别做了什么。
3. **缺扫描完整与输出完整的区分**：输出分页/Top-K不能把未检查对象当安全。未知或域外对象必须进入覆盖账本，影响结论范围。
4. **缺主动视觉验收**：一张共同初图不证明可见性、局部取景、遮挡解消、模糊或扫视收益；最新三对题零图片。几何异常普查与视觉可读性应该分开判定。
5. **缺跨编辑增量的完整收益**：本组静态一次任务不能证明留存/增量有效，尤其不能证明隐去changed对象后仍无漏检。
6. **成本仍有未知**：美元/provider重试/真实resolved模型、图片token和协调审核总成本未完整取得；部分批次thin EXIT未知。不能以文字字节替token、以launcher退出替全部PID退出或把准备成本记零。

## 6. 最有价值的下一项验收设计（建议，不启动）

在当前凹槽资格任务按原目标结束以后，最有信息量的独立验收是**固定一个未见的整场检修任务，给条件而不给对象名、问题数或候选上限，要求找全该范围内的异常关系**。不是再把三对题换几个名字，也不是“找前三个问题”。

任务先明确可评判的语义，例如“列出指定装配区域所有实体穿插和低于给定允许间隙的对象对；分别定位并解释；列出无法判断的范围”。区域/容差属于用户目标，不能由插件内部Top-K替代。原生允许同样的批量读取、BVH、解析捷径和合理缓存；插件组自然选工具，不强迫路线。固定当前产品/资产/题面/原生能力/实际工具目录，同模型同effort，预先冻结顺序和重复数，不以试答后换题争取获胜。

**真值和漏检**：独立于生产求解建立全体eligible对象/对象对的身份清单及几何真值。覆盖正例、阴性近邻和域外项，包含遮挡、小特征、凸包重叠但实体分离、并列最近、局部高密度，以及排序靠后/远离显著大物体的异常。不给模型真值数量。分别计算候选阶段召回、最终异常召回、误报、定位正确率、unknown覆盖和无依据“全场完成”次数。分母为全体真值异常，不能是工具返回的候选；unknown对真实异常计未检出，同时单列诚实程度。若扫描中止，返回未检查集合/范围并将完整任务记incomplete，不能用返回前K项绕过分母。

**完整成本**：从任务相关首次预取/Hook/启动开始计到答案和真实关闭；同时报告prompt→final。目录/索引构建、候选过滤、精测、证据投影、图片、所有失败/回退/分页、前置注入及上下文token全部入账。工具尝试、物理RPC、采集对象/顶点/面数、传输及模型可见字节、input/cached/output/reasoning、可得CPU/RSS和关闭记录分别保存；嵌套跨度不相加，未知费用不估算。准备/安装/预检/审核成本另外完整列账，不静默摊薄。

**验收顺序**：先对固定输入做一次无模型链路资格核对，确认当前公开入口能表达完整范围，并交出覆盖/unknown而非只给样例对。只有资格成立，才运行一次冻结消费者对照；先封存匿名质量及漏检，再揭成本。质量未保持时，较快完成不能记净收益。资源限制可以存在，但不能变成题目只查前K项的成功条件。单场景重复只用于观察波动，仍不宣称广泛泛化。

这一设计能直接回答架构问题：轻量全场目录与完整候选覆盖是否真正减少模型筛选、重复采集和补查，并让精测与必要局部证据在同次结果中完成；若失败，能定位到漏候选、支持域、入口、证据或完整成本的一个接点。没有证据前，不用新Hook、训练或额外模块替代这项验收。
