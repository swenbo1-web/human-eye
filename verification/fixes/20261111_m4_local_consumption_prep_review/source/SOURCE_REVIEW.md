# 九格准备包：来源、输入与安装独立复核

固定提交 `169b0be061e91b126f46313478690564ccb2bd60`，PLAN SHA `698b74ec8607e499693d1d34394e4ae06f9bca2e52ac1bda456cc96d4e453761`，FREEZE SHA `3699408f1341ab951b5e5a6457f4026c5bb8db2eb0fc2ce92ec79f51601b344d`。

**来源与输入子项通过；发现一项证据总数口径需要更正。此结论不是全包 GO。** 根已另行发现首格未启动消费者时的打包器处理问题，本子审未复现或审核其修复，也不据来源通过放行消费者。

本轮只读当前文件、固定 Git blob、wheel 与 AST，执行自写标准库核验脚本。未启动 CLI、模型、Blender、产品、安装器或作者验证脚本，未修改实施树；核查前后实施树干净。没有借用根的 Agent Learning 句柄或更新父任务。

## 实际重算结果

- PLAN、FREEZE、ARTIFACT_INDEX 及 PREP_READY 互相引用的摘要一致；PLAN 所列全部 dispatch 输入当前 hash 一致。
- 索引 **680** 份文件、**14,738,497** 字节全部匹配；加根目录三份 index/freeze/readiness 为 **683**。但该提交实际包含 **692** 份批次原件，已全部逐 Git blob 与当前字节核对通过。
- 差额是 **9** 份位于 synthetic/run_01、run_02、run_03 及其合成打包 private/control 内的 `FREEZE.json`。`seal_preparation.py:81–82` 以 basename 排除自引用文件，连这些非根的合成原件也一起排除了。它们未被删除，仍在 Git，独立复核已补齐散列。因此“683 份全部原件”不准确，应称“680 份索引 + 3 份根 seal；另有 9 份已提交的合成 FREEZE”。完整路径见 `SOURCE_REVIEW.json`。无需为此删除文件或重跑消费者。
- **11 项**共用输入与旧批次逐字节一致，包括 prompt、task、session rules、方向、目录、相机、PNG、blend、原始快照及两项绑定/原生定义。PNG 为同一 1,185,069 字节、1200×900 图，prompt 13,998 字节。并未换题、换图或增加插件必用提示。
- actor 与 consumer_transport 分别逐字节等于旧 M4；既有 native actor、worker 和 thin helper 当前 hash 与冻结清单一致。driver 的分组/控制流由另一子审负责，本子审只读确认 N 使用共同依赖、不启动产品，P0/P1 分别选各自固定安装及 schema。

## 当前安装与实际目录来源

| 项目 | P0 | P1 |
|---|---|---|
| 固定产品 | `107641ec19919d56aa843c1949261590fc338148` | `e077fce38b5951efff8166b3b688d05ffa2ebf04` |
| 隔离版本 | `9.7.2+m4.r2` | `9.7.2+lr.r1` |
| 运行源数 | 137 | 137 |
| Canonical | `7a3d108bc5658508d76d98fe24b8f3dee4feac2d50856202b2ea7395c3dc9cc1` | `53db41976085ce5f361d026196f4da5faf80d639af33dfced35ba58e328ef732` |
| 当前源/Git/wheel | 137/137 相同 | 137/137 相同 |
| 当前 entry/admin/binding | 摘要与目标路径一致 | 摘要与目标路径一致 |

重新读取的是当前两份实际安装目录，并逐一与固定提交和原 wheel 比较，不仅采信旧 READY 的 passed。重新枚举运行源确认无增减，canonical 独立重算一致。P1 的当前工作树 137 源也仍与产品提交一致。两版 READY 副本等于其原件且与 PLAN 内对应配置相等；binding 的 release、site-packages 和 dependency Python 都指向该版本实际路径。

两版使用同一 Python 可执行文件及 venv 配置，当前 SHA 分别为 `d59c9a894b319828d023f3aa83d9a3488d2339f9e27e60e49b02abb0d53cf538`、`bf765add0c33477d19211357fe4543f3c3e94d1387a0dc82d7db39d555f6babf`。当前 Codex CLI 文件 SHA 为 `01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6`，与 PLAN 相符；未启动这些程序检查登录或导入依赖。

P0/P1 公开目录逐字节等于上轮实际 installed metadata 中对应 baseline_S/candidate_S 的两工具目录。历史 initialize 来源摘要和版本与当前核验字节匹配。两版仅 `human_eye_spatial_relations.description` 增加“可交付捕获三角片及可发布的近似边界位置”的一句说明；输入 schema 与 `human_eye_surface_nearest` 完全相同。共同 native 定义与现存 native actor 的 AST 字面量一致。

历史真实 initialize 加当前静态同源检查，可以支持准备绑定；**不等于本轮已启动进程并验证 loaded identity**。正式运行仍由原入口核验实际加载版本。当前 Pro 认证、额度、provider 可用性、resolved model/effort、图片实际接收和认知使用都未测；旧 ChatGPT 登录记录或同一 CLI 文件不能证明当前可调用。PLAN 正确保留这些未知。

## 分母、历史及准备成本

固定顺序为 `N,P0,P1 / P0,P1,N / P1,N,P0`，每组三格，共一个场景的九个新消费者。旧六格没有加入新分母。根目录没有 GO、STARTED、RUN_RESULT 或 cells，准备阶段仍为零正式消费者；synthetic 中的同名材料只是合成测试。

旧 sequence pin 拒绝、synthetic/run_01 九格转换遗漏、run_02 合成路径过长、根 draft 误读成本列表的原失败记录均仍存在并纳入本轮 hash 核查。后来的 run_03 通过没有覆盖旧失败。这些通过数字是作者已保存结果，本子审没有重新运行那 231 项合成检查，也没有复核评分语义。

准备窗口从 `2026-11-10T21:41:21.895821Z` 至 `21:55:56.959123Z`，独立重算为 **875.063302 秒**。范围是新证据目录创建至 readiness seal，包含此期间准备和修正；不包括更早只读审阅、之后 Git 提交/回报或本轮根复核。协调 token、费用和这些范围外耗时未测。旧安装 READY 的 elapsed 属于历史安装，未计作本次新增安装成本，亦不能与已包含的工作重复相加。

`CLEANUP_AUTOREVIEW_REJECTION.json` 保留自动审批在进程创建前拒绝删除 .pyc 的记录。当前 `quality_handoff/__pycache__/pack_quality.cpython-312.pyc` 仍留在本地、未纳入 Git 或索引。本子审未删除、重试清理或绕过拒绝。

可复核脚本 `recompute.py` 与逐项 SHA/结果 `SOURCE_REVIEW.json` 同目录。后续打包器修复及重新冻结属于新版本，不能直接沿用本报告给新准备摘要背书。
