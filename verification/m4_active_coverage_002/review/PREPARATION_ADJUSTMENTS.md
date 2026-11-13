# 准备期静态调整记录

以下三项在正式开始前通过静态阅读提出并修正，期间没有执行子进程预试或render。原表达式和修正结论保留于此。

## 旧帧引用的读取阶段

首稿 `verify_frozen` 和 `--freeze` 使用 `hashes(reference_files())`，会在新worker运行前读取001的PNG、NPZ与帧JSON字节，而冻结字段标为 `parent_post_run_reference_only`。

修正后，`reference_hashes()` 只读取001已封 `CONTENT_MANIFEST.json` 的十八份预期摘要，source whitelist绑定该清单。旧帧实际内容读取留给child完成后的管理员validate。本次静态复读确认runner中的旧帧路径只用于从清单索引期望值。

## 控制器时界的描述

首稿先执行首次 `verify_frozen`、写锁，再设置 `batch_started`，PREREG文字却覆盖全部setup/import/input integrity，窗口范围与描述不一致。

修正后，`batch_started` 位于run入口、首次校验及唯一锁之前。PREREG与结果明确列控制器bootstrap、标准库import、首次FROZEN读取及最终自发布处于整批记录窗外，保持未测。每个worker的主时界仍在Popen之前开始，覆盖自身启动、import及完整退出回读。

## unknown尝试数的汇总

首稿 `sum(row.get('render_attempts') or 0 ...)` 将缺失尝试数合入一个确定总数；虽然另有完整性标志，数值字段会被读作实际完整计数。

修正后，逐arm记录known lower bound。存在unknown时actual总数为null，失败保留并停止后续槽。已知数值和未开始槽的语义单列。

## 静态复读版本

- runner SHA256为 `9ae321f697dc3b53ddc39eec26d607db355ab1f58825632e4ac8600bb0aaf2bd`。
- PREREGISTRATION SHA256为 `9460084ee17ec18e9b1fbed9441faa0d58907e0535dbf18aa609d36d95704135`。
- 001根接受记录 SHA256为 `706028a58c48b1c2ae1bacc0cfdd4c1e72460ee8ab0189ae2294a2a375216a2a`，包含已接受的首次三角形见证与定向控制资格，本批沿用。

这些摘要对应本轮准备静态复读，最终冻结摘要由root统一记录。尚待runtime和validate实际源码完成后静态核对整条接线。

## ndarray元数据字段

准备稿runtime的 `array_metadata` 输出dtype、dtype_str、shape、nbytes及sha256五个字段，validator首稿却将其与缺少dtype_str的四字段字典全等比较。两端业务数据正确时也会被拒绝。

静态修正将validator期望的dtype_str绑定实际数组的 `value.dtype.str`，保留五字段完整比较。该项在首个worker启动前发现并更正，期间没有制造失败运行或渲染样本。

## 像素不足控制的收口条件

准备稿控制只要求BACK有真实像素不足，以及B在BACK之后继续一次观察。root补齐实际反馈验收，要求BACK不足集合中的区域确实出现在后续step.new_roi_ids，最终像素不足为空且unresolved只含当前池几何不可见区域。验证从实际集合推导，控制目标身份与终态数量没有手填。

该补齐属于唯一正式批开始前的控制接线检查，图像预算和主性能分母保持原计划。
