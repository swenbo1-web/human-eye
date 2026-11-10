# COMPLEX-005：真实升级前安装版与当前版

本批纠正比较基线。004 的 O 是开发快照，不是用户升级前的默认安装；004 结果保持原样封存，不拼入本轮样本。

根对话在 `D:/hefe/verification/fixes/20261110_native_plugin_compare_005/ROOT_PLAN.md` 核定本轮范围，最终执行仍需根检查冻结文件后发送 GO。

## 固定三组

- N：仅共同原生 `execute_blender_code`，原定义复用 003。
- H：真实原安装 `9.7.2+20261103.scene.trace.r1`，125 源，canonical `a045a800256f4767271308d239c735177f992ce3408d927d42bde5f1d4b60d8f`；独立字节对应固定历史 Git `001743bb4700719bda1448a49fbb4601bbde24b2`，并核对升级前实际 doctor、部署计划及 binding。只读使用现存受控 entry，不重建旧产品。
- C：当前安装 `9.7.2+20261110.scale.opt.r1`，137 源，canonical `3fc2651e108ad7ac252394871d78e1abaee1200c92a018125984b2fc240193bd`，固定产品 `df016079b0265ee327f884c90dd4815c392016b6`。

H/C 使用各自真实普通 serve，现存同一依赖 Python。源码、entry、binding、实际初始化身份和目录分别绑定，不能要求跨版本 schema 相同，也不能用当前 main 替代 H。

## 工具公开合同

根已核定：N 一个工具；H/C 各三个工具，即共同原生工具，加该版原定义 `human_eye_scene_observe` 与 `human_eye_connection_status`。完整源目录保留供审查；写工具、当前版无关 arm 专家，以及普通 serve 未提供的专用接口不公开。

H 的 query modes 为 `overview/exact_pairs/nearest/top1/mesh_structure/mesh_surface`；C 保留自己的原字段和 modes，包括新增的 `task/surface_nearest`。H 的旧 nearest/top1 合同是可证实的非穿插精确表面净距与其剪枝范围，不能包装成无条件全场 unsigned 查询。支持、unknown、拒绝与回退均记录为实际结果；不预先断言 H 一定无法完成某题。

目录、说明、schema、返回均不按组改写。status 若由模型调用，与其他工具一样计次数、字节和耗时。scene_observe 的零图限制公开执行：缺失或 true 的 include_image 被拒绝，不静默改成 false；status 不套用图片参数条件。

## 输入、顺序与预算

两题分别复用 003 的 assembly.initial 和 SCALE-DIAG 的 D48，原题干、004 中立 SESSION_RULES、原 oracle 和私有评分规则均保持原字节。两题 × N/H/C × 三轮 = 18 个全新消费者和独立场景副本，固定平衡轮换，全部串行。N/H/C 都重采样，不拼接历史结果，无补样或替换。

请求 `gpt-6.1-sol`、medium，既有 ChatGPT/Pro 登录，同一已核 CLI。共同预算：450 秒消费者、570 秒完整格、32 次工具尝试、每次 30 秒、工具响应合计 1 MiB、代码 256 KiB、128 worker RPC、图像 0、额外消费者重试 0。费用、供应商请求数、实际解析的模型档位保持未测；不按 API 单价外推 Pro 用量。Google/API/key/训练继续暂停。

准备和预检只验证真实能力、明确拒绝、来源、原件保护和清理；不把预检调用模板交给模型，不将旧版域外输出改成答案。预检与正式消费者之间无缓存或场景复用。

## 隔离、计量与审查

只修改本批目录的最小适配与计量，不修改 004、产品、默认配置、Hook trust、共享 Blender 或原资产。模型仅获得共同题目及实际公开工具；私有 oracle、计划、旧答案和其他格不进入其输入或空工作目录。原生 Python 属于被审计的只读协议，不宣称恶意代码的 OS 文件沙盒；所有实际代码保留检查。

每格从准备开始记录完整生命周期至终态回读、关闭与回收；另列 prompt→final、工具区间、目录与控制开销、实际 TX/RX、内部 RPC、代码/文本字节及实际 usage。嵌套时间不相加；缓存输入、推理输出按子集处理。批次准备、协调和审查成本不能被记成零或冒充包含于单格耗时。

缺少客户端正常退出收据时保留缺失，不伪造 graceful EOF；实际已知请求回应、独立后端 close/回收与当前进程清理分别记录。

正式 18 格完成后一次提交同编号匿名 final 与真实工具证据。代码、参数、方法、错误、回退及几何值保留，只去掉显式分组、行政身份、计时和 usage；私有映射、原件 hash 与摘取规则保留。管理员先封存正确性/依据/只读审查，再揭盲成本。方法措辞可泄漏路线，不声称完美双盲。失败、unknown、错误和未运行都保留分母；成功子集另列 n，不把错误的快当收益。每题每组 n=3，不声称 p95 或大型资产普适能力。

Agent Learning 当前连接未绑定（host_epoch=5，rebind_required=true），本批记录本地保留待同步，不借用根对话句柄或任务身份。该观察接入问题不阻止已授权的独立只读比较。
