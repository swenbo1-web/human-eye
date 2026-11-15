# 两个产品版本的公共运行接线

正式顺序为 A1、B1、B2、A2、A3、B3。两组实际执行角色均为 P，具有相同五项工具并从 active_observation(include_images=true) 开始。`comparison_arm` 明确表示 A/B，槽名和产品摘要另行绑定。消费者、owner 及原时钟中的 `group=P` 保留其真实执行含义。

每槽直接复用已接受 routed `run_slot` 代码对象。新 connect_slot 仅选择该臂的固定 manifest、产品 binding 和同一公共提示词，再调用原 route 代码对象。A 指向旧安装，B 指向本批新安装。完整槽时钟包含来源校验、命令接线、模型回合及清理归档。槽后保存事实核对处于批次协调时钟内。

两个 manifest 使用前批原始几何、相机、capture 和 task 输入的同一绝对路径与摘要。公共完整 P 提示词逐字节复制。两臂共用原 NumPy/Pillow 与已固定的只读 Shapely 目录。源码闭包包含旧绝对来源与新安装、checkout 的141源文件。

新 audit 边界覆盖旧封存工作区、旧运行根和新运行根。当前 owner 输出、公开几何相机和只读公共依赖具有原有读取例外。资格图像、私有真值及其它槽输出受相同隔离检查。

资格命令指定 Q01 等独占编号，目录为 preparation/Q01/QA 与 QB。每臂一条主动观察、一次现有帧缓存复读，实际构造均进入同一永久 raster_budget。所有失败与后续资格累计最多12次，正式最多36次，全批48次。资格重试先核对既有进程终态与完整回执，旧编号和账本保持可回放。

冻结版本另存 FROZEN_R01 等原件，当前 FROZEN.json 与其对应快照一致。源码修复后增加冻结修订并在同一资格余额内重新验证。正式入口要求管理员资格结果绑定当前冻结与实际最后一对记录。

新聚合生产者为 source-face-binding-six-route-v1，launch 为 source-face-binding-launch-v1。状态仍位于每条 record，独立评分需结合 slot、comparison_arm、实际 P 角色和当前消费者回执核对。
