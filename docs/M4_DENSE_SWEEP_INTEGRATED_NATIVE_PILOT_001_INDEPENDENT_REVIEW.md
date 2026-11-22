# M4 密集全场原生对照资格独立复核

固定 `cee6fe78`、`219541e9` 和原 1,072 B 题面。原冻结判定 QN 通过、QP 拒绝，N1/P1 均未运行。核远端证据 `8a7ff397efd99fb5474c3018a36444db36f13395` 及其 ZIP 736 项、2,002,049 B、SHA-256 `018c22641c8e539aa42ba0c4e36d324178f90699877f3c15504c363d1769bc09`。原冻结 `5145456e2a8dbd272800a70e5e0b9ea9402e034592a29d8008f26367579f3aad`。资格用时 4.209623／6.272875 秒，业务 6／4。该诊断覆盖范围不同，正式原答和模型收益目前没有数据。 [原报告与封存原件](https://github.com/swenbo1-web/human-eye/tree/8a7ff397efd99fb5474c3018a36444db36f13395/verification/m4_dense_sweep_integrated_native_pilot_001)

原 QN 两条普通 raster 预约结算各为 1，绑定各自独占槽和不同 frame ordinal。QP 三条结算各为 1，逐份以原 `product_audit.jsonl` 字节切片重算摘要，同产品实例的三个独立生产 attempt；无图量测的新增构图为 0。原 claim 和 settlement 的标签、token、摘要、时钟及上下界均匹配。逐槽值 2、3；两个结果发布时的累计值 2、5，待结为 0，正式构图和模型均为 0。两槽 Blender 的实际持有句柄均确认退出 0 并释放，QP 另有真实 MCP EOF、退出 0 及句柄释放。原关闭和带结果 SHA 的发布均早于各自既定期限。冻结 `qualification/closed.py` 末段把单槽 `proof['rasters']` 与批累计 `all_raster_actual` 比较，复现 QP 3 对 5 的拒绝。 [原账本与结算](https://github.com/swenbo1-web/human-eye/blob/8a7ff397efd99fb5474c3018a36444db36f13395/verification/m4_dense_sweep_integrated_native_pilot_001/evidence/RASTER_SCOPE_RECONCILIATION.json)

同一 QP 原线包实际发现正文 8,108 B，三张原图。两张完整局部图的表面／对比边界像素为 LEFT 103,695／1,372 和局部 SCENE 49,929／926，已按 PNG 和原归属数组独立复算。同名全场 SCENE 只有 1／1。两张局部图的回读块与首包原文件一致。三候选、六个视向具名挡片、0.25 m 世界 +Z 及真实点对通过。独立有理投影核实六向正面积，2×514 个三角的包围盒距离下界均大于等于 1/16 m²，点对达到。固定 CLI 原件重放 18/18。局部与全场同名的等长单字节错绑控制继续有效。 [原答前诊断、图和关闭](https://github.com/swenbo1-web/human-eye/blob/8a7ff397efd99fb5474c3018a36444db36f13395/verification/m4_dense_sweep_integrated_native_pilot_001/REPORT.md)

原 `admission.qualified` 还核原发布到验收在原独占期限内，原执行器要求新槽目录。补充离线复核时钟应独立记账。历史批保留 1/2、正式 0/2；下一步以[只读原件的派生准入和正式恢复](M4_DENSE_SWEEP_INTEGRATED_NATIVE_PILOT_RECOVERY_001_PLAN.md)推进，零追加资格。
