# CONTINUITY-001 FIX2：三轮收集后统一验收

2026-11-13。固定基线1875bf45c09e8cca606f4de3fd8f0e821cc0d8a5。只修工程runner的证据阶段顺序和结果记账，不增加在线capture reader，不改产品、共享worker或已接通消费者。

## 为什么选择这个最小改动

FIX1在线verify_business读取关闭后才发布的WIRE，必然在BASE后中止。事实/距离/kernel的报告仅写入结果，并不决定后续操作；BASE、REPEAT、登记EDIT和第三轮查询均已固定。因此在三轮完成、唯一finish确认之后复用现有WIRE reader验收，既能覆盖原目标，也不需要另一套call文件、CRLF重建和证据来源合同。

FIX1原结果0工程通过/1失败/2未运行、prelaunch失败live0及全部后验诊断不改。在线reader候选保留作历史诊断，本批不采用。继续固定产品452b44d2、138源4067c864…a9f6、原BASE/EDIT和已有隔离安装。新增材料集中verification/m4_surface_scan_continuity_001_fix2/，引用旧固定材料摘要，避免无意义复制整套fixture与旧日志。

## 唯一运行路径

`启动 → BASE收集 → REPEAT收集 → 登记EDIT及回读 → EDIT收集 → 唯一finish → 逐轮事实核验 → sequence核验 → 结果与完整计时`

在线继续检查成功回执、真实thin EOF/退出、同endpoint/owner/backend/product/session、轮次屏障和原deadline。回执明确业务错误、unknown/partial或执行状态不明时保留真实状态并停止后续，不自动重试。这里只读当前回执状态，不依赖WIRE。

登记EDIT的前态核对、单次执行、实际姿态回读仍在线，由原actor.qa_advance完成；不得把这部分也延后。初始化与登记EDIT回读文件按原流程保存。当前观察结果不用于决定额外动作，测试副本以外无编辑。

保留各轮业务的原started_ns/ended_ns，thin结束时固定；后验失败不得将ended_ns重写为关闭后的时间。另记qualification_started_ns、qualification_ended_ns和错误。宿主事件须落在该轮原业务区间；现有事件只有started_ns和elapsed_ns，按两者相加核结束位置，不假定存在新的ended_ns字段。避免后续查询、QA、EDIT和关闭事件混入。

唯一finish必须在正常和异常路径都执行；只在后台确认关闭、终态WIRE已发布时进行可支持的后验核验。BASE/REPEAT用原INITIAL，EDIT用当时保存的登记EDIT回读，不得都套最终快照。原read_capture按目标sequence前缀回放，同worker旧资源服务REPEAT/EDIT的零资源包，不读未来capture证明过去。

沿用FIX1唯一活动bind_source_snapshot、verify_c_turn、verify_c_sequence及原WIRE reader的字节逻辑；只调整调用时机。必要共享路径改用明确固定引用，不重新设计资格函数。窄几何与rich来源未记录的边界保持。

## 执行状态和验收状态分别记录

保留计划三轮、实际尝试、成功返回、真实错误、未运行，以及每轮资格通过/失败/未核验。三轮成功后才发现某轮事实不合格，仍记录三次已执行；不得倒写未执行，不得重新发业务请求。

finish失败、WIRE缺失/不完整、后验异常或期限不足时，整体资格不得通过。没有完成资格的轮次标未核验；不能用“row.errors为空”当资格通过。验收失败也必须尽可能发布原件、关闭回执、分母和失败计时，发布异常另列，不能造成自动重跑。

原绝对590秒覆盖启动、三轮、登记EDIT、关闭、后验核验及结果写关；工具30秒。后移验收不重置期限、不从总成本排除后验耗时。计时文件自身发布按既有口径另列。

## 冻结前的一个阶段集成回归

用实际新的runner协调路径做无Blender/无provider阶段替身测试：finish之前WIRE不可读，finish之后才开放已冻结原件。证明三轮先收集、finish只一次、随后逐轮核验；不是分别调用几个helper后宣称贯通。

同一测试重点覆盖两种拒绝：finish/WIRE失败时不把未核验轮次当通过；后验某轮失败时保留三次已执行和各自原时间窗口。来源fixture分别对应INITIAL与EDIT，复用实际旧REPEAT/EDIT资源历史。保持小范围，不重建测试平台、不增加无关矩阵。

先完成准备路径自检，确认当前batch/PREPARATION/Git引用一致，再提交冻结；不能再次因复制旧批路径在live前才发现基础接线问题。旧consumer接线与N资格按固定字节复用，没有新缺口就不重复运行其全部E2E。

## 唯一新工程及交付

冻结后仅启动一个全新owned C，三次业务仍为ordinary default surface_scan、2mm、零图像。要求71/71/72匹配、112/0/10新kernel、每轮一次捕获、同session/runtime、BASE与REPEAT binding相同而EDIT失效。后台/source/actor/worker/stdio/consumer/产品保持固定，旧N三轮仅作为工程证据复用，新增N为0。

一次live失败保留并结束，不追加样本、不继续旧已关闭实例；准备期离线错误可修正留档。Google/key/503/付费暂停；新增模型/provider/API=0；默认配置、原资产、共享GUI、竞争分支不动。

交付最小runner diff、阶段集成证据、准备/交付commit、唯一C三轮原件、关闭后完整事实核验与状态分母、分段成本和旧证据引用。通过后下一项即冻结公平N/C连续模型消费，真实模型续接与usage范围仍留该阶段验证。

主动回报root local/01a1971f-eef5-7a23-a1b1-2352beb80a77，标记 **M4-SURFACE-SCAN-CONTINUITY-001_FIX2_READY**，随后结束等根复核，不自行开始模型消费。
