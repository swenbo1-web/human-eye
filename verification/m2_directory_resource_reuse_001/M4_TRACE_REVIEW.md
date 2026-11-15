# M4 既有宿主轨迹复核

本次只读核查基线为 `8f2a739e789b777358d84a168154bc7c50b929e5`。结论为 `not_actionable_on_qualified_natural_task_evidence`。保留 1 条真实技术复用机会，符合本批自然任务要求的命中为 0。目录在自然任务中的需求频率仍为 unknown。

## 分母与核查边界

核查现有 47 个 M4 命名空间中的原始 TX，以及 12 份既有外部归档索引。按实际宿主会话计算，主动观察为 4 条 owned 会话，合计 24 条 stdio RPC，包含 13 次成功主动观察、1 次错误查询和1次目录。另两批旧采集各11条 owned 会话，共44份真实采集脚本，均未调用目录。合计26条有明确实际宿主记录的有限工程会话。这些会话的资产重复，不能当成26种独立资产覆盖。

原始文件计数为 1201 份 literal TX 和 300 份索引映射 TX，二者存在副本重叠。文件数、协议层副本和初始化请求均未加入自然任务分母。非对象或无法JSON解码的 14 份原件逐项保留。CAPTURE_REPLAY及固定packet消费不提供真实Blender驻留证据。现有归档不覆盖全部历史自然使用。

## 保留的技术命中

`m4_active_observation_host_bridge_001` 的 acceptance_02 依次为 baseline观察、重命名观察、nonplanar_source观察、bad_active_query、ping、old_readonly_regression目录。最后一次成功观察与目录之间没有私有场景控制。QA脚本005与006取同一个 resident module、tag 和 `_mcp_resident_host`，QA PID为 1968。

资源为 `mesh:('uid', 277)`，版本 29，对象实例277，4个顶点、2个三角形。捕获与目录的 instance、epoch、revision分别为 `15493779e75e4e44b5b2f2f4208e30d2`、1、3，目录明确 `cache_hit=false`。局部坐标、单位尺度与单位矩阵直接记录，目录边界逐轴与前一实际世界捕获一致，退出快照也保持相同几何和矩阵。nonplanar ROI的unknown状态仍保留，该状态不使完整网格捕获失效。

历史运行的产品整体SHA为 `b12db7282381df800fbd0d44d2f921e332a6b85c2fb3ac77aba51b5cc462b278`。宿主单文件SHA为 `9a63545aec488cead3be508f97afefc9fa7135beb82e85cff10ca7ad4d3b59e9`，与当前基线同名单文件一致。这是历史真实入口证据，当前3748整体版本的新实测次数为0。资源29指该mesh的revision编号，驻留资源总数未测。源码证明 capture_scene 进入驻留路径，存储 world mesh、pose和资源。相同同步revision、未改变场景及成功只读守卫支持资源未失效的推断。实际 `_resource_stamp` 元组和目录入口的内部mesh引用没有直接侧录，因此JSON中将这两项与直接证据分开。不得声称测得新方案时延。

目录miss成功代码路径对这一个对象执行1次to_mesh和4次顶点世界变换。该数量来自确定代码路径与实际对象规模，原件未保存前后residency_work计数或独立native profiler。原三角预算为6 loops减2×2 polygons，等于2。没有把三角数量替代一般多边形预算规则。

## 请求目的与自然任务资格

原 `HARNESS_PROTOCOL.json` 的 fixed_requests 已登记 `old_readonly_regression`。实际 `run_acceptance_r2.py` 第222至225行以同名请求调用目录，仅校验成功和纯文本交付。该请求紧随错误查询与ping，原报告也将其称作旧directory只读入口回归。日志未记录后续依赖目录完成的业务任务。由此保留技术重复工作事实，同时本批“自然任务中首次需要目录”的资格仍为0。未以“工程测试”这一名称否定真实宿主调用，也未将兼容回归推成自然任务收益。

## 执行与限制

只读取既有相关归档及固定的13个 D:/he_* 根目录元数据，相关live TX与其D盘原件逐字节核对。未打开blend、图像或数组，新增Blender、产品观察、模型、raster、evaluator和产品import均为0。源码、安装和旧记录保持原字节。复核人参与过M1产品实现，此关联在JSON中登记。

完整请求顺序、原始输入SHA、直接字段、推断和未暴露项见同目录 M4_TRACE_REVIEW.json。当前结果可支持按计划结束本批资格核查。自然任务机会及端到端收益仍须由后续实际轨迹提供。
