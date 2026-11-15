# M6-IMAGE-CORRESPONDENCE-005 实施与实际修复报告

2026-11-16。固定起点 `6ed6c88e2ae91d08cff1e80fed436d2e3572bf77`，固定合同为 `b6a03e79807b494352eca71fd44dec9204780ecd`。新增实施与证据位于 `verification/m6_image_correspondence_005/`。固定提交身份、完整清单核验与一次完成回报收据保存在提交后生成的HANDOFF。

## 分层结果

对应组件在本开发样本上达到69点评估预算的点与面积召回目标，TP47、FP22、FN0，精确率68.1159%，点召回和面积召回均100%。四个实际消费者完成提交、保存、新进程回读和保存版本预览，技术QA全部通过。实际恢复质量为1/4通过，第二阶段native通过三项最低判据。v1 facts因支持改善不足及正常点误改失败，v2 facts因正常点误改失败。

| 会话 | 支持47 RMSE，mm | 支持下降 | 410 RMSE，mm | 正常227 RMS，mm | TP / FP / FN | 独立恢复质量 |
|---|---:|---:|---:|---:|---|---|
| v1 native | 1.574921697 | 7.231282% | 0.533390835 | 0.017508763 | 35 / 5 / 12 | fail |
| v1 facts | 1.349074685 | 20.534507% | 0.473061419 | 0.165433561 | 44 / 19 / 3 | fail |
| v2 facts | 0.947751193 | 44.173946% | 0.386841157 | 0.290358839 | 47 / 60 / 0 | fail |
| v2 native | 1.160301545 | 31.653944% | 0.397320537 | 0.079867591 | 45 / 26 / 2 | pass |

三项最低判据为47点支持域RMSE下降至少30%、410点域RMSE严格下降、227个正常可编辑点误改RMS≤0.10mm。第二阶段facts支持域下降44.1739%，正常点误改RMS为0.290359mm。第二阶段native支持域下降31.6539%，正常点误改RMS为0.079868mm。连续误差、正常影响和侧深度测量分别保留。[实际保存独立评分](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/FINAL_VERIFICATION.json)

唯一优化新增逐目标局部支撑引用。facts实际读取并试算这些集合，最终转用216点共享支撑的全局quadric和Laplacian扩散。native自行从共享PNG及几何计算，最终使用自选69点共享支撑。当前证据支持模块规则与接口成立，逐目标扩展的最终恢复收益归因仍不足。该扩展保持实验候选状态，同质量成本收益保持未测。[优化判断](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/OPTIMIZATION_RESULT.json)

## 固定数据和实际保存来源

沿用004去格点样本的同一正常目标、受损模型、410/274域、47/227/363评价分母、八张PNG、相机及6.8936608558mm单次/累计预算。27,304个源顶点、29,073个原生多边形和53,264个派生三角形保持。正常和受损blend、公开初态、评分目标及控制载荷按004固定MANIFEST身份复制，两个blend另由新Blender进程fresh读回，全部数组逐字段dtype/shape/bytes一致。初态包SHA256为 `755a1cbba7595a1e5ab6263eebc8c8002336ba63a71d54e592a648ea06aa0e19`。

评分目标继续取004共享扰动后新正常模型的实际保存回读。004实际正常变化RMS约0.122135mm、最大0.202824mm，其原始构造记录通过固定来源绑定保留。005八张输入PNG复用原实际渲染字节，IMAGE_BINDING逐项绑定004原始render receipt/run及新复制blend的相同SHA。新输入状态核验产生2次真实Bpy读取，输入PNG复制产生0次新渲染。[模型与初态身份](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/CASE_BINDING.json) · [图像实际来源](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/IMAGE_BINDING.json)

公开输入16字段只含当前受损几何、源ID/拓扑、矩阵、域、边界和由实际受损几何重建的n0。正常3D、标签和评分目标由控制/评分端持有。四个独立会话从相同version0副本起步，顺序为v1 native→facts、v2 facts→native。阶段内统一冻结运行源、任务与输入，独立真值评分在各阶段两会话终态后执行。四份PROMPT的SHA256相同，前缀为 `e573dce0`。[计划](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/PLAN.json) · [共同输入冻结](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/PLAN_FREEZE.json)

## 对应规则、像素见证与分母

固定采用三张局部匹配视图的RGB最大通道绝对差，能量为max(diff−2DN,0)。以完整当前显示mesh在像素中心建立最近三角zbuffer，按关联三角可见像素面积归一汇总源点信号，三视角取最大，分数相同按sourceID升序排序。前69个I点作为活动核心摘要，实际写域为I274。

| 源点分母 | 数量 |
|---|---:|
| 全部源点 / F / I | 27304 / 410 / 274 |
| 完整受损支持 / 支持中关联面可见 | 47 / 47 |
| I中关联面拥有可见像素面积 | 234 |
| I中正注意力 / 全mesh正注意力 | 77 / 94 |
| I外正注意力 | 17 |
| core / 外围支撑 / 过渡 / 未观测I点 | 69 / 209 / 29 / 40 |
| core TP / FP / FN | 47 / 22 / 0 |
| 47点当前lumped面积，m² | 0.001741589048835909 |

完整mesh正注意力94点进入拟合排除，覆盖I外邻点。外围支撑为可观测、注意力为零、距任一core点32mm以内的源点，排除core及正注意力集合。评分端核对209点外围池受损污染为0。核心、低差异外围支撑、过渡与未观测引用均绑定session/version/geometry/PNG/camera，另给全mesh排除引用。完整数组经NPZ/Python读取，默认focus给核心、外围和完整排除的可读packet，过渡与未观测可resolve。[模块评分及完整集合](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/CORRESPONDENCE_SCORE.json)

| 局部视图，每图409600像素 | 当前mesh映射 | diff>2DN | 差异且无当前mesh | 差异且映射F关联面外 | 差异且近三角边界 |
|---|---:|---:|---:|---:|---:|
| 正面 | 184359 | 5225 | 17 | 0 | 592 |
| 侧面 | 202892 | 3765 | 0 | 311 | 422 |
| 45度 | 232778 | 5148 | 5 | 0 | 595 |

近边界按重心坐标最小值≤0.02标记，对应几何边缘及渲染抗锯齿混合的观察范围。三视图深度平局事件均0。逐像素face、polygon、sourceIDs、深度、覆盖次数及信号见证保存在基线ARRAYS。`incident_face_visible`记录关联面可见像素面积，顶点自身可见性由独立射线单列。

独立实现使用完整mesh的Möller–Trumbore射线计算。固定每视图11×11像素中心，共363条，全部face owner、triangle/polygon/sourceID、深度和重投影见证通过。179条有mesh命中，均存在被遮挡的后续交点。另取51条固定顶点投影射线，26点自身可见。射线按提供的2×3投影仿射零空间构造，用camera背轴定向，最大重投影误差5.68e−13px，最大深度差1.18e−15m。camera背轴与仿射零空间单位向量差最高4.70e−8，属于实际元数据浮点观察。[独立射线与可见性预检](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/RAY_PREFLIGHT.json)

## 首版实际求解与唯一优化

v1 native读取匹配像素和相机，自建投影差异及椭圆选区，采用X(Y,Z)四次多项式，46个共享拟合支撑中含2个受损点、15个模块正注意力点。47个目标拟合后实际修改40点，沿+X，最大位移5.78994mm。峰值24205估X幅5.387125mm，该轴真实需求3.234352mm。

v1 facts实际读取core69、outer209、完整排除94引用，79个实际共享支撑均为正常点，正注意力交集0。最终thin-plate加二次约束拟合系统rank85、条件数约66172，所有63个目标复用同一支撑池。峰值最远支撑61.911mm、支撑法向与声明拟合轴的最低点积0.354，估幅5.997643mm，声明轴[0.8,0.6,0]的真实需求3.686472mm，经渐隐后实际最大位移5.262878mm。当前缺口表现为宽域基面外推与幅度偏差。首版完整raw/model/fit/score在优化前固定。[首版快照](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/STAGE_V1_SNAPSHOT.json) · [首版实际拟合审计](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/FIT_AUDIT_v1.json)

本批选择逐目标32mm、法向点积>0.55、最多32个最近外围支撑，平局按sourceID。该实现选择在派生前写入OPTIMIZATION_PLAN，采用当前mesh面积加权法向。新增每目标membership、数量、二次设计rank/condition、角格、最大角gap、距离和法向覆盖，求解与位移继续由消费者计算。全部23组原对应数组及引用包中既有数组字段逐位保持，DN2、69点评估预算与固定数据身份通过。[优化固定依据](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/OPTIMIZATION_BINDING.json)

独立局部支撑审计101/101通过，69目标支撑数1–32、中位25，rank6有66个，另外rank1/2/4各1个，角覆盖1–6格，最大距离31.999654mm，最小法向点积0.550141，最大满秩条件数40806.866。真实峰值24205只取得1个支撑、rank1，24203和24206同样秩不足。此规则暴露了当前凹陷法向门控下的支撑覆盖缺口，满秩点也出现高条件数与局部试估幅不稳定。[逐目标支撑独立核验](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/OPTIMIZED_SUPPORT_AUDIT.json)

v2 facts工具4真实读取并按69列membership试算局部二次拟合，随后工具5试算自建较宽邻域。最终工具7改为216点共享支撑的隐式quadric，rank9、条件数约13.8689、支撑残差RMS1.50808mm。支撑受损污染0、正注意力交集0，107目标均复用该池，经幅度扣除、缩放与Laplacian扩散后提交107点。峰值估幅6.350146mm，声明轴真实需求3.832022mm。最终正常点扩散达到60点。

v2 native自行用三视图均值RGB差>3DN、五轮binary dilation及当前源点投影构造suspect，结合空间/法向门控取得69个共享支撑，受损污染0，包含10个模块正注意力正常点。对52个目标做加权三次拟合rank10，方向[1,1,0]/√2，再用邻接0.2混合，实际修改71点、最大位移5.065042mm。最终最低恢复判据通过。两路最终提交均为displacements_world，诊断中的最终位移与实际payload逐位吻合。[第二阶段实际拟合审计](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/FIT_AUDIT_v2.json)

逐目标支撑进入了facts试算，最终实际修复采用共享支撑。两次facts实际修复成功数为0/2，native为1/2。逐目标扩展的恢复收益与同质量效率仍需后续实际接入证据。当前保留实验源码和两份阶段归档，产品采用判断为暂缓。下一合同可优先验收支撑覆盖充分且真正进入实际拟合的接口，连同幅度与正常点影响记录。[优化结果](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/OPTIMIZATION_RESULT.json)

## 实际误差、技术质量与自评

初始47支持域RMS/p95/max为1.697686172 / 3.396864123 / 3.871250307mm，410域为0.574796893 / 1.133684151 / 3.871250307mm。正常227及363点初始目标误差为0。下面均以mm计。

| 会话 | 域 | RMS | p95 | max |
|---|---|---:|---:|---:|
| v1 native | 支持47 | 1.574921697 | 3.097683404 | 3.823707986 |
| v1 native | 观察410 | 0.533390835 | 1.038745011 | 3.823707986 |
| v1 native | 正常227 | 0.017508763 | 0.000000000 | 0.256221741 |
| v1 native | 正常363 | 0.013845706 | 0.000000000 | 0.256221741 |
| v1 facts | 支持47 | 1.349074685 | 2.286299164 | 2.392159477 |
| v1 facts | 观察410 | 0.473061419 | 1.277536064 | 2.392159477 |
| v1 facts | 正常227 | 0.165433561 | 0.127689689 | 1.208713651 |
| v1 facts | 正常363 | 0.130822738 | 0.001091662 | 1.208713651 |
| v2 facts | 支持47 | 0.947751193 | 1.761721570 | 1.916082949 |
| v2 facts | 观察410 | 0.386841157 | 0.985673174 | 2.043230708 |
| v2 facts | 正常227 | 0.290358839 | 0.406611720 | 2.043230708 |
| v2 facts | 正常363 | 0.229612046 | 0.223276359 | 2.043230708 |
| v2 native | 支持47 | 1.160301545 | 2.150213743 | 3.324619205 |
| v2 native | 观察410 | 0.397320537 | 0.770145234 | 3.324619205 |
| v2 native | 正常227 | 0.079867591 | 0.041784386 | 0.856682111 |
| v2 native | 正常363 | 0.063158267 | 0.012427525 | 0.856682111 |

四份最终保存文件另由四个新Blender进程导出，56项数组/文件身份检查通过。四路域外27,030点原生坐标逐位保持，source IDs、矩阵、原生拓扑、派生三角顺序/稳定键、UV/材质及场景身份通过。新增退化、反转、额外接触与关系变化均0，扫描完整，unresolved为0。接触配对覆盖至少一面关联I274或实际变化点的全部无序三角配对。单次/累计预算通过，梯度和法向按观测保留。

| 会话 | 法向变化max，度 | 关联边梯度max | 跨界梯度max | 支持X误差RMS，mm | F的X跨度前/后，mm |
|---|---:|---:|---:|---:|---|
| v1 native | 28.052588 | 1.002093192 | 0.000431756 | 1.268874408 | 92.304861 / 92.304861 |
| v1 facts | 22.205792 | 0.799286369 | 0.145131406 | 0.913826095 | 92.304861 / 92.304861 |
| v2 facts | 18.602948 | 0.262283298 | 0.262283298 | 0.365881743 | 92.304861 / 92.304861 |
| v2 native | 28.348112 | 1.270503987 | 0.086502582 | 0.635778294 | 92.304861 / 92.304861 |

关联边879条，跨界边119条。24张独立PNG路径包括8张共享初态和16张最终图，所有四组相机/尺寸/几何哈希与原图身份核对通过。16张消费者保存版本预览与独立最终渲染RGBA逐像素一致。[实际图像清单](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/VIEWABLES.json) · [16对像素核验](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/PREVIEW_PIXEL_VERIFICATION_all.json)

| 会话 | 实际执行 | 模型任务自评 | 独立恢复判据 |
|---|---|---|---|
| v1 native | 提交/保存/fresh回读/预览完成 | 局部修复完成，视觉改善 | fail |
| v1 facts | 提交/保存/fresh回读/预览完成 | 局部修复尝试完成，视觉改善 | fail |
| v2 facts | 提交/保存/fresh回读/预览完成 | 修复未完成，保守局部改善 | fail |
| v2 native | 提交/保存/fresh回读/预览完成 | 局部修复完成，视觉改善 | pass |

模型自评依据来自其观察和原始最终回答，独立质量依据来自实际保存文件与隐藏目标。艺术验收和跨样本稳定性仍未测。[四份原始消费统计](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/CONSUMER_STATS_all.json)

## 输入、实际访问与版本隔离

双方均能在Python按需读取同八张绑定PNG、camera metadata和完整当前mesh。逐PNG CRC及独立Pillow解码10/10通过，RGB数组共9,676,800B逐字节一致。source三角、polygon offsets/vertices和矩阵通过G提供。事实组额外获得自动对应和版本绑定引用。两阶段运行源分别归档24项和26项，后者含新增localized_support.py与优化binding。实际运行源变更为facts_api.py、python_executor.py和新增localized_support.py，attention源correspondence.py的SHA保持 `a2a70c2d35eb22dd4304fc0e5c735c33897562a2377d03957feeabf7016b3597`。

全部25次消费者Python计算绑定version0及实际初态SHA，89项显式文件访问均为共享PNG、已交付引用和自有payload，拒绝访问数0。两次工具执行错误分别为v1 facts的cdist导入受限、v2 native的globals调用受限，随后各自在同一会话恢复。v2有3次worker标准输出截断，Bridge事实文本截断为0，完整数组及实际提交证据保留。隔离使用进程内导入/AST限制和CPython文件审计，OS沙箱认证未测。provider内部图像预处理、注意力、解析模型设置与隐式重试未测。

## 完整成本与失败保留

| 会话 | Pro墙钟s | input | cached input | output | reasoning | 工具 | PNG块 |
|---|---:|---:|---:|---:|---:|---:|---:|
| v1 native | 140.9244185 | 248852 | 215040 | 3787 | 696 | 9 | 12 |
| v1 facts | 189.2203767 | 337012 | 298624 | 4923 | 908 | 11 | 12 |
| v2 facts | 150.4327750 | 263224 | 227328 | 4125 | 920 | 9 | 12 |
| v2 native | 183.1452789 | 274542 | 219392 | 4350 | 972 | 10 | 12 |

四真实Pro合计663.7228491s，input 1,123,630，其中cached 960,384，非缓存 163,246，output 17,185，其中reasoning 3,496。cached和reasoning分别作为input与output子集列示。39个工具、48个实际PNG块，原PNG共19,068,206B。

两个阶段消费者墙钟为330.1447952s和333.5780539s，后者约增加1.04%。非缓存input为72,200和91,046，约增加26.10%。实际求解方法和质量随会话改变，同质量效率归因保持未建立。四个会话监控树CPU合计69.484375s，最大采样树RSS696,991,744B。

26个实际Blender作业为5写、12读、9渲染，全部退出0。细分为固定输入fresh读2、恢复控制写/读/独立读3、控制预览1、四正式编辑4、正式回读4、正式预览4、独立最终读4、独立最终渲染4。监控进程墙钟34.0393841s、作业内墙钟34.0835315s、树CPU25.875s，最大采样树RSS450,330,624B。

消费者Python按需像素读取40次、实际冷解码40次、同worker命中0次，原PNG累计16,508,496B、解码数组49,152,000B，墙钟16.0035880s、CPU15.96875s。自动对应两次正式focus均冷算，合计7.3284221s、CPU7.3125s，完整内部数组峰值38,683,896B。首次基线冷算3.7279703s，同版本预检复用约0.05s。逐目标局部支撑纯计算约0.00629s。内部NPZ/数组量、模型公开文本和MCP图像字节分别统计，计时按嵌套作用域保留。

预检包括真实恢复控制19/19、对应23/23、独立射线24/24、mock59/59、实际案例29/29、独立PNG10/10、保存预览10/10、优化支撑21/21、独立优化支撑101/101和优化runtime20/20。全部原始尝试与源身份保留。

已保留的普通失败包括首轮-I导入顺序、对应focus摘要超长、射线camera轴重投影偏差、NumPy布尔序列化、局部runtime夹具相对路径、优化审计显式路径cwd误判。根首次将渲染与其依赖的AUDIT并行调度，随后按依赖顺序恢复。再次渲染时before_local.obj别名缺失，复制实际fresh OBJ字节后续跑，已完成native渲染作业被复用。第二阶段快照初次缺stage专属stats，生成该文件后重试。额外patch和只读诊断读取失败单列。所有这些恢复均在既定四会话和固定数据内完成。[补充失败与成本记录](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/FINALIZATION_COST_NOTES.json)

完整COSTS列出所有唯一监控根、准备/失败/优化、PNG解码/栅格/聚合/cache、facts/引用、Python、实际API/Bpy和端到端快照。root与子代理模型用量/费用、provider费用、全任务CPU及峰值RSS未测。四消费者Bridge终态closed字段为false，CLI均退出0、readers停止且safe_to_continue为true，最终CIM核查另记。冻结session_api.py继承的末尾空行按实际执行字节保留，格式例外写入HANDOFF。训练、Google/API、新增付费API、正式部署均为0。[完整成本](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/COSTS.json)

## 可复核产物与证据范围

- v1 native [实际模型](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/private/sessions/v1_repair_native/versions/001/model.blend) · [最终回答](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/private/consumers/v1/repair/native/PUBLIC_FINAL.txt) · [45度结果图](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/private/results/v1_repair_native/after_views/forearm_45.png)
- v1 facts [实际模型](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/private/sessions/v1_repair_facts/versions/001/model.blend) · [最终回答](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/private/consumers/v1/repair/facts/PUBLIC_FINAL.txt) · [45度结果图](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/private/results/v1_repair_facts/after_views/forearm_45.png)
- v2 facts [实际模型](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/private/sessions/v2_repair_facts/versions/001/model.blend) · [最终回答](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/private/consumers/v2/repair/facts/PUBLIC_FINAL.txt) · [45度结果图](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/private/results/v2_repair_facts/after_views/forearm_45.png)
- v2 native [实际模型](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/private/sessions/v2_repair_native/versions/001/model.blend) · [最终回答](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/private/consumers/v2/repair/native/PUBLIC_FINAL.txt) · [45度结果图](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/private/results/v2_repair_native/after_views/forearm_45.png)

该比较覆盖一个固定开发样本的四次实际会话。点/面积定位、拟合支撑、幅度、实际保存恢复和正常点影响分别验收。跨资产收益、图像及focus独立贡献、随机算法选择的稳定性仍在未测范围。当前结果支持继续完善实际拟合支撑覆盖和幅度求解，最终恢复1/4的事实保留。

Git交付根目录公开脚本与报告，大体积private模型、原始会话、对应数组和逐点评分保存在本地，MANIFEST逐文件记录字节数与SHA256。完整性核验、固定提交与唯一回报分别可复核。[完整性核验](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/DELIVERY_VERIFICATION.json) · [本地证据清单](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/MANIFEST.json) · [提交与交接收据](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_correspondence_005/HANDOFF.json)
