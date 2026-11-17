# M6-CALIBRATION-TRANSFER-007 交付报告

2026-11-17。固定起点 `d7cbbac89389ee6f7bfbac8fb45de3ff348abbe0`，固定合同 `b4694efa2805ce43751d3ae5a65f01110208f46c`。本批新增 `verification/m6_calibration_transfer_007/`，固定提交身份及提交后一次规划回报、AL 交付见 HANDOFF。

## 本例结果与阶段决定

一份新真实 Pro 提案成功保存、独立回读并预览。冻结 006 V2 对该提案完成 α={0,0.5,1} 实际校准，图像选择 α=0.5。三个候选技术 QA 均通过，三个候选独立恢复均失败。raw α=1 的支持 RMSE 下降 13.484804%，所选 α=0.5 下降 12.413144%，均低于 30% 门槛。正常可编辑 231 点误改 RMS、p95、max 均为 0。

半幅相对 raw 的 RGB 目标下降 9.972053%，支持 RMSE 增加 1.238696%。本例技术迁移验收通过，恢复应用验收失败，独立几何质量增益未成立。后续决定建议先独立复核图像排序与支持点几何排序的分歧，再决定验证范围。 [STAGE_DECISION.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_calibration_transfer_007/STAGE_DECISION.json>)

## 来源、单位与隔离资产

按 DATA001 索引原顺序首个 validation、candidate_valid 且 usable_for_training 的 pair，固定 `cat_reference_roi0_c0_r0_a0_pair`。来源组为 cat_transfer，与 Yanyite 来源组不同，曾用于此前验证。该例属于外资产迁移个案。七个原来源文件按规划完整 SHA 绑定核验。完整网格 7207 点、14410 三角，F384、局部713三角/1096边、B0=53、B1=57、I274。私有支持43点全在I，正常I231、正常F341。 [PLANNING_PREFLIGHT.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_calibration_transfer_007/PLANNING_PREFLIGHT.json>) [SOURCE_INPUT_BINDING.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_calibration_transfer_007/SOURCE_INPUT_BINDING.json>)

源单位为 source_native，物理长度未标注。合同固定 ell=0.002567906610453878，单次及累计预算均取 ell。正常I位移 RMS 上限为 0.014506080599458708ell，即 0.00003725026026312677 source-unit。所有误差与位移分布同时列 source-unit 及除以 ell 的数值。历史 `_m` 字段名在适配器中保留并注明实际单位。

构造端通过原 data_io.read_current 重建完整正常/当前网格，分别构造独立中性 blend，保存后由独立 Blender 进程 fresh 导出。模型收到的 V0、法向、拓扑和事实来自实际受损文件。评分目标取新正常模型实际回读。两资产源到 float32 保存的单坐标最大误差均为 1.4890670752e-8，欧氏 RMS 分别为 7.6792500038e-9 和 7.6796496088e-9 source-unit。实际保存后的当前 ell 为 0.0025679066101832048，合同预算继续使用预先固定值。

隐藏正确目标控制真实提交、保存、fresh 回读，控制原生坐标与实际正常模型逐位相同，22 项保护及接触检查通过。控制最大位移 0.00039800950783226165，小于固定预算。目标、支持、源生成参数及构造读取器均保留在消费者隔离范围外。 [ASSET_PREPARATION.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_calibration_transfer_007/ASSET_PREPARATION.json>) [SCORING_BINDING.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_calibration_transfer_007/SCORING_BINDING.json>)

## 当前几何相机与图像

三局部相机在新 Pro 前由实际当前 F 冻结。中心为 F 均值，正交尺度为 1.5 倍 F bbox 对角线。主方向为当前 F 单位顶点法向均值的单位向量，切向取最大绝对分量正号的 PCA 第一轴投影至法向切面并归一，另两方向取 (n±u)/sqrt(2)。距离由完整当前 bbox 确定。整体加三局部的正常/当前八张真实图均为640×640，使用同一 Workbench 着色/光照。旧重例预览另为历史来源。

实际相机均值、法向、符号 PCA、尺度、距离已独立重算，normal/current 相机字典相同，F 全部384点投影落在局部640²范围。图像度量只使用三局部图，覆盖全部 3,686,400 个 RGB 标量。初态 RGB 绝对和为192170。 [CAMERAS.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_calibration_transfer_007/CAMERAS.json>) [IMAGE_BINDING.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_calibration_transfer_007/IMAGE_BINDING.json>)

## 唯一新模型与原提案

实际请求 gpt-6.1-sol medium，一个会话，用时 202.3151511s，完成11/12次工具调用，600秒上限内完成。工具为 images、focus、7次 execute_python、submit_edit、images。七份原始 CODE 与全部工具输入输出留存。模型从实际图片将部位识别为动物足部中央趾垫，F/I 为提供的范围。模型最终自评为局部视觉改善、完整恢复 incomplete/unknown。 [原回答](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_calibration_transfer_007/private/consumers/raw/sample_07/facts/PUBLIC_FINAL.txt>) [CONSUMER_AUDIT.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_calibration_transfer_007/CONSUMER_AUDIT.json>)

模型实际使用当前图像对应和像素差，检查外部支持后，以31个低图差、朝前的支持点拟合二次 y(x,z) 曲面。最终31点支持全在I，rank6，condition24.74599107785905，拟合残差 RMS 0.00012824162492077558 source-unit。模型自行选取0.75增益、世界−Y轴，提交13点位移。raw提交技术检查通过，实际独立进程回读与四视图预览均完成。

源正常坐标的1e-6十进制格点线索以及规划1e-9阈值诊断 TP43/FP0 为已知来源限制。完整实际 CODE 未使用格点反演，np.round用于打印坐标。图像、当前几何和模型拟合共同参与了本提案，单例的普遍感知优势保持未测。实际消费者26次文件访问事件均允许，0次拒绝。独立预检对私有正常路径的拒绝记录属于隔离测试。

原始13点世界位移载荷按原字节冻结，SHA256 `8a0331d51769afae668223ff95a491f0308737301f27f575233d665c04d81d80`。canonical世界位移副本与模型原载荷字节相同，保存 float32 重构逐位通过。raw 即 α=1。独立执行的校准 α=1 与 raw 的完整回读九字段、原载荷、相机和三张 RGBA 相同，比较17/17通过。 [PROPOSAL_FREEZE.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_calibration_transfer_007/PROPOSAL_FREEZE.json>) [RAW_CALIBRATION_COMPARISON.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_calibration_transfer_007/RAW_CALIBRATION_COMPARISON.json>)

## 冻结组件和实际校准

006校准17项源中15份保持原字节，calibrator仅改批次/提案来源说明，协议客户端接受新提案名称。005图像对应数学、DN2、raster/tie规则、69点核心预算和0.032支持半径数值保持，当前I仍274，因此69/274比例相同。半径在本例解释为 source-native 数值。对象surface、资产引用、相机job.views、源单位和中性模型任务通过既有接口适配。23份执行源均在Pro前封存原/新身份及差异。 [ADAPTATION.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_calibration_transfer_007/ADAPTATION.json>) [CONSUMER_ADAPTATION.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_calibration_transfer_007/CONSUMER_ADAPTATION.json>) [PRE_PRO_FREEZE.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_calibration_transfer_007/PRE_PRO_FREEZE.json>)

实际协议客户端调用 V2。一个拥有的 Blender 进程完成三候选，每个候选从同一个受损初态载入，每个写/读/渲染步骤均从磁盘重开实际文件。V2 回读为同PID fresh_disk_reopen。历史 reader 首行 fresh-process 文案勘误记录在适配说明中。三个系数、世界位移形状、完整RGB目标和精确平局小alpha规则按合同执行。

选择器只使用技术可用状态和图像整数绝对误差和，归一分母为实际 α=0。选择已冻结，随后独立 Pillow 重算三图整数目标并读取私有正常几何/支持。α0误差为0时ratio未定义的路径由预检覆盖，本例分母为192170。 [IMAGE_SELECTION_FREEZE_v2_raw_proposal.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_calibration_transfer_007/IMAGE_SELECTION_FREEZE_v2_raw_proposal.json>) [CALIBRATION_SCORES_v2.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_calibration_transfer_007/CALIBRATION_SCORES_v2.json>)

|α|RGB绝对和|pooled MAE DN|归一误差|front / side / 45° 绝对和|技术|图像选中|恢复|
|---:|---:|---:|---:|---:|---|---|---|
|0|192170|0.052129448785|1.000000000000|70026 / 67836 / 54308|pass||失败|
|0.5|187160|0.050770399306|0.973929333403|70713 / 64588 / 51859|pass|是|失败|
|1|207891|0.056394042969|1.081807774366|78664 / 66332 / 62895|pass||失败|

各单视图分母为1,228,800。各视图 MAE 和原始RGB数组在校准结果及每候选 image_measurement/RGB.npz 保留。

## 私有几何质量与保护

恢复须同时满足 S43 RMSE 下降≥30%、F384 RMSE严格下降、正常I231位移RMS≤0.014506080599458708ell。下表每格为 RMSE / p95 / max，左表采用source-unit，右表除以ell。正常域采用对实际正常模型的误差，本例与误改位移相同。

|α|支持43 source-unit|观察384 source-unit|正常341 source-unit|正常I231 source-unit|TP / FP / FN|
|---:|---:|---:|---:|---:|---:|
|0|0.000191901669301 / 0.000371257660085 / 0.000398009507832|6.42166089316e-05 / 0.000138152463691 / 0.000398009507832|0 / 0 / 0|0 / 0 / 0|0 / 0 / 43|
|0.5|0.000168080638504 / 0.00030955308559 / 0.000375259348556|5.62453087099e-05 / 0.000117145938362 / 0.000375259348556|0 / 0 / 0|0 / 0 / 0|13 / 0 / 30|
|1|0.000166024104442 / 0.000297764033263 / 0.000375259348556|5.55571247867e-05 / 0.000138484365839 / 0.000375259348556|0 / 0 / 0|0 / 0 / 0|13 / 0 / 30|

|α|支持43 /ell|观察384 /ell|正常341 /ell|正常I231 /ell|
|---:|---:|---:|---:|---:|
|0|0.0747307820776 / 0.144575997653 / 0.154993762706|0.0250073770869 / 0.0537996448659 / 0.154993762706|0 / 0 / 0|0 / 0 / 0|
|0.5|0.0654543423892 / 0.120546862697 / 0.146134344227|0.0219031753261 / 0.0456192362622 / 0.146134344227|0 / 0 / 0|0 / 0 / 0|
|1|0.0646534822434 / 0.115955943277 / 0.146134344227|0.0216351811863 / 0.0539288949509 / 0.146134344227|0 / 0 / 0|0 / 0 / 0|

所有候选保持源ID、域外原生float32、拓扑、矩阵、UV/材质和其他场景对象。新退化、翻转、新额外接触对和关系变化均为0。非零half/full各执行完整关联域精确接触对扫描，alpha0以相同实际几何与三角数组验证。raw与隐藏控制分别完成各自技术/接触检查。

|α|最大位移 source-unit /ell|incident梯度 RMS / p95 / max|边界梯度 max|边长应变 RMS / max|
|---:|---:|---:|---:|---:|
|0|0 / 0|0 / 0 / 0|0|0 / 0|
|0.5|0.0001882747747 / 0.0733183885792|0.0254601055 / 0.0204705738 / 0.361860124|0|0.0124587702 / 0.0843994936|
|1|0.000376549549401 / 0.146636777158|0.0509201606 / 0.0409413757 / 0.723718919|0|0.0205643619 / 0.178199781|

完整评分还列world X/Y/Z分量的支持/观察/正常/正常I误差及位移RMSE、p95、max和/ell值，以及F三维bounds。技术过渡指标为观察量，恢复门槛按固定三条件执行。

## 成本与失败恢复

|执行路径|墙钟 s|tree CPU s|峰值tree RSS B|
|---|---:|---:|---:|
|同一Pro生成与raw保存/回读/预览共同前段|202.696097400|18.796875|631959552|
|固定V2冷校准增量|13.506759300|13.078125|547766272|
|共同前段加校准|216.202856700|31.875000|631959552|

独立资产构造、匹配图片、隐藏控制和中性输入准备为两条路径共享准备。资产首次准备监控6.1311761s、重试7.3680074s，中性输入准备按COSTS记录，单列保留全部失败。预检、私有评分及实施审计成本另列，其嵌套时间按作用域保留。实际客户端完整路径的raw前段包括模型工具中的3个Bpy，校准增量包括其批进程及RGB测量。

本批新增Pro恰为1，input365804、cached322944、output4443、reasoning1746 tokens，缓存量为input子集。11个实际模型工具全部成功，7次实际CODE执行全部成功。原始图与保存后预览通过实际MCP图像块交付。新增训练、Google/API、正式部署均为0。费用、resolved backend/effort、供应商内部重试以及全任务CPU/RSS、根/协作模型用量保持unknown。

新增12个Bpy进程，资产与隐藏控制8、raw3、校准1。按逻辑操作计，资产8、raw3、批处理9，共20。物理进程脚本分布为build2、read4、render3、edit2、batch1。12进程均完成，进程墙钟18.2728183s、tree CPU10.671875s、最大tree RSS432,431,104B。批处理资源按一次进程累计，9步增量保留。全客户端tree RSS还包含数值解释器与CLI进程。

校准RGB冷解码12张、缓存命中6次，解码14,745,600B，缓存峰值14,745,600B。PNG解码、压缩RGB归档、真实协议序列化及各worker均在原计时层级记录。该冷调用表示本次请求候选/解码缓存初始为空，OS缓存状态未测。007为冻结组件迁移验证，首版对照和再次优化保持未运行。 [COSTS.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_calibration_transfer_007/COSTS.json>)

第一次资产准备在完成4个真实build/read后，np.float32标量写JSON报错。显式float转换后，重试先核身份复用这4个完成作业，再执行剩余4个，失败日志保留。前置消费者预检因路径fallback核验做了一次最小适配并重复预检，均未启动Pro。部分只读路径猜测失败及成本范围见实施记录。消费者最后bridge记录closed=false，实际CLI退出0且已reap，独立最终进程扫描为0个本批进程。 [ASSET_IMPLEMENTATION_COSTS.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_calibration_transfer_007/ASSET_IMPLEMENTATION_COSTS.json>) [CONSUMER_IMPLEMENTATION_COSTS.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_calibration_transfer_007/CONSUMER_IMPLEMENTATION_COSTS.json>) [FINALIZATION_COST_NOTES.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_calibration_transfer_007/FINALIZATION_COST_NOTES.json>)

## 入口与交付

从仓库根运行实际冻结校准入口，精确相同输入将复用绑定结果。

```powershell
verification/m6_shape_train_001/private/venv/Scripts/python.exe -I -B -X utf8 verification/m6_calibration_transfer_007/protocol_client.py --stage v2 --proposal raw_proposal
```

运行适配预检23/23、模型桥接预检59/59、实际新输入/访问隔离预检11/11、native单位评分fixture11/11、私有评分完整性10/10、raw/alpha1比较17/17均通过。最终交付核验280/280通过，覆盖全部实际身份、源码归档、图像先冻结、协议入口和进程清理。 [DELIVERY_VERIFICATION.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_calibration_transfer_007/DELIVERY_VERIFICATION.json>)

范围为一个曾用validation外资产、一份实际新模型提案和三个预先固定系数。三个采样值恢复失败的结论按本采样范围成立。连续系数、跨资产平均收益、原生/插件普遍优劣保持未测。组件技术迁移通过与独立恢复失败分别记录。

本地新增证据由MANIFEST完整清点，旧数据集、005/006执行源码按固定来源引用。Git包含本批根层公开源码/计划/结果，私有模型/图/执行证据按本地清单归档。MANIFEST排除自身及提交后HANDOFF。旧reader的freshprocess文案及继承session_api EOF空行按原执行字节记录。默认Git格式检查返回2并报告CRLF相关提示与EOF空行，cr-at-eol检查返回2且仅报告该EOF空行；具体数量记录于提交后HANDOFF。 [MANIFEST.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_calibration_transfer_007/MANIFEST.json>) [HANDOFF.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_calibration_transfer_007/HANDOFF.json>)

### 实际工件

- 原提案 α=1，[模型](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_calibration_transfer_007/private/sessions/raw_sample_07_facts/versions/001/model.blend>)，[fresh回读](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_calibration_transfer_007/private/sessions/raw_sample_07_facts/versions/001/independent00/readback.npz>)，[原载荷](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_calibration_transfer_007/private/proposal/world_delta.npz>)
- 图像选中 α=0.5，[模型](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_calibration_transfer_007/private/sessions/v2_raw_proposal_a05/versions/001/model.blend>)，[磁盘回读](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_calibration_transfer_007/private/sessions/v2_raw_proposal_a05/batch_attempts/read00/readback.npz>)，[current_forearm_front](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_calibration_transfer_007/private/sessions/v2_raw_proposal_a05/batch_attempts/render00/images/forearm_front.png>)、[current_forearm_side](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_calibration_transfer_007/private/sessions/v2_raw_proposal_a05/batch_attempts/render00/images/forearm_side.png>)、[current_forearm_45](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_calibration_transfer_007/private/sessions/v2_raw_proposal_a05/batch_attempts/render00/images/forearm_45.png>)
