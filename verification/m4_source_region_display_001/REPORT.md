# source_region 显示参与修复验收

同一 Yanyite 原件、同一 748 面与 410 点选区、同一 SCENE 相机完成隔离候选实测。正常状态的选区像素从 0 增至 35,452，显示与观察不足反馈分项通过。

## 实现与结果

宿主每次读取当前 active view layer 的 visible_get，并记录 view layer、对象实例和原始 hide 标志。resident、delta 与普通捕获传递当前快照。显示身份进入 source_region 图片范围、帧和缓存，栅格跳过未参与对象，完整对象顺序及源三角 offset 得以保留。量测继续使用完整几何和显式参考对象。

原隐藏 Cube 排除于图像，角色局部可见。显示 Cube 时，选区零像素，结果给出 partial / evidence_insufficient 和 displayed_without_pixels。隐藏目标时，给出 selected_region_not_displayed。两种状态的表面距离事实均保留，binary64 值持续为 0.37011719389236364 米，与独立固定答案一致。选区位于 Cube 内部，该数值表达两个三角表面的距离。

正常图片含 166,193 个角色前景像素，其中 35,452 个属于选区。源区域仍存在真实自遮挡，完整曲面可见性保持 unknown。

| 实际调用 | 顶层状态 | 选区像素 | 新增构造 | 完整请求秒 |
| --- | --- | --- | --- | --- |
| main/initial | complete | 35452 | 1 | 4.142578 |
| main/repeat | complete | 35452 | 0 | 0.750595 |
| state/initial | complete | 35452 | 1 | 3.657858 |
| state/cube_visible | partial | 0 | 1 | 2.971286 |
| state/cube_restored | complete | 35452 | 1 | 3.017000 |
| state/target_hidden | partial | 0 | 1 | 2.752840 |
| state/target_restored | complete | 35452 | 1 | 3.074267 |
| state/repeat | complete | 35452 | 0 | 0.663085 |

## 状态与成本

实际两次 owned，共八次公开请求、六次构造、六份 fresh 来源导出。四次夹具 hide_set 操作全部在独立副本完成，产品 setter 为零，blend 保存次数为零。原文件、两个副本摘要、所有几何和显示标志的恢复均核验通过。

两次完整 owned 为 10.651605 秒和 29.718977 秒，均包含启动、导出、独立答案、公开交付、一次额外计数读取与关闭。额外计数 RPC 的约 0.375 秒和 0.369 秒包含在其中。宿主显示快照累计读取及小摘要成本分别为 83,100 和 242,100 纳秒，两个会话读取 2 次与 6 次，共处理 4 与 12 个对象行。性能按本批实际窗口记录。

同态复读均新增构造零。真实宿主状态代际依次为 1、2、3、4、5、5，几何摘要保持相等。恢复显示后取得当前新引用并各构造当前帧，图像内容和帧内容身份恢复一致。纯控制另验证同几何代际的显示隔离和恢复缓存。此处分别保留实际代际行为与同代复用证据。

## 独立验收与剩余范围

240 项选择回归在源码和受控隔离安装各通过一次。合成 PNG/NPZ 编码次数与耗时单列在 tests/REGRESSIONS_source.json 和 REGRESSIONS_installed.json，实际注意力栅格均由 guard 禁用。新宿主合同、旧来源见证、取消、期限、delta、原生证据与受控源等相关路径覆盖在选择回归和保存记录中。

独立图像检查覆盖八次实际交付的 1,258,279 个前景源成员、RGB 和深度点，固定网格最近射线 2,048 条，748 面中心累计 5,984 条。全图逐点核声明源成员，最近遮挡按预先固定射线范围核验。八次交付均对应原始 stdio 和已保存 PNG，额外 main 离线复检原件以 ATTEMPT_02 保留，全部通过。

另跑九项 worker 协议检查，其中八项通过，一项 canonical 与 examples 副本相同检查因既有差异失败。两份 worker 文件均与 828d1265 字节相等，证据及 traceback 保存在 tests/WORKER_BASELINE_OBSERVATION.*。通用关闭日志 status 仍记 unknown，对应 closed 响应、指纹和保留进程句柄确认正常退出。

本批仍为一个静态资产的明确选区任务。完整曲面可见性保留 unknown，模型自主定位、骨骼或 modifier 扩域及整任务模型收益尚待对应任务。建议下一步开展一个有限 Codex 消费任务，核对其对当前区域、距离、局部图片和 unknown 的实际理解。

候选源码与 wheel 安装绑定见 R0_RUN_BINDING.json，运行前输入见 SOURCE_FREEZE.json，完整状态和原始证据见 DECISION.json、checks 下各独立报告及 runtime_archive，最终内容由 CONTENT_MANIFEST.json 固定。
