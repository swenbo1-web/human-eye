# M2-DIRECTORY-RESOURCE-REUSE-001 来源与退出独立复核

结论：接受本批 `not_actionable` 出口。未发现产品修改、来源不一致或足以要求继续目录实施的本批证据。这是按原计划结束有限资格核查，不是证明目录复用永远无用，也不是新的性能通过。

## 本轮实际执行

只用 Git 读取、标准库文件/JSON/哈希核对及源码阅读；没有导入产品，没有运行 Blender、产品、模型消费者或 raster。未修改作者树、旧封存、安装、配置或其他分支。产物仅在本目录，无 Git 提交。

固定作者树为 `C:/Users/Administrator/.codex/worktrees/m2-dir-001/hefe`，HEAD `fde0e9ab21fb6eaee1750befd64ad1bebdde2961`，基线 `8f2a739e789b777358d84a168154bc7c50b929e5`，分支 `codex/m2-directory-resource-reuse-001`。读取时工作树干净。

`audit.py` 的有效结果为 `RESULT.json`：280 条离线断言通过、0 失败，读取 347 个唯一文件。断言数是文件、身份和结构核对数，不是产品功能测试数。

- 27 条 Git 差异全为 `verification/m2_directory_resource_reuse_001/` 下新增文件；26 项内容清单、总字节数和 27 个 Git blob 全部吻合。产品修改数独立确认是 0。
- FINAL_AUDIT 的 25 个直属 artifact SHA 全验；12 个重要旧 pin 全验（M1、M4 witness、transfer、view reuse 的 manifest/FROZEN/FINAL_AUDIT）。未机械重复这些旧 pin 内的完整嵌套矩阵。
- RUN_BINDING 的 141 源逐项与基线 Git、当前作者树和 `D:/he_source_face_001/product` 同字节。总摘要独立重算为 `3748d88b618db7de1347d632f2a68f3ed82a2ebb8a6321586fe756be07ea8148`。
- SOURCE_ELIGIBILITY_REVIEW 的全部 21 个关键证据 pin 和 6 个源码 pin 验证通过。
- 原管理员计划 SHA 为 `19c991d42ac17d0b8e38cfe7286c2c4c28fc4dd554c2e25c29fd52cc41d2cf21`；其中明确允许自然任务未命中时交付 not_actionable、零产品改动、零正式矩阵，转下一主线前等根复核。本批输出满足该出口。

## 关键原件核读

三项已有缓存覆盖全查，而非抽取最快例子：entry_01、entry_02 的冷目录均 miss、directory_after_full 均 hit，capture_state 与原冷目录一致；typed_01 的 directory_after_selected 与 directory_hot 保存原件逐字节相同且 cache_hit=true。因此这三项不能当作新增复用的收益机会。

唯一技术例核读实际 `stdio/rpc_08/TX.bin`、RX、`server/CAPTURE_03.json`、HARNESS_PROTOCOL 及运行器。请求 ID 为 `old_readonly_regression`，mode=directory，与预登记 fixed_requests 一致；目录确实 cache_hit=false，与前一捕获同 instance/epoch/revision 和对象实例，历史 host SHA 与当前源码相同。该宿主重复取数事实成立。

但运行器第 222–225 行只检查旧只读入口成功且输出纯文本；此后直接核对 raster 预算、guard、标记通过及清理，没有目录事实参与另一个业务结果的逻辑。因此它不能满足这次预登记的自然任务资格。入口处私有资源 stamp/pose 并未直接保存，可删除工作量仍是源码推断，不是本轮实测。

当前源码本身没有变化：目录 miss 会重新提取 evaluated mesh、变换顶点；resource 有 world mesh/stamp/pose，但缺原目录 `max(0, loops-2*polygons)` 预算元数据。若将来另有自然命中，仍不能用实际三角数替代该预算；本批没有偷偷实施这一替换。

## 采用的作者记录及未重跑范围

作者盘点为 M2 42 个工程宿主、368 条业务读取、139 次显式目录（98 hit / 41 miss），三项资源后目录已有缓存、26 条人工变更后的兼容性 unknown；M4 26 个工程宿主、1 个技术例、0 个合格自然例。本轮检查这些 JSON 分母彼此一致，并核读上述决定性原件；没有重新逐条枚举 368 条宿主事件。

作者的 M2 4,702 文件、M4 1,622 输入文件、补充 2,221 JSON/JSONL 和旧 M1 1,116 文件全矩阵没有在本轮重复执行。报告中这些数字属于作者记录，不能写为本轮独立全验。主要旧 pin 和关键 27 项来源已另行验证，足以支持本范围的零产品改动和有限退出核查。

正式六槽、候选、追加优化均是未运行；`D:/he_directory_reuse_001` 不存在。完整收益和协调审核 token/费用保持 unknown。零新增调用对本复核是直接执行事实；作者零调用来自账本，并有零产品差异、同字节安装、无候选运行目录支持，无法据此证明没有任何未记录外部行为。

## AL 与本轮脚本记录

作者前置与完成记录均为 `pending_current_chat_host_binding`、task_write_calls=0，不追认为已登记。

本复核使用自身句柄 `d92066a03b624a7a832bc2e4e11670e6`，返回 context_bound=true、assignment.current=false，assignment 仍归旧根任务 `95de6bf0-582e-412b-888b-c8e5ac70796b`；parent_task 显示新任务 `f2ac3511-ed05-469e-9a8b-710340bd4bed` / write_version 711。已向父复核报告，并按其当前明确委派继续离线工作；未借父句柄或回填已归新阶段。

首轮脚本在最后 AL 检查误将 `context_bound` 当作文档顶层字段，抛 KeyError，未写 RESULT；实际字段在 `actual_response.context_bound`。保留 `audit_R0.py` 和 `REVIEW_ATTEMPTS.json`，修正直接字段访问后完整离线重跑通过。这是复核脚本自身 schema 错误，不是候选缺陷；未用默认值跳过检查。
