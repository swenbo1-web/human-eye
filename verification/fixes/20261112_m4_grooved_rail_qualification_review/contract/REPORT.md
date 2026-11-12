# 独立资格合同子审

2026-11-12。**本子审未发现阻止下一固定六格的合同、制备来源或收尾缺陷；65/65 个离线检查通过。** 完整距离、相交、自交和包含资格由父审及数学子审另行决定；本结论不能单独替代它们，也不构成六格执行指令。

核查唯一实施树 `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_transfer_001`。父指派 HEAD 为 `9f38e8522cfeea9a580a19baad0e0d823eb1a16f`，本子审未运行 Git；HEAD、全包 manifest 与产品基线由父审独立核对。已读根冻结计划和包内 DESIGN 全文，已读 builder、export、controller、audit_saved_asset，以及关闭相关 helper 源码。

自身 learning-worker 绑定已核：context `cf0eab4c79024ea8bbc3111f61822211`，assignment `0300ec24-79d5-4b96-8f99-7738fab384ed`，当前固定父任务 `5c3264ff-fb5e-4705-b980-8568715aa93c` revision 1 / write_version 599，`parent_read_only`。未修改父任务。只在本 contract 目录写入脚本、结果和报告。

## 独立检查分母与结果

`check_contract.py` 重新从冻结设计手工转录有理坐标与三角规则，未导入作者 builder、oracle 或产品实现。使用指定 Python 的 `-I -B -X utf8` 执行，exit 0，`RESULTS.json` 保存 65 项检查。

| 本次实际独立核查 | 分母与结果 |
|---|---|
| 冻结文本 | 根 PLAN 与包 PLAN、根唯一设计与包 DESIGN，2/2 字节一致 |
| 实际局部几何 | 4 对象、26 点、78 坐标分量逐项等于固定有理值转 binary32 |
| 三角编号 | 36/36 与固定规格相同；Target 24，三四面体各 4 |
| 壳边与连通 | 54 条对象边均恰两次反向使用；4/4 面图连通 |
| 槽端盖 | 固定下端五片、反向上端五片、14 侧面；未用跨槽中心扇形；实际 xz 有理面积和等于实际七边形面积 |
| 世界表示 | 78/78 世界坐标分量由实际矩阵及实际局部值按声明的 binary64 次序重算相同 |
| 单位与矩阵 | METRIC/METERS、scene scale 1、局部 mm；输入严格为固定 R/1000 与 T/1000；四对象实际矩阵一致 |
| 答案泄露 | 4 对象与 mesh 名仅为指定名称；自定义属性和材质为空；mesh attribute 全为普通内建名；scene 属性为空 |
| 静态输入 | 4/4 无父对象、修改器、约束、动画、shape key |
| 进程证据 | 两个独占进程的 PID/退出/回收回执闭合；QA 1 次导出执行加 1 次关闭 |

矩阵实际读回与输入最大元素差 `2.3283064365386963e-10`，符合已记录 Blender 分解后存储差；实际值未吸附回名义值。世界坐标相对理想规格误差全部小于 `1e-6 m`；具体最大值保存在 RESULTS 的 `world_nominal_error_below_1e_6m.detail`。本项是表示一致性检查，不代替真实最近点精度证明。

## 资产、worker 与成本

资产和 QA input 副本字节相同，SHA256 `49c0dccb233181a97d6d1508cc2570c03c961dffd2f8c8ef4ba12ebae3f9ec67`。快照 SHA256 `6bb073b9aa29e7eecc5aa74ad2330cbb8fb5c5e06c79e70bf71091a33470ff52`。原始 export receipt JSON、call stdout 与独立快照相同；QA SCRIPT 与 export 脚本文本相同。控制器、构建、导出、冻结、helper 的当前 SHA256 与开工回执一致，helper 同时匹配 SESSION 绑定。

builder PID 26560，exit 0，reaped；QA PID 13068，在 snapshot/session/closed/close 之间一致，exit 0，reaped，close response `closed`、error null。QA 初末几何指纹相同、未 poisoned，资产和受保护文件保持相同。构建、QA worker 和导出 stderr 均空，PREPARATION errors 为空，没有 FAILURE 文件。已知构建失败 0、唯一候选 1、oracle run 1 无 exception；没有从失败后另选替补的包内迹象。

WORKER_EVENTS 第二条 `status=unknown` 已核原因：helper 初始化 event 为 unknown，处理 close 后直接发送 closed 并 break，finally 仍写 event，未更新其 status。独立 close 回执与 WORKER_CLOSED/exit 0 能消除此条的关闭歧义；它不是第二次几何执行，也不应被当成待决消费者结果。

成本账有明确窗口，独立重算纳秒和时间戳一致：控制器 1.7478196 秒；嵌套 builder 0.6062143 秒、QA close 0.1399730 秒；oracle 分析 0.8763288 秒，包含发布 0.9153460 秒；freeze 至 finalizer 输入核验 1399.879649 秒。这些窗口不能相加为总耗时。协调者/审阅费用、早期读取及随后发布/Git/回报未完整计量，作者已经明确标为 unmeasured 或排除范围，没有将其报为零。

## 零调用证据与结论边界

作者报告的评测消费者、产品预试、图片均为 0。当前独立核查支持这一包内声明：控制器只启动 factory build 与 condition N 的独占原生 QA，构建/导出脚本无产品或模型调用，QA 仅记录一个导出 script，包内无图片，ledger 与 PREPARATION 的相关计数均为 0。这里的 QA `condition=N` 是读取基础设施的分组参数，不是一格模型消费者。未发起 Blender、产品、消费者、模型或 API 新运行。

“未出现包外未记录活动”不能由静态包证明，本审没有作此无限否定。作者所报 288 个互体三角对、294 个自体三角对、54 次包含查询，以及 A/B/C 真值/特征属于作者几何证据，本子审不冒称独立重算这些分母；交由数学子审审查。若父审的 manifest/Git 与数学资格均通过，可保持原冻结题面、六格次序、原门槛及预算推进，不需要为当前记录文字或关闭日志格式另开修复。
