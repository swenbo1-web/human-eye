# PERF-INTEGRATED-001 执行前缀与阻断

## 结果

本批在复杂题独立真值的输入核验失败后停止。窗口为 `PERF-INTEGRATED-001-WINDOW-01`，执行 HEAD 为 `33c400a413673ade13906a400db4a90231c736e2`。实际资格会话为 **0/4**，消费者为 **0/4**，任务回答为 **0/12**。完整 P/N 对照尚未进入。

同版隔离安装成功，实际相关回归 **168/168**，失败、错误、跳过均为 0。两个 Blender 资产构造均完成，control 真值生成成功，assembly 真值入口 exit 1。原始异常为 `ValueError: Object_01 world vertices`，见 `truth_assembly.stderr.log`。冻结源码、题目和 1e-7m 门槛在执行后保持原字节，重跑次数为 0。

## 已执行身份与分母

| 项目 | 实际值 |
| --- | --- |
| 产品提交 | `326b64c74b2672fd620ddb9cac83bf47dd5355f2` |
| 安装来源 | 新建 venv／`installed_distribution` |
| 发布标签 | `9.7.2+perf.integrated.1` |
| 源清单 | 130，`20fe8507cf3f802bd9471d2e8f7d00470f6013a6236f40e82258bd6aa6e7c5a0` |
| Python／NumPy／Pillow | 3.12.14／2.3.5／12.3.0 |
| wheel 构建／venv／离线安装 | 各 1 次，exit 0 |
| unittest loader／testsRun | 168／168，无失败、错误、跳过 |
| 作者后台 Blender 构造 | 2/2，exit 0 |
| 独立 truth 入口 | 2 次，control exit 0、assembly exit 1 |
| 资格 native／observe／QA 更新 | 各 0 |
| 消费者链／回答／重试／付费 API | 各 0 |

`INSTALLED_IDENTITY.json` 保存 purelib 实际来源、版本、完整 130 源与身份。回归加载的产品模块均核位于该 purelib，结束时 drift compatible，失败后对安装源的只读逐文件 SHA 核查也为零差异。21 个 QA 脚本按 freeze 复制到 purelib 的 verification，另复制固定旧 inputs 与空包初始化文件。回归选定模块和全部实际方法 ID、完整 stderr 输出均保存。

168 个测试方法内部发生产品调用，通用 kernel 调用总数未单独计量。资格和消费者的零分母仅指对应阶段。

## 实际失败与事后算术

control 的 initial／changed 两状态均经实际 oracle 入口完成，unchanged 复用 initial 真值。assembly 在 initial 目标的世界坐标比较中失败，目标局部顶点、矩阵、三角面比较已通过，目标其余 affine／闭合检查、其他对象核验、initial 关系计算及 changed oracle 均未进入。assembly `TRUTH.json` 未生成。

独立事后只读算术以保存的 mesh／matrix JSON 与冻结理想构造核对，没有调用产品或重新执行 fixture／truth 入口。首个超界分量为零基顶点 8 的 X。

| 数值 | m |
| --- | ---: |
| 实际派生世界坐标 | -0.6893162842999061 |
| 理想世界坐标 | -0.6893163974770407 |
| 首个绝对误差 | 1.1317713455305523e-7 |
| 目标最大世界分量误差 | 1.1317713466407753e-7 |
| 冻结门槛 | 1e-7 |
| 局部顶点最大分量误差 | 2.8517396333249678e-8 |
| 矩阵最大分量误差 | 9.934107458864361e-8 |

局部坐标和矩阵各自比较通过，组合后的世界分量超过冻结门槛。world_vertices 由实际局部坐标和实际 matrix 的 Python affine 算术派生。保存的 changed 快照在事后算术中也超界，该结果与实际 oracle 已执行状态分列于 `OFFLINE_FAILURE_REVIEW.json`。

本轮阻断发生于作者真值输入资格。复杂题产品的 unsupported／原生回退仍属预登记预期，实际资格观测、模型质量、当前性、fallback 成本、usage 和 P/N 收益均未测。旧 M2/M3 性能结论继续保留。

## 完整前缀成本

| 外层步骤 | wall s | launcher PID | exit |
| --- | ---: | ---: | ---: |
| build | 0.8490617 | 24456 | 0 |
| venv | 4.0314115 | 10276 | 0 |
| install | 1.4183190 | 16000 | 0 |
| regressions | 11.9362183 | 23136 | 0 |
| asset_control | 1.2561266 | 27600 | 0 |
| truth_control | 0.0793325 | 22168 | 0 |
| asset_assembly | 1.0245515 | 17724 | 0 |
| truth_assembly | 0.0958179 | 28936 | 1 |

八步外层 wall 合计为 **20.690839s**。从首次执行 `2026-11-06T18:04:05.1361821Z` 到失败退出 `2026-11-06T18:06:06.2789791Z` 的完整执行前缀为 **121.142797s**，含步骤间 QA 物化、复制和调度间隔。两个范围分列，回归内部 11.7422909s 是其中的嵌套范围。二进制哈希和最初 launcher 物化早于 WINDOW 起点，未另计时。封存、只读算术、Git 和最终报告在工作停止后完成。

每步保存实际 argv、UTC 起止、launcher exit、初次 CIM 身份观察和 stdout／stderr。生成的 `run_step.ps1` 执行单次有界启动，步骤超时受全局 3600 秒剩余量限制，实际 forced cleanup 均为 false。Blender 构造额外在固定 fixture 前执行 `sys.dont_write_bytecode=True` 的 QA 启动设置，以将输出留在本批目录。冻结 fixture 算法照原文件执行。

`BINARY_PINS.json` 记录 Python launcher、实际 base Python image 和 Blender exe 内容 SHA。依赖 wheel 的 SHA 见原 freeze，构建的 wheel／完整 source bundle 与 BUILD 原件保留。外部标准库、全部 DLL 和原生句柄存量未完整 pin／采样。CPU、RSS、临时分配和消费者 token／费用没有测量结果。

## 清理与封存

8 个 launcher 退出记录完整，18 个已观察 PID 在清理复查时均不存在，匹配本轮 run 路径的 Python／Blender 进程为空。`CLEANUP.json` 保存实际查询时刻与范围。redirector 子进程独立退出码、未观察的完整进程树和句柄存量未测。资格与消费者进程启动数为 0。

`qa/qualification.py` 在停止通知前已完成文本物化，未编译、未执行且未完成写后审阅，仅保留为未执行准备原件。其内容没有用于本次结果。

本地 venv 留存于 run_01，Git 封存采用构建 wheel／source bundle、安装身份、QA 复制摘要及全部非 venv 原件。`EVIDENCE_MANIFEST.json` 逐项列出封存文件的长度／SHA，自身摘要由最终回报给出。实际输出量另列于 manifest，安装目录的本地保留范围明确列出。

回报类别为 `PERF_INTEGRATED_001_BLOCKED`。本轮工作停止、清理完成，窗口可释放。主线收到原件后独立复核，本批至此结束。
