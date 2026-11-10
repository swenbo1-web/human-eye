# LRC-PREP-001 独立只读复查

结论：本项修复的源码、有限验收记录和索引范围澄清通过，未发现阻塞。未执行打包器、运行器、测试、产品、Codex CLI、模型或Blender；只读取源代码、既有合成输出及一次只读Git cat-file对象流，并新增本复查与索引范围记录。正式模型消费者仍为0，本结论不是正式GO或任务收益验收。

## 零PID失败出口

候选打包器SHA256为 `3b960695d5308ac64c5512191d7c0dc4e854a72b5fa07b97ccb5dfe0c0b3c365`。diff仅新增有限零启动失败校验与调用，原正PID入口及事实/文本/请求/原答案/归档投影保持。

已直接对照真实driver：STARTED只有started_ns、max_consumers、plan_sha256；终止RUN_RESULT没有cycle_id或plan_sha256。候选没有要求这些不存在的字段，而是核本cycle GO的授权、PLAN摘要和max9，STARTED的同一摘要、max9及正整数时钟，以及终止首格前缀的计数、stop、原始时序、wall差值和within_570s一致性。它不要求预算超限失败变成通过，也不因真实超限标志False而拒绝归档。

两类真实生产形态均可表达：首格输入/actor/初态失败时consumer=None、错误在外层；CLI创建失败时已有consumer字典、PID为null、错误在consumer.errors而外层可以为空。缺失PID亦保持缺失，不补键、假PID、答案或成功状态。finish和worker_deadline不作为额外准入要求。新GO/STARTED原字节自动进入private/control、原有摘要回执和末尾moving-source检查。缺少正PID本身不是“实际从未启动进程”的证明，此修复只交接已绑定的原始失败记录，未知状态仍属未知。

## 定向合成证据

已只读 `tests/run_fix_checks.py`（SHA `5f68f70d98b7af7fd60b5c5dd4f7255ccab1717847ad257a017b67cb8148bbcd`）及RESULTS_02：原231项与新增/包装79项，共310项通过，0失败和异常，socket/subprocess尝试0。归档旧断言源码按原SHA编译复用，只有新输出目录、候选SHA和归档后需要恢复的原图片base运行上下文明确替换，没有修改原断言。

三种合法consumer None/null PID/缺失PID场景通过实际main打包路径；28个缺失或错绑GO/STARTED、未终止、计数/时序/失败状态不符等场景逐一要求精确拒绝原因，未拿缺输入图片的偶然错误代替。直接读取OUTPUTS_02.zip和清单，618个原件逐SHA/字节一致；三种合法结果均保留九格、首格失败及八格not_run，GO/STARTED/RUN_RESULT公开包私有控制副本与原字节相同，无answer.txt伪造。旧231项继续覆盖双分组绑定、嵌套事实、重复尝试、缺响应、原答案和unknown保真。

首次包装检查因旧归档脚本__file__祖先改变、原图片base未恢复而失败；RESULTS_01和原输出保留。02仅校正此明确运行上下文，不能称首次全部通过。本代理未执行或重跑这两次检查。

## 原索引与提交数量

`INDEX_SCOPE_REVIEW.json` 从原提交 `169b0be061e91b126f46313478690564ccb2bd60` 独立读取Git树与blob：692份批次文件等于680份索引材料、3份根级自引用与9份嵌套FREEZE。原680行的SHA和字节与原提交全部一致；9份漏索引文件均在Git且当前原字节未变，精确路径、SHA、字节和Git blob已逐项记录，无未解释遗漏。

已静态阅读根的seal收窄：只排除批次根级ARTIFACT_INDEX/FREEZE/PREP_READY/FIX_READY及明确的本地bytecode，不再按basename排除所有嵌套记录。历史内嵌FREEZE和原修订元数据会作为普通证据进入新索引。本复查不执行seal、不改PLAN或现有封存；最终新索引/摘要一致性由根一次封存核对。

产品、driver/actor/transport、安装、图文输入、评分语义、收益门槛、顺序、匿名映射和运行预算未因本项修复扩展。本项只改变已保存控制记录的失败交接出口，现有纯合成证据足以覆盖，无需追加真实产品或Blender测试。当前Pro认证、额度及provider可用性仍未测。只支持这项准备交接修正，等待根独立冻结与正式九格GO。
