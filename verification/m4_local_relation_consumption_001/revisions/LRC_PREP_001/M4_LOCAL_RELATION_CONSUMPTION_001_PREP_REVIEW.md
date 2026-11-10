# M4-LOCAL-RELATION-CONSUMPTION-001：准备包复核

**暂不发正式GO。** 固定准备 `169b0be061e91b126f46313478690564ccb2bd60` 的分组、来源、评分语义与主要合成路径通过，但匿名打包器不能交付“第一格启动前失败、零消费者启动”的真实终止批次。先修这一项报告出口，再核必要差异；模型消费者继续为0。

固定 PLAN SHA `698b74ec8607e499693d1d34394e4ae06f9bca2e52ac1bda456cc96d4e453761`；打包器 SHA `90f07a6b78457bb7ca9a5b93fbb7d78bf3439b547cfb21ff4fbae0b0c76ab0d4`。

## LRC-PREP-001：零消费者启动的失败包被拒绝

位置：实施树 `verification/m4_local_relation_consumption_001/quality_handoff/pack_quality.py:332`。该断言要求执行记录中至少有一个 `consumer_pid > 0`，用来区分真实执行与准备。

运行器在格循环前已创建当前批次 STARTED。首格输入核对、actor启动或初始快照失败时，可以合法结束并保存第一格 `consumer=None`、非空错误/停止原因，以及有 `batch_ended_ns` 的终止 RUN_RESULT；后八格未运行。若CLI创建失败，已有消费者记录也可能真实保留 `consumer_pid=None`。这些都是正式失败结果，不能要求虚构PID才能归档。

根与独立质量子审分别构造完整合成输入、九格计划/映射、绑定的合成GO/STARTED和终止记录，均复现：

`AssertionError: at least one recorded consumer launcher is required; preparation is not a quality run`

公开INDEX没有生成。原RUN_RESULT未被删，缺口是失败交接被拒绝；不是产品几何或模型回答质量错误。根复现位于 `verification/fixes/20261111_m4_local_consumption_prep_review/repro_zero_launch.py`、`ZERO_LAUNCH_REPRO.json`。所有GO/PID/终止数据均明确标为合成测试，实际模型、产品、Blender进程为0。

最小修复要求：

1. 允许由本批真实GO、STARTED和终止RUN_RESULT共同绑定的零启动失败前缀生成完整九格交接；保持真实null和未运行尾格，不生成假PID、假答案或成功状态。
2. 只有准备材料、缺失/不一致的启动绑定或未终止运行仍不能冒充正式交接。沿既有控制记录做窄范围来源核对，不新增通用运行框架。
3. 增加首格失败＋八格not_run的合成反例，并覆盖缺少/错配启动依据的拒绝；既有231项、三组绑定和语义保留继续通过。无需真实模型或Blender验证。
4. 保存169b0be0及本次反例，更新必要脚本摘要/PLAN/FREEZE/索引，回报FIX_READY。产品、输入、顺序、评分语义、收益规则、安装和运行时预算不变。

## 已通过的独立检查

- 根实际重放作者合成测试231/231与3个分组测试，另用真实冻结PLAN逐格核九格映射。直接编译已核源字节，未删除或读取本地缓存执行这些模块；无外部进程/网络尝试。
- 运行器子审83项无进程mock通过，覆盖实际prepare配置生成和consume记账前段。外部N/P0/P1到内部N/P的映射及external_group保留正确，两READY/schema分别选择；新cells/lrc01…09接本批目录，空工作区沿旧前缀但不复用旧01…06。actor/transport与旧版原字节相同，原时界、计时、关闭和停止路径保留。
- 质量子审确认原17个字段、86个语义叶值不变；只更新允许的样本元数据。双分组绑定、合法嵌套字段、错误/重复/缺响应、未确认文本和原final字节保留。新收益合同分别对P0和N比较，先质量后完整中位时间及实际token，不混历史六格。
- 来源子审核当前P0/P1各137安装源、Git/wheel/canonical、entry/admin/binding、共用Python与CLI字节；产品树137源未变。两工具目录只有relations说明的已审差异；11项共同输入逐字节沿用。当前Pro登录、额度和provider可用性仍未测，未用静态文件核验冒充在线成功。

## 准备资料数量澄清

原ARTIFACT_INDEX列680文件，加根级INDEX/FREEZE/PREP_READY为683；固定提交实际有692份批次文件。封存脚本按basename排除FREEZE，另有9份嵌套合成FREEZE未入索引，但均在Git且完整存在，来源子审已逐blob补核。

这不是9份原件丢失，也不影响三组安装选择。应在本次修正封存时明确“索引范围”和“提交文件总数”，列出9份漏索引文件；可收窄为只排除根级自引用记录，或保留范围并提供独立补充摘要，不能再称683等于全部提交原件。不为此重跑产品或重新随机匿名映射。

作者报告的875.063302秒是目录创建至readiness封存的部分准备窗口；本轮聊天完整窗口约1044.878秒，范围不同、相互嵌套，不相加。历史准备失败均保留。缓存删除曾被自动审批以“blocked by policy”拒绝，未执行或重试，缓存保持本地；本复核无需清理它。

本轮原件与分项报告在 `verification/fixes/20261111_m4_local_consumption_prep_review/`，分别为根重放/复现、`runtime/`驱动、`quality/`语义与打包、`source/`当前来源核查。实施者只处理上述准备交接修正，完成后根复核再决定唯一九格GO。
