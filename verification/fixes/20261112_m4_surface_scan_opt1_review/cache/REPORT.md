# OPT1 对象依赖缓存：独立源码与条件探针复核

2026-11-12。结论：未发现这八个文件的改动引入错误对象对复用或使当前扫描错误 complete 的阻塞缺陷。对象依赖能跨局部 scene revision 保留未变几何测量，现有全目录和覆盖检查继续执行。独立 31 项纯 Python decoder/cache 探针通过，支持将工程候选交完整消费者对照，不建议继续为本固定题追加缓存变体。

本报告不独立认证 33 个实际 Blender 请求、质量 oracle 或性能比例；那些由父任务另行核查。本子审没有启动产品服务进程、Blender、模型、网络或付费 API，也没有执行作者 224 项套件。

## 身份与方法

使用 learning-worker 技能和自身 Hook 句柄，assignment `192ddf16-e681-4bb7-9755-219e26a5b51c`，父任务 `2ceda2c3-5d8c-4544-8471-d6807eb70579` / revision 1 / write_version 607，只读父任务。未写实施树、Git 或父任务状态。

源码固定产品 `c1cb2da32034e056a270384e691a2cde8dddbc0d`，相对初版 `c6355a01a4c6ee204a0d676cd9309f02428fe3ba` 审八文件 diff，约 177 行新增、10 行删除。语义阅读扩及原 ReadContext 的 reset/activate、delta 捕获和两条 host 返回路径，以及作者定向测试定义。采用的源码和测试/报告文件逐项与证据提交 `860b87138d40de9cc08b01c947dd864d58da9295` 的 Git 字节核对，见 `SOURCES.json`。

独立 `probe_cache.py` 载入两份已核 Git 字节的冻结模块 `scene_residency.py`、`scene_cache.py`，放在本审独立 Python 包命名空间；不导入作者 fixture、产品几何 solver、runtime 服务或审计脚本。自建三个三角形的资源/姿态包，用明确的几何端点结果检查缓存应命中还是重新计算。它验证的是版本依赖和缓存行为，不冒充一次三维最短距离验收。

## 数据流与键的充分性

1. `live_service.py:1408` 在当前 host 捕获和 `_packet` 校验之后，调用私有 getter。两条 host getter 均转交本实例 decoder；正常返回的是原 decoder payload，没有为取依赖而新增 wire 字段或 RPC。
2. `SceneDeltaDecoder.apply` 每次先清上一 token，只在完整解码成功、资源状态正式提交时生成当前 `SurfaceScanDependencies`。getter 要求相同 payload 对象及对应 capture/host/document 签名，成功取出后清 decoder 引用。
3. token 类由模块内 authority 创建，objects 是只读映射，元素为标量元组。普通 JSON 字段/普通 dict 不会触发绑定。其签名是内部所有权检查，不是对任意恶意进程代码的隔离承诺；当前同步请求在 decoder 与 reducer 之间没有改写顶点的代码路径。
4. reducer 在正常化后核 union、名称、来源和 incarnation，再把当前 mesh 实例绑定到短依赖摘要。摘要包含 runtime source，以及 host source、decoder owner、host instance/epoch、document epoch、incarnation、resource id/revision/admission、实际 matrix/scale；signed zero 保留。
5. pair 键继续包含算法版本、数值参数和有序 focal/reference。表面 solver 的输入是当前世界顶点/三角面；标签、pivot、display axes 不改变这一算子的距离。普通 task/solid 没有启用 `_surface_scan`，仍走原 `_measurement_mesh` 元数据合同。

对象名来自当前目录。重命名不使旧标签进入新报告；对序相反使用相反的依赖顺序，直接 miss 后得到相反端点，不靠不完整的见证翻转复用。阈值不在几何距离键内，当前 reducer 用已存精确距离重新比较，排除集合和覆盖仍由本请求重建。

## 资源冲突、删除及普通路径交错

相同 resource id/revision 的扫描重传需要完整内容一致，序列化比较保留 `-0.0` 与 `+0.0`。冲突在正式资源/world/admission 状态提交前拒绝，失败后不发布 token。

资源从 live 集合移除时同时移除 admission。原 ID/版本后来重入时获得新序号，因此不能命中删除前的值。decoder owner 隔离连接对象，instance/epoch/document 又提供宿主和文档变更边界。

普通非 scan delta 的旧合同不新增同版本冲突拒绝，但每次资源替换递增 admission。独立探针专门验证了“先 scan 缓存 → 普通 delta 同版本替换数组 → 再 scan”：新 scan 不沿用旧缓存，所见端点来自替换后的几何。该交错不会通过普通路径绕过新键的失效。

## 独立探针结果

31 条条件断言全部通过，覆盖：

- 首次 miss、局部移动只命中未变 pair、移动端点更新、反向 pair 独立 miss 与端点对序。
- 通用测量键与 scan namespace 分离，同面数几何变化 miss，其他未变 pair 继续 hit。
- 同版本不同内容原子拒绝，删除后同资源重入失效，普通 delta 交错重绑后失效。
- copied payload、capture 签名变化、普通 dict 凭据回退；getter 消费后不再取得相同 token。
- incarnation、尺度、document、host epoch、matrix signed zero、runtime source 和 decoder owner 变化失效。
- unknown 结果不写成有效缓存，预算 callback 在 miss 时阻止计算而 hit 不扣新核预算。
- 现有 store 的真实 LRU 淘汰；容量 1/2 的小型反例均触发预期重新计算。

探针没有失败后重试产品，也没有增加性能样本。完整代码、所用两份模块摘要和全部断言在 `probe_cache.py` 与 `PROBES.json`。

## 状态、容量和性能结构

ReadContext 仍在每次 activate/reset 清当前绑定；OPT1 没有保留旧完整场景报告跨 revision。每次 packet 全目录、分区和当前 unsupported 状态先检查，unknown_source 在测量查找前处理。结果 complete 的含义仍来自当前 coverage，而不是缓存命中数量。

token 在本请求栈内临时保留 raw packet；cache 只保存当前 normalized mesh 引用与摘要，不保存 token。getter 消费后 decoder 不再保留该 packet。当前 mesh 附带 map 受 256 对象范围限制，不累积运动历史。

测量结果仍在原 `_measurements` LRU、原 `_charge`/`_trim` 路径，配置 2 MiB/256 entries 不变。新增依赖摘要保持短键，未扩 store 或复制一套几何。进程 RSS、临时编码峰值仍须看真实记录，不能由 accounted bytes 推导全进程内存。

源码中未见为实现命中新增每 pair 全场哈希或全资源扫描。完整 JSON 资源内容比较仅发生在同版本重传，通常 delta 命中不传资源数组。逐 pair 依赖诊断和请求 cache.stats 有成本，已进入本候选的真实计量；不根据代码行数估算它的净耗时。

## 结论边界

当前改动满足“仅缩小 scan surface 测量依赖、复用已有 store、保留完整当前覆盖”的设计。31 项条件探针和源码审查未发现需要先派修复的错误复用。作者 224 项、实际 104 hit/10 miss 和成本门仍应由根基于原件独立确认，不能用本报告替代。

传输父期限等待、hidden 求值/包围界异常和旧 nearest g06 是前一阶段已披露的问题，本次八文件没有关闭这些事项。缓存工程收口后应转固定模型消费，不再无限细调这个已定位场景的内部速度。模型答全、自然调用和整个任务净收益才是下一未证能力。
