# 主动覆盖002静态准入清单

依据根计划 SHA256 `9f2d398d10998242ac6bbecbc7e34f8ab970fb98eee4d68b73fa680f694bf27c`，基线为 `bfcc35e32aab0b724261a5140fc5d05df9ddad48`。本检查只读源码和合同，准备阶段没有执行render、算法资格、性能或子进程预试。runtime与runner落盘后逐项更新审查结论。

001根独审已接受优化几何及完整相机，并补核二十二个首次三角形见证面积和二十个定向控制。本批复用该资格证据，范围限按需调度、真实像素反馈及新进程成本。管理员接受记录和ROOT_REVIEW位于新批admin目录，运行器输入白名单保持geometry/camera与固定依赖源码。

## 合同与001复用结论

- 复用优化 build_index、CoverageState 及固定光栅。每个正式worker从空实际图像缓存开始，只建一次索引。A与B使用相同geometry、camera、像素规则、PNG/NPZ策略和CPU加载方式。
- CoverageState 的 next_view 使用实际covered_mask，排除observed_views，平分沿固定camera顺序。observe只将几何完整和实际readable的交集记覆盖。重复已观察视角会返回reused，场景或候选身份变化时rebind清空观察与covered。
- region_ids按几何身份排序，scene_identity采用几何规范化身份。名称或枚举顺序属于几何等价输入时，状态中的ROI bit位置保持一致。owner数组仍须保留生成该帧时的对象映射，避免将旧owner索引按另一份mesh顺序重解释。
- 002应从observed receipt推导每次pixel_shortfall，保留其观察历史。最终未覆盖采用state.unresolved终值，最终像素不足集合与该终值相交。后来得到合格观察的ROI应移出最终不足集合。
- rebind若触及runtime持有的frame/receipt引用，须按同一changed标志失效。这项处理沿现有state语义，累计实际raster尝试账目继续保留。

## runtime准入

- 运行输入限新批复制的原字节geometry/camera和已冻结依赖源码。允许调用001 adapter的纯load_meshes、render_one、readability_for_rois。prepare、assess及receipt_for_view携带旧图准备/读取路径，运行链不得调用它们。
- 不读取001 PNG、NPZ、READABILITY、oracle、预给ROI名单、view_masks答案或最优子集。资格完成后的控制器管理员比图使用独立路径，不回流child。
- 每个选择只调用一次共同depth/owner光栅，保留全部物体。像素资格只来自该新帧，固定16表面像素、4边界像素、24RGB对比阈值。
- 先形成实际PNG及当前观察回执，再更新state。预期几何覆盖不会提前计入actual covered。已尝试视角不重复生成，已完成状态再查询返回零新图。
- A固定六图顺序，B按实际反馈逐次选择。主B需要第三图时应在第三次光栅前保留资格失败；需要第三图本身即为停批依据，禁止截断后报成功。
- 主场景B的像素评估为两帧各六个ROI，共十二项；A为六帧共三十六项。记录实际次数，包含失败尝试及任何准备消耗。
- pixel_shortfall历史、最终uncovered、当前池几何不可覆盖分别给出各自语义。控制中的A/B终态由真实新帧产生，不能把主场景的5/1硬填为控制期望。

## runner及唯一批次准入

- 在第一次Popen之前固定十二run槽，六对顺序AB、BA、AB、BA、AB、BA，各使用新进程、新输出目录和空应用缓存。正式子进程不读取前一个run结果或图片缓存。
- 没有准备期预渲染或资格子进程预试。主图上限48、控制上限12、总上限60同时约束全部实际尝试，失败与准备消耗不会重置预算。
- 主B第三图需求、覆盖不一致或已知运行错误完成收尾后停余批，所有未开始槽标not_run，原失败及输出保留。无需有效样本替补。
- 主时界在启动进程前开始，经过退出、结果解析、全部PNG/NPZ回读、解码/摘要及计数核验之后结束。import、JSON、索引、raster、像素、编码和发布由实际新进程计入。
- 控制器整批时界的起点与其setup/import/初始source校验范围对应。窗口外的控制器启动或准备成本明确留为未测，避免把较窄窗口描述为全部投入。
- 两arm的NPZ输出策略一致并计入字节与时间，数组nbytes只表示载荷。worker阶段时钟、控制器主时界、整批协调/进度窗口各保留其原范围。
- 新帧PNG与001冻结PNG/RGB严格对应。NPZ自身摘要绑定新产物，数组内容按固定dtype/shape/数值核对；压缩容器的时间元数据与像素内容各按其语义处理。
- 失败worker仍应退出/reap并回读已产生计数与输出。无法确认的执行状态保留unknown并停止，不能将失败默认当零尝试。
- 存在unknown尝试数时，已知尝试之和可作为下界单列，完整actual总数保持null。失败后的剩余槽仍为not_run。
- OS文件缓存状态保持实录，fresh worker与空应用缓存的结论不外推为系统冷缓存。

## 固定控制准入

- 控制在执行前生成并冻结，只把BACK的跨度扩大64倍。projection前两行相应缩小，span、half_span、view_span、m_per_pixel等显示字段同步，方向、中心、near/far及512分辨率保持。
- 原几何投影范围元数据继续描述同一geometry，控制额外跨度单列。候选身份包含修改的projection，沿现有rebind语义失效。
- 控制A/B各至多一次，不混入主十二run或主性能分母。B可继续其他尚未观察且有几何增益的候选，BACK只尝试一次。
- 验证几何完整但实际像素不足的真实回执、未达标不记覆盖及最终有限停止。该控制不预填readability，不改变阈值、布局或追加倍数试验。

## 正式后静态复核

- 保留十二主槽与至多两个控制槽，逐项核原进程/时界/调用序列/PNG/NPZ/像素行/覆盖历史和终态。
- 固定三维几何发现与主场景覆盖要求由实际数据验证；控制A/B按真实终态对应。十八轮旧模型结果或001六图数据不进入本批样本。
- 列六个配对B/A原值、比值中位数及原值中位数之比，保持计数与质量同一合同。净时间门严格为完整主时间比中位数小于1。
- 原始失败、未运行、准备消耗、整批协调和未测项全部保留。正式后不追加样本或重试。

新增模型、provider/API及Blender次数应为零。本审查不操作Git、产品、旧原件、用户资产或共享GUI。
