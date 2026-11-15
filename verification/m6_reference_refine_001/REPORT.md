# M6-REFERENCE-REFINE-001 原画前臂对应

本批按固定合同的不确定度分支完成原画、真实模型与sourceID对应。当前标注尚不能稳定决定前臂外展或收窄。

## 实际测量

| 肘腕站 | 原画外距/EW | 模型外距/EW | 模型减原画 | 原画宽/EW | 模型宽/EW |
|---|---:|---:|---:|---:|---:|
| 15% | 0.195714 | 0.186156 | -0.009558 | 0.377532 | 0.389379 |
| 35% | 0.195714 | 0.178028 | -0.017687 | 0.368442 | 0.369480 |
| 55% | 0.167143 | 0.156035 | -0.011108 | 0.294416 | 0.289821 |
| 75% | 0.138571 | 0.124536 | -0.014035 | 0.228571 | 0.222167 |
| 90% | 0.120455 | 0.109091 | -0.011364 | 0.200000 | 0.189358 |

主标注原画E=(707,520)、W=(752,695)，模型局部E=(282,126)、W=(354,421)，仅用EW相似变换。五站平均外距误差为肘腕长的1.2750%。3个原画像素的保守边界项为1.6603%，原画与模型分别81组合理锚点情景的残差敏感性区间在五站均跨0。这些是手工定位敏感性，统计置信度未测。

27组颜色阈值检查的边缘最大位移约1.03原画像素。另一名agent在看不到前组坐标和位移方向时独立选点，原画E=(708,524)、W=(751,678)，模型E=(274,140)、W=(350,393)。该对应的五站外距残差均为正，平均绝对误差1.4450%。两套腕前位置存在纵向分歧，锚点由agent视觉标注，用户尚未确认。

主标注35%站的内外轮廓同向偏移，宽度仅差0.001038EW。轴线或姿态对应可产生这种投影差。当前证据支持先交付可核查对应，进一步单侧形变的方向需要更明确的锚点依据。

## 模型与真实图

[完整对应模型](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_reference_refine_001/private/results/corresponding_model.blend) 的SHA与原始模型一致。599点前臂观察域、五站截线与原生polygon/sourceIDs的重心坐标映射已保留，最近可见E/W源点为24321与16916。独立边截法复算五站外距及宽度，24项来源/坐标/保护/引用检查通过，实际focus和resolve各1次。

[整体对应图](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_reference_refine_001/private/annotation/whole_front_source_mapping.png)、[局部对应图](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_reference_refine_001/private/annotation/forearm_front_source_mapping.png)、[同尺度轮廓叠图](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_reference_refine_001/private/annotation/similarity_contour_overlay.png)、[侧面](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_reference_refine_001/private/views/before/forearm_side.png)和[45度](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_reference_refine_001/private/views/before/forearm_45.png) 来自真实原模型。位置示意图标出原410点种子，599点观察域和五站源映射另有JSON及NPZ原件。原画标注与独立标注原件均在本机private目录。

## 运行范围和成本

依固定合同关于标注不确定度的条款，Pro会话0、几何编辑0、训练0。四个计划消费者及首版后优化记录为未运行，轮廓改善百分比记为不适用。本批交付对应模型和测量，修改后图片、消费者原回答与全任务提速结果均无新增原件。

本地消费者预检18项通过，CLI图片参数和4个MCP图像块的原字节经协议客户端验证。Pro实际图像消费为0。新任务的编辑/评价适配草稿留作本机过程记录，其实际执行预检在当前分支中未运行。公开执行入口为prepare_sources、prepare_views、observe和verify_observation及标注/阈值/source映射脚本。

实际Blender2次，1次新进程读取与1次生成4视图的渲染。数值控制器及标注、27阈值、独立选点、IPC/图片协议预检、失败探针均分别计入COSTS及关联原件，嵌套计时单列。模型推理费用、主线程与子agent视觉选点推理的时间和token成本未测。

原画、模型文件及正式插件保持原有身份。当前全部27304源点受到保护，变动点0，新增自交的受影响域为空，坐标/拓扑/矩阵逐位保持由实际回读及源文件摘要核验。

建议规划下一步先统一肘关节中心与腕前最窄位置的解剖标志，再结合姿态对应固定一个超过标注不确定度的可见修改目标。本批结束后进入既有独立复核和明确派工循环。
