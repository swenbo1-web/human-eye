# M4 密集光栅叉积独立复核

2026-11-20。接受隔离候选 `9552d5c7103d9d8a08799adde96534990c6815f9`，直接承接 `f72e648f763fb6399f82c8e5d7f2b35840597bed`。143 源 `301caf777d446938497b53d5d49d67279cdcdb4ba2ee03e8aeb7e737c66076b6`，wheel `289cd77e16eb56bbcee3442db5e882b7ce3650732420c0a1e081ee737f3bf177`。两版 wheel 各 150 成员，Git／wheel／安装源码逐项一致。唯一改动 `attention_raster.py`。实测归档 `42e72c2611b99a477e88a5fb26ead0cbad5e71b1`，恢复冻结 `da2979f1fbc65d8a3ebac64f3c028f9781b2e8e8d124e5087d3f3728da791447`。[作者实测](https://github.com/swenbo1-web/human-eye/blob/42e72c2611b99a477e88a5fb26ead0cbad5e71b1/verification/m4_dense_raster_cross_001/REPORT.md)

## 位级和现场核验

定长乘减沿已安装 NumPy 2.3.5 的双 float64 三维叉积顺序。原边长归一、零尺度、长度、光照和取整保持。独立提取实际安装的两个分支，25,601 对宽指数、符号零及次正规浮点等输入的法向字节逐项相同。另有 4,500 对在触发浮点下溢异常的设置下作控制，结果字节或异常状态一致。原 8 张真实封存帧和普通、明确源区域等格式与数组回归通过。两版历史测试各 25 项，均 24 通过，1 因同一旧 yaw 快照缺失报错。首次入口误用旧批准入在启动 Blender 或记账前退出，原失败保留，产品和验收条件相同，恢复仅改测试接线。[离线与回归](https://github.com/swenbo1-web/human-eye/blob/42e72c2611b99a477e88a5fb26ead0cbad5e71b1/verification/m4_dense_raster_cross_001/checks/OFFLINE_CONTROLS.json) · [首次失败](https://github.com/swenbo1-web/human-eye/blob/42e72c2611b99a477e88a5fb26ead0cbad5e71b1/verification/m4_dense_raster_cross_001/prelaunch/FAILURE.json)

| 配对 | 两帧纯光栅 A→B | 冷服务端 RPC 节省 |
|---|---:|---:|
| 1 | 733.082→605.364 ms | 125.055 ms |
| 2 | 718.519→603.050 ms | 111.818 ms |
| 3 | 717.026→613.712 ms | 106.376 ms |

三对真实 Blender 均等价，纯光栅中位降 **16.07%**，冷 RPC 中位省 **111.818 ms**，完整独占窗中位省 **168.262 ms**。12 张实际 PNG、对应 NPZ 及数组字节一致。每槽 13 区域、11 条可读见证、两条具名挡物，固定 CLI 完整。独立复核原请求、真实回包、当前源、进程退出与 549 份归档。实际六槽、六业务、十二次构图，零模型。ZIP SHA256 `692a05b0293cef88b8ace973a05331bce09d33cd6f7c9b7c21177f090cbcf179`。[现场逐对与分段](https://github.com/swenbo1-web/human-eye/blob/42e72c2611b99a477e88a5fb26ead0cbad5e71b1/verification/m4_dense_raster_cross_001/checks/LIVE_REVIEW.json)

到此冻结 M4 本轮密集内核。此前导轨和密集用户任务的模型结果沿各自同版分母，局部工程节省不可直接相加为模型端到端收益。下一项[同版本观察和量测资格](M5_GLOBAL_OBSERVE_MEASURE_QUALIFICATION_001_PLAN.md)使用同一 M4 候选检查现有 M5 联合入口。聚焦实际结果是否可同包消费及同代来源，暂不新增模型或产品改动。
