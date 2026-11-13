# FIX1独立复核：纠正证据阶段，简化工程runner

2026-11-13。固定交付1875bf45c09e8cca606f4de3fd8f0e821cc0d8a5。本轮只读源码/原件及执行离线函数，没有新增产品、Blender、CLI消费者、模型或API运行。

**FIX1工程资格仍失败。消费循环接线可保留；下一修复采用关闭后统一验收，复用原WIRE路径，无需新增在线capture reader。**

## 当前事实

8000b52f冻结后的第一次命令在创建reservation/启动实例之前，因残留旧批Git路径拒绝，live=0。修正并重新冻结e06597f后只有一次新C：BASE成功返回和thin退出，后置资格因WIRE/INDEX不存在失败，REPEAT/EDIT未运行。原分母0通过/1失败/2未运行保持。

C原complete71对、112新kernel、一次捕获的后验事实可核，不把它升级为原工程通过。登记EDIT未执行，owner无活动轮次，产品和Blender已关闭回收。完整4.1995286秒包含失败和清理；不把它当连续模型收益。

## 这次遗漏在哪里

固定worker先写关SCRIPT/stdout/stderr，再发布完成事件并发送响应；完整WIRE在主循环退出后的meter.flush才发布。在线verify_business依赖终态WIRE，因此原成功响应并不能满足该读取条件。上一阶段使用已关闭实例回放，验证了内容却没有验证资料可见阶段。

独立源码审查确认，verify_business结果仅存入报告，后续固定EDIT不读取其数值。原reader关闭后按sequence前缀重放，能给REPEAT和EDIT复用历史资源；没有必须在线完成事实评分的控制依赖。

作者在线call reader候选可以重建已有记录，但引入了另一套文件和文本字节重建路径。本批选择更小改动：只移动不参与控制的事实/几何/kernel/sequence验收到唯一finish之后。来源快照、每轮原时界、在线执行状态与EDIT回读仍保留；运行状态和后验资格分别记录。详见[FIX2计划](M4_SURFACE_SCAN_CONTINUITY_001_FIX2_PLAN.md)。

## 消费循环接线已经完成

根独立读取真实consume_turn与episode协调源码，确认它们调用persist/显式UUID resume、共享workdir、绝对deadline、事件解析和真实原件归档。对已有十个本地替身case作103项独立核查，全通过，包括正常N/C六轮线程/目录/端点/进程、原ZIP成员和错误/归档失败分母。[原件核查](../verification/fixes/20261113_m4_surface_scan_continuity_fix1_review/CONSUMER_REVIEW.json)

这是既有本地子进程替身证据，不是新跑真实模型；synthetic usage没有求和，真实上下文和费用仍未测。该接线无新缺口，不在FIX2重做或全面重跑。

## 来源、阶段与下一项

独立[来源与关闭核查](../verification/fixes/20261113_m4_surface_scan_continuity_fix1_review/binding/REPORT.md)76项全过，绑定1,314交付、1,190准备、362外部输入和实际138源；原件证明唯一BASE、无EDIT、原时限内关闭，没有未知动作阻塞。检查数不是业务样本数，也不采用作者4,008项作为独立成绩。首次prelaunch零live还依赖失败原回执与确定的预留前路径拒绝，未重建全机历史进程。

独立[阶段复核](../verification/fixes/20261113_m4_surface_scan_continuity_fix1_review/phase/REPORT.md)26项全过，证明在线缺WIRE符合发布顺序，终态原reader可按三阶段sequence前缀重建相应资源而不借未来数据。另一次只读架构复核同样确认后验评分不影响预定控制路径。原始业务时界必须保持，资格另记时界；未评分不能算通过。

本轮自身问题保留：来源核验器初版直接比较Windows物理CRLF文本与WIRE逻辑LF文本，三个call比较失败；按实际write_text行为核对后通过，ATTEMPT_01留存。FIX2选择复用原WIRE路径，无需把这种文本重建纳入新运行接口。子AL旧assignment归属保留，根以当前任务登记。

原两批C失败均保留。下一批只改runner阶段及分母，在“关闭前没有WIRE、关闭后才出现”的真实协调路径替身上测试，再冻结并运行唯一新C三轮。若通过就进入连续模型消费合同，不继续增加无因果依据的准备层检查。
