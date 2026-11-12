# 主动视觉与场景记忆只读架构复核

2026-11-12。任务 `b67eb704-e56b-472c-811a-5f50f165c006` 的子任务；assignment `78cf4eca-3356-4b90-ad7e-cc799e414bb0` 已用本子 Agent 的真实 context 核对，父任务只读。应用了 learning-worker。实施树为 `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe`，读取时 HEAD `a44a6138b9d354ecc98a4fbd76095f0536d6973f`。对本审覆盖的产品目录/根模块执行只读 `git diff --name-only e836e03f HEAD -- ...` 无差异，产品目录工作区状态无输出；137 源 canonical 身份由总审负责，本审未另重算整份 manifest。

**结论：局部放大、局部选视角、真实遮挡、相机驻留防抖、几何/测量缓存和宿主资源增量均已有实现；“无明确目标时自主扫全场、选择下一处、融合已见证据直到任务充分”的统一闭环，在当前 ordinary 入口未接通。** 特别是默认原生图像路线绕开了投影 attention；普通几何采集已增量化，但原生视觉证明支路仍反复完整采集。不能把旧类名、像素增益或零图片关系题的模型收益当作完整人眼扫视验收。

本次只读源码与既有公开复核报告；未运行产品、测试、Blender、模型或 API，未修改实施树，未联系正在做凹槽资格的实施对话。下述采集次数均为**静态成功路径计数**，不是本次时延、CPU、RSS 或净收益实测。

## 当前真正可达的路径

下列源码位置均以实施树为根；为减少重复，表格中的短路径均为 `human_eye_plugin/` 内文件。完整绝对根：`C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/`。

| 层次 | 已实现/可达证据 | 边界与缺口 |
| --- | --- | --- |
| 产品入口 | `production_server.py:92–122` 正常模式构造 live service，使用 live_spatial_mcp；legacy 需显式 `--demo`。`live_spatial_mcp.py:838–868` 调 `service.observe`。 | 不能把 `plugin_facade` / 旧 MCP 门面的能力直接算进 ordinary live。 |
| 原生图像默认分支 | `live_service.py:560–601` 默认 `native_visual={mode:auto,view:SCENE}`；已建立 distinct pair 且宿主支持时选原生。`1113–1120` 将投影 `include_image` 设为 false，`1195–1218` 另交付原生图像。 | 默认图像不经过 Q4 attention、投影标签恢复和 local_view。无 pair 时不能启用 native multiscale（`576–580`）。 |
| 投影四视图 | `scene_rendering.py:853–932`：紧凑场景 XY/XZ/SCENE/TARGET；场景半径超过 focus 半径 4 倍时切导航图+工作区双视图+目标图。所有 supplied meshes 参加深度。 | 是固定布局加目标拟合，不是全场区域探索。没有 pair 时 ordinary 显式 `attention=hold/contact_pair_not_established`（`live_service.py:1136–1141`）。 |
| 投影主动相机 | `auto_router.py:1240–1267` 真正调用 `apply_attention_to_canvas`；`attention_policy.py:232–335` 从当前已测 clearance/witness 生成候选。 | 只为已知 focal 的正间隙段改善屏幕采样；不是对未知异常、孔、凹槽等全场结构生成候选。 |
| 遮挡和可读性 | `attention_rendering.py:498–516,555–586` 先全场 ray 检查，再真实 depth/owner/RGB；`attention_policy.py:519–548` 不足则不采用。`attention_raster.py:118–145` 对全部输入网格逐顶点/三角形投影与裁剪。 | 证明范围是两个 witness 及局部表面，不是全 ROI 可见、更不是模型正确识别；没有通过外围几何 LOD 来减少全场几何成本。 |
| 防抖/驻留 | `attention_policy.py:24–38` 默认 1 秒 dwell、切换成本、40ms 额外预算、24 候选；`335–436` 根据旧相机与当前 witness 保持 focus；`551–558` 只保存当前相机/时刻/签名。 | 这是单个 focus 的 hysteresis，没有全场 visited region/novelty/尚未解决任务项队列。重复调用不会因“此处已经看懂”自动转下一处。 |
| 图像交付 | `live_spatial_mcp.py:697–726` 把 PNG 放入真正 MCP image block，原生验证 384×384、最多 2 张，不把 base64 重复塞文本。 | 这证明接口能交付图片，不能证明 provider 接收、模型注意了图片、图像提高正确率或减少总成本。 |
| 场景暂留 | `scene_cache.py:133–169,296–375` 有内容寻址快照、变更分类、默认16帧与256测量；router 实例使用2MiB（`auto_router.py:567`）。`scene_cache.py:408–444` 同 ordered mesh pair+算法版本+参数复用成功测量。 | 记的是几何/数值结果，不是任务假设、已见表面、视角覆盖、解释证据的累积。`estimated_saved_ms` 是缓存记录估算，不等于整任务墙钟收益。 |
| 宿主驻留与增量 | `blender_host.py:536–667,1128–1132`；`scene_residency.py:24–100`；`blender_mcp_host.py:495–497`。 | 是真实可达的工程能力，不能笼统说“每次全量 to_mesh”。但视觉旁路不使用它，详见下文。 |
| 变化失效 | `scene_residency.py:33–69` depsgraph geometry dirty、undo/redo/load reset、context/epoch；`blender_host.py:588–645` resource stamp 与 pose 分离。`scene_delta.py:127–185` 文档身份/完整性不满足则 full resync。 | 不同层失效粒度不一致：`ReadContext.activate` 在 generation 变化时清全部 selection/results（`read_context.py:40–54`）；全 observation key 包含完整 scene fingerprint（`auto_router.py:798–803`）。未变化的 pair measurement 仍可能命中，不能说全层都重算。 |

`human_eye_spatial_relations` 和 `human_eye_surface_nearest` 在 `live_spatial_mcp.py:843–849` 明确转为 `include_image=false`；task query 同样要求无图片（`live_service.py:1062–1066`）。这条事实路线可能很有价值，但其消费收益不会验证原生/投影视觉扫视。

## 三个主要架构发现

**1. 主动“看清当前已知间隙”已实现；主动“接下来该看哪里”仍缺任务闭环。**

投影 attention 的输入是已有的 `scene_contacts`，不是新发现或模型不确定性。它要求 `measurement_valid=true`、严格 clearance > 0、见证距离一致，并拒绝间隙大于较小对象 extent 的25%；参考对象优先、之后按距离排列，最多考察4个 contact（`attention_policy.py:295–335`）。候选是固定方向及补充 contact-frame 方向，以 capped projected gap gain 减切换成本排序（`328–334,377–435`）。该设计有真实预算、遮挡和确认机制；但它优化的是一条已解间隙在图上的采样，不会决定全场哪些对象/区域尚未被解释。

当前最小持久 attention state 只有 focus_key、last_shift、camera_plan、签名及增益（`attention_policy.py:551–558`）。`scene_cache` 不存已观察区域/视角覆盖或待判定假设，native plan 也不接收 previous observation。故“下一眼”的依据至多是当前像素收益/前相机，不是累计任务证据。拒绝遮挡候选后有局部尝试/hold，未发现基于跨调用覆盖自动选择新区域的 ordinary 调度链。

另外 `visible_refill.py:193–202,460–500,553–555` 的候选补充是同优先级对象在当前已渲染视图中的标签补位，`local_view.py:165–301` 是指定 visual focus 的可读性局部窗口。它们改善单次显示，不能当成跨观察扫视与记忆融合。

旧代码的 `SpatialScratchpadRingBuffer`、`SphericalIoRMultiLocusSniffer` 确实存在于 `human_eye_foveated_renderer.py:2922,3293`，调用见旧 `module_2_low_token_mcp_scene_bridge.py:1418,1481–1506` 与 `plugin_facade.py:100,149,274`。但当前 `scene_rendering.py:1–5,36–46` 明确只复用 legacy surface rasterizer，不用旧相机、X-ray/shared pools；当前 production 默认 live 也不经 legacy facade。因此这类旧类名不能补足现行普通入口的闭环证据。

**2. 原生多尺度不是通用多视角扫视；默认 SCENE 的密集物体局部窗口覆盖尤其有限。**

实际 native planner 是 `blender_host.py:2452` 的 `plan_readonly_dense_focus`，按 V1→V2→V3 扩展：

- V1 `episode_gateway.py:606–664`：固定请求 view 的全景+最多一个同向 detail；384×384，最多2图。只对 focal 为3–64顶点、1–128三角的对象计算 projected minimum edge-normal width。全景 feature <12px、zoom≥2、detail≥32px且中心 ray 确认为 focal 才补图。遮挡/unknown 则保留全景，没有换方向继续扫。
- V2 `episode_gateway.py:667–727,756–780`：V1没有补图且 reason为 overview_sufficient 时，只对严格8顶点/12三角的轴对齐盒 pair、小于1px的正间隙加跨视图窗口；gap axis 决定 XY/XZ，三个 ray sample，不是任意几何异常的全视角搜索。此分支最多6×全场三角测试预算4096、顶点4096。
- V3 `episode_gateway.py:822–890`：只有 V1因 focus_budget_exceeded、且用户请求 view∈{XY,XZ} 才尝试密集 focal 的 projected bounds 窗口；全场 2×triangles≤4096、vertices≤4096；仍只有中心 ray。质量标注明确是 bbox opportunity，不是 thin section 或完整可见性。

默认 view 是 SCENE（`live_service.py:562,610`）；其方向固定为 `(1,-1,.75)` 归一化，另两个固定轴向见 `episode_gateway.py:466–488`。因此密集焦点在默认 SCENE 下不能获得 V3，通常退到一张全景；这不是提高max_candidates就能解决的投影 attention 问题。应先分清实际交付分支，再评价局部放大覆盖。

当前能确认的多尺度是多个不同取景范围的独立窗口；没有在这条 ordinary pipeline 中看到随偏心距渐变的外围模糊、连续中心凹分辨率分配或几何 LOD。投影 raster 的裁剪与预算拒绝不等于 LOD。外围模糊是否改善模型消费也没有本轮实测，不能用“模仿人眼”直接推出收益。

**3. 普通采集已有增量，但默认原生图像存在完整采集旁路；缓存命中不代表免重拍。**

普通 `capture_scene()` 调 `_capture(_resident=True)`（`blender_host.py:1128–1132`），静态完整 capture 可直接命中（`574–577`）。仅 resource stamp 变化才 `to_mesh/calc_loop_triangles`（`593–625`），仅 pose 变化才做 world transform（`632–645`）。MCP host 持久宿主接入后执行 resource delta（`blender_mcp_host.py:445–497`）；wire 只传缺少revision的资源（`scene_residency.py:75–100`），decoder按resource/matrix/scale复用世界坐标（`155–170`）。这部分是接通的。

但 `capture_readonly_evidence()` 调 `_capture(_native_evidence=True,_read_only_native=True)`，未设 `_resident=True`（`blender_host.py:1770–1782`）。`_capture` 的 `_resident` 默认false（`808–809`），因而原生证据走全对象 evaluated mesh、triangulate、顶点变换、原始/求值拓扑比对（`843–895`），不能享受上面的几何驻留。

成功的 `observe_readonly_native` 内：开始采一次（`2437`）；每个 frame 在 `_readonly_render_view` 中渲染前/后各采一次（`2370,2375`）；所有frame结束再采一次（`2470`）。因此该方法可见成功路径是 **2+2×N 次完整 readonly evidence 采集**：N=1时4次、N=2时6次；另外 ordinary observe 最初还有一次可驻留的 `capture_scene`（`live_service.py:1092–1095`）。这只是源码调用计数；未新测每次成本，未断言每次间隔/采集全部可删除。

`live_service.py:1195–1201` 不因 router `cache_hit=true` 跳过 `_read_native_visual`；原生PNG和plan只在 `_save` 后挂到 detached delivery，不进缓存（`1191–1208`）。因此对同一静态场景重复图像请求，底层测量可命中，而原生图像仍重新规划、渲染与验证。这样做保留了当前一致性和恢复证据，优化必须提供等价的新鲜度/恢复验证，不能直接删检查。

用户显式 `scene_delta` 的 `make_scene_delta` 在 complete current scene 已取得后才执行（`live_service.py:1233–1245`）；这是另一层返回包优化，与宿主 resource delta 不同，不能当成省掉原生采集的证据。

## 最小算法改进顺序与验收

建议唯一主路线是把现有能力接成“粗扫发现—按缺证据选下一眼—精查—更新累积证据”的一条普通观察循环；先不增加一套独立视觉框架，也不以外围模糊为首要目标。

1. **先统一一次观察的场景版本与图像分支。** 以现有宿主 resident snapshot/resource revision 为本次读取的共享基础，几何事实、视角规划和原生render验证引用同一受控版本；将完整证据重建拆成内容资源验证和每次新鲜度/状态恢复验证。先测 native 4/6次旁路的分项成本与重复比例，再决定哪些可在同一只读lease中安全共用。验收包括静态重复、只移一个对象、修改拓扑、undo/load、渲染异常后恢复；记录 `to_mesh/triangulation/transformed vertices/full evidence captures/PNG`，不能只看最终cache_hit。
2. **在现有 read context 增加一个小的任务观察状态。** 最少保留 `{object_or_region, task_question, evidence_refs, visible_views, unresolved_reason, dependent_resource_revisions}`；几何变更使依赖证据失效，普通无关metadata变化不必清所有任务项。其用途是明确“已回答什么/还缺什么”，不是把历史图像当实时几何。先用现有目录、bounds、关系/最近点候选；不要要求用户先给 focal/reference 才能发现下一处。
3. **用未解决证据的预期减少量选择下一眼。** 将现有投影候选方向、native XY/XZ/SCENE/局部框统一为候选动作；粗评 `任务相关性×新可见面积或待判定项覆盖×预计辨识增益 −采集/渲染/模型消费成本−重复视角惩罚`。遮挡候选用bounded depth/owner采样筛选；本次未见、被挡住、尺寸不足分别处理。已有dwell防抖可复用，但完成一个问题后应允许转向，而非永远保持最大gap-pixel收益的同一focus。
4. **只在几何事实不足时生成图，并融合交付。** 若三对关系已充分，直接交付事实；若任务缺的是凹槽/材料/遮挡解释，交付相关局部图+明确对象/区域映射+已知与未知证据。达到充分性、预算耗尽、无可用增益时结束。先完成这条闭环，再评估外围降采样/模糊/LOD能否降低真实成本；几何精测应仍引用原分辨率资源。

每步先做算法级分项测量，再用未见任务做完整模型消费对照。最小有效门槛是：无预给目标时候选召回/遗漏率；连续观察是否转到真正未解决区域；增加/移除遮挡后能否失效并补看；重复静态请求的完整采集/渲染次数；模型能否准确定位和解释；完整墙钟、总输入输出、图像数/像素预算及错误后补查都记账。像素间隙增大、cache命中、软件单测通过只能作为中间指标。

## 既有模型结果能证明什么

已读取 `D:/hefe/docs/M4_OBSERVATION_BASELINE_001_REVIEW.md` 与 `D:/hefe/docs/M4_SPATIAL_FACT_CONSUMPTION_001_REVIEW.md` 的相关段落。前者是较早产品 `107641ec...` 的28网格找目标/关系/解释任务：初图相同，新增图片0，`64`行明确未做主动视觉实验；`72`行还保留provider接收/认知使用图片未知。其完整耗时中位数插件53.7364秒、原生52.6611秒，质量两组3/3；不能将这些数值归因到当前native旁路，也不能据此断言视角算法无效。

后者固定产品就是 `e836e03f...`、137源摘要 `2c453e56...c390`（`9`行）；空间事实消费任务报告57.93%中位时间改善、45.01%累计token改善，但`40`行明确为合成题每组三次、零图片，不覆盖人眼视觉能力。它支持事实消费价值，不证明自主扫视已完成，也不能抵消本审定位的图像路径缺口。旧COMPLEX-005由另一子审负责，本报告不另引用其结论。

本审完成的是静态可达性与架构边界核对。任何改进的分段提速和整任务净收益仍待以后授权测量；当前没有依据宣称新增视觉能力已经被模型有效消费。
