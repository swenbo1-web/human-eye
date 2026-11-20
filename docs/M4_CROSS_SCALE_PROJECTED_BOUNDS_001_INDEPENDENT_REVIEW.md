# M4 全场投影筛选 001 独立复核

2026-11-20。接受隔离工程候选 `3cbf240562b61cff18c2818c6d134904259b36b7`。直接承接 `3aa1d1fb43ae9a8207acd17bdab8d2861720c5a6`，唯一产品变更是 `active_observation.py`。运行 143 源 `6f2fc9762f9410f968c4768545c14077ca944f75416fb04aa9d14145a4c630d8`，wheel `a763f75d3a705ac51295b642ad9a1375b7f0d6fc13e40a30bbb7c8fe766c7c94`。核对 Git、wheel 与隔离安装逐字节一致，同一 5 项工具。冻结 `ffe2faac19f8ec5b26f5af93988a2051aef56ddf`，证据 `17bce4aa30f8cf9a3d044c0eb856935a8dccf9d9`。[作者报告](https://github.com/swenbo1-web/human-eye/blob/17bce4aa30f8cf9a3d044c0eb856935a8dccf9d9/verification/m4_cross_scale_projected_bounds_001/REPORT.md)

## 原始证据和算法

同一有效区间与目标有严格正跨度，并且三角下端小于区域上端、三角上端大于区域下端，才进入下一层。精确有理端点按轴排序后，`bisect_left` 保留下端的严格小于，`bisect_right` 保留上端的严格大于。三角的既有顺序与精确遮挡核不动。独立核 91,440 组有理区间，含 36,509 组相交、同端点、零宽和极近有理端点。三份封存终态重放的完整 `CoverageIndex` 和有序深度分支逐项相同，分母分别为 9,098、9,098、2,007。21 对象终态关闭优化及强制视锥证明失败，两种情况均走旧分支并得到同值。

现有嵌套搜索仍逐区域扫描三角。整数秩替换的是循环里重复的有理比较。每视角最多每轴 `2T` 个端点、`T` 条秩记录，临时表在该视角结束释放。作者的第一次空间验收被自行设定的相邻实测倍增阈值拦截，原退出保留。报告同时保留暖缓存跳变及清理有理数哈希缓存后的峰值，CPython 哈希缓存上限独立核为 16,384 项。容器上界与实际小规模离线峰值支持本批的线性空间目标，完整进程 RSS 未测。[空间原件](https://github.com/swenbo1-web/human-eye/blob/17bce4aa30f8cf9a3d044c0eb856935a8dccf9d9/verification/m4_cross_scale_projected_bounds_001/checks/PROJECTED_BOUNDS_CONTROLS.json) · [首次验收退出](https://github.com/swenbo1-web/human-eye/blob/17bce4aa30f8cf9a3d044c0eb856935a8dccf9d9/verification/m4_cross_scale_projected_bounds_001/checks/FIRST_OFFLINE_FAILURE.txt)

## Blender 三对实测

| 配对 | 冷全场索引 A→B | 冷服务端 RPC A→B |
| --- | ---: | ---: |
| 1 | 894.077→662.237 ms | 1,680.951→1,437.565 ms |
| 2 | 891.006→662.515 ms | 1,671.179→1,438.047 ms |
| 3 | 890.367→665.143 ms | 1,670.923→1,449.883 ms |

冷索引配对降幅中位 **25.64%**，冷 RPC 三对均改善，中位省 **233.132 ms**。两请求连贯窗口和完整独占窗口配对中位分别省 235.105、251.840 ms。六槽都取得相同任务证据；N22 原图与既有原件一致，N10 8,835／0 且未交付原图，N11 保留正面积遮挡未知。每槽冷简报 10,570 B 与三次实际构图，后续无图全量 393,750 B，索引命中、零新增构图。独立核验覆盖 25 个 Git 封存内容、1,455 个冻结输入和 623 件运行原件。运行 ZIP SHA256 `fc038944320d14a507cf5454dd58df20e31ce560d6450814fcf532a6d18d416b`。[逐槽证据](https://github.com/swenbo1-web/human-eye/blob/17bce4aa30f8cf9a3d044c0eb856935a8dccf9d9/verification/m4_cross_scale_projected_bounds_001/checks/LIVE_REVIEW.json)

本轮只有六个工程槽、12 条业务和 18 次构图，零模型或 API。模型补查、token 和完整任务收益未测。冻住这个内核，转到[高面数装配的完整巡检试验](M4_DENSE_PANEL_SWEEP_001_PLAN.md)。先验证现场首包交付，再使用有限实际消费者对照。
