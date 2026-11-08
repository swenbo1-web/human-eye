# CONSUMPTION-RUN-001 — single invocation stopped

唯一授权调用已结束，8答没有完成：T01/N启动后Codex CLI以exit1退出，0公开JSON事件、0终答；冻结runner因登记树回收证据无法确认停止继续，余7槽原样not_run。没有重试、换模型/provider、补答或改valid位。controller自身exit0只表示程序返回结果，不表示消费者成功。

| 槽 | 任务/臂 | 原始状态 |
| --- | --- | --- |
| 1 | T01 N | error |
| 2 | T01 P | not_run |
| 3 | T02 P | not_run |
| 4 | T02 N | not_run |
| 5 | T03 N | not_run |
| 6 | T03 P | not_run |
| 7 | T04 P | not_run |
| 8 | T04 N | not_run |

后7槽reason均为previous_slot_cleanup_not_confirmed_no_further_start；dispatch为空，未启动。第1槽reason原始为null，consumer.exit_code=1、process_reaped=true、registered_tree_cleanup.confirmed=false，均保留，不将来源不明的退出改写为某个推断错误。

## 已观察调用与缺测

1个私有NativeSession和1个Codex进程尝试，0返回模型答案，0观察到的工具动作、公开事件、执行代码/产品捕获。唯一真实物理RPC是原owner close，完整TX17B/RX62B；原worker audit只有sequence1 close，其原status=unknown保留，显式closed response和owner wait另证关闭。未启动P槽，未执行产品或HE观察。

911字节原题面通过既有预算计入并向CLI stdin写入；不等于已经送达模型。实际schema/模型输入送达、backend、provider请求数、usage/token及费用没有公开证据，保持null/unexposed。未配置或调用Google/Key/替代付费API，没有超授权的第二消费者。没有MCP STARTED或协议帧原件；观察到的MCP启动数为0，不能把缺收据升级为任意进程均未曾存在的证明。

消费者stderr记录71字节；冻结runner的既定隐私过滤只保留字节数，未保留正文。controller外层stdout/stderr均0字节。故无法从原件确认CLI错误原因，不猜测配置/认证/provider原因，也不重放命令以找回消息。没有final.txt或公开答案；本批不评几何正确性，不解析/展示评分truth，不据此得出原生或插件能力、速度或收益结论。旧封存仅由机器比较字节/SHA做完整性核对，未将管理员内容投递给消费者或用于评分。

## 时间（同机perf本地观察）

外层一次controller子进程2026-11-08T02:44:33.205707Z开始，02:44:35.641233Z结束，wall2.435568秒；exec工具含wrapper观察2.6345921秒。runner测量2.3426949秒，第1槽冷链含回收1.6663684秒；这些嵌套，不相加。

第1槽dispatch→host-ready1.1752929秒（原helper startup1.0917819秒为其中子段）；CLI Popen→观察exit48.8318ms；consumer记录段含其清理53.2861ms；原close外层169.4442ms。final接收、first tool、turn completed均null，答案延迟为null，不能把快速失败当任务延迟。完整各perf时刻、原180秒期限、parent600秒期限和window在原JSON保留。

## 回收和来源

controller PID23304 owner wait/reap exit0；Blender PID28760显式closed、owner wait/reap exit0，poison=false，最终=初始几何fingerprint，原deadline不变。只读定向PID/私有runtime-path扫描未发现仍存活的匹配进程。CLI父Popen的exit1/reap有原记录，但冻结消费者没有记录该PID；登记native桥STARTED缺失，树确认保持false。后续只读扫描不改写这个位，也不能证明任意Python后代均已清理。没有杀不属于本批的进程或新增RPC。

17冻结组件、131产品及canonical01c296、helper5bc、原题面/原资产和两份私有input.blend的SHA保持。未修改旧封存、产品或运行文件。临时owned会话原始日志/配置/私有输入完整存入NEUTRAL_SESSION_BYTES.zip，原位置保留；不存在新渲染或PNG。源码/阶段封存与审计为管理成本，未混充模型性能。

## 证据和关闭

actual_01是冻结runner原始输出，未补写状态/原因；STARTED/OWNED_PROCESS/RESULT及controller raw流在本目录。COUNTS_AUDIT和CLEANUP_AUDIT仅做计数/来源/归属，不是消费者或评分者。AUTHORIZATION_SNAPSHOT绑定原approval、PLAN cb78和同token窗口；实际source c4b5564、产品17db41c保持。ACTUAL_EVIDENCE_INDEX单独封存新增运行证据，不覆盖旧索引。

本次按停止合同关闭唯一尝试，8槽分母完整，7个未跑原因可核。之后只有根复核与独立计分阶段；本实施者不加测、不优化、不补消费者。
