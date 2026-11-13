# M4-ACTIVE-COVERAGE-003：独立像素反馈复核与下一任务建议

本文件由根复核子任务 `active003_feedback_consumer_design` 独立产出。作者固定提交为 `f2b9dc01621d5b7adb330c096b6460eb3be9c552`。本轮实际执行自己的 `audit_feedback.py`，仅解码已存 PNG/NPZ、计算像素及重建有限状态；没有导入作者 validator、评分器或 coverage 模块，没有新光栅、Blender、模型或 API 调用。完整 Git/源码和所有帧哈希由根并行复核，完整费用/进程生命周期由其它子任务负责。

## 本轮实际结果

`RESULTS.json` 保存输入摘要、696 项检查、18 帧与108个 ROI 像素行：696通过、0失败。覆盖两控制完整10帧与第一主配对8帧；其余10个主进程没有重新逐像素计数。本轮没有重新执行几何分类；几何 mask 与已接受001矩阵逐项比较相同。

控制B真实顺序为 SCENE → BACK → LEFT → TOP，逐次新增2、0、2、1。每帧独立从 owners 计算目标表面像素，从相邻 owner 变化及 RGB 距离≥24计算对比边界；固定16表面像素、4边界像素门槛。

| 帧 | 实际非零目标像素 | 新覆盖 | 累计覆盖 |
| --- | --- | ---: | ---: |
| SCENE | Obj_004、Obj_005均340表面/72边界 | 2 | 2 |
| BACK（跨度64倍） | 六个目标均0表面/0边界；整张图仅3个前景像素 | 0 | 2 |
| LEFT | Obj_003为759/108；Obj_001为792/110 | 2 | 4 |
| TOP | Obj_002为676/100 | 1 | 5 |

BACK几何完整的三个目标没有被计成覆盖。历史像素不足集合保留这三个目标，LEFT/TOP补足后最终像素不足为空。最终未覆盖的Obj_006属于固定相机池无法几何完整观察，不再误列为仍未修复的像素不足。

控制A固定六图与控制B最终都是5覆盖/1有限池未覆盖；首个主配对同样一致，主B两帧SCENE/BACK新增2、3。四个抽核进程的重复查询均零新光栅且状态不变。B的下一视角逐步由当前实际覆盖重新推算，包含BACK失败后LEFT、再TOP的确定顺序，不读取作者预先写出的正确序列来决定状态。

抽核18帧中，除两张专门改变了跨度的控制BACK，所有PNG解码RGB、color、owner、depth与001原件逐元素相同；其余相机姿态也相同。控制BACK确认跨度比64，图像与旧BACK不同，六目标零像素。本轮另外直接目视了control_B的BACK和LEFT原PNG：前者只有极小亮点，后者为深色背景上的灰色矩形投影，与算术结果相符。

这关闭了本固定工程任务的“几何预计有收益但真实像素不足后能否继续取证”缺口。没有证明材质语义识别、任意复杂场景扫视或真实模型消费收益。

## 现有消费壳能否直接复用

不能原样直接启动图像对照，但可以复用已核验的CLI启动、公共MCP工具调用、实际事件归档与同一Pro登录方式。不要重做整套评测平台。

以下路径均相对于 `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/`，行号经本轮源码读取确认：

| 位置 | 当前事实 | 对下一批的影响 |
| --- | --- | --- |
| `verification/m4_surface_scan_continuous_consumption_002/runtime/driver.py:34` | 复用FIX1 actor和interface-fix coordinator/transport | 可复用运行壳，不能仅换场景和标题 |
| 同文件`:99` | 契约固定image_count/new_images/image_bytes=0 | 正式图像实验不能通过原契约 |
| 同文件`:119` | 绑定旧C公共工具schema | 旧surface_scan不含003主动覆盖原型入口 |
| `verification/m4_surface_scan_continuity_001_fix1/runtime/actor.py:271` | 原生执行响应包成text | 输出文件名或base64文本不等于image content block |
| 同文件`:282`、`:291` | 强制include_image=false；拒绝image block | 必须实际接通两路相同图像能力 |
| `verification/m4_surface_scan_continuity_001_fix1/runtime/consumer_transport.py:174` | 图像交付计数固定0，定义为text-only | 不能沿用这些字段就宣称已收图 |
| `verification/m4_surface_scan_compact_consumption_001/runtime/consumer_transport.py:58` | 已有带预授权工具schema的CLI argv | 可以在新批最小适配，保持同模型/努力/服务设置 |
| 同文件`:92` | 固定现有Pro CLI模型与登录方式 | 不新增provider/API，不读取Google密钥 |
| `verification/native_plugin_complex_003/actor.py:6` | 原生允许自写Python/NumPy/BVH及缓存，但说明明确禁图 | 保留原生自由求解；图像禁令须在新试验入口真实解除 |
| `verification/m4_surface_scan_continuous_interface_fix_001/compatibility.py:10` | 已知owner/CLI成功envelope映射要求content完全相同 | 可以复用精确内容比对，不能任意删图或把差异默认为成功 |
| `verification/m4_active_coverage_003/runtime.py:132`、`:152` | PNG保存到本地后构造actual_image_delivered=true并直接observe | 这是内部本地证据回执，不是MCP/CLI/模型图像收件证明 |

另外，旧消费任务使用自己的assembly.blend；003当前28对象/200顶点/276三角形是另一份几何。原生正式对照必须获得与003完全相同的几何、相机和图像能力，不能把旧Blender资产当作已绑定。003仍是封存实验原型，本轮没有证明默认插件已经提供该公共能力。

## 唯一建议下一任务：双路图像交付资格

冻结003几何、相机、可读性阈值和调度算法，不继续微调性能。根据根随后收窄的设计，下一项建议命名 `M4-ACTIVE-IMAGE-CONSUMPTION-001`，只补实际模型收图这一个明确缺口：在新的隔离试验目录，为共同公共图像传输函数接通原生读取出口与插件观察出口，并用现有Pro CLI各执行一次真实消费。无需新渲染：两路使用同字节、同顺序的已封存control_B SCENE和BACK64两张PNG，明确这只是本地PNG重放的传输资格，不是按需引擎消费benchmark。两张图已由本子任务独立解码：前景分别12634和3像素，差异显著；这些私有数量不发送模型。

实现保持一个公共image-content构造与传输函数；原生使用普通图像读取能力，插件出口包装相同两张PNG并明确是verification adapter而非默认产品。只暴露PNG、必要尺寸/媒体类型/opaque引用，不附文件名SCENE/BACK、目标列表、私有mask、owner数组、前景数量、正确视角顺序、预期图像描述或评分器。两路完全相同题面，要求调用可用图像工具，区分哪张有显著轮廓、哪张几乎空白并简述可见依据；不要求识别ROI或执行扫视算法。保持同CLI、模型、推理设置和预算，一路一个fresh Pro session、一个user turn、明确有限工具调用。两张不同输入、两路各交付一次，应分别记录为2张源图、0次新光栅、最多4次正常图像交付，而不是2张图成本覆盖全部传输。

先用现有非模型协议检查验证PNG解码和内容块，之后每路最多一个Pro资格轮。记录源PNG SHA、公共工具schema、原始请求、owner输出、stdio实际image内容块、CLI实际完成事件及回答、图片次数/字节、CLI公开usage和完整耗时。若宿主不公开某一级provider/model收件事实，保留该级未测，不能拿文件存在或结果路径代替图像收件。模型仅说“我看到图片”不够；回答应正确关联opaque引用，分别说明明显形状与近空白差异，且这些内容未在文本预给。这仍只是资格信号，不能凭每路一次描述推断视觉语义能力收益。

保留原生普通Python自由计算的语义，不能为资格把它换成内置答案工具。若模型直接使用Python统计像素得到分类，记录其实际途径；图像传输可以通过，但模型视觉消费仍未证。若资格不启动Blender，就使用诚实的普通Python/图片读取工具名，不沿用execute_blender_code却实际不给bpy。正式独立原生求解能力留到后续真实任务，当前不要为了两张图重新部署Blender资产。

### 共享helper的最小复用位置

- `verification/native_plugin_complex_003/reused/stdio_attach.py:18` 的attach和`:54` 的stdin/stdout循环已透传完整JSON，`:58`与`:65`保存TX/RX原字节，可以继续复用。它本身没有把image剥成text。
- `verification/m4_surface_scan_continuous_interface_fix_001/compatibility.py:10`至`:32`对已知成功envelope做精确content比较，可以复用；若CLI呈现图像的实际格式不同，应保留原件、明确观察到的变化，不能随意丢image字段让比较通过。
- `human_eye_plugin/agent_adapters.py:81`至`:93`给出标准MCP块 `type=image, mimeType=image/png, data=base64`。最小新helper只需从已冻结PNG原字节构造此块，两路共用；不需要为它导入整套router或给PNG重新编码。
- `human_eye_plugin/live_spatial_mcp.py:817`至`:829`现有多图片分支固定384×384，本批是512×512，因此不适合作为直接双图复用入口；不要为资格修改产品尺寸合同。
- `verification/engineering_native_service.py:25`至`:53`已有native图片返回，但同样绑定384尺寸、Blender host、source与task生命周期。只借用标准MCP形状即可，整服务导入会扩大任务。

资格两路都通过后封存公共入口和调用样例，回根复核；不在本批自动顺接3配对“看图语义收益”。失败保留原调用、已构造和已发图成本；不自动重复模型调用补样，不改算法/阈值尝试刷过。两路均0新渲染、最多2次现有Pro消费；Google API继续0。这是运输可用性资格，时间和模型回答不能作为插件比原生更强的评分。

## 为什么不立即做3配对“视觉发现”

当前图像所有物体同色，无纹理、文字、材质、局部凹陷或其它仅图像揭示的信息。六个目标是源网格可确定的矩形，几何遮挡和固定视角池的可见性可以直接由源数据计算。像素反馈确实提供了数值可读性门槛，但尚无必须由模型看图才能求解的业务问题。强制原生看完六张、强制插件只看两张，会把工程调度基线冒充独立模型能力。

若根之后选择只检验“模型能否使用几何事实与观察规划”，可以在上述资格后单独冻结3配对小规模试验：相同几何与相机、共同通用Python/原生读取及同图像能力，插件组额外使用冻结主动覆盖工具；两路自由决定是否获取图像、如何查询和缓存。不给解、不给目标ID、不给固定六图路线。质量先判完整目标集合、已覆盖依据和有限池未知说明，再看完整任务时间、工具次数、文本/图像、可取得usage和费用。该结果只能称事实消费与任务规划收益，不能称视觉语义发现或通用扫视完成。

在真正需要模型图像认知的后续任务中，必须有对两路都可见、却未直接编码为插件答案的视觉信息，并有独立真值。构造该任务应作为另一项明确能力试验；本轮不新增材质、贴字、专家模型或新模块。

## 状态区分

- 独立通过：上述18帧/108行像素、反馈/终态、已有图像一致性及原消费入口只读检查。
- 独立失败：0。
- 未运行：任何新模型、渲染、Blender、API、正式消费A/B、剩余10个主进程逐像素计数、任何产品或默认入口更新。
- 作者日志：其余全批性能与来源结论仍由根/其它审计独立核对，不把作者报告合并成本子任务执行结果。
