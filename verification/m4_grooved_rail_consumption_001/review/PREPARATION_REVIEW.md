# 凹槽迁移消费阶段独立准备审

独立准备审通过，当前冻结范围内无阻塞项。

## 输入及固定身份

身份检查 26 项通过。管理员资格封存、所列文件及计划均核对固定根提交 `25e4f21335a53b28c5688dc6611f13204a6fde15` 的实际 Git 字节。资格包 57 份文件逐项匹配实施提交 `9f38e8522cfeea9a580a19baad0e0d823eb1a16f`，56 项清单的长度和 SHA256 匹配。

本批资产、实际快照和独立真值分别匹配资格包中的 `49c0dccb…ec67`、`6bb073b9…ff52`、`2d072197…eaa74`。共同消费者题面为管理员固定的 446 字节 UTF-8 原文，候选为 Part_A、Part_B、Part_C。新快照已有 unit_scale_m、完整局部坐标、世界矩阵及 faces，既有归一化直接接受该结构。

产品提交为 `e836e03f4b3821f869c72ac3e50df5204f28b50f`，137 源码规范摘要为 `2c453e56f3abf83a49f9c8ef37a3a77728dd8f05168db4fd5217d3bad465c390`。工作树源码、隔离安装源码及固定产品 Git blob 逐项相符，launcher、安装绑定和受保护文件哈希匹配。

## 最小复用及模型可见内容

actor 与上一批逐字节相同。transport 仅替换六格空工作目录根路径。driver 仅替换本批 CYCLE 和 grc 槽标记，run wrapper 仅替换私有导入标签，匿名打包器仅替换 CYCLE。其余预算、失败处理、原始业务转发和生命周期逻辑均沿用原源码。

actor 保留旧私有 clientInfo.version 与内部模块标签，这些标签进入管理记录。当前阶段、资产和评分绑定由新 driver、PLAN、目录与冻结输入确定。

共同原生声明与基准 NATIVE 字典一致，P 中的原生声明与 N 相同。ordinary observe 完整声明来自同源已保存的实际 tools/list，actor 在正式启动时还会将实际所选声明与冻结声明完整比较。普通 serve 使用原入口，完整业务响应透传。

CLI argv 为纯构造记录，精确预授权 N/P 各自工具名称。新工作目录、ephemeral 上下文、关闭的 Hook/记忆/用户规则以及共同设置均与当前合同相符。图像参数未进入 argv，初图与新增图预算均为零。

## 期限、失败和退出

六格顺序为 N1/P1、P2/N2、N3/P3。消费者 450 秒、完整单格 570 秒、actor 启动 40 秒、32 次工具尝试、128 RPC、单工具 30 秒、每格累计 1 MiB 响应、单代码 256 KiB 均与原合同一致。driver 在每格原期限内核冻结输入，状态不明、quota、断管或关闭未确认会停止序列，保留已执行前缀和未运行尾格。

纯函数检查确认旧阶段授权、重复槽、变更顺序和扩样均被拒绝。完整新快照归一化通过，单位、坐标、对象名或面改变被拒绝。服务错误分类确认显式 HTTP/status/error 429/503 和 quota 文本触发停止，普通 PID、端口和散列数字保持正常分类。

两个 mocked owner finish 用例分别覆盖正常写入和 BrokenPipe，均关闭 stdin 并执行 wait。真实 actor、Blender worker 和产品 runtime retained handle 的检查逻辑沿用字节固定实现。薄客户端 EXIT 回执单独保留 confirmed、unknown 或 rejected，实际 owned 进程退出采用各自回执。

原生 Python 使用既有审计边界，图片观察使用原 helper 的 PNG 扫描与 render hooks。审查结论保留这些记录范围。32 次尝试及 256 KiB 代码界沿用既有实现，本轮动态检查集中于复用改动及已列路径。

## 评分和匿名交接

评分的 13 项固定事实、距离和每坐标分量 `1e-6 m` 标准、有效等价最近见证、完整精度先行及舍入校验均与原合同相同。候选及独立真值布局已替换为当前资格输入。产品分支、unknown、回退和额外断言按新计划保留。

匿名打包的纯合成检查全部通过，覆盖六槽、终止前缀、not_run 尾格、完整业务嵌套事实、错误、unknown、证明字段和最终字节。映射及成本分别保留。工具名称和业务内容可能暴露路线，本轮采用管理组标与成本遮蔽的有限盲化。

## 最终冻结记录

最终准备检查 48 项通过。PLAN SHA256 为 `6229c8b4eec4340ccb2dd11bef4ba45db3a65b4e5cac82d70e4c6254c920e4aa`，与 FREEZE 和 GO 相同。全部 33 个本地 dispatch 输入和 8 个外部依赖哈希匹配。检查结束时尚无 STARTED 或正式执行结果。

可重放记录为 `INPUT_IDENTITY.json` 和 `FINAL_STATIC_CHECK.json`，其 reviewer_source_sha256 分别绑定实际检查代码。身份检查执行 3 条只读 Git 命令。当前审查真实 CLI、产品、Blender 和评测消费者启动计数均为 0，owner 收尾仅使用模拟对象。

新审阅连接实际查询结果为 context_bound=false、host_epoch=5、rebind_required=true，未使用其他上下文句柄。工作授权沿用本批明确派单。

消费者答案质量、采用机制和成本留待各自正式审查阶段。
