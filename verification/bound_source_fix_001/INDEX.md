# BOUND-SOURCE-FIX-001 索引

完成：候选f34db5c，2正常成功＋3指定来源拒绝；非nearest/发布准入。

- `REPORT.md`：唯一产品变更、测试/历史失败、工作/内存、五态和清理。
- `CANDIDATE_IDENTITY.json`：131源/ae3bd4a…唯一候选。
- `PREREGISTRATION.md`、`test_source_validation.py`、`DIRECTED_TESTS.txt`：16定向用例及真实输出。
- `regressions.py`、`REGRESSIONS*.json`、`LEGACY*.txt`、`HOST_SELECTED_REGRESSION.txt`：raw旧fake失败、初适配失败、最终17＋71通过；原件均保留。
- `measure_work.py`、`WORK_COUNTS.json`：helper本身实际属性读数与临时marker分配，不含原witness/capture，不是性能样本。
- `PREP_STAGE_CHECK_ERROR.json`：启动前raw日志空格检查问题，未导致真实重试。
- `controller.py`、`worker_body.py`、`analyze.py`：唯一冻结执行/离线分析源。
- `run_01/PLAN.json`、`FREEZE.json`、`ENVIRONMENT.json`、五份STATE脚本：启动前分母和字节绑定。
- `run_01/rpc_*`：原始TX/RX、回执和字节；`owned`含私有原样input、实际执行脚本、oracle、状态/捕获/受控错误、journal和NativeSession生命周期原件。
- `run_01/ANALYSIS.json`：真实五态独立核验；0真实重放。
- `POST_SOURCE_CHECK.json`：131源、原件/helper/binary、旧_capture正文及冻结代码最终复核。
- `DELIVERY_MANIFEST.json`：除自身外本目录全部证据成员字节/SHA256。

可仅重放离线：`python -I -S -B verification/bound_source_fix_001/analyze.py`。不得移除STARTED后重跑controller或扩展真实分母。既有QA/static历史和另一线M3分支未改。
