# VISUAL-BENEFIT-004A-R1 公共消费者合同修复

本批仅修六题的公开含义、评分绑定和正式工具入口。**正式消费者仍为 0，未启动 004B，也没有模型任务收益结论。** 产品 129 源摘要仍为 `6a5375fb5d5577e8de05c043db7523263cf96ad8386ee524a04beb25feb9f382`，基线提交为 `284699285c349bd4124bf8c863c4546df1c6d033`。

## 修复前的反例

`verification/fixes/20261104_visual_benefit004a_r1/OLD_FAILURES.json` 在评分修改前，用精确 `git show 2846992:verification/visual004_scoring.py` 的代码记录：

- V03 其余字段正确，`inside_hole` 因未公开的完整枚举被判错；原规范字符串的对照通过。
- V06 的 `visual_visibility` 未说明其实是“内部表面不可见”谓词，普通可见性理解下的 `False` 被判错。
- V04 没有公开 target/reference 对应的形体；旧原生 README 还明确允许消费者绕过 owner broker 直接调用低层脚本。

以上是作者构造的评分反例，不是正式模型答案或真实宿主几何证据。旧场景、问题、真值和 PNG 字节全部保留。

## 统一公开语义

新增 `visual004_contract.py` 从公共任务构建 `visual004-public-semantics-v1` / `004A-R1` 补充，覆盖六题的 **15 个角色、23 个字段、10 种事实类型**。双方获得相同的角色描述、完整取值域、米制单位、布尔谓词、世界轴及方向定义，不含正确对象 ID、正确选择、距离、局部答案、最佳视角或支持检查结果。

- V03 的四种 canonical 值均公开；不设同义归并。含义不完整的 `inside_hole` 明确非法，不能凭它推断是否接触。格式合法而事实错误的 `inside_hole_contact` 仍不得分。
- V04 明确 target 是白色八角柱，reference 是绿色 U 架；最近方向从 target 表面指向 reference 表面。
- V05 的 `centroid_direction` 明确定义为完整 AABB 中心的 target-minus-reference，数组顺序 X/Y/Z；每轴公开对应正、负及相等字符串域。
- V06 明确 `True` 表示内部表面在指定外部不透明视图中不可见，`False` 表示该不可见谓词不成立，不能与普通 visibility=false 混用。
- 数字不接受布尔、单位字符串或非有限值；未知仍须显式 status=unknown/value=null。局部描述仍保留独立盲审，不因格式正确自动给满分。

正式 score contract、answer 和 consumer input 升为 v2。补充版本包含在 SHA-256 中，`public_contract_sha256` 必须出现在任务合同、答案和每条实际证据绑定中。评分与消费者入口都按可信公共任务重建模板，拒绝缺失、错案例、错摘要及“改内容后自行重算摘要”的补充。只保留历史评分 v1 兼容；正式输入和本版计划验证器均拒绝降级。

新计划将六个补充实际落盘并绑定路径、版本、字节摘要及原始问题/资产。复查发现过缺失 policy 字段会跳过补充检查的候选问题，现已改为 v2 schema、公开合同策略、v2 score schema 和统一入口策略全部必需，逐题校验无条件执行；对应反例已加入测试。

## 正式入口与计量

正式 P/N 消费者只允许 `visual004_session.py --workspace <自身目录> --requestJSON <自身请求>`，普通 bpy/Python 仍通过 broker 的 native_run 执行。低层 `visual004_native.py --script`、NativeSession、worker socket、直接产品 wrapper 及启动接口均明确仅供协调者资格/调试使用。

原六题、配对顺序、原始 600 秒、48 次公共请求、文字及图像预算不变。内部 64/128 RPC 上限不是额外公共额度。controller 需审计实际宿主工具和脚本，对偏离或无法判定的入口保留原样本、原答案和所有已观察/未知成本并标注协议偏离；不重开或换样本。这是公开合同与审计，不是 Python 安全沙箱。

代码须同时符合 UTF-8 262144 字节、broker 序列化 JSON 294912 字节和内层 execute_code JSON 266240 字节限制。ensure_ascii、封套和换行均计实际报文；UTF-8 未超限不保证任意 Unicode 代码能通过 JSON 线限。本批没有改传输限制或扩大承诺。

## 验收及保留失败

- 最终七模块 **204/204 普通、204/204 `-O`**，记录 `ALL_TESTS_003_NORMAL.txt` / `ALL_TESTS_003_OPTIMIZED.txt`。原六模块 133 个测试方法全部保留，新增 71 项。合法公共值的格式构造、原规范真值兼容、错误布尔/方向/数字/角色、遗漏、unknown、无证据、篡改与降级均有覆盖。
- 六题的纯 Python 整合记录 `QUALIFICATION_RESULT.json`：只使用公开定义即可构造格式合法的字段；两组共同合同一致，原真值类型兼容。该校验使用明确标注的作者 fixture，不替代真实几何或宿主交付证明。
- `FINAL_BINDING_VERIFICATION.json` 将这 12 份作者公共输入与最终候选逐字节重建对照，并核实原 133 个测试方法均保留；计划 guard 后续加固没有使先前输入失配。
- 中间普通全组出现过退出 124，优化组 202 项通过；原 `ALL_TESTS_002_*` 不删除、不计为通过。最终串行 204 项双模式通过，不掩盖中间失败。
- 无 Blender 的定向诊断：原样夹具 6/6 通过；仅在诊断进程将首次 READY 写入延迟 80ms，复现空 JSON、清理线程仍存活，以及约 20 秒后的 watchdog 退出 124 调用。与原失败形态一致，但原日志无堆栈，不能唯一归因。诊断脚本、输出和 `NATIVE_FIXTURE_SCHEDULED_READY.json` 保留；本批不改低层 helper 或旧夹具，不宣称该竞态已修。
- 旧 004A 的 811 份证据大小及 SHA 均未变；18 份旧源码按原 `git show 2846992:path` 核对，不拿当前修改盘替代旧源码。旧 seal `b8695419c4fbc0bf17c42be97ce43ca49c6541db979c7e66976caadd0acf49ce` 保留。

有效计划在新 R1 目录 `final_protocol/FORMAL_PLAN.json`，六个公开补充在其 `public_contracts/`；验证时资产根仍指向旧 004A 根，`--output-dir` 指向新 R1 的 final_protocol。旧计划、seals、失败和资产不覆盖。

## 未运行与边界

未重造资产、重跑 Blender、改产品/阈值/默认配置、启动正式模型、安装、push 或重试清理。未调用 Google/key/付费/学习库，旧 USD0.02 预留保持。图片与生命周期生产实现未改，因此没有新图像验收，也不将旧校准冒充本次新测。

原 V03 `geometry_resource_limit`、V06 `reference_pair_geometry_unknown`、P native 灰色材质限制保持；测试 READY 竞态作为新发现的已有验证风险交回复核。真实模型质量、图片机制因果收益、任务 token、完整任务耗时/成本和峰值 RSS 仍未测。完成回报后等待独立复核，不自行开始 004B 或扩展其他模块。
