# 五次实际观察的独立质量复核

固定候选 `452b44d2dcf231d6675bef54e568db0431a29261`，138 源摘要为 `4067c864c3db1ba586cd7179e6430db5acc4d71675b5295416d471632851a9f6`。只读取唯一 `engineering/run_01`，3,680 项离线检查通过。

| 实际请求 | 匹配数 | 完整正文 UTF-8 B | 独立 raw 位值核对 | full 表面见证点 |
| --- | --- | --- | --- | --- |
| BASE default | 71 | 7,911 | 71 | 展示省略 |
| BASE brief | 71 | 7,911 | 71 | 展示省略 |
| BASE full | 71 | 34,754 | 71 | 142 |
| EDIT default | 72 | 7,912 | 72 | 展示省略 |
| EDIT full | 72 | 35,209 | 72 | 144 |

## 实际输入与正文绑定

五份回执的请求和响应均逐项绑定产品原始 stdio TX/RX。正文长度由实际 content text 的 UTF-8 字节重算，compact 的对象表、列说明、metadata、来源及 trace 全计入 10 KiB 门。

独立解码器按照列说明和局部索引恢复 ID/name，按 common metadata 与逐行 exceptions 合并恢复方法、见证状态和其他元数据。五次共 357 行的原始 distance_m 位值逐行等于实际私有 observe disposition。默认/brief/full 同态结果的顺序、对象身份、raw 位值、逐行 metadata 及所有原顶层字段一致，逐请求 trace 作为当前观察身份单列。

所有结果保留 complete、24 对象和 276 对覆盖分区，unknown/deferred 为零，delivery 的原始总数、交付数和 complete 一致。BASE default/brief 和 EDIT default 均低于 10 KiB。

## 独立几何事实与见证

重用资格阶段冻结的 BASE/EDIT exact rational truth，先核 SHA256 及其快照绑定。两个实际 QA 快照的完整字段与冻结快照逐项相同，仅排除 pid 和副本路径。552 个原全对象对的精确平方距离与 binary64 的 2 mm 阈值重新核成员关系，未重新执行几何求解。

五次可见匹配集合完整，BASE 为 71、EDIT 为 72，漏项、误报和重复均为零。357 条距离以有理数平方区间核对独立真值，误差沿用 1e-10 m。

两个 full 的 286 个见证点用本核验器独立的有理数点到三角形算法检查，分别位于当前对应对象的三角表面容差内，见证间距与报告的距离一致。算法使用精确平面投影和三条线段界，未导入产品投影器或几何求解函数。

BASE full 与旧封存 P1 首次详细响应的全部原顶层键相同，除当前 binding 和 trace 外，每个字段连同全部原始见证、方法和匹配顺序完全一致。两个 full 的文本均符合原紧凑 JSON 序列化合同，未出现 display_encoding。

## 来源变化和缓存事实

每个响应都绑定本候选 source。BASE 三次和 EDIT 两次分别具有相同场景及来源 binding。姿态编辑后 scene revision、scene fingerprint 和含空间覆盖的 directory digest 均变化，document epoch 与 host/runtime source 保持。五次 trace 各异。

私有原 observe 记录的新增 kernel 次数为 112/0/0/10/0，与冻结预期相符。这是实际记录的计算工作核对。完整扫描分区与独立真值共同验证了编辑后的结果。

## 保留事项

初始终端检查曾因过宽摘要截断，并误用过两个探查键。正式核验器首次将原有理数的十进制字符串直接传给两参数 Fraction，随后改为显式整数解析。第二次误将 directory digest 当作仅由名称构成的身份，核源合同后确认它还包含空间覆盖，改为要求姿态变化时失效。失败及修正留在 `CHECK_HISTORY.json`。

本轮仅新增 `audits/quality/` 材料，没有修改已有 semantics、工程原件或产品文件。新增 Blender、product、模型与 API 运行均为零。实际 stdio 到工程控制器的完整响应可核，模型实际上下文、token 和完整任务收益仍未测。

`verify_quality.py` 可用既有 Python 加 `-I -B -X utf8` 离线复算，结果为 `QUALITY_RESULT.json`。Agent Learning 当前未绑定，host epoch 5，需要宿主重连。
