# 共同原生入口与任务总账候选（2026-10-31）

本批新增77源码候选，build `sha256:27c2ff862f47fe9656b862c8f2f3ced0dde3080367e19a0a8ee7d3e7bc246062`，SDK目录为 `.human-eye/releases/9.7.2+20261031.common.gateway.candidate.r1/`。当前聊天仍运行既有b77/76，身份和健康已核对；本批未激活新MCP入口。

旧目标账本按goal核算，未注册的普通原生移动没有共同episode总额。新增 `episode_gateway.py` 在每个实际setter旁记录完整原生before/after；同一原始pair、QPC截止、步数/步长/累计路径跨native与auto共用，目标关闭或新调度都不能重置。每次前进保留原预算内回退槽及路径，因此8次硬上限下第8个普通前进会被拒绝以保留回退容量；两组遵守相同规则。回退本身同样耗槽与路径，完整记录且失败仍冻结。

原目标截止和原episode截止均在赋值旁复检。reserve与复制之后到期会取消两层预留，保留已消耗的预留身份，实际setter为零；不会为“恢复”进行未进入赋值的多余回退。确认失败的原生姿态不可用时保留unknown，不能把进程退出后的缺失轨迹计作零。

新typed入口提供原始native query、真实Blender Workbench384三视角图、显式世界Z移动和episode状态，无通用Python执行或路径参数。`verification/model_trial/common_owned_gateway.py` 对A2/C2提供逐字相同的原生四工具（query/look/compute/transform）；C2另有无参数的已注册任务入口。原生计算继续运行相同受限数学解释器，在独立进程使用相同perf_counter原截止，启动/发送/计算/结果验收均计时。

任务的原支撑三角形、方向与目标对两组同样公开，不从私有评分器单独给C2答案。原始task与initial evidence一直保留；auto在本episode剩余预算内派生更紧限额，并重新取实际当前证据。调用者不能提供新的event、auth、budget或deadline。未知结果、坏计量报告或未决goal会阻断后续各写入口；普通native也不能绕过未关闭的自动goal。

原生PNG实际含文件路径及时间元数据。公共wrapper现校验CRC和结构，只保留像素、透明度与必要颜色chunk；剔除文本、EXIF、时间和未知ancillary。RGBA/IDAT及palette透明度测试保持。当前Workbench支持域中ICC图明确拒绝，不能宣称任意PNG/ICC净化。私有原生证据和异常只留owner侧。

| 本批验收 | 结果 |
| --- | --- |
| 最终回归 | 1340项运行，1339通过，1既有WinError1314符号链接权限跳过 |
| 新增独立测试 | 43项：22个episode/host边界与21个common接口/PNG边界，包含在总回归中 |
| 共同初态 | A2/C2完整公开几何、任务及四工具schema完全相等；XY/XZ/SCENE三种实际native图的解码RGBA完全相等 |
| 合理原生基线 | 原生组仅用共同公开scene经原有baseline_program与受限计算求解，4个实际setter达到0.0010000057573859179m |
| 自动组质量 | 同一公开任务及初态，4个实际setter达到相同原生间隙；每setter链、13个非平移矩阵值、XY、局部网格及非目标保持 |
| 混合路由 | 原生前缀→自动任务→原生后缀，共6个setter在同一episode中；后缀故意改变最终间隙，此case只证明路由与计量 |
| 预算边界 | 7个native setter之后第8个前进拒绝，auto没有补发新预算；原episode、截止与累计路径不变 |
| 只读边界 | 在支持域的未锁定静态场景上，可信owner read_only令两写入口零移动 |
| 丢回执 | 真setter后owner丢弃回执，owner见1次，engine计数null；wrapper两route及直接typed native均阻断 |
| 独立原生复核 | 10组验收及额外1565条细粒度raw检查；不把后者当作测试方法或模型样本数 |
| 生命周期 | 接受的6个场景、12个自有进程均exit0并回收，输入blend字节保持 |

保留失败：首轮harness误解compute的result envelope，零移动；第二轮三case通过后在锁定资产的严格原生证据捕获入口拒绝，8进程回收。新run003改为显式owner只读测试，未放宽生产原始证据条件，也不将锁定资产启动读路由计为通过。另保留早期回退状态转换失败及修复、PNG元数据反例和审查脚本错误。

这是有限two-box、固定支撑面、世界Z终态域的共同入口工程验收。完整渲染属性/相机/选择状态的实际回读恢复尚未保存，现只有代码审查和真实geometry前后不变；锁定资产的只读启动证据入口仍不支持。其他复杂资产、泛化三维路径及真实模型收益未验证。公共wrapper继续保留formal_eligible=false，不能用本批脚本对照宣布模型巨大提升。

下一顺序：补锁定资产typed只读启动证据与完整renderstate前后回读；加入密集/遮挡/不同尺度等共同fixture并核验原生基线可达性；再固定launcher/安装接入与provider/usage/总费用/实际截止合同。学习先验和增量变形仍按原路线独立推进。

本批未重试上轮被拒的缓存删除；原b77目录含其原85文件和3份生成缓存，全部原字节保持。新candidate禁止生成引擎pyc，当前目录80文件一致。旧A/B/C与原owner bridge、生产配置、历史state和先前sealed阶段保持。

证据：[本轮目录](../verification/fixes/20261031_v21_common_gateway/)、[接受配对](../verification/fixes/20261031_v21_common_gateway/owned_work/run_003/RESULT.json)、[真实边界](../verification/fixes/20261031_v21_common_gateway/owned_work/boundary_001/RESULT.json)、[独立验收](../verification/fixes/20261031_v21_common_gateway/acceptance_work/FINAL_REVIEW.json)、[raw复核](../verification/fixes/20261031_v21_common_gateway/review_work/RAW_ARTIFACT_REVIEW.json)。
