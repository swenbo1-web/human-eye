# M5 全场观察与整件量测资格独立复核

2026-11-20。A、B 两次已冻结实测正常结束，原核验 `0/2` 失败保留，原件复核 `2/2`。正式证据 `6562ba5ef6569512465adad2725f2bfa50748423`，冻结 `023256f3195113d417dad1fafb3f3a05c6df65356bb0c8326f9e7e0601cd9246`。两路同产品 `9552d5c7103d9d8a08799adde96534990c6815f9`／143 源 `301caf777d446938497b53d5d49d67279cdcdb4ba2ee03e8aeb7e737c66076b6`。原核验器对比旧固定资产路径，成本读取器访问旧回执路径字段。两路实际启动路径和固定资产摘要一致，原 TX/RX 从真实 stdio 收据的索引还原，未重跑。78 个 Git 内容、2,670 个冻结输入和 256 个运行原件独立核对；ZIP SHA256 `8d584ee6444fc46f7d2756057178ff8bee0bf13e2902c37e43d2772e8e91cfdd`。[原判定](https://github.com/swenbo1-web/human-eye/blob/6562ba5ef6569512465adad2725f2bfa50748423/verification/m5_global_observe_measure_qualification_001/DECISION.json) · [原件复核](https://github.com/swenbo1-web/human-eye/blob/6562ba5ef6569512465adad2725f2bfa50748423/verification/m5_global_observe_measure_qualification_001/checks/OFFLINE_LIVE_RECONCILIATION.json)

## 同版事实与成本

同一 28 对象、416 点、744 三角装配。两路均保留 N22 的 SCENE 原图、N10 局部 TOP 像素不足（8,835／0）以及 N11 六方向遮挡来源，三帧 PNG／NPZ 等价。N11→N22 **整件** 间隙真值 `29527887/1073741824 m`，约 **27.49998774 mm**，方向 +Y。面对面的精确 y 下界可达，两现有原答点对均位于当前源三角。B 的两个对象通过父观察绑定、当前实例、捕获代和有序源连接，观察面不作为量测范围。A 的独立选择键与 B 的派生选择键各自有效。同一份输出的 `surface_proximity` 几何事实没有变化。[真值](https://github.com/swenbo1-web/human-eye/blob/6562ba5ef6569512465adad2725f2bfa50748423/verification/m5_global_observe_measure_qualification_001/truth/MEASUREMENT_TRUTH.json)

| 口径 | A 分开 | B 联合 |
|---|---:|---:|
| 外层批量 | 1 | 1 |
| 内层公开请求／Blender 业务读取 | 2／2 | 1／1 |
| 量测求解／构图 | 1／3 | 1／3 |
| 内层正文 | 9,570 B | 10,902 B |
| 外层实际正文 | 10,344 B | 11,738 B |
| 外层客户端窗口 | 1,529.27 ms | 1,472.84 ms |
| 完整独占窗口 | 3,765.76 ms | 3,638.14 ms |

A 的第二次宿主读取已使用现有资源，点及三角新增转发为零，仍约 16.32 ms。两路各一次求解，144 候选三角对及 22 窄相位相同。B 省去一次调用与读取，外层工具轮数没有变化。单对计时只作诊断。两路实际外层回包的固定 CLI 回放通过，B 最长工具头下只剩 **227 B**。无模型与 API，完整消费者收益未测。[资源账本](https://github.com/swenbo1-web/human-eye/blob/6562ba5ef6569512465adad2725f2bfa50748423/verification/m5_global_observe_measure_qualification_001/RESOURCE_RECHECK.json)

## 可删除的重复交付

B 联合 `task_result` 有 2,781 B，A 独立 `task_query` 1,464 B，两路表面距离事实同为 530 B。增加主要来自公共外层已含的场景绑定、代、对象与身份在量测来源中再次复制。当前独立 `task_query` 直接发布原 JSON。只读试算让联合量测使用同包父绑定和对象表，保留每个测量对象的有序源摘要、范围、距离及点对，原件内层 10,902→9,572 B，实际外层包装重建 11,738→10,308 B。这是包含全部原任务必要事实的可行性试算，生产实现还需覆盖量测顺序和异形来源。

同一安装的另一份只读复算用 6,148 三角密集装配的原图和求值数据，求实际 `M4_Far_00→M4_Near` 整件距离（0.9959999998100102 m），沿原格式与同一外层包装组合结果。当前格式外层 12,154 B，加 35 B 工具头超过固定预算，触发截断；可逆的紧凑试算约 10,976 B。该组合为封存源离线复现，模型端、服务商入参与第二场景实际 Blender 联合请求均未运行。一轮[合包来源去重验收](M5_JOINT_BRIEF_SOURCE_PROJECTION_001_PLAN.md)处理这个已复现的交付问题，本次数据没有足够依据启动六个模型对照。
