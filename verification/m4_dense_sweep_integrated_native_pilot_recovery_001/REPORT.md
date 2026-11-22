# M4 密集全场原生对照恢复

**两份旧资格的派生准入通过，正式对照未完成。** N1 启动时，派生准入把资格目录留在 Python 模块搜索路径中，运行器随后加载了同名的资格预算模块，无法导入运行所需的 `Budget` 类。N1 在构造运行器前失败。P1 按冻结顺序保留为未运行。本批新增 Blender、模型、业务调用和构图均为 0。 [原 N1 结果](evidence/N1_SLOT_RESULT.json) · [实际分母](evidence/ACTUAL_DENOMINATOR.json)

| 范围 | 资格或正式状态 | Blender | 业务调用 | 构图 | 模型 |
| --- | --- | ---: | ---: | ---: | ---: |
| 原 QN | 原判通过 | 1 | 6 | 2 | 0 |
| 原 QP | 原判拒绝，恢复批从原件派生通过 | 1 | 4 | 3 | 0 |
| 新 N1 | 启动尝试失败 | 0 | 0 | 0 | 0 |
| 新 P1 | 未运行 | 0 | 0 | 0 | 0 |
| 合计实际资源 | 原资格计一次 | 2 | 10 | 5 | 0 |

N1 从启动记录到发布 2.028 秒，其中准入校核 2.009 秒。槽仅含原启动、结果和发布三个文件，未创建预算或工作进程。正式原答、原图、模型质量、用量和整任务收益无实测。 [新运行次序](evidence/SEQUENCE.jsonl) · [正式计量](evidence/FORMAL_LEDGER.json)

## 原判和恢复准入

原批 QN 通过、QP 拒绝及正式两槽未运行完整保留。736 件原 ZIP 成员逐件核对 Git、索引、长度、SHA-256 与现存文件。按 owner 核对旧构图预约、结算、时钟、上限、唯一命中和实际证据。QN 的两个 native ordinal 与原 PNG 回包一致。QP 的三个 audit 切片绑定原 producer attempt，发现计 3 次，无图量测计 0 次。两个槽发布时的本槽值为 2／3，累计值为 2／5，待结为 0。旧关闭及带结果摘要的发布采用原时钟验收，派生准入另记本次离线时钟。 [派生准入](evidence/DERIVED_ADMISSION.json)

复用冻结的几何、图像和路径校验，原 QP 三片、两张完整局部原 PNG、六向正面积遮挡、0.25 m 世界 +Z 及真实点对均可从原线包复核。19 项构图与关闭反例全部拒绝；另外验证错发布摘要、晚发布和坏关闭。对 19,446 B 原 QP 线包只改 1 B，将局部 SCENE 换为同名全场帧，仍按作用域错绑拒绝。 [构图反例](qualification/BUDGET_PREFLIGHT.json) · [恢复入口预飞](qualification/RECOVERY_PREFLIGHT.json) · [原现场四张 PNG 与线包](../m4_dense_sweep_integrated_native_pilot_001/REPORT.md)

## 启动故障离线复现

派发预飞提早导入了运行器，漏掉正式顺序中的“先执行准入，再首次导入运行器”。两个独立冷 Python 进程沿真实启动入口复现。原路径再次出现相同 `ImportError`。另一进程仅在内存保留并恢复准入前的 `sys.path`，成功导入正式运行器、桥接和 `harness/budget.py`，在构造运行器前主动停止。离线验证只读固定来源，原冻结、原 N1 失败和 P1 未运行保持。 [启动复现和修法对照](evidence/RUNTIME_IMPORT_ISOLATION.json)

本批只复用原 `cee6fe78` 隔离安装、`219541e9` 资产、原 1,072 B 题面及工具合同。固定规划 `67b4e561ba387d04d905b9d51e1ca23e3738571d`，新冻结 `ea4c90e1567ac61d823f97a6d58244ce73e7e85d862a376041730e52f61b4bca`，795 项输入。新派生准入 `7d37be07327a090741b4ba6bfbfa5229007d8404a14e90938966e8906dd93a56`。新资格、替补、产品或资产重建、安装、原资产或旧证据写入、共享配置改动、Google、额外模型 API 和费用均为 0。 [冻结](FROZEN.json)

新归档 9 件、28,580 B，SHA-256 `aef290d67a13869ffb643298d10592adb7c48611e22ec19ebc969561741f78c2`。原资格 ZIP 独立保留。 [新归档索引](RAW_INDEX.json) · [新原件 ZIP](ORIGINAL_RUNTIME.zip)
