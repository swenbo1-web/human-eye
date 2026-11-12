# M4-SPATIAL-FACT-CONSUMPTION-001 匿名来源与合同核查

结论：**通过，可以在此公包上进行匿名质量评分。** 本报告只核来源、冻结合同和公包完整性，不给答案分数，不推定分组，不判断采用率或收益。

## 本轮实际核验

- 固定完成提交 `5cdf62f311f94890ca569d06c1a858f1578225e4`，准备提交 `02c7784ec4e23e9b03a3485367d8db54b4d5db34`；实施工作树干净。父任务澄清允许只读 Git 后，仅用了 `rev-parse/status/cat-file`，没有 Git 写操作。
- 公包 **30/30 文件**逐字节匹配完成提交的 Git blob，也完全匹配 `PUBLIC_PACKET_MANIFEST.json` 的文件集合、字节数和 SHA256；没有漏列或多余文件。重新计算包摘要为 `efc074849f20b15f6ad1702467c765dbb576f5846b68e7a00754c776abd1fb9f`，与 manifest、READY、POSTRUN_INTEGRITY 相同。
- 根计划 `D:/hefe/docs/M4_SPATIAL_FACT_CONSUMPTION_001_PLAN.md`、批次 `ROOT_PLAN.md`、准备提交和完成提交的该文件逐字节相同，摘要 **`aa6b4ffaf6eb6ca93c4fec28a3134fedd25a0c5be54582f9f47fdbd044ed040a`**。
- 本地执行 `PLAN.json` 仅做字节/hash 核验，没有解码其分组或成本配置。它在准备和完成提交之间不变，摘要 **`d40c81babcb1a9d1826752df4dfe23e5d790536bd23cf0798edc0bbc90f9e672`**。这是执行配置的摘要，与根 Markdown 计划的摘要不同是正常情况，不能将两者混作来源冲突。
- 公共题面与根计划唯一引用题面一致，也与准备提交的 `input/PROMPT.txt` 原样一致；三份公共评分资料 `SCORING_CONTRACT.json / ACTUAL_SNAPSHOT.json / TRUTH.json` 与批次冻结文件、准备提交、完成提交逐字节相同。
- 实际输入 `scene.blend` 与上一工程批 `entry/run_01/native/input.blend` 逐字节相同，SHA256 `27f197a8cc312832382ae06cb633cbf846f20a1a22797909a15dfda8513ade46`。快照保留 14 个对象、848 顶点、1640 三角形。
- 六个匿名槽均存在，答案摘要与公共 INDEX 内的最终答案摘要一致；各槽公共来源投影指向同一资产，初图为零、无 CLI 图片参数，记录的初末几何与文件摘要相同。此处只验证公包投影的一致性，没有读取其私有原件来重新证明过程行为。

## 摘要口径核清

公开 `ACTUAL_SNAPSHOT.json` 的**文件原始字节 SHA256** 是 `29dfdccd839170b70ec03339925323d433b5e4221d1caac6649b2060fefa453c`。

`TRUTH.json.binding.snapshot_sha256` 的 `e89897c10026d1e8d02ec07c7227cbaa7539ca96659c449b8ab8aea4a5780f08` 是同一对象的**紧凑、键排序 canonical JSON 摘要**，来源为 `verification/spatial_task_qualification_001/oracle/verify_actual.py:36–41,130`。本轮重算一致；旧实际快照、本批冻结快照和公包快照本身均逐字节相同，没有几何变化。

## 合同一致性

- 每格分母固定为三个关系、三个真实最短间隙、三个 4 mm 判断、三对定位见证、一个限定候选集合内最近者/真实并列；六格完整保留，不以完成槽重新定义分母。
- 距离容差 `1e-6 m`、最终见证逐分量 `1e-6 m`、舍入点欧氏及点间距界与根计划一致；接受任意有效最近点对，不要求评分者或插件选中的同一三角形/点。
- 合理原生捷径和可信来源绑定工具事实均可作为依据；未要求消费者重跑内核或输出证明大整数。仅碰巧正确的 AABB/顶点近似不能替代真实最短证明。
- unknown/incomplete 与错误确定答案分开；不要求闭壳健康，额外“无自交/全场无碰撞”等声称另记，不把空间分离证书升级为资产健康。
- 先质量后成本的边界保持。公共 README 明确说明工具正文可能暴露路线，只做到组标签与成本遮蔽，不声称完全双盲。

## 限制与执行记录

独立脚本 `check_public_source.py` 只使用标准库、文件读和只读 Git，执行结果见 `RESULTS.json`。产品/Blender/模型执行为 0；未打开 private、原运行格、成本、usage 或分组映射，未解析答案和工具业务正文以推定路线。来源投影里的初末相同与退出字段仍是生产者记录，本核查不能排除全部瞬时操作。作者 `review/POSTRUN_REVIEW.md` 所述 thin-client EXIT 缺失限定保留，本轮不把其独立 owner/worker 退出结论写成我实际复验。

第一次脚本执行将 oracle 的 canonical snapshot 摘要误与原始文件摘要比较，在该断言处失败。只读核对既有摘要实现后，修正审查脚本区分两种口径，未修改公包、产品或评分预期；第二次全部检查通过。该失败是审查脚本口径错误，未据此误报作者来源缺陷。

AL 使用自己的合法句柄读取上下文，仍为 `parent_read_only / assignment.current=false`；未借父句柄或写父 task。最终质量判断由根与独立评分者分别完成。
