# M1-JOINT-FULL-TASK-TAIL-SCOPE-001

唯一目标是修复 `475ae93a` 将量测尾置扩展到所有有序量测事实组合后，合法多事实请求可使原先保留的达标帧来源字段遭固定 CLI 裁剪。只增加一次有直接反例的候选。待用的非共面选区排序题保持待验收状态。

1. 用 Far00 正式 P1 原 ZIP 复现。取 `slots/P1/product_full/call_001/SERVICE_RESULT.json` 和 `slots/P1/native/WIRE/002/RESPONSE.bin`、`003/RESPONSE.bin` 的当前源及有序选择。把同一首调的嵌套 `requested_facts` 换成原合同支持的 `aabb,center_delta,axis_gap,surface_clearance,solid_relation,nearest_witness,pair_relation,surface_proximity,closed_solid_relation,spatial_relation`。必须用实际隔离安装的量测算子在同一封存数据上生成结果，保全实际 JSON-RPC 请求、生产记录和回包。把实际历史槽和新增派生控制分别记账。
2. 验证原基线 `c8f87c54`、原候选 `475ae93a` 的反例。固定 33/34/35 B 工具头、12,000 B 结果与 3,000 近似 token 历史两阶段。原基线保全达标帧级来源，原候选能恢复多事实但达标 SCENE 的 `host_binding_sha256` 与 `source_revision` 及其它帧字段出现新增裁失。原图、观察行路径／引用／摘要不得误报缺失。记录差异和原失败。
3. 从 `475ae93a` 一次窄修。原条件只额外限定 `task_result.facts` 精确为单个 `surface_proximity`。多事实以及其它单独配对事实走原有成员顺序；单独距离的 unknown 状态及理由保持。新增控制包括合法十项、距离加 AABB、一个非距离配对、原单距离成功和原 unknown。两个历史单距离原件复用 12/12 门。多事实线包在仅消除因固定产品身份导致的差异后与原基线字节一致，固定裁剪后原有帧字段及图仍保全。保留上一批无关路径和热分段核验，控制本次各版本回包字段不变，不增加字段、工作、缓存或求解流程。
4. 只读回放，一次候选隔离构建和安装，核 Git、wheel 和实装字节。无新 Blender、模型、构图、替补、重建、Google、额外 API 或费用，正式配置不切换。若失败留下明确剩余差异，收口本批。

回报 `M1-JOINT-FULL-TASK-TAIL-SCOPE-001_READY` 至 `local/01a1971f-eef5-7a23-a1b1-2352beb80a77`，附固定身份、封存反例、各阶段分母和时间、单距离正例及未测项目。
