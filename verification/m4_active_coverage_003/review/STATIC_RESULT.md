# M4-ACTIVE-COVERAGE-003 静态准入结论

最终源码静态审查未发现阻塞项。允许根按既定流程冻结来源，运行唯一四个无图 probe。四项全部真实合格且冻结字节一致后，同源进入新的 12 个主槽和 2 个控制槽。任何实际资格失败均保留原件并停止。

审查方执行 probe、engine、几何资格、渲染、性能样本及模型/provider/Blender/API 的次数均为 0。实际启动资格和本固定任务的净时间收益仍待对应原件证明。

## 已核接线

- child 使用固定直接 base exe，保留 `-I -B -X utf8`，bootstrap 显式插入原 venv site-packages。四 probe 与正式 runtime 调用同一 launch、bootstrap、依赖加载和原 Popen 句柄回收函数。
- 实际 NumPy/PIL 文件、版本和初始化 SHA、固定产品安装及真实 base prefix 被记录和验证。base exe、bootstrap、控制器、runtime、validator、probe、资格器及明确依赖均进入冻结源图。
- Popen 与 child PID 保持严格相等。清理通过原句柄 kill 和 5 秒有界 wait，确认进程回收并关闭句柄及所持管道。清理状态未知会失败。
- 四 probe 各一次。timeout 先核实际握手，再触发登记等待期限。nonzero 保留真实非零退出。receipt_failure 在 marker 实际一次后故意省略回执，保持动作事实与回执失败。probe 源码没有 index、mesh、geometry/camera 读取或 raster 调用。
- 根发现的握手发布与退出轮询竞态已在冻结前修正，原表达式和修正含义记录于 `PREPARATION_ADJUSTMENTS.md`。
- 正式门逐项要求四 case passed、整体 all_passed、零光栅、原 FROZEN 摘要及完整来源映射一致，执行前后继续核同源。正式性能路径没有 probe 分支。
- runtime 的 8 个来源字段与 validator 一致。新 geometry、主相机、BACK64 控制相机和依赖 manifest 与 002 原字节一致。
- 主槽 48 次、控制槽最多 12 次、新批最多 60 次，连同旧 002 六次累计最多 66 次。失败停止余槽，未知计数保留 unknown。主时界覆盖启动、退出和完整图片/数组/结果回读，资格投入另列。

## 固定源码

| 文件 | SHA256 |
| --- | --- |
| runner.py | `1e8e522fd95b0ad216989f871f870c82c3487cc6aeac59c527746ff4348f9711` |
| runtime.py | `e99fd1bb73b6e82cfd5103181cdbd0ba24fc26c9b9a72be99a70dfaf6e5272c0` |
| validate.py | `788fcba5c3569ad0917636967661a759c436d0fd754f04ba894ac60fe21227ed` |
| bootstrap.py | `d064956653c40c4d4db73fcb0932bb98eca7b0c9ef1e1bf157e76807cbead31b` |
| launch.py | `ec14fa508c471059612bd9d8c379104d4045c1e3dfb56b8b5979f7eb619c2953` |
| probe.py | `52c43fb722bdedfe572130d9cfc5fa8ec863db6c9b4f4f49c33cd45bf7eea63d` |
| qualify.py | `378f6c92d49e6b4ad371d3cca5f358b7e779edd7641c956d0920c1248e49cbaa` |

计划、PREREGISTRATION 和输入摘要完整绑定于 `STATIC_RESULT.json`。003 新资格无法追溯证明 002 的旧 PID 谱系。002 的一个失败、剩余未运行槽及实际六次光栅成本继续保留。
