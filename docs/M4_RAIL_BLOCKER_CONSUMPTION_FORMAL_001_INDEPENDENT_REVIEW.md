# M4 导轨遮挡正式对照独立复核

2026-11-20。正式证据 `a17083c0dff7d4e90daae59406b4a19960583df4`，冻结 `6fb5477eafec623d640e7d31bf2a854787ffdf3d8a80c5fdd3ee7bd11d718b5d`。A/B 产品为 `278fd300`／`e03ee486`，均固定同一资产、题面、原普通工具和 Pro 请求配置。确认旧失败保留、派生准入由原四份真实工具交付及两组源和关闭回执得出，新增资格为零。正式六槽按 A1→B1→B2→A2→A3→B3 各运行一次，六个 fresh CLI 均正常完成，替补为零。独立复核 51 个 Git 内容、1,332 条冻结输入、1,308 件 ZIP 原件及全部 29 条真实工具记录。[作者报告](https://github.com/swenbo1-web/human-eye/blob/a17083c0dff7d4e90daae59406b4a19960583df4/verification/m4_rail_blocker_consumption_formal_001/REPORT.md)

## 正式质量与成本

两臂原答各 3/3 完整，六格均引用当轮实际交付的两根导轨局部 SCENE。独立源与像素数据一致。B 三格均引用两个 `M12[10]` 首包来源。A1 通过普通几何找到另一个合法的 `M12[7]`，A2/A3 通过原生取数／LEFT 图确认 `M12[10]`。B1/B2 首包后未再做挡物定位，B3 在采用后另读挡片顶点。三对挡物相关补查各 `3→0、3→0、3→2`。全量请求和与挡物无关的普通复核单列，保留 A3 一次带筛选范围请求拒绝。原答、同槽帧和各次工具证据逐项对应。[质量](https://github.com/swenbo1-web/human-eye/blob/a17083c0dff7d4e90daae59406b4a19960583df4/verification/m4_rail_blocker_consumption_formal_001/scoring/QUALITY.json) · [补查归因](https://github.com/swenbo1-web/human-eye/blob/a17083c0dff7d4e90daae59406b4a19960583df4/verification/m4_rail_blocker_consumption_formal_001/scoring/FOLLOWUPS.json)

| 对 | A 完整窗 | B 完整窗 | 配对改善 | 业务 | 构图 |
|---|---:|---:|---:|---:|---:|
| 1 | 133.537 s | 120.782 s | +9.55% | 6→4 | 3→3 |
| 2 | 75.398 s | 104.062 s | −38.02% | 5→3 | 5→3 |
| 3 | 103.604 s | 68.348 s | +34.03% | 7→4 | 5→3 |

三对均同质量，B 两对更快，配对降幅中位 **9.55%**，低于已预登记的 10%。完整门限未过。原始 CLI input＋output **358,234→171,796（少 52.04%）**，未缓存输入 86,291→61,692，业务调用 **18→11**，新构图 **13→9**。第二对 B 慢 28.663 秒，提示送出到首次合格证据增加 23.515 秒，其中 23.454 秒发生于提示送出至薄客户端收到首个工具请求之间。首包产品 RPC 699.74→740.44 ms，只多约 41 ms。该阶段的内部原因未测。四个槽额外使用 `full`，共五份成功长回包在固定 CLI 重放中裁剪，实际线上文件和事件完整。服务商实际输入和费用未测。运行原件归档 SHA256 `b5a95c704367094da1cba88ef353433d74bee2e9c11fa3401ab870d0ed18d2d2`。[分段时钟与用量](https://github.com/swenbo1-web/human-eye/blob/a17083c0dff7d4e90daae59406b4a19960583df4/verification/m4_rail_blocker_consumption_formal_001/RUNTIME_REVIEW.json)

## 收口与另一项计算热点

具名来源保留在已接受的隔离工程候选。导轨用例的质量、采用、补查和 token 信号成立，完整时间以原门限失败封存。下一批独立验证[全场像素上界提前结束](M4_GLOBAL_PIXEL_BOUND_SHORT_CIRCUIT_001_PLAN.md)。该计算实际占密集资格 LEFT 阶段 335–418 ms。使用当前安装和三套封存源只读试算，密集 LEFT 按原顺序第一次上界为 1,551，已超过拍摄放弃门槛 16。现有做法仍遍历十个区域，五次交错试算中位 330.016→32.894 ms，原判定均为继续拍摄。28 对象的单次 TOP 上界保持 5,026 和原实际拍摄。21 对象已封存的五个跳过视角仍生成同七条小目标证书，判定与内容完全一致。此结果是内存试算，现场独立配对待下批。
