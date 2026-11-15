# 成本审阅初稿记录

本文件对应保留的 `COST_REVIEW.json` 初稿。初稿599项检查中449项通过，150项数组 dtype 比较因表示形式不同产生误报。NPY 使用 `|u1`、`<i4` 等描述符，保存元数据使用 `uint8`、`int32` 等类型名。

修正记录位于 `COST_REVIEW_CORRECTION_EVENTS.json`，原分析脚本保留为 `analysis_scripts/review_cost_attempt_01.py`。最终审阅采用 `COST_REVIEW_R1.json` 和 `COST_REVIEW_R1.md`。
