# M1 源面绑定的冻结评分与成本合同

本批六槽为 A1、B1、B2、A2、A3、B3，均通过同一 P 执行角色调用产品。A/B 为比较版本标签。读取 `source-face-binding-six-route-v1` 和 `source-face-binding-launch-v1`，逐条核对当前槽位、实际 group=P、comparison_arm、唯一顺序、计数、原消费者有效终态及持有进程确认。失败与未运行均保留在六槽分母。

## 共同质量

沿用上一批原文绑定、精确面集合、完整见证、可读阈值、两像素定位、两源面判断、unsupported 源分量与有限池未知原因。默认可测条件仍为单张当前帧完整正向、入框、零正面积遮挡，实际表面像素至少16、RGB距离至少24的独特边界像素至少4。所有额外未撤回的错误事实均列入 contradictions。

原生身份可用对象加局部源三角形、全局源三角形、四角，或唯一中心与正向法向。当前 ROI 可以作为别名，多个别名必须一致。源三角形与四角精确比较，单位法向仅沿既有无理归一化舍入容差。

`admin/TRUTH.json` 与 `admin/PIXEL_TRUTH.json` 逐字节复用上一批独立合格资料。`REFERENCE_TRUTH_BINDING.json` 固定原几何、N六帧像素真值、原冻结与资格封存。原像素文件继续指向旧 N 六帧的来源。当前 A/B 的实际帧由保存缓冲独立重新核算，当前 manifest 必须绑定相同源几何、相机、capture 和任务输入。新候选资格另行绑定当前最终冻结和实际资格运行。

## 原文归一化

顶层采用 `source-face-binding-normalized-v1`，slots 恰好六个唯一槽。共同字段继承原合同，包括 raw_answer_path、raw_answer_sha256、sources、coverage_use_excerpt、panels、remaining、unsupported、pixel_targets、source_targets、finite_pool_only、finite_pool_support、global_invisibility_overclaim、contradictions 和 extra_tool_classification。

每个 support 为实际来源的非空连续摘录与 source_id。当前工具结果绑定实际消费者收件，工具请求仅支撑过程和采用诊断。引用 JSON 文件须位于当前 owner，并由当前 final 明确引用文件名。保留 CRLF 原始字节。缺失内容保持缺失，外部真值仅供判分。

所有核心几何和任务质量检查保持既有含义。`interface_scoring.py` 对 identity、tools、support、witness、extent、unsupported_identity 和原事实采用方法执行独立 AST 相等检查。最终完整语义核对包括额外声明，根在首次内容评分及质量封存前审核摘录是否蕴含归一化内容。

## 实际采用源面绑定

`product_adoption.claims` 继续记录当前产品事实的真实出处和最终使用，与最终质量分别判定。新增 `source_binding_use.claims` 专门记录新默认源面绑定的实际消费。

每条源面绑定采用声明包含以下内容。

- identity 标识一个当前独立源面区域。
- product_support 指向实际首个默认 active_observation 的公开结果摘录。
- operation 指明 source_face_to_region_lookup、region_to_source_faces、pixel_source_face_to_region 或 direct_table_reasoning。
- operation_support 给出实际当前请求代码、输出或明确的表格推理依据，展示源面范围如何用于上述操作。
- task_use_support 给出当前 final 或 final 明确引用文件中的任务使用摘录。
- binding_scoped=true 和 dataflow_confirmed_by_review=true 由审核实际数据流后填写。

当前保存结果核验器先证明 B 实际交付了 v5、正确作用域语义及与原始 source mapping 逐项一致的范围。收到字段本身不计采用。采用检查还要求上面的操作及任务使用证据，人工数据流审核仍是必要条件。直接读取映射、buffer 拾取与直接表格推理均为正常消费方式。

A 已有完整原始映射与公开缓冲映射。A 若使用这些能力，保留其具体过程事实；本批新默认字段采用门限只计算 B 的三次真实采用。

## 反查与必要取证诊断

每槽新增 process_diagnostics.geometry_reverse_lookup 和 full_witness_pixel_recomputation，分别记录模型消费阶段几何反查和完整见证像素重算。每项具有 observed 布尔或 null、review_complete、reviewed_tool_attempts、support 和 reason。只有全部实际业务调用已经审查、摘录存在，才发布明确的发生或未发生判断。审查不全保留 unknown。

extra_tool_classification 仍逐个涵盖实际额外调用。代码类别与操作诊断独立，混合调用保留完整代码依据。direct-only 沿既有正确结果诊断，额外原生操作的必要性未测。

成本另从实际帧记录 TOP 是否由固定采样点要求、首个产品帧是否已含 TOP、随后实际原生 TOP 构造次数。重复 PNG 内容块按实际交付计数和计字节。TOP 缺帧取证和重复图片交付分别记录。

## 质量封存后展开成本

根完成独立原文与数据流审核后，首次六槽内容评分写入新输出，随后封存 quality_path、quality_sha256 和全部相关 inputs，设置 cost_analysis_unlocked_after_this_seal=true。质量失败同样可封存并展开成本。

每槽使用实际共同 run_slot 起止，检查前到退出、清理、归档和 SLOT_RESULT 写入关闭。外层批次含槽间管理员事实核对。嵌套的 route、consumer、工具、产品、raster 和交付时钟分别列出。

实际工具回复文本按每个 MCP result.content 中的 text UTF8 字节求和，并核对每次 content_metrics。助手公开文字按 all_public_messages 的 text 另行求和并核对 consumer.public_text_bytes。二者使用不同字段。JSON、PNG、base64、stdio 和内部数组分别计量，重复交付成本保留。

CLI usage 要求六槽使用相同来源、模型、medium/default 配置，以及每次真实 stdout.raw.bin 的 turn.completed 事件，与原始 usage_rows 和汇总一致。cached 属于 input，reasoning 属于 output。未知现金、图像 token、provider 内部请求、完整人工成本继续标为未测。

有限正信号要求 A/B 各3/3整份正确、B实际源面绑定采用3/3、三对完整耗时中位B/A≤0.90且至少两对更快、B总原始input+output不高于A。失败时间保存，成功速度分母只使用双方完整正确的配对。三对结果只覆盖这个固定任务。

所有资格尝试共用累计12次额度，正式上限36，全批48。成本报告读取全部 Qnn 资格运行和持久化 ledger，不重置旧尝试。旧新插件比较不新增原生对照样本。

## 离线准备检查

`interface_scoring.py --prepare-contract` 对旧真实六槽记录做明确的元数据适配接口检查、反例控制、采用证据控制和旧文本计数回归，再生成当前源码合同。适配旧记录不构成新的 A/B 执行证据。该入口不启动模型、观察、raster 或完整内容评分。所有结果独占写入新 namespace。
