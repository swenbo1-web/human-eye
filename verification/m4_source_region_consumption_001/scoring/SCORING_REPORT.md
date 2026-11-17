# M4-SOURCE-REGION-CONSUMPTION-001 作者评分

统一评分在三份原答封存并由 root 明确释放后进行。证据读取限于三份 answers 正文和原冻结 RUBRIC、CASE_ANSWERS。冻结规则与原始失败状态均保留。

## 总体结果

| 例 | 内容门 pass / fail / unrun | 内容结果 | 原观测 JSON / 原生 PNG | 原 harness 状态 | accepted |
| --- | --- | --- | --- | --- | --- |
| S1 | 0 / 0 / 9 | unrun | 未交付 / 0 块 | failed | false |
| S2 | 5 / 4 / 0 | failed | 已交付 / 1 块 | failed | false |
| S3 | 6 / 3 / 0 | failed | 已交付 / 1 块 | failed | false |

- 接受数为 **0/3**。内容门共 11 pass、7 fail、9 unrun。成功交付观测的两例内容接受数为 0/2。
- S1 的旧薄 MCP 拒绝 CLI 标准 `_meta`，造成原 JSON 与 PNG 未交付。原答诚实报告读取失败，九门均记 unrun，保留该例分母。
- S2、S3 各交付原 JSON 与 1 块原生 PNG。原答均自述 JSON 中段截断，未采用距离、单位换算及原见证，且缺少本例已支持的表面分离结论。上述必需结论的遗漏构成内容失败。
- S2 还遗漏 Cube 参与本次显示的事实。两例均采用了完整所选三角测量范围、0 选区像素、全部 748 个所选三角缺少当前图像样本及谨慎的实体内外判断。
- 三例原 harness 状态均为 failed。S2、S3 的旧 archive 算法将 CLI 通用空资源枚举计入 owner read 后产生计数差异。此处执行事实来自 root 的评分释放消息，原始计数与输入边界由独立 audit 核查。
- 正距离推出实体 outside 的错误为 0，缺乏依据的肯定 inside 为 0。图片对答案的独立贡献仍未量测。

## 冻结口径的适用

G1 采用至少两位有效数字、忠实四舍五入与绝对误差不超过 0.0005 m 的原规则。S2、S3 均未报量值，记录为必需量值遗漏。G3 按冻结规则中 measurement_scope 自然语言等价即可的条款评分，单位缺失归入 G1。G7 接受全选集没有可见样本、无法观察其表面外观及说明所缺来源的同义表达。G9 核查实际主要结论的本例来源绑定，工具文本截断的实际原因留给独立 audit。

S2、S3 的条件性距离解释和实体分类保留是正确部分。G8 同时要求采用本例已测正距离所支持的实际表面关系，二者在这项要求上均缺失，因此 G8 为 fail。私有 inside 证书用于核对内外推断，公开信息不足的答案依据冻结规则合格。

## S1

[原答](C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe/verification/m4_source_region_consumption_001/answers/S1.txt) 的 SHA256 为 `cffb146193ba51c041ed5cdd1d940157aec0761444483fdaf2e05170ea1cd316`。行号按原文物理行计算，空行计入。

| 门 | 判定 | 原答行号与短摘录 | 理由 |
| --- | --- | --- | --- |
| G1 distance_and_units | unrun | L4 “未取得距离字段、单位定义或最近点对，无法报告数值” | S1未获得原观测JSON或PNG。按root释放评分时给出的执行事实，该门缺少可消费证据，记unrun并保留原分母。 |
| G2 region_and_original_witness | unrun | L4 “无法报告数值，也无法引用对应区域” | S1未获得原观测JSON或PNG。按root释放评分时给出的执行事实，该门缺少可消费证据，记unrun并保留原分母。 |
| G3 complete_measurement_scope | unrun | L1 “未提供原始 JSON 或 PNG” | S1未获得原观测JSON或PNG。按root释放评分时给出的执行事实，该门缺少可消费证据，记unrun并保留原分母。 |
| G4 case_display_scope_and_status | unrun | L5 “未取得图片及选区掩膜，无法核实选区标记、可见范围或像素数量” | S1未获得原观测JSON或PNG。按root释放评分时给出的执行事实，该门缺少可消费证据，记unrun并保留原分母。 |
| G5 selected_pixel_count | unrun | L5 “未取得图片及选区掩膜” | S1未获得原观测JSON或PNG。按root释放评分时给出的执行事实，该门缺少可消费证据，记unrun并保留原分母。 |
| G6 observed_samples_and_unseen_parts | unrun | L6 “无法确定哪些部分被遮挡、位于画外，或未被本次观测覆盖” | S1未获得原观测JSON或PNG。按root释放评分时给出的执行事实，该门缺少可消费证据，记unrun并保留原分母。 |
| G7 complete_visibility_unknown_and_missing_information | unrun | L3 “本次各项结果只能标记为**未知**”<br>L11 “这同一份封存观测的原始 JSON 和 PNG” | S1未获得原观测JSON或PNG。按root释放评分时给出的执行事实，该门缺少可消费证据，记unrun并保留原分母。 |
| G8 surface_relation_and_solid_inference | unrun | L7 “目前没有证据支持分离、接触、相交或内外归属中的任何一种结论” | S1未获得原观测JSON或PNG。按root释放评分时给出的执行事实，该门缺少可消费证据，记unrun并保留原分母。 原答第9行的通用距离含义说明保留为谨慎表达，本例几何结论仍未得到评测。 |
| G9 major_citations_binding_and_supported_claims | unrun | L1 “不能把“读取失败”解释为“选区没有可见像素”或“距离为零””<br>L11 “逐项引用实际来源” | S1未获得原观测JSON或PNG。按root释放评分时给出的执行事实，该门缺少可消费证据，记unrun并保留原分母。 原答诚实报告读取失败，未伪造本例区域、图像或距离来源。 |

内容错误分类为 无，九门未获得可评测观测证据。执行分类为 `execution_or_image_delivery_failure`。

## S2

[原答](C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe/verification/m4_source_region_consumption_001/answers/S2.txt) 的 SHA256 为 `40a7dcb7e8811c8f1e42851a057c604b8344d81e32c2b397046ecbd68d8726fc`。行号按原文物理行计算，空行计入。

| 门 | 判定 | 原答行号与短摘录 | 理由 |
| --- | --- | --- | --- |
| G1 distance_and_units | fail | L8 “目前不能可靠报告最近距离数值、单位或最近点／三角形见证。” | 原答未报告本例0.37011719389236364 m及毫米换算。数字比较缺少被报告量值，按必需量值遗漏判fail。 |
| G2 region_and_original_witness | fail | L3 “source-region:67406db56fa00e9b715175753e4906dd87c159ab0d5238ca95c46f1ede9de873”<br>L9 “参考表面身份，以及最近点对和对应三角形等见证字段” | 区域R正确绑定S2。原答将参考对象身份和原见证视为缺失，没有采用Cube及原nearest_witness或source_mapping，G2必需来源不完整。 |
| G3 complete_measurement_scope | pass | L7 “完整选中源三角形并集到参考三角形表面”<br>L7 “748 个选中源三角形” | 采用了完整选集并集到参考三角表面的测量范围，并区分图片可见子集。符合G3允许measurement_scope自然语言等价的条款。单位遗漏计入G1。 |
| G4 case_display_scope_and_status | fail | L12 “selected_region_displayed_without_pixels”<br>L13 “selected_object_participates: true”<br>L21 “测量完成与视觉证据不足并不矛盾” | 原答正确采用选中对象参与显示、0选区像素和图片证据不足的含义。缺少Cube也参与本次active-view-layer有效视口显示的本例事实，故G4组合要求未全部通过。 |
| G5 selected_pixel_count | pass | L12 “选区可见像素数为 0。” | 0像素与S2 visibility.selected_surface_pixels一致，并引用当前图像I。 |
| G6 observed_samples_and_unseen_parts | pass | L14 “全部 748 个选中三角形均未获得当前帧的可见像素证据” | 准确识别全部748个所选三角没有当前帧可见样本，引用R的actual_frame_visibility未知集合及I。 |
| G7 complete_visibility_unknown_and_missing_information | pass | L14 “全部 748 个选中三角形均未获得当前帧的可见像素证据”<br>L14 “无法观察选区形状、表面间隙、接触位置或最近距离见证所在位置”<br>L19 “还需参考网格是否封闭、是否构成有效实体，以及带符号距离、点在实体内外分类或体积相交证据” | 按冻结同义表达条款，全部选区缺少图像样本及无法观察的明确范围足以保留完整曲面可见性未知，并说明实际缺少选区图像证据。实体分类缺少的封闭/有效实体及内外分类来源也已说明。 |
| G8 surface_relation_and_solid_inference | fail | L17 “当前不能判定表面分离、接触或相交”<br>L18 “若可靠结果为正且超过数值误差，只能支持这两组表面分离”<br>L19 “正距离也可能对应内含状态” | 原答给出了正确的条件性距离含义和谨慎的实体内外判断。它未采用本例已测正距离，拒绝给出本例选区与Cube参考表面分离/无接触的受支持结论，G8组合要求未全部通过。 |
| G9 major_citations_binding_and_supported_claims | pass | L3 “source-region:67406db56fa00e9b715175753e4906dd87c159ab0d5238ca95c46f1ede9de873”<br>L4 “source-region-image:87950933087b5b958c0d73e641fbe179425398b5f33d9aae302ffe0377250e32”<br>L7 “【来源：R，`task_result`、`measurement_scope`】”<br>L14 “【来源：R，`unknowns.actual_frame_visibility`；I】” | R与I均为S2原绑定，已作出的测量范围、像素与未见集合等主要结论具有可唯一解析来源。遮挡、画外、裁剪被作为尚未区分的可能性。G1/G2/G4/G8的必需事实遗漏保留各自fail。工具截断自述的实际原因归独立audit。 |

内容错误分类为 `distance_or_unit_error`、`measurement_source_or_witness_error`、`display_scope_or_status_error`、`surface_or_solid_inference_error`。执行分类为 `execution_or_image_delivery_failure`。

## S3

[原答](C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe/verification/m4_source_region_consumption_001/answers/S3.txt) 的 SHA256 为 `0a5d57a5c9baef10d4c4cf267554ec7cafcdf91a5d3b90663f87f8f290012325`。行号按原文物理行计算，空行计入。

| 门 | 判定 | 原答行号与短摘录 | 理由 |
| --- | --- | --- | --- |
| G1 distance_and_units | fail | L12 “距离数值、单位及最近点见证无法可靠报告” | 原答未报告本例0.37011719389236364 m及毫米换算。按必需量值遗漏判fail。 |
| G2 region_and_original_witness | fail | L6 “source-region:9dac0581531ea07b6555cf45b7a2d57b9fd426bed863947cf7d0cc17bea5a6bb”<br>L12 “不能补造见证点坐标或三角形编号”<br>L13 “选区侧和参考侧的见证点及三角形标识” | R及采集epoch/revision正确绑定S3，且后文识别Cube。原答没有采用原nearest_witness或source_mapping，G2的原见证来源缺失。 |
| G3 complete_measurement_scope | pass | L11 “完整选中源三角形并集到参考三角形表面”<br>L11 “测量状态为 `complete`” | 完整所选三角并集到参考三角表面的自然语言范围正确，且避免将其外推为源对象整体。符合G3允许measurement_scope自然语言等价的条款。单位遗漏计入G1。 |
| G4 case_display_scope_and_status | pass | L3 “整体状态为 `partial / evidence_insufficient`”<br>L17 “selected_region_not_displayed”<br>L17 “selected_object_participates=false”<br>L19 “参考对象 `Cube` 也因不可见而被排除” | 正确采用选区未参加显示及原原因、整体partial/evidence_insufficient，并保留几何量测complete。Cube同样从图片排除的事实采用正确。 |
| G5 selected_pixel_count | pass | L17 “选区可见像素为 0” | 0像素与S3 visibility.selected_surface_pixels一致，引用R显示记录与图像I。 |
| G6 observed_samples_and_unseen_parts | pass | L18 “未观察到的是全部 748 个选中源三角形的表面外观”<br>L17 “所列选中三角形均没有可见像素样本” | 准确识别全部748个所选三角无当前帧可见样本，并将原因归于本例未显示状态。 |
| G7 complete_visibility_unknown_and_missing_information | pass | L17 “所列选中三角形均没有可见像素样本”<br>L18 “不能从这张图确认选区形状、朝向、接触位置或最近点位置”<br>L28 “还需要参考网格是否封闭、是否定义有效实体，以及覆盖相关区域的内外分类或有符号距离证据” | 按冻结同义表达条款，未显示及全部所选表面缺少外观/像素证据明确保留完整可见性未知，并说明所缺图像证据。实体分类所缺封闭实体与内外分类来源也已说明。 |
| G8 surface_relation_and_solid_inference | fail | L23 “本次可读取内容不足以给出确定的接触、分离或实体内外结论”<br>L26 “只支持**该选区与参考表面分离**”<br>L26 “更不说明选区在实体外部”<br>L28 “无符号表面距离不能判定实体内外或包含关系” | 条件性表面距离解释、选区/整对象范围限制和实体分类保留均正确。原答未采用本例已测正距离支持实际表面分离/无接触，G8组合要求未全部通过。 |
| G9 major_citations_binding_and_supported_claims | pass | L6 “source-region:9dac0581531ea07b6555cf45b7a2d57b9fd426bed863947cf7d0cc17bea5a6bb”<br>L7 “source-region-image:ead4683c30c3bc348b8494946c44538daa0648a0ea5fa297cf37da2e14129326”<br>L19 “participating_object_indices=[]”<br>L19 “excluded_object_indices=[0,1]” | R、I、实例162和epoch=1/revision=4均属于S3，显示、未见、测量范围等实际主要结论具有可解析的本例来源。条件性通用解释明确标为解释边界。工具截断自述的实际原因归独立audit。 |

内容错误分类为 `distance_or_unit_error`、`measurement_source_or_witness_error`、`surface_or_solid_inference_error`。执行分类为 `execution_or_image_delivery_failure`。

## 可复核材料

[AUTHOR_SCORES.json](C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe/verification/m4_source_region_consumption_001/scoring/AUTHOR_SCORES.json) 保存每门原文摘录、行号、预期原 JSON 指针、来源解析、正确细项与错误类别。冻结评分文件的 SHA256 已逐字核对。

- RUBRIC.json 为 `1f5deb4b12e083dd5de952e617ee5629f04b68152759dc29bcaed6708d73f9af`。
- CASE_ANSWERS.json 为 `0c7449a5f7a70ce2982cdada064574e6ef142f8187b7bb0ede9353143baf97f3`。

实际工具截断位置、CLI 空资源枚举与输入边界仍待独立 audit，本报告的内容失败原因保留为原答未采用必需事实。
