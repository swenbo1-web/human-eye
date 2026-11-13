# FIX2 三轮事实与缓存来源独立复核

2026-11-13。交付 `56caf228f6d0224f36796606c7f27b3c24223768`，准备 `1511af696b564a0b261b70d5f0562325daa1f2a7`。父 AL 任务 `f275a20b-0fb0-4d1a-88ac-1cf335b3b929` revision 1 / write 624；子代理旧 assignment 如实保留，未借父句柄。

**通过：未发现阻塞正式 N/C 连续模型消费的事实或缓存失效缺陷。** 不需要再新增一轮工程准备。本结论来自原始响应、请求绑定审计、实际 capture 资源和固定 BASE/EDIT 真值，未执行作者整套 checker。

## 本轮实际核验范围

只读一个已录制的 C episode、三个业务调用。新增 live / Blender / 模型 / API 调用均为 0。每轮核全体 276 对，共 828 份处置；公开匹配共 214 条。独立脚本 4143/4143 断言通过，断言数不代表业务样本数。

`review_facts.py` 自行解码 compact 表、核单位/对象引用、计算真值距离及阈值成员关系、重算 pair 依赖 key，并逐对连接缓存与实际几何。唯一复用的是既有正确 `read_capture` 来源函数的 AST 提取；读取时禁止目标序号之后的 WIRE payload。源码和输入 SHA 见 `INPUT_SHA256.json`，全部结果见 `RESULTS.json`。

| 轮次 | capture序号 | 匹配 | 新计算记录 | pair命中记录 | 全结果命中 | 本次传输资源 |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| BASE | 2 | 71 | 112 | 0 | 否 | 24 |
| REPEAT | 3 | 71 | 0 | 0 | 是 | 0 |
| EDIT | 7 | 72 | 10 | 104 | 否 | 0 |

原件执行分母为 planned/attempted/successful_returns/succeeded 各 3，failed/not_run 各 0。旧 001、FIX1 的失败记录本轮未改动。

## 几何与独立真值

BASE/EDIT truth 和 rich reference 均先核既定 SHA。三轮 24 个对象的实际 capture local vertices、faces、完整 matrix、单位与对应当时 owner snapshot 及固定 reference 精确相同。REPEAT、EDIT 的零资源包均从序号 2 的 24 个资源解析，未读取未来 capture。

三轮每个 pair 的阈值状态与独立有理数平方距离一致；界限排除还核了 lower > 2 mm 且 lower² ≤ 真值距离平方。全部 measured distance 用 90 位 Decimal 平方根核对，最大绝对误差约 **1.034223025 × 10⁻¹⁸ m**，小于沿用的 10⁻¹⁰ m 验收容差；没有放宽容差。公开 matches 与 private disposition 的 distance_m 位表示一致，派生 mm 也是 distance_m×1000 的相同浮点结果。无漏对、多对、重复、unknown 或 deferred。

这些仍是 unsigned triangle surface distance；solid relation 明确 not_evaluated，不能写成实体碰撞判定。

## 缓存不只由汇总计数支持

REPEAT 的完整 capture 几何、资源引用、binding、276 对处置及公开事实与 BASE 相同。原审计 pair_calls=kernel_calls=0，逐 pair diagnostics 为空，measurement cache 前后完全相同；live_service 的全结果命中分支复用已存完整结果与相同处置，未进入 pair 循环。这里的 0 pair hit 增量不意味着没有复用，而是复用发生在更外层。

EDIT 的实际几何只有 Obj_008 的 matrix[2][3] 从 0 变为 `-0.000750000006519258 m`；全部 local vertices/faces 不变，其余 23 对象完整几何不变。document_epoch/宿主源/runtime源保持，scene_revision、scene_fingerprint、directory_sha256 均失效。

原审计有 114 份独立 pair diagnostics。逐项核对后：

- **104 次命中**：两端均非 Obj_008；实际两端 capture 几何与 BASE 完全相同；BASE 已计算该 pair；dependency key 相同；原处置逐字段相同；surface_pair_count=0、surface_work 为空。
- **10 次新计算**：全部涉及 Obj_008；surface_pair_count=1、surface_work 有实际工作计量；旧候选的 dependency key 改变，另两对为新候选。measurement computations 增量为 10，entries 从 112 到 122，hits 增量为 104。
- 从所有 pair diagnostics 汇集的对象依赖摘要只改变 Obj_008。按源码公开的算法版本、参数、两端依赖摘要自行重算 pair key，全部对应实际记录。

因此 104/10 有实际前后几何、资源版本、逐 pair key 和输出支持，不是仅接受报告中的总计。此轮没有新增内核 profiler；相关执行次数仍来自实际计量事件，并由这些独立条件交叉核对。

## EDIT 的准确变化

- 唯一新增 match：**Obj_002–Obj_008**，`0.0014999989653006196 m`；无 match 退出。
- 仅两条既有 match 距离改变：**Obj_008–Obj_013、Obj_008–Obj_014**，均由 `0.000499999150633812 m` 变为 `0.0 m`。
- **253 对不涉及 Obj_008 的处置逐字段相同**。
- 从 broad exclusion 进入 measured 的仅两对：上述新增 match，以及 **Obj_003–Obj_008** 的阴性结果 `0.028444248998134317 m`。覆盖由 164 excluded / 71 match / 41 nonmatch 变为 162 / 72 / 42。
- 模型交付仍为完整紧凑表：7911 / 7911 / 7912 UTF-8 字节。内部资源增量和缓存复用不等于模型只收到变化。

## 未测范围

真值本轮核 SHA 后使用，没有重新从三角形生成整套高精度 oracle。对象依赖 hash 内含未记录的私有 decoder-owner token，未逆推其原像；本轮独立重算的是两端已记录对象摘要形成的 pair key，并以真实几何、资源与身份核对其复用条件。缺失 rich 来源字段仍未补造。

真实模型线程续接、模型是否正确使用当前状态、N 同上下文及脚本缓存的对照效果、usage 定义和完整模型任务净收益均未测。下一项应是冻结后的正式连续 N/C 消费，不再重复本题工程准备。
