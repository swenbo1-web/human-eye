# M4-SELECTED-GEOMETRY-CONSUMPTION-001 准备复核

## 判定与边界

当前准备材料具备提交 PREP_READY 审核的条件。正式消费者仍为零，后续唯一九格执行需要本 cycle 的独立 GO，绑定准确 PLAN SHA 与 max_consumers=9。本次复核读取源码、差异、JSON、原始保存记录并计算摘要，业务产品、CLI 消费者、Blender 和安装启动数均为零。

核对的 PLAN SHA256 为 `bd8af1e9619ccf9dad8c43a3ecf17eb240843f5b76f4ca9390b8a283ecc00096`。31 个 dispatch 引用的实际文件摘要全部匹配，`synthetic/FROZEN_INPUTS_01.json` 绑定同一 PLAN，记录 passed=true。正式执行、匿名评分、机制成立和端到端收益均待后续对应阶段取证。

## 最小复用与来源

- `runtime/actor.py` 与原 M4-local actor 原字节相同，SHA256 为 `d1b71de84efb57d6c5df6301789817327b8c1669e1f945d817991db78b5b7f7e`。
- `runtime/consumer_transport.py` 原字节沿用，SHA256 为 `69e5fdbc701b95ae9af02b4039c465a6818d42e03178fb86ccab5c7c895cbb31`。
- 共享 backend 仍为原 `native_plugin_complex_003/reused/accepted_native.py`，SHA256 为 `13887e30d9f08309102e17704b91603325df13c490bdcc6bcda8b74ac01c59b8`。本轮使用普通生命周期和动态实际请求，未引入前次 QA profiling 或 23 序列协议。
- `runtime/driver.py.diff` 限于 cycle、九格顺序、外部 N/P/G 与原内部 N/P 的映射、P/G 安装来源及新输出身份。`prepare`、`finish`、`snapshot_binding`、`run_models` 的 AST 复用原实现，原时界、收尾、失败保留及停止尾部沿用。
- `runtime/pack_quality.py.diff` 限于 cycle 与三组外部身份。原 payload 投影、原答案和代码字节保真、零启动失败判定及 not_run 尾部规则沿用。
- P 继续使用 e077、137 源、canonical `53db41976085ce5f361d026196f4da5faf80d639af33dfced35ba58e328ef732` 的 `lr.r1`。G 使用独立 00b13060、137 源、canonical `4ebc3910652ee461d9fa7476c8df0ecf6312580d6a02e1066c0eac88bef5c76c` 的 `sg.r1`。共同依赖 Python 一致，默认激活关闭。

共享 actor 在 N 使用原生入口，在 P/G 同为原插件 actor 路径。G 的公开目录增加 geometry 能力属于候选暴露差异，P 与 N 仍可自行采用合理读取和计算路线。

## 输入、评分和抽样

独立实读确认 prompt、初图、资产的实际 SHA 分别为 `c443f907474a78ebb2491127d0064ea301d6c4ecbc6d60f1d91adc33fe1f9757`、`42466e241a4239552fa418b7f79bf1fd73c10092f174c3e87444ed5e93cbed0a`、`91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85`。三者与旧共同输入一致，场景、目录、相机和方向保持原任务含义，题面未加入 geometry 提示或插件使用指引。

评分的 17 个语义字段与原基线逐项等值。四份真值、输入绑定、来源绑定和回放引用与旧原件字节相同。新评分合同实际 SHA 为 `9364d86c2fa236fa7db7a60b5efd8d12cd33b78626256d8dbdacac7b94ddd93a`，等价记录已与之对齐。评分接受等价单位、自然语言和可验证的解析快捷证据，未知、缺失、错误、来源问题和未运行状态分别保留。执行来源绑定由执行记录承担。

匿名映射初稿的 Q 前缀及乱序行与沿用 packager 合同不兼容，协调方已在消费者零启动阶段纠正为 `answer_[0-9a-f]{16}` 和固定 slot 行序。`preparation_history/ANONYMOUS_MAPPING_CORRECTION.json` 与四份原稿保留此次修改，真值、题面及上述评分语义保持一致。质量展示再按 opaque ID 排序。

九格固定 NPG、PGN、GNP，每组各三格，全部来自同一历史场景。失败、未知和 not_run 尾部保持九格分母，替补数为零。过去矩阵只作历史证据。一场景的三次重复支持本任务内的观察，覆盖范围仍为一场景。

## 公平控制与 GO

PLAN 与 pure 输入回执的 15 项共同参数吻合。请求模型为 `gpt-6.1-sol`，effort 为 medium。共同 CLI 原字节、Pro 路由和实际 `--image` 参数构造沿用，hooks、记忆和无关工具关闭。消费者时界 450 秒、原 cell 时界 570 秒、actor 启动 40 秒、工具尝试 32 次、物理 RPC 128 次、单次工具 30 秒、完整文本响应总预算 1 MiB、单次原生代码 256 KiB、初图 1 张和新增图片 0 张均保持原合同。

570 秒从每格输入校验前开始，延续至拥有的服务及 backend 收尾。准备、构建、安装和审核成本另列。实际 argv 与图像字节的准备检查已经保存，provider 图像接收、模型视觉消费、当前 Pro 可用额度及未暴露的 resolved model/effort 保持 pending 或 unknown。PLAN 中 `prepared_file_and_argument_contract_verified=false` 为保守记录，纯检查与实际 provider 接收两种证据在回执和说明中各有范围。

`driver.go_contract` 核当前 cycle、授权 true、准确 PLAN SHA、max9、sgc01 至 sgc09、固定组序和安装映射。旧 GO 无法作为当前派发授权。准备阶段的 synthetic GO 仅存内存测试对象。当前 PLAN 的 formal status 字符串描述后续阶段目标，实际 phase 与 model_execution_authorized 仍明确为准备、false。

## 机制分类与收益判定

`MECHANISM_CLASSIFICATION.json` 将四种功能类别、操作子类和信息新颖性分开记录。同集合几何补查明确按真实 attempt 计数，覆盖新场景读取、缓存打印和未向模型交付几何的缓存计算。纯已交付数据计算单列 compute-only。缺失三角片仍属于合法新增几何。中心或简单算术、关系重算各有独立类别。

consumer 程序持有完整数组与模型已见完整数组分别记载。协调方私有 INITIAL、schema 能力、片段见证、未知几何或仅顶点均不能自动填补完整 mesh 或连接信息。对象实例、来源代和实际字段的先前覆盖决定重复标签。混合调用完整计成本并保留新增颜色、材质或外集合对象字段。来源、操作和正确使用无法确认时保留 unknown，相关不确定性会使机制成立条件保持未证实。

G 至少 2/3 格需自然请求并正确使用 geometry，且有证据避免原同类局部补查。G 同类补查总数还须低于本轮 P。P 可自行避免补查。只有实际总工具调用下降才能声称减少模型工具往返，几何字段覆盖与完整调用节省分别判断。

匿名质量先封存，再揭示机制与分组成本。G 与每个比较组均需 3/3 完整正确，之后分别比较 G/P 与 G/N。两个比较都要求完整 cell 中位时间和三格实际 input+output token 总量各自不增加，并至少一项达到 10% 降幅。缺失 usage 保留 unknown，缓存或 reasoning 子集避免重复相加，字节量和墙钟各按其实际单位报告。费用、provider 内部重试和未暴露字段保持未知。机制成功、质量通过与净收益是三个独立结论。

## 唯一工程 smoke 与现有 QA

已只读核 `smoke/run_01/RESULTS.json`、三次原请求响应、worker 和关闭记录。一次拥有的后台会话完成 OFF、vertices、full，模型消费者为零，306 项来源检查均通过，errors 为空。三个响应的 core 在仅剥 trace 与显式 geometry 后严格相等，来源和 revision 一致。

OFF 省略 geometry。vertices 返回两个选择对象的 40 个世界顶点，full 再附对应 76 个捕获三角片。预期值取实际捕获的 local、矩阵、米制比例与三角数组。资源 delta 为 4、0、0，后两次结果缓存命中，明确输出的 exact/surface/closed pair 计数均为零。工程 smoke 的 source 核对与这些诊断支持附件复用范围，完整正式任务收益仍待消费者记录。

四条实际宿主序列包含三次业务请求与一次 close。原 backend 第四条 close 事件保留 `status=unknown`，同时独立 closed 回执、实际拥有进程退出和产品 runtime 句柄均确认 exit0。初终几何指纹一致，原文件和保护文件未变，新增图片为零。

synthetic/r1 的 38 项检查覆盖三组映射、旧 GO 拒绝、actor/transport 原字节、公共参数、完整 payload 和答案字节、初图 argv，以及两种零启动失败与八个 not_run 尾部。`FROZEN_INPUTS_01.json` 进一步核本次准确 PLAN、九映射、共同参数与原初图。上述检查保留各自 source 和执行范围，消费者与业务调用均为零。

## 收口

本次采用已有后端、最薄派发映射和限定的合同记录。机制计数的初始歧义与匿名身份元数据不兼容已在正式消费者前纠正并保留历史。当前读取材料中未见需要扩展产品、补历史完整矩阵或追加准备场景的阻塞。默认延迟归因及默认准入保持原有限结论，后续按已冻结的一次九格任务验证质量、实际自然使用及完整成本。
