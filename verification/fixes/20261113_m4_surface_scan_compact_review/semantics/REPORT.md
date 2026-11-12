# COMPACT-FACTS-001 独立源码语义复核

2026-11-13。结论：**本轮未发现阻塞三组消费对照的事实丢失、身份混淆、错误 complete 或 full 兼容缺陷。可将固定候选交下一阶段消费验证。** 此结论覆盖展示函数及源码路由，不替代独立安装/实际入口验收，也不预判模型收益。

固定产品 `452b44d2dcf231d6675bef54e568db0431a29261`，交付 `6ab4e53409e539c71a377f48708f2f8725db6dde`。基线 `c1cb2da32034e056a270384e691a2cde8dddbc0d`。唯一运行源码变化为 `human_eye_plugin/live_spatial_mcp.py`；本轮编译执行的 Git 源字节 SHA256 为 `6fc5a4b8286130f2e6847ee4d7f4efee94c65a0591940e72b924f24ccd55081f`。实施树前后均无未提交修改。

## 本轮实际检查

`review_semantics.py` 从两固定 Git blob 提取展示纯函数，以独立消费端解码器恢复紧凑行；没有导入整个产品、调用作者 checker、开启 Blender/模型/API 或修改实施树。遥测入口使用空实现，因此这里的耗时只是离线函数成本。检查脚本、原输入摘要及逐项结果分别为 `review_semantics.py`、`INPUT_SHA256.json`、`CHECKS.json`、`RESULT.json`。

**772/772 项断言通过，0 失败。** 这是断言数，包括 426 个逐行浮点位比较，不是 772 个独立场景。

| 核验项 | 本轮结果 |
| --- | --- |
| 封存六次 P1/P2/P3 full/brief 响应 | 每次原 71 行均按原顺序恢复；ID、名称、原 distance_m 位模式及全部非坐标逐行字段保持 |
| 实际紧凑业务正文 | 每次 34,754 → 7,911 B，减少约 77.24%；包含对象表、说明、binding 等全部正文 |
| 原顶层语义 | 每个已有顶层字段逐项恢复，包括 scope、coverage、unknown、delivery、binding、trace、authority |
| 默认与 brief | scan 同一输入得到相同紧凑正文；明确 full 与旧函数对相同输入的输出逐字节一致 |
| 身份与名称 | 重复名字使用不同对象索引；Unicode、引号、换行和附加对象字段保持，投影不把对象表当场景全目录 |
| 逐行元数据 | 不同 witness_status、method、reason、未来嵌套字段保留；布尔、整数、浮点、正负零不会被 Python 等值比较错误合并 |
| absent 与 null | 某两行显式 null、另一行缺字段能够分别恢复，没有错误提取成共用字段 |
| partial / unknown / 空结果 | 状态与原上游 delivery.complete=false 均保持，没有因表示缩小自动补齐或升为 complete |
| 距离边界 | 正负零、最小正 subnormal、最小正规数、阈值两侧、最大有限 binary64 与大整数保持原值；展示 mm 不用于重新筛选 |
| 毫米溢出 | 大有限米值的 mm 以十进制整数字符串给出，经 Fraction 独立核对为原 binary64 值乘 1000 的精确结果 |
| 未支持结构 | 保留字段冲突、未知 status、不同单位/坐标框架、坏端点/见证形状、同 ID 内容冲突回退原 full 字节 |
| 错误与非有限值 | is_error 保留 full；原数据 NaN/Infinity 在旧/新版本均拒绝，未因删见证而被隐藏；主动投影异常与输出编码异常回退原全文 |
| 非 scan 默认 | task_query、surface_nearest、directory、普通旧结果、arm expert、普通错误默认输出与旧函数一致 |
| 可变对象隔离 | 修改投影对象表、coverage 和逐行嵌套元数据不反写原 service value |

独立数值夹具刻意含超过阈值的已经交付行，以验证展示层不重新分类；这不证明求解器应将它归入匹配。原 full 世界见证坐标只在紧凑表示省略，属于已批准范围；其他逐行字段经过 common + exception 规则无损还原。

## 源码和架构判断

`project_surface_scan_brief` 只读取现有 service value，构造对象表、行与说明，没有宿主采集、求解、网络或持久缓存路径。原 full JSON 校验先于投影，展示失败可回原文本。Common 字段按 JSON 编码逐值比较，避免 True/1、0/-0 等不恰当合并；exception 按稳定行号合并，原匹配顺序未变。

scan 省略 detail 的结构改变是明确的兼容变化：旧客户端若依赖 `matches[i].objects`，需要识别 `display_encoding` 或显式 `full`，不能声称零适配兼容。当前公开 description、schema 条件默认与 `COMPATIBILITY.md` 均披露该变化。非 scan 的省略默认仍为 full。普通服务内部结果未变。

显式 full 是新的当前观察，可复用原缓存；它不是旧 trace 的历史证据读取。本候选没有新增服务、检索库或回读协议。组合多次结果应使用 scene/source binding，不能要求 trace 相同或假设两请求之间场景不变。

本轮原始源 diff 与探针支持进入消费测试，不支持把“CLI 正文缩小”写成“模型输入完整”“模型会直接采用”或 token/端到端收益。相应指标须由后续九格回答。

## 已知非阻塞边界与下一次优化条件

1. **空结果存在负收益。** 使用封存真实顶层 envelope、仅将 matches 换成空列表的表示探针，原 full 为 1,546 B，紧凑为 2,243 B，增加 697 B（约 45.1%）。新增列说明和引用协议有固定成本。本探针只测空列表表示，不声称它是独立采集的真实零匹配场景。此次 71 行任务明显节省，不能推广为所有任务都节省。仅当后续真实空结果任务出现并影响成本时，再决定按实际编码取较短表示；不为此改冻结候选、追加门或延迟消费。
2. **等价端点字段顺序可触发 full。** 同一个 ID 的端点记录如果仅字典键顺序不同，JSON 字符串比较会将其视作冲突，回退 full。已实测原正文完整保留，这是表示降级，不是身份或事实错误。封存六次输入未触发。未来存在这种输入时，可比较稳定规范编码或缓存规范端点编码；没有必要在本轮替换算法。
3. **展示投影增加少量 CPU。** 单次离线探针，每路径 60 次，旧 full 中位 0.1903 ms、新显式 full 0.1904 ms、新默认 0.85695 ms，新增约 0.67 ms。新默认包含完整值预序列化、端点一致性编码与紧凑编码。此处没有真实遥测、安装或宿主开销，不作端到端性能承诺，也不以这点成本启动优化循环。

## 三路消费方案附审

已读根 `M4_SURFACE_SCAN_COMPACT_CONSUMPTION_001_PLAN.md`，本次读本 SHA256 为 `0dfea3156b5c6db34b835bc45441eb7aabb23cccc30953928a5a39cf8e73a3fd`。没有发现必须修改的变量控制遗漏：九格 N/O/C 拉丁顺序、各格新上下文与 owned 进程、O 明确为扫描 OPT1 而非桌面旧主干、真实工具 schema 变更属于整候选、固定题面与预算、先有限匿名质量后成本解封、C/N 原 0.70 门与 C/O 改善分别判定均明确。

维持原计划。三次重复只筛选此固定任务；失败与 unknown 不补样，实际 usage 缺失不记 token 门通过。新格式是否减少原生重算由实际事件判断，不从消费者自述推断心理信任。

## 复跑与边界

```powershell
& 'D:\hefe\.human-eye\releases\9.7.2+20261028.support.discovery.r1\.venv\Scripts\python.exe' -I -B -X utf8 'D:\hefe\verification\fixes\20261113_m4_surface_scan_compact_review\semantics\review_semantics.py'
```

本轮未运行：Blender/模型/API、实际安装入口五观察、provider 输入采样、未知外部 JSON 客户端全集。入口及证据验收由根其他核验并行处理；不能把本报告的纯函数通过替代它们。

Agent Learning：子 Agent 句柄 `83190789b8504a49bb04b5450cedf946` 仍归属此前固定 assignment，session 显示 current=false。本轮依据根明确的新只读委派执行，未借句柄、改父任务或把旧 assignment 伪称当前阶段记录。
