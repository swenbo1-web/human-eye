# M4 全场像素上界提前结束独立复核

2026-11-20。接受隔离候选 `f72e648f763fb6399f82c8e5d7f2b35840597bed`，直接承接 `e03ee486dc8f86f6a7d2fb75d012d181edcf8f3c`。143 源 `0e71932b2bccbf8a6583460875cea8bdc55b092b7d8f3391c9b0124aef986d4f`，wheel `2831c5da64a5f477712d3c2bfc72dfd4cef7092b02ab9ca96ff1b28fc84ee7ce`。两套 wheel 各 150 成员，143 运行源与 Git 和隔离安装逐件核验，只有 `active_observation_region_task.py` 改变。实际验收 `9547ec8ee2ddea85263da761dc4fed3adbdecca8`，恢复冻结 `8c9424b343f2794158f0b7d7a584f9d697fa9ea0a2c999207bbdeb9ad84b381e`。[作者报告](https://github.com/swenbo1-web/human-eye/blob/9547ec8ee2ddea85263da761dc4fed3adbdecca8/verification/m4_global_pixel_bound_short_circuit_001/REPORT.md)

## 正确性和实测

直接执行两安装的 `_render_scope` 隔离控制，37,449 组模拟的候选顺序、覆盖、预测、空序列、阈值、已知及未知条件下，构图顺序、回调与实际跳过证书一致。实际求界减少的情况为 28,230 组，短路调用是原序列前缀。21 对象的五个真实跳过保留原 7 条完整证书，28 对象单次 TOP 和原图保留。两版各自新增历史回归 33 项，均为 23 通过、8 失败、2 错误，失败标识逐项相同；旧 schema、构图数和模拟回调差异保留。首次旧准入模块误导入发生在 Blender 启动前，零业务及零实际构图，原冻结和失败回执保留。恢复只改测试接线。[离线控制](https://github.com/swenbo1-web/human-eye/blob/9547ec8ee2ddea85263da761dc4fed3adbdecca8/verification/m4_global_pixel_bound_short_circuit_001/checks/OFFLINE_CONTROLS.json) · [启动失败](https://github.com/swenbo1-web/human-eye/blob/9547ec8ee2ddea85263da761dc4fed3adbdecca8/verification/m4_global_pixel_bound_short_circuit_001/prelaunch/FAILURE.json)

| 配对 | LEFT 求界 A→B | 冷 RPC 节省 | 原图和任务事实 |
|---|---:|---:|---|
| 1 | 338.678→32.972 ms | 285.938 ms | 等价 |
| 2 | 340.716→32.978 ms | 324.047 ms | 等价 |
| 3 | 336.906→35.601 ms | 236.671 ms | 等价 |

六个实槽的 13 区域、11 条可读见证、两条具名遮挡一致，SCENE/LEFT 原 PNG 与 NPZ 逐字节相同。实际求界 10→1，LEFT 段配对中位降 **90.26%**，冷 RPC 中位少 **285.938 ms**，独占窗中位少 **314.449 ms**。正好 6 次 Blender、6 业务、12 构图，模型为零。2,290 项恢复冻结输入、42 件 Git 内容及 549 件原件通过独立复核；ZIP SHA256 `853d1bbde7295110e2a5a7214c40eb59a7cfed5169302e5f94e0c5b96fd6c9ef`。[实际线包和计时](https://github.com/swenbo1-web/human-eye/blob/9547ec8ee2ddea85263da761dc4fed3adbdecca8/verification/m4_global_pixel_bound_short_circuit_001/checks/LIVE_REVIEW.json)

## 下一处可测的工作

候选每组两图的真实光栅合计约 716–777 ms，约占构图与发布阶段的九成。PNG/NPZ 发布合计约 56–64 ms。独立复放当前安装和真实相机，密集 SCENE 逐个面调用 6,148 次通用 `np.cross`，插桩累计约 152 ms，数组轴分派为主要开销。仅等价展开固定三分量叉积的内存试算，原 SCENE／LEFT 中位 373.446／373.637 ms，候选 309.761／311.595 ms。原始 RGB、深度、所有者及源三角数组逐字节一致。该值为同进程试算，整链净收益待[单变量工程对照](M4_DENSE_RASTER_CROSS_001_PLAN.md)。目前没有依据为归档和模型回包再增加新链路。
