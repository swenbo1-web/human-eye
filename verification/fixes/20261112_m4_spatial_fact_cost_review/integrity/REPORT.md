# M4-SPATIAL-FACT-CONSUMPTION-001 解封来源独立复核

结论：**本轮来源和保存的执行完整性证据通过，未发现阻断缺陷。** 六个薄客户端的 EXIT 回执仍为 unknown；独立后端退出证据不能将它们改写为 confirmed。本报告不复算几何质量，也不替代成本与消费机制审查。

## 已独立核验

| 范围 | 实际检查与结果 |
|---|---|
| 原正式证据 | `ORIGINAL_DATA_INDEX.json` 的 1087 项与正式提交 `5cdf62f311f94890ca569d06c1a858f1578225e4` 的整个批次文件集合完全一致；每项核原始字节、Git blob ID、字节数、SHA256，并核当前磁盘及新提交完全相同。 |
| 解封新增文件 | 固定新提交 `a44a6138b9d354ecc98a4fbd76095f0536d6973f` 相对原提交仅添加 `cost_review_01/` 内 27 个文件。`REVIEW_MANIFEST.json` 列 26 项，加清单本身为 27；逐项核摘要、字节数和固定 Git blob。没有原件或产品修改。 |
| 质量封存 | seal 原始 SHA256 `fa467d121359d8ffff45693887de2598f1d34a811bf031849215042ef0e44852`；复制件、`D:/hefe` 实际 seal 与根提交 `3a4b090532e01920110e6ee2be1702bc1c45c265` 完全相同。seal 引用的 20 个质量文件逐项核实际根字节、固定 Git、大小和摘要，不重新打分。 |
| 执行冻结 | 执行 PLAN `d40c81ba…e672` 在准备提交 `02c7784e…db34` 已冻结；FREEZE、GO、26 个 dispatch 输入均匹配；8 个明确列出的外部输入当前哈希仍匹配，未扫描其他目录。 |
| 产品/安装 | 137 源逐项核工作树、产品提交 `e836e03f…b50f`、正式/解封提交、既有隔离安装同字节；规范摘要重算为 `2c453e56…c390`。未导入产品或启动安装入口。 |
| 资产/配置 | 同一实际副本 SHA `27f197a8…de46`；六个独占 worker 的资产副本均同字节、工作目录各异。六格实际 CLI `-c` 参数与共同冻结 settings 对照，初图/新交付图零、无 `--image`；三个产品配置完整绑定各自私有 native host/port、独立 state/audit 和固定产品身份。 |
| 工具声明 | 六份实际薄客户端 `tools/list` 原始 RX 与各自冻结工具列表相同；共同原生声明跨两组相同，产品组只额外转发原普通 observe 声明。三个实际产品进程启动命令均未带 `--spatial-task-only`。 |
| 原件归档 | 六份匿名包对应原始 ZIP 的全部 437 成员，与对应正式格文件集合和每个实际原始文件逐字节相同；最终公开答案也逐字节匹配各格 PUBLIC_FINAL。没有以作者“已通过”字段代替这些比较。 |

## 六格状态与退出证据

固定顺序 `N/P、P/N、N/P` 的六格均已启动、完成，无替补；RUN_RESULT 的逐格 consumer/finish 与独立保存文件相同。六个 CLI thread_id 各异，保存的 CLI 状态 completed、退出码 0、process_reaped=true，valid_completion/safe_to_continue=true；无调度级错误或工具越界。

逐格沿 ACTOR_LAUNCH → OWNER_FINISH → owner/CLOSE → native/SESSION、native/CLOSE、WORKER_CLOSED 核对 launcher/owner/worker PID、原 570 秒期限、初末几何摘要与回执一致性。六个 native owner 的保存回执均记录 process_reaped=true、exit_code=0，worker 未 poisoned。此处读取和检查的是原先执行时产生的证据，没有再次探测当前 OS 进程。

三个产品格另核 PRODUCT_RUNTIME_PROOF 的 launcher/runtime 父链与创建时间、业务前已保留的 handle，以及结束后的 retained Windows handle 退出记录。实际实现 `preflight_client.py:117–140` 用同一保留句柄的 `WaitForSingleObject/GetExitCodeProcess` 判断退出，再关闭句柄；保存值均为 exited=true、exit_code=0、handle_closed=true。它没有把“PID 查不到”当退出证明。

**六个 thin-client 状态继续保留 unknown。** 每格的 bridge STARTED 原件存在，对应 EXIT 原件确实不存在；`bridge_cleanup.confirmed=null`、`receipt_status=unknown`、`missing_exit_count=1` 与原件一致。独立 CLI/owner/native/product 的退出证据成立，并不补齐薄客户端自身缺失的正常退出回执；也不据此反推后端没有关闭。

原 450 秒 consumer 期限、570 秒全格期限都与各自首次起点一致，没有重开；所有格在其已登记期限内结束。时间数值的收益比较由另一个成本复核负责。

## 质量在前的顺序与可证明范围

可核的记录顺序（UTC）为：正式证据提交 **08:29:46** → seal **08:47:08.737425** → 根质量提交 **08:47:32** → 本地解封工单 **08:53:06.878198** → 解封提交 **09:17:04**。seal 绑定原公包摘要 `efc07484…fb9f` 和 6/6、78/78 质量结论；本轮没有改动它。

这个顺序能证明保存工件的先后，不能仅凭 Git 和文件时间证明每次私有文件访问的先后。作者解封工单也明确记载：本地工单落盘前已有只读检查和委派。未把较晚的工单时间当成所有读取的精确开始时间；也没有证据据此认定先于质量 seal 解封。完整访问历史属于本轮未独立可见项。

## 仍未知与范围限制

- 薄客户端正常 EXIT 回执缺失；当前 OS 存活状态未另查。
- 资产初末相同、原生代码审计和已记录图片事件，不能排除任意 Python 的全部瞬时操作。本轮不把有限审计称完整沙箱证明。
- 服务器实际模型/effort、provider 调用总数、货币费用不由来源一致性推导；不因配置相同就声明服务端解析值已知。
- 未重新执行产品、Blender、消费者、API、几何 oracle、正式 driver 或作者完整性检查器；只运行自己的标准库来源/回执核查脚本。
- AL 已用自身真实句柄复核：context_bound=true，但 assignment.current=false，仍为旧任务 `6cf50798…febe` 的 parent_read_only 绑定；当前父任务为 `015e941d…61cc`。未借父句柄、未写父任务。

## 核查脚本记录

`check_integrity.py` 和 `RESULTS.json` 提供完整可复核断言及逐格退出摘要。首轮脚本在共同原生 schema 摘要断言失败：审查脚本从键排序的 schema 文件重序列化，但原 producer 摘要依原代码字典顺序。只读核对既有 `encoded()` 实现后，以 AST literal 读取已冻结 NATIVE 声明、核结构等价并保留原插入顺序重算，检查通过；未修改作者证据、产品或预期摘要。随后增加三个实际产品配置的完整绑定核验并再次通过。没有运行新的产品候选或试验。
