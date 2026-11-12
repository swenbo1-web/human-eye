# 独立匿名质量审查

审查结果：六份原始 final 均为 **complete_correct**。每份都明确声明完整，准确列出全部 71 个阈值内对象对；没有漏项、误报、重复、错误距离、伪零或展示不足。此判断在读取任何根评分之前独立形成。

## 范围与方法

- 唯一质量输入为 `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_surface_scan_consumption_001/runtime/handoff_01/public/` 的 30 个文件。未访问 private、匿名映射、组别、成本或 usage，未尝试解组。原 ZIP 的给定 SHA 是父任务输入，本子任务没有读取或验证 ZIP。
- 先读公共题面、评分合同、BASE 真值，再完整阅读六份 `answer.txt`，并检查必要业务证据与来源一致性。没有使用作者评分程序，也没有读取根评分。没有执行证据中的消费者代码；没有启动 Blender、消费者或业务 API，没有修改实施树或 Git。
- 人工确定表达含义，脚本仅展开已确认含义的表格并核对数值。两个压缩零距离表按文字明确的“左侧对象分别与每一个右侧对象构成一对”展开；不把右侧对象两两组合。所有 final 已直接列全，不需要靠引用工具列表补足内容。
- 数值判断不使用舍入后的 oracle 平方根。对每个声明值 d（mm），检查精确 `exact_squared_distance_m2` 是否位于 `[max(0,d−0.000500001)/1000, (d+0.000500001)/1000]` 两端平方之间。真匹配归属按 `Fraction(binary64(0.002))²` 比较，276 对均与真值标记一致。
- 单位和精度单独核验：非零值有效小数精度至少 0.001 mm；确为零允许写 0。数值错误与展示不足分栏，未把格式问题当作几何错误。每个 `0` 还要求真值平方距离精确等于零，不能仅靠容差通过。
- 明确完整但缺对会判 incorrect；承认不完整的漏项判 incomplete；确定错误优先于不完整。当前六份没有这类问题。保留六格固定分母，不因中途错误替换、合并或剔除任何格。

## 六格结论

| 匿名 ID | 状态 | 真匹配覆盖 | 误报 / 漏项 / 重复 | 数值错误 / 展示不足 | 额外确定错误 | 辅助工具失败 |
|---|---|---:|---|---|---:|---:|
| answer_007886c1beefd7c6 | complete_correct | 71/71 | 0 / 0 / 0 | 0 / 0 | 0 | 0 |
| answer_16df3f049c011e05 | complete_correct | 71/71 | 0 / 0 / 0 | 0 / 0 | 0 | 0 |
| answer_3b74126ed5f72eba | complete_correct | 71/71 | 0 / 0 / 0 | 0 / 0 | 0 | 0 |
| answer_7958cbdd56ce7e5d | complete_correct | 71/71 | 0 / 0 / 0 | 0 / 0 | 0 | 2 |
| answer_a5958c6899df02aa | complete_correct | 71/71 | 0 / 0 / 0 | 0 / 0 | 0 | 1 |
| answer_b9ec064a37f1c4a1 | complete_correct | 71/71 | 0 / 0 / 0 | 0 / 0 | 0 | 0 |

固定分母汇总：complete_correct = 6；incomplete = 0；incorrect = 0；execution_failed = 0；not_run = 0。合同中类别拼写为 execution_failure，父任务要求回报 execution_failed；这里采用父任务拼写，不改变定义。

每份含 43 个精确零和 28 个正距离。`answer_7958cbdd56ce7e5d` 使用三位小数，最大绝对误差 `0.0004696848679267291587663638541 mm`；其余五份使用六位小数，最大绝对误差 `0.0000004933605194091796875 mm`。均小于容差 `0.000500001 mm`。三位小数满足原题，不能额外要求六位。

## 人工解释与额外断言

- `answer_007886c1beefd7c6`：final 第 5 行定义零距离分组含义，展开为 43 对；正值表为 28 对。第 57 行明确“检查完整”。24 对象、978 三角形、276 对、112 候选、164 下界排除、41 实测不匹配均得到快照、真值与公开事件支持。公开事件 3/7 分别提供无额外实例、有限坐标与计数的相关输出（JSON 数组下标）。
- `answer_16df3f049c011e05`：71 个独立表格行均完整正确，第 80 行明确完整与 unknown=0。六位毫米显示足够。“含隐藏对象”是检查范围声明，并不要求场景中确有隐藏对象。公开业务事件 1/3 的 71 个 match 也逐条核对通过；原生结果事件 7 提供再次计算结果。
- `answer_3b74126ed5f72eba`：第 42 行明确零组右侧对象之间不推断距离；完整性声明在第 59 行。第 60–61 行的 436,640 个跨对象三角形对、205 个非匹配及最近非匹配 `Obj_002—Obj_008 = 2.249999 mm` 与冻结真值和快照组合计数一致。公开事件 5 返回 exhaustive_object_pairs=276、exhaustive_triangle_pairs=436640、qualifying=71、zero=43、discrepancies=[]；因此额外“无剪枝全量复核”有可见执行证据。没有要求消费者重放任何指定证明算法。
- `answer_7958cbdd56ce7e5d`：71 个独立行的三位毫米显示全部通过。第 80–81 行完整性、未列出对象均超过阈值及 unknown=0 与真值吻合。两次辅助错误没有被隐去；成功业务结果和后续计算仍完整支持交付。
- `answer_a5958c6899df02aa`：71 个独立行全部通过；第 81 行明确本次检查完整且未知/延后/不支持项为零。一次辅助参数错误被保留；第 1 行所谓“完整清单”与实际 71 行一致。
- `answer_b9ec064a37f1c4a1`：71 个独立行全部通过；第 80 行声明完整。第 81–82 行全量三角对计数和最近非匹配断言都得到真值与公开事件 7 支持，该事件报告 same_pairs=True、max_distance_difference_mm=0.0、exact_zero_count=43。正文额外提到的 2.249999 mm 是非匹配例子，不能误解析成第 72 个阈值匹配。

全部六份均限制结论为无符号三角表面距离，没有从零距离或非匹配外推实体穿入、包含或“无碰撞”。没有发现未被消解的 unknown。浮点/当前几何精度限定是适当说明，不会把已完整检查变成“不完整”。

快照独立结构检查确认 24 对象、530 顶点、978 三角形、276 无序对象对和 436,640 跨对象三角形对；全体坐标有限、无空三角对象。逐三角形用精确有理数叉积检查，未发现退化三角形。单位为 world / m / METRIC / scale_length=1.0。真值候选标记的 Linf 与紧 AABB L2 各保留 112 对，与 164 排除一致；71 达标，41 候选不达标，总计 205 非匹配。最近非匹配确为 Obj_002—Obj_008，显示 2.249999 mm 通过同一容差。

## 失败记录与执行状态

`INDEX.json` 的六份 final 都 present、consumer_valid_completion=true、owner_finish_confirmed=true，最终文件 SHA 与 INDEX 的原 final SHA 一致。这些字段仅用于确认 final 身份与执行状态；质量通过来自上述独立逐对核验。

保留的辅助失败：

| 匿名 ID | `public_tool_events` 下标 | 原始错误 |
|---|---:|---|
| answer_7958cbdd56ce7e5d | 5 | task candidates must contain 1..3 explicit selectors |
| answer_7958cbdd56ce7e5d | 7 | surface_scan requires only mode and threshold_m |
| answer_a5958c6899df02aa | 5 | task candidates must contain 1..3 explicit selectors |

完整错误对象保存在 `business_evidence_review.json`。三次属于中间工具调用失败；已有确认可用且质量正确的 final，所以不是整个格 execution_failed。重复的成功请求也全部保留，没有筛选只留某次。

本审查自身先前两次过宽输出发生截断，一次补充行号显示因 Windows 默认 GBK 解码失败。这些记录在 `review_failures.json`，没有改写为通过。正式脚本首次运行成功，日志为 `run_01.log`；其读取显式使用 UTF-8，并把全部 276 对核验落盘。补充显示改成 UTF-8 读取后还遇到终端 GBK 输出乱码，该问题不影响文件内容或正式脚本断言，后续使用 Python `-X utf8` 输出。

## 来源与不确定性边界

30 文件逐个 SHA 保存在 `quality_results.json`；评分三文件 SHA 与 INDEX 一致，TRUTH.snapshot_sha256 与快照原字节 SHA 一致，真值 state=base。六格配置资产哈希与身份资产哈希相符，初末记录文件哈希相等，producer CLOSE 记录 geometry_unchanged/asset_unchanged/source_file_unchanged/protected_files_unchanged=true，初末几何指纹相等。

可见代码 AST 的主机相关调用是求值网格读取、临时 to_mesh/clear 与三角化缓存计算；未发现场景属性赋值、移动对象或保存文件调用。上述证据支持只读声明，但初末相等及 producer 记录并不能证明期间绝无任何瞬时变化。本审查没有独立观察原运行，也没有原始网络帧，因此不作这种更强认证。公开工具内容会暴露技术路线，匿名并非完全盲化；未据此推断组别、收益或采用结论。

## 产物与复跑

- `audit_quality.py`：独立审查脚本，只读 public，只向本 independent 目录写产物；不导入作者评分器，不执行证据代码。
- `quality_results.json`：30 文件哈希、精确阈值/快照检查、每格人工解释与状态。
- `true_71_pair_cells.csv`：426 个真匹配核验格，保留原 final 行号、展示值、真值精确分数、误差及各项检查结果。
- `all_276_pair_cells.csv`：1,656 个全场景对象对核验格，含 205 个非匹配每格的正确排除状态。
- `business_evidence_review.json`：业务列表逐条核验、完整性与 unknown、辅助失败全文、来源记录及代码 AST 阅读索引。
- `review_failures.json`、`run_01.log`：保留审查失败与正式成功运行。

复跑：`D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe -X utf8 D:/hefe/verification/fixes/20261112_m4_surface_scan_consumer_quality_review/independent/audit_quality.py`。复跑会重生成本目录评分 JSON/CSV，不改变 public 输入。
