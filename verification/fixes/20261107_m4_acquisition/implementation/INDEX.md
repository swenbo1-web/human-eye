# 文件索引

- `RESULTS.md` 为唯一判定报告，结论 M4_ACQUIRE_001_DEPENDENCY。
- `audit_sources.py` 为仅用标准库读取固定 Git blob、重建 131 源身份、提取行号原文和宿主方法清单的复核脚本，不 import/执行产品，不模拟取数策略。
- `source_index.json` 为脚本实际生成的固定源码 manifest、原文锚点和接口检查记录。Git blob 为证据来源，当前工作树产品文件不作基线。

复现命令如下，只写本目录内的 source_index.json，不访问 Blender。

```powershell
& 'D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe' -I -S -B 'D:/hefe/verification/fixes/20261107_m4_acquisition/implementation/audit_sources.py'
```

报告/脚本/索引的 SHA256 与提交号由唯一完成回报附送。任务书在上一级 ASSIGNMENT.md，本轮没有改写。
