# ARCH-READ-CONTEXT-OPT-001

产品 `ba72c21614d9547ce48615d02f7f37389d22dd6f`，继续codex/architecture-read-context，父提交为已审8935b78证据/0414a9a产品。只改read_context.py（+20/−3）：同instance/epoch/revision保留最近8个选择，每选择最多16个结果，总容量最多128个结果体。有序selector、selection_key、入口模式仍区分；global版本、source/host代际改变清旧选择，无token仍逐次新鲜。

切回选择时恢复其normalized scene/MeshEntity和结果，并立即重绑SceneCache当前私有mesh；资源键仍含完整global token。结果隔离、原几何/unknown/并列、动作账本边界和宿主协议未改。没有通用缓存框架或新增宿主资源版本。

| 固定序列 | 原normalize/task_result总次* | 本版总次 | 第三次normalize/task_result/mesh build/精算 |
| --- | ---: | ---: | --- |
| AB→AD→AB | 3/3 | 2/2 | 全部0 |
| AB→ABC→AB | 3/3 | 2/2 | 全部0 |

*旧次数直接复用根READ_CONTEXT_001_REVIEW的同字节独立结果，没有重跑旧版。新WORK_MEMORY.json记录实际每次调用；不把该工作量变化冒称完整任务延迟收益。旧版也可能命中pair memo，新增收益限定为省去切回时的规范化/实体构建与task_result，不另宣称精算加速。task→nearest→task→nearest另测只normalize2、task_result1、nearest summarizer1，输出及私有mesh绑定保持隔离。

新增选择复用有明确内存代价：AB单槽2实体/1296 B数值数组，AB/AD两槽4实体/2592 B，AB/ABC两槽5实体/3240 B。8槽样本16实体/10368 B，第9选择淘汰后仍为8槽/16实体/10368 B，首槽独占Mesh的weakref已释放；global revision变化后回到1槽/2实体/1296 B。数组沿NumPy根buffer去重，**不含scene dict/list、结果体、Python对象开销或RSS**；不是进程内存上限。每槽16/全局128结果上限另有淘汰测试。

新增11方法、受影响task12和nearest9共32方法一次全过，0失败/error/skip；另4个工作/内存计数场景全部断言通过，不混入unittest分母。覆盖两条切换序列、顺序/别名、版本/host/source失效、旧无token、caller修改隔离、选择/结果LRU淘汰及切回补新问题时的mesh绑定。未重复初版50项全矩阵，旧16证据逐字节不变。

132源摘要、固定字节及原日志SHA见RESULTS。一个协助者写/跑新测试，一个只读审查者核LRU引用与资源重绑；产品由本线实施者修改。没有Blender、live RPC、模型/API、延迟benchmark或原资产/正式配置改动。本批唯一追加优化到此结束，不做第三轮小优化；下一步由根合并M2同版做真实入口和生命周期验证，之后接M5，目前仍未宣称整体架构/M5完成。
