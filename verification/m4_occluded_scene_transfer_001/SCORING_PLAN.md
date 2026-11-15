# 新遮挡场景的冻结评分与成本口径

正式结果逐槽先形成原文归一化与质量记录，封存后再读取耗时和 usage 排名。六槽顺序为 N1、P1、P2、N2、N3、P3，失败及未运行均进入分母。任务固定一个新 CAPTURE_REPLAY 场景。

## 独立事实

`oracle.py` 从固定源三角形与有理数平面投影判断正向、入框和正面积遮挡。所有 unsupported 三角形仍参与遮挡。资格 N 的六个真实 PNG 和 raw source-owner 缓冲形成独立像素真值，每面至少 16 个表面像素、4 个 RGB 距离至少 24 的边界像素。一张当前帧同时满足完整几何与可读条件才构成见证。

`saved_evidence.py` 逐份读取当前 owner 原件，将产品 ROI 绑定到独立的对象与局部三角形集合。源三角形和四角采用精确有限有理数。单位法向可能包含无理归一化系数，优先检查精确正比例关系，随后仅对单位向量方向允许 `2e-14` 的双精度舍入误差。两种检查均保持朝向正向。

实际产品事实同时核对支持域、唯一源区域、世界描述、每个公开像素行、图片字节、完整见证 index/ref、covered/remaining 精确集合、有限池几何不可达集合及逐面未知原因。资格 P 的实际帧子集可能少于六张，诚实的 pending 状态保留。正式完整巡检必须覆盖资格六视图内全部可完整且可读的面。

正式 N/P 均使用本槽当前帧。原生面身份可用对象加局部源三角形集合、全局源三角形集合、世界四角或唯一中心加正向法向。ROI 为额外别名。

## 原文归一化

`score_saved.py` 接收 `occluded-scene-transfer-normalized-v1`，顶层 `slots` 必须有六个唯一槽。各槽保留以下字段。

- `slot_id`、`raw_answer_path`、`raw_answer_sha256` 绑定实际 PUBLIC_FINAL。
- `sources` 保留唯一 `id`、`kind`、`path`、`sha256`。kind 可以是 `tool_result`、`cited_artifact` 或诊断用 `tool_request`。引用文件必须位于当前 owner，且最终答的 `final_citation_excerpt` 明确包含文件名。
- `coverage_use_excerpt` 必须为最终答实际使用覆盖事实的原文。
- `panels` 对每个支持面恰好一行，含 `identity`、`status`、`support`。covered 的 `views` 至少一个当前 `{view,ref}`，每个引用均应是该面完整可读见证。unknown 附 `reason_code` 和 `finite_pool_only=true`。
- `remaining` 为所有未完成面 identity 的明确列表，与实际完整集互补。
- `unsupported` 恰好一条，含 `status=unsupported`、`domain=outside_supported_rectangle_domain`、`component_count=1`、`shape=nonrectangular`、`identity` 及 `support`。identity 可用完整 `global_source_triangle_indices`，也可用唯一 `object_name` 或 `object_index` 绑定该非矩形分量。若同时声明局部 `source_triangle_indices`，须精确匹配。缺少全部身份信息会被拒绝，归一化不能从真值补填。
- `pixel_targets` 恰好两个，用固定任务 `id`，含面 `identity`、`center_world_m`、`front_direction_world`、`view`、`ref`、`support`。范围可用 `quad_world_m`、`bounds_world_m` 或 `half_edge_u_world_m` 与 `half_edge_v_world_m`。它们应对应固定 `(view_name,x,y)` 的当前 raw-owner 实际归属。
- `source_targets` 恰好两个，用固定任务 `id`，含 `identity`、`status`、`support`、`finite_pool_only=true`。covered 附当前完整见证 `witness={view,ref}`，unknown 附准确 `reason_code`。
- `finite_pool_only=true`、`global_invisibility_overclaim=false`、`finite_pool_support` 和 `contradictions=[]` 需有实际原文依据。

每个 `support` 为一个或多个 `{source_id,excerpt}`，excerpt 需为该原始来源的非空连续子串。程序核对不可变字节和数值事实。原文是否蕴含归一化声明，交由独立人工语义审核。缺失字段和含糊回答保持缺失。

## 采用与补核

P 的 `product_adoption.claims` 逐项给出 `identity`、`product_support` 和最终答 `final_use_excerpt`。product_support 必须指向本槽实际首个 active_observation 公开结果原文。至少一个任务相关事实有真实产品出处和最终使用原文时，计实际产品事实采用。该记录与最终任务质量分别判定，任务别处答错仍可保留已经发生的事实采用。

`extra_tool_classification` 覆盖全部额外实际业务工具，记录 `attempt`、`category`、`support`。P 从第 2 个业务工具开始，N 从第 1 个开始。类别允许 public_json_query、cached_image_read、existing_buffer_lookup、format_artifact、cached_product_observation、raw_source_read、native_computation、new_native_observation 和 unknown。请求代码可以支撑该诊断分类。

direct-only 是正确结果的诊断项，分类缺失或未知保留 null。原生补核按实际发生记录，必要性保持未测。补核耗时和 usage 全部计入完整任务。

## 生命周期与输出

终态读取实际 routed 六槽生产者，使用每条 `records[i].execution_state`，核对唯一槽顺序、组别、计数、零重试、launcher 和每槽异常、原消费者 valid_completion 及已有实际进程确认。保留已接受的持有句柄终态确认语义。不会要求不存在的单 P1 顶层终态字段。

全部输出采用独占创建，限定新任务 namespace。`interface_checks.py` 仅从既有真实六槽生产者做离线接口正反例核对，完整内容评分和新增模型/产品/栅格调用均为零。

## 成本解锁与判定

质量完成后，根创建 `QUALITY_SEAL.json`，包含 `cost_analysis_unlocked_after_this_seal=true`、`quality_path`、`quality_sha256`、`inputs=[{path,sha256}]`。质量失败同样可以封存并分析成本，成功速度比较只使用双方均完整正确的对应配对。

成本入口为 `cost_audit.py --quality-seal <path> --output <new COST.json>`。每槽使用既有 routed `SLOT_TIMING` 中检查前至清理、归档和 SLOT_RESULT 关闭的完整时界。route、consumer、工具、产品、栅格与图片交付为嵌套范围。数组、PNG、NPZ、base64、JSON、stdio 字节分别记录。

双方各 3/3 完整正确、P 3/3 实际采用产品事实、三个 P/N 完整耗时比中位数至多 0.90 且至少两对 P 更快、P 总原始 input+output 不增加，才记录此固定任务有限工程正信号。cached 属于 input，reasoning 属于 output。CLI 原始事件和汇总需一致，六槽同源。缺 usage、质量失败或未完成不会产生整体收益通过。

现金、图像 token、provider 内部请求数和完整人工成本保留未测。三对结果对应本任务，后续方向由实际新缺陷决定。
