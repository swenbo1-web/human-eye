驱动子项结论：**未发现新增驱动接线阻断。** 固定提交为 `169b0be061e91b126f46313478690564ccb2bd60`。根正在处理的“首格零消费者启动失败不能归档”属于打包器问题；本报告不据此签发正式 GO。

本轮实际做了源码差异审查，以及83项独立无进程检查，覆盖全部9格。未调用 `run_models`；没有创建正式 GO、STARTED 或 cells；没有启动 CLI、Blender、产品服务或真实 actor。模拟的 prepare 将全部 Popen 边界替换为内存对象、输出限定在根复核目录；实际 transport consume 读取这些生成的 cell.json，生成 argv 和初始记录，在 Popen 边界被注入异常，然后走其原有 finally。该核查比只检查 arm_runtime 返回值多覆盖了配置→cell文件→transport目录→argv→consumer记录的接线。

原件：[DRIVER_WIRING_REVIEW.json](D:/hefe/verification/fixes/20261111_m4_local_consumption_prep_review/runtime/DRIVER_WIRING_REVIEW.json)，SHA-256 `bb49909730e7b8170528b0129740199f4dd1a0580b234d37a0f99f7696163712`。复现脚本：[check_driver.py](D:/hefe/verification/fixes/20261111_m4_local_consumption_prep_review/runtime/check_driver.py)。这些是根目录里的模拟回执，不是作者正式预检或消费成绩。

具体结论

- [driver.arm_runtime:40](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_local_relation_consumption_001/runtime/driver.py:40) 正确将外部 N/P0/P1 转为内部 N/P。P0/P1 对应不同 READY、entry、install_root、源码摘要和公共 schema；N 不启动插件。原 slot 未修改，`external_group` 同时进入 actor config、cell.json 和内部 slot。
- [prepare:71](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_local_relation_consumption_001/runtime/driver.py:71) 实际读取按 profile 选择的 READY 和 schema，不只依赖纯函数返回。actor/transport 与已审六格版本逐字节相同。[actor:109](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_local_relation_consumption_001/runtime/actor.py:109) 运行时会核对真实 initialize 的源码身份，随后第114行要求实际 tools/list 完整 schema 等于所选配置；本轮未把这段源码检查声称成新的真实进程验收。
- [consumer_transport:132](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_local_relation_consumption_001/runtime/consumer_transport.py:132) 的 HERE 来自新包文件位置，实际读取新包 `cells/lrc01..09/cell.json`，endpoint 与 attachments 均来自对应格。空工作区父目录仍叫 `.m4_observation_baseline_001_runtime/work`，但叶目录使用新的 lrc01..09，且强制为空。本轮只读确认原位置9格均可满足 fresh 条件；模拟实际走通9个对应目录，没有把旧01..06拿来消费。
- [consumer记录:141](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_local_relation_consumption_001/runtime/consumer_transport.py:141) 使用 `{**slot}`，因此真实 transport 形态中 group 是内部 N/P，external_group 保留外部 N/P0/P1。9格模拟持久化记录均验证这一点，不能仅根据内部 group 区分两个插件版本。
- 原450秒消费者、570秒整格、40秒actor启动预算保持。模拟核对 actor deadline 从传入原 cell_started_ns 计算，consumer deadline 从自身 started_ns 加450秒；原代码的 timeout/cleanup路径未改。整格计时从逐格验证前到实际 owner close 后，包含清理；若清理使总时长超过570秒，保留超限结果并停止后续格，不重置期限。570秒是完整结果的预算判断，不应描述成关闭动作绝不会越过该时刻。
- [GO合同:57](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_local_relation_consumption_001/runtime/driver.py:57) 接受新 cycle、固定 PLAN SHA、最大9格及固定新序列；真实旧六格 GO、新cycle但最大6格、错误hash、旧cell名、重排顺序五项均被独立调用拒绝。正式 `STARTED.json` 仍以独占创建防止同包重复启动。
- 同步消费、清理和停止逻辑相对旧驱动未扩大。`safe_to_continue`、配置/协议失败、provider不可用、owner关闭不明和整格超限仍停止；没有新增替补或自动重跑。thin EXIT未知与后端关闭仍分开记录，未用未知thin状态冒充正常退出。

首格零消费者失败能否形成终止批次

可以，在磁盘正常可写且原异常被既有处理捕获的情况下：[第178行](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_local_relation_consumption_001/runtime/driver.py:178) 在格循环前已创建 STARTED；首格 prepare/consume失败进入 except/finally，尽力关闭已取得的actor，追加一条带error/stop的记录；第243行先写格记录，随后break，第247行记录批次结束并写 terminal RUN_RESULT。

若 CLI Popen 尚未成功，transport已建立并保存记录，`consumer_pid=None`、thread未启动、errors保留，finally仍执行。此次9格模拟的受控异常正经过了这个真实函数路径（没有进程），验证了零PID记录可保存。若失败发生在prepare返回前，外层可能只有 `consumer=None/finish=None`，仍会记录终止格；若prepare内部已尝试close，其独立关闭原件留在格目录。**因此“至少一个consumer_pid>0”不能作为归档此类真实终止批次的必要条件。** 它们必须归档为未完成/未启动，不能补造答案或消费完成。

局限：没有独立重跑真实 tools/list、启动超时、actor关闭超时或模型消费；停止循环通过固定代码差异核对，未执行run_models。整体正式运行还需先关闭根指出的打包器终止批次问题。
