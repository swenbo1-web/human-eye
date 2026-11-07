# BOUND-SOURCE-QA-001 索引

状态：一次四状态实测完成。正常更新正确；NaN/越界角索引正常RNA可达并被当前目录严格排除。不等于最终nearest错误或产品准入。

- `REPORT.md`：结论、build、四状态、NaN比较口径、字节/清理及一个针对性建议。
- `PREREGISTRATION.md`、`controller.py`、`worker_body.py`：启动前冻结原件，不再改动。
- `run_01/PLAN.json`、`FREEZE.json`、`ENVIRONMENT.json`、`STARTED.json`：身份、原资产/二进制、源码、脚本分母及启动记录。
- `run_01/STATE_1.py` 至 `STATE_4.py`：四份实际代码；SHA与TX及worker执行记录一致。
- `run_01/rpc_1` 至 `rpc_4`、`rpc_close`：原始 TX/RX、解析回执和实际socket字节计数。
- `run_01/owned`：原样私有input.blend、NativeSession配置/ready、四次实际SCRIPT/stdout、事件/关闭及每状态 journal、native oracle、capture、恢复结果。
- `run_01/ANALYSIS.json`、`analyze.py`：独立离线核验与四状态摘要，不启动Blender、不导入产品。
- `run_01/OFFLINE_INITIAL_ANALYSIS_ERROR.json`：保留首次离线查错字段及零真实重放记录。
- `POST_SOURCE_CHECK.json`：交付前产品/原资产/helper/二进制/脚本再次核验。
- `DELIVERY_MANIFEST.json`：除自身外全部交付成员字节数与SHA256。

只重放离线分析：`python -I -S -B verification/bound_source_qa_001/analyze.py`。controller 的单轮标记禁止再次启动；不要删除 STARTED、替换环境或重跑真实状态来扩展分母。根汇合下一阶段决定后续实现，本轮无生产gate、无默认切换、无性能比较。
