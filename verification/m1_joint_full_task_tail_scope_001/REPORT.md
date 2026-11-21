# M1 目标观察全量回包的单距离尾置验收

**通过隔离工程验收。** `4e4c653a` 将现有目标观察显式 `full` 的量测尾置收窄到 `task_result.facts` 恰好只有 `surface_proximity`。独立顺序关系、量测值和 `unknown` 理由继续由原流程生成。十项、距离加 AABB 和单项 `axis_gap` 沿 `c8f87c54` 的成员顺序。改动仅涉及 `human_eye_plugin/live_spatial_mcp.py` 的一处判断。

## 冻结身份

| 项目 | 值 |
| --- | --- |
| 方案 | `5122ef745fcd73267847956e9c655f058e6b5190` |
| 原布局与过宽候选 | `c8f87c54`、`475ae93a` |
| 窄修候选 | `4e4c653a4d4726576f4f4d2a9d7b9decede44cbf` |
| 143 件运行源摘要 | `a436539e9f5389b9ebaa5ccacc0a4845d53d2429923b4443b15e3f49e2a6e846` |
| 隔离 wheel 摘要 | `72fc32b8ccce647047b9fada49238b69521fa41551069bae3d20d542768fbc53` |

只构建和安装一次。143 件 Git、wheel 与安装文件逐件核验，实际 stdio `tools/list` 五项原线包逐字节相同。见 [安装证明](install/BUILD_INSTALL.json) 和 [目录回包](checks/TOOLS_LIST.json)。

## 实际回放

| 验收 | 分母与结果 |
| --- | --- |
| 两份历史单距离真请求 | Far00、M09 共 2/2，候选与 `475ae93a` 的实际回包逐字节相同。Far00 正文 30,121 B、原图 1 张，M09 正文 28,679 B、原图 2 张。 |
| 固定裁剪 | 33/34/35 B 工具头，12,000 B 交付和 3,000 近似 token 历史重读。两份原件合计 12/12，整件距离、点对、世界方向以及原图与必要见证均保留。 |
| 既有兼容控制 | 24/24 与 `475ae93a` 同字节。对照 `c8f87c54`，18 项原样、6 项符合已接收的单事实尾置。单距离合成 `unknown` 附带空值和原理由，裁剪 6/6。 |
| 扩展控制 | 4 种请求 × 3 版实际安装，共 12 份 stdio 回包，以 Far00 封存的同一求值和有序对象绑定计算。候选单距离沿旧尾置，另外 3 种布局与原版在仅去掉固定产品身份差异后同字节。每份回包检查两阶段 × 三个工具头。 |

十项反例来自 Far00 P1 的封存首调生产记录与普通工具第 2、3 包，派生控制单独记账。三版均由各自安装的 `_validated_scene` 和 `task_result` 求值，再经实际 MCP writer。正文 31,690 B，量测成员 4,286 B，原线包 39,622 B。过宽的 `475ae93a` 尾置使固定裁剪保住 137 个原来会被裁的量测叶值，同时在三个头的两个阶段新增裁失 `frames[0].source_revision`、`host_binding_sha256`、`scene_identity` 和 `candidate_identity`。同值的 `binding.scene_revision` 也在六次裁剪中丢失。原 PNG 与观察行路径、引用、摘要在三版都保留。

窄修在六次裁剪中恢复两个版本字段和原可用帧绑定。十项量测仍受原固定裁剪预算限制，137 个量测叶值在重放的交付和历史阶段都被裁去，未裁剪的真实 MCP 回包保有全部原值。距离加 AABB 也恢复原布局，单项 `axis_gap` 两版布局相同。见 [三版原线包](evidence/expanded)、[两阶段确切字节和版本字段](checks/EXPANDED_STAGE_BYTES.json)、[扩展验收](checks/SCOPE_CONTROLS.json)、[历史正例](checks/POSITIVES.json) 和 [兼容矩阵](checks/PRIOR_MATRIX.json)。

## 成本与证据

两份历史请求各做每臂 72 次热请求，6 个交错独立进程。Far00 实际派发中位数 1.27845 → 1.28090 ms，输出序列化 0.62990 → 0.63125 ms。M09 派发 1.16100 → 1.15960 ms，序列化 0.57725 → 0.57050 ms。十项控制各版一次序列化加 stdio 为 3.058 / 3.065 / 3.056 ms，封存的量测求值和绑源分别计时。样本只覆盖离线回放。见 [分段时钟](checks/COST.json) 和 [十项分段](checks/SCOPE_CONTROLS.json)。

两份历史正例和原多事实反例保持原判定。新增 Blender、模型、构图、替补、资产重建、Google、额外 API 及费用均为 0。默认配置未切换，留出的非共面选区排序任务未运行。尚未测自然模型调用或补查是否减少。固定 CLI 裁剪的证据来自两阶段重放。

248 件封存原件在本机 `D:/he_m1_joint_full_task_tail_scope_001/REPLAY_ORIGINALS.zip`，2,448,091 B，SHA-256 `94886889bbeeba5683ca90887cd50a699c9a222b7d28269e41b61e42aa88fd25`。重点实际回包及三版 35 B 双阶段正文随本分支提交，其他原件按 [封存索引](RAW_INDEX.json) 逐件复核。
