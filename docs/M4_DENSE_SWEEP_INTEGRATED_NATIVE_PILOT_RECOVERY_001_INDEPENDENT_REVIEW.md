# M4 密集原生对照恢复独立复核

原 `8a7ff397` 的 QN 通过、QP 拒绝和原正式两槽未运行继续保留。`62a631344922ddcea57d78b051a37d33629ad3a2` 的恢复冻结 `ea4c90e1567ac61d823f97a6d58244ce73e7e85d862a376041730e52f61b4bca` 含 795 项，派生准入 `7d37be07327a090741b4ba6bfbfa5229007d8404a14e90938966e8906dd93a56` 通过。两旧资格的 2／3 独占构图、累计 5、业务 10、原出版及关闭继续绑定。完整三片、局部原图、六向遮挡、0.25 m 世界 +Z 和实点对由同批原件支持。恢复 ZIP 9 项、28,580 B、摘要 `aef290d67a13869ffb643298d10592adb7c48611e22ec19ebc969561741f78c2`，逐项核验长度、SHA-256 和 CRC。 [恢复报告和原件](https://github.com/swenbo1-web/human-eye/tree/62a631344922ddcea57d78b051a37d33629ad3a2/verification/m4_dense_sweep_integrated_native_pilot_recovery_001)

N1 在构造运行器前失败，P1 未运行。原 N1 结果摘要 `0f09e4e6d1c538877e7b9d713c96b2a7e674f10e24972cb0c2bc458daf48e963`，独占窗 2.027766 秒，准入 2.0087216 秒。新现场、模型、业务、构图均为 0。冻结保留原失败和末启动状态。 [正式真实分母](https://github.com/swenbo1-web/human-eye/blob/62a631344922ddcea57d78b051a37d33629ad3a2/verification/m4_dense_sweep_integrated_native_pilot_recovery_001/evidence/ACTUAL_DENOMINATOR.json)

独立以固定解释器分别执行两次冷入口。原路径的真 `validate_admission` 通过，`verify_derived` 执行检查代码后遗留资格、oracle、依赖等临时搜索路径。正式首次导入运行器时先命中 `qualification/budget.py`，重现 `cannot import name 'Budget'`。在验收入口返回时还原准入前的 `sys.path`，同一真准入后首次导入命中 `harness/budget.py`，正确导入 `Runtime` 和 `Owner` 后在构造前按离线探针停止。准入过程未把 `budget`、`runtime`、`bridge` 留在模块缓存。旧预飞提前导入它们，实际验证次序因此不同。本次独立复现零新现场和模型。 [原栈和冷入口对照](https://github.com/swenbo1-web/human-eye/blob/62a631344922ddcea57d78b051a37d33629ad3a2/verification/m4_dense_sweep_integrated_native_pilot_recovery_001/evidence/RUNTIME_IMPORT_ISOLATION.json)

采用[正式冷启动修复方案](M4_DENSE_SWEEP_INTEGRATED_NATIVE_STARTUP_001_PLAN.md)。原资格不重跑，两个历史失败阶段分开保留。
