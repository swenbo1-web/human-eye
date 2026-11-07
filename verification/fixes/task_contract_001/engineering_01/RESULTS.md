# TASK-CONTRACT-001 ENGINEERING-01

已完成一个最小候选的工程验收。新增消费者答案为0，额外付费API请求为0。模型是否减少补查、总体时间/token/费用净收益仍未测。

产品初版提交为 `4549570de1ad520c1ceb1b15536fe8a3cfc0b603`，当前产品为130源 / `c839ae09682dfb7fa086fa791428d50dd84edeb91f3d1edc406ce610d8c6ea4f`。一次隔离安装版本为 `9.7.2+task.contract.1`，安装身份及130份源字节核对一致。后续只修新增测试夹具和记录，产品 pin 保持一致。

## 交付合同

既有 requested_facts 新增 pair_relation，输入选择器与 mode 延续原入口。分离交付原表面间隙、最近点及 A→B 方向。严格零间隙且非重叠交付 touching，方向未定义无需成为该事实的缺项。严格穿插交付既有认证脱离证据，其字段说明平移对象、方法和范围。

关系按严格零容差口径投影。容差内真实重叠仍为 penetrating，小正间隙仍为 separated。旧 solid_relation 继续使用原容差分类。大坐标点发布不足时，pair_relation 保留已知关系、间隙及具体 unknown 原因。显式额外请求 nearest_witness 时，其旧 unknown 仍影响顶层 partial。

复用同一次 strict 结果，pair_relation 的三个计算需求与旧三 facts 相同，沿同一 pair cache 键直接投影。单独请求 pair_relation 时只构造该复合事实。旧 nearest 投影搬入共用函数，旧值及 unknown 语义保持。正交和多组件沿各自已有方法与数值，不伪造单凸 SAT、内部点或全局最小深度。矛盾 strict 正证与非负数值返回 unknown。

task 输出迁移为 task-query-v3。binding 仅用 runtime_source_sha256 标识代码，scene_revision 和 scene_fingerprint 继续绑定当前有效采集，包括来源与 revision。工具描述及真实使用方版本断言已更新。产品变更仅 task_query.py、live_service.py、live_spatial_mcp.py 三份源文件，几何、SAT 和支持域没有源码变化。

## 固定定向测试

首次固定五模块运行96个唯一方法，94通过、1失败、1错误，无跳过。失败来自新增交换测试使用逐位浮点相等断言，实际差异约7e-18m。错误来自新增歧义夹具复制了唯一 mark_label，在几何绑定前被现有校验拒绝。

仅将交换断言改为1e-14m容差，并给歧义对象独立标签、保留重复名称。随后一次定向重验这两项，2/2通过。首次 UNIT_RESULT.json、stderr 和分母保留。修正及重验均保持原产品 pin。

18项新合同方法覆盖分离/接触/穿插、非轴旋转与交换、微重叠与小正间隙、大坐标见证发布不足、不支持与歧义、显式旧 nearest 的 unknown、正交/多组件证据、源码摘要固定时场景变化、新 revision 下缓存复用、一次当前采集与一次事实编码，以及冲突证据护栏。旧单标量不新增见证遍历的相关断言随固定清单运行。

## 唯一真实 control 会话

复用同字节 control blend、patch 与原独立 truth。一次后台 Blender 会话完成3次 pair_relation observe 和1次 QA 更新，额外 native 读取为0，显式安装身份检查为1。三次均 measured / observed。

| 状态 | 关系与数值 | 新 CLI stdout B | 旧三 facts CLI stdout B | 新 CLI 完整进程 ms |
|---|---|---:|---:|---:|
| initial | separated，间隙0.009999997913837433m，方向+X | 1,158 | 1,482 | 321.5500 |
| unchanged | 同间隙、最近点和方向，当前绑定一致 | 1,158 | 1,482 | 231.2429 |
| changed | penetrating，A沿−X的认证脱离量0.004999998956918716m | 1,268 | 1,643 | 230.9292 |
| 合计 | 三次所需事实均完整 | 3,584 | 4,607 | 783.7221 |

逐状态真实 CLI stdout 均更小，合计减少1,023B，即22.21%。原始进程 stdout/stderr 已保存，两组按相同交付边界比较。changed 的既有 SAT 数值证据逐项一致，复合事实省去了该任务未请求的最近见证 unknown。旧显式 nearest 的 unknown 由合同测试保留验证。

实际累计3次 selected capture、2次 pair measurement、2次 shared paired SAT、1次完整 witness traversal、0次 scalar traversal、0次 fallback SAT、0次 full capture、3次 task content encoding。audit 的 exact_pair_count 为1/0/1，中间一次 pair cache hit，仍进行当前采集。更新后 revision/fingerprint 变化，runtime_source_sha256 保持代码身份。

本轮 CLI 计时只覆盖 subprocess.run 启动至返回且已回收进程，排除父 QA 的响应检查、落盘和 COUNTS 读取。它包含实际被测入口及 QA 计数包裹的影响。旧工程931ms带有QA包络，未作同口径纯CLI时间比较。其他层时间嵌套保留，不相加。

## 清理和证据

service launcher 与实际 Blender worker 均正常 exit 0，worker 已回收，watchdog 退出，forced_cleanup 为空。原资产与保护文件校验一致，本轮路径匹配的 Python/Blender 残留为0。安装身份进程的一个旧 PID 编号已被后来启动的 Edge 复用，已按创建时间及进程名称核对。

完整实施 turn 从2026-11-07T02:59:27.767Z开始，40分钟截止为03:39:27.767Z。最后实验已完成，封存时间及截至封存投入见 MEASUREMENTS.json。协调根继续负责最终深审及一次实质优化机会评估。

主要原件为 UNIT_RESULT.json、UNIT_RECHECK.json、INSTALLED_IDENTITY.json、MEASUREMENTS.json、CLEANUP.json、control/RESULT.json、逐状态 CLI.stdout/COUNTS，以及 session 中实际请求、响应、audit、worker 事件和 QA 回执。build/BUILD.json 与 wheel 保存候选来源和可用安装包，source zip 和 venv 留在本地。EVIDENCE_INDEX.json 索引主要原件。
