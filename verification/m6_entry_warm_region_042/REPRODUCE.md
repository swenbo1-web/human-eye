# M6-042 复核入口

冻结合同位于 c7c00d98289fad46e71a4278db7b7a4ea5858d5d 的 docs/M6_FORMAL_ENTRY_AND_WARM_REGION_042_TASK.md。041 已发布实验位于 37de6d795f6329e0257a327d862ac87d5131a439。042 的完整原件留在 D:/HumanEye/runs/M6-042-ENTRY-WARM-REGION。

## 普通 Blender 暖读

用标准库从已封存的 GUI、生产 stdio 收据和原始请求／答复重新检查 48 条业务结果与 12 对暖读。默认只读并打印 JSON。

    python -I -B audit_live.py D:/HumanEye/runs/M6-042-ENTRY-WARM-REGION/live

live_yanyite.py 记录实际执行入口。它复用 036 的普通 Blender GUI 和 stdio、041 的两套实际安装、034 的选区真值，以及同字节 Yanyite 源。freeze 和 run 产生新档案，使用已有原件重算时无需运行这两个阶段。每组完整时钟与公开答复见各 CELL.json 及 client 下的 TX／RX 文件。H3 的独立采集在全部正式业务请求后完成。

## Codex 与同几何回放

entry 与 replay 子目录记载各自入口、状态和取证边界。实际宿主事件和纯回放各按自己的分母评分。

完整原件见 EVIDENCE.json，合并决议见 RESULTS.json。
