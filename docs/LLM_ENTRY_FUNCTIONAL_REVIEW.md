# E0/E1 功能验收与真实宿主下一步

2026-11-06，主验收025，`codex/aggressive-v1`。**ACCEPT_E0_E1_FUNCTIONAL_HOST_AND_VALUE_PENDING**：接受 revision_003 的 R1–R4 修正与五例原生功能。关闭本次实现返工，继续真实模型接入；不是完整 E1 收益通过，不放行 E2。原[024失败](LLM_ENTRY_PREFLIGHT_REVIEW.md)及其归档不变。

## 结论及独立检查

交付基于 `655de7662df9fb55de2fd3141bbc7e870f73862f`，manifest SHA256 `dc44bf3b9d5f024c7acce38bb71bd0b8bf0482e8801662d8e766025a1a092d8a`，40源 ZIP SHA256 `097b33d5ac975c613a7a353b0fd7802ef01eef69d068571ff75bd054078fa4b3`。主干三路独立审查冻结代码、原始记录与数学，运行针对性 CPU 探针；本轮主干没有另跑 Blender/GPU 或模型。

| 验收对象 | 核对结果及边界 |
| --- | --- |
| 来源 | 40交付源、33原生源、12引用证据一致；17已验收内核、relay及pump与前批相同 |
| CPU | 作者24/24；主干独立验证错误后新显式任务、连接渲染器复用、结果/相机取回；不是原生性能成绩 |
| 原生功能 | 两个限定串行进程，原五例5/5，正常退出且summary PASS；旧批0/5继续保留 |
| 几何与写入 | 对10份真实before/after RNA独立全三角对重算；4次动作各写1次，已达标例0次；原8e-9m门未变 |
| 场景保持 | reference、parent、context记录精确不变，moving拓扑不变；最大实际顶点/回包位移分量偏差5.464e-10m |
| 主线程与释放 | 实际Windows immediate-child PID、主线程dispatch/close、stdio EOF、listener和GUI timer释放均有记录 |
| 图像 | 四数值例GPU init/render/close为0/0/0；occluded例为1/2/1，SECTION与NATURAL各一张1024×512 PNG，与对应实际camera/单位/切面/image_id匹配 |
| 打包 | 新增可选`human-eye-task-mcp`脚本及stdio模块；wheel导入和`--help`通过，原入口不变；没有安装或切换默认配置 |

五例为nonconvex、parented、already-reached、occluded、parented-rescaled。occluded中附加inspect是功能检查，不能拿其调用次数充当模型任务回合。GUI首次Python观察可见，随后仅隐藏自有PID；案例前后与结束时隐藏，未操作用户窗口，不宣称启动从未闪现。

## 架构和算法没有新增重大退化

R1删除两层永久写锁。错误返回本次实际write_status及已知Outcome，清除失效证据；下一条显式请求重新观察。没有自动重试、恢复旧算法或暗中重复动作。

R2删除每run依赖/父级遍历及缺乏误差依据的1e-9 witness重复门。固定拓扑、独立刚体、reference固定等条件由可信绑定声明。最近点解析式和实际全局before/after仍保留；数值路径不引入TD、完整AO、CF预测、图像或候选搜索。主干重放旧被拒surface，确认现在可到达一次execute；不扩大为任意远坐标Blender精度保证。

R3由连接惰性拥有一个VGRenderer，跨目标复用，EOF/stop释放。根侧冻结源码联合双件的三张图为1次初始化/3次渲染/1次关闭；真实原生两图为1/2/1。当前实际geometry/context仍按新图准备，未把旧场景当最新场景。没有实测新的GPU提速百分比。

R4当前result原样取回，当前camera取自实际生成该图的metadata，查询不重新执行或渲染。默认仍是一份JSON TextContent，按需加一份ImageContent；图像base64和相机矩阵不重复进入正文。

保留两个有限合同：显式换模式后，原result可能引用旧image_id，camera只属于最近图，必须按ID对应；零gap请求SECTION实际回NATURAL，之后显式请求NATURAL可能多渲染一次。本批不为这两个已知限定重开优化或建设历史仓库。

## 正式任务设计可承接的部分

D02改为边—边内部见证，D03改为顶点—面内部见证。根侧用90位Decimal独立重算56个合成状态区间，当前外扩后的区间包含对应高精度上下界；最小内部重心权重大于0.28。最大单侧外扩仅为任务容差的8.66e-10倍。初次18/56区间倒置及最大4.34e-19m原件保留，不把修订倒写成首测通过。这只覆盖固定数学样本，真实RNA仍待后续资格。

14例/臂、原目标/容差、V五点多数判定、180秒截断和完整配对统计承接[草案](LLM_TASK_PROTOCOL_DRAFT.md)。目前N helper的2个小seed只证明正确性；其O(Fa×Fb)广相及多次最小二乘不宜直接当合理性能基线。N可使用通用BVH、mathutils、向量化和一次批处理，并按同等开发预算冻结，不能靠慢评分oracle制造本端收益。

四个正式V的实际PNG/相机/样点/标签、N实际worker/RNA/setter审计、真实宿主模型及usage仍待完成。普通occluded图不能顶替四V资格，脚本stdout不能顶替模型实际使用。

## 下一步与证据

按[真实宿主pilot协议](LLM_HOST_PILOT_PROTOCOL.md)先做一个数值任务和一个带图任务，使用实际ChatGPT登录的Codex CLI及隔离的本地MCP配置；最多两个新模型上下文、一个自有GUI worker。同期只准备N/V可执行程序，不启动新的广域原生矩阵或正式双臂收益批次。作者自测后主动唤醒主干，主干不轮询等待。

根侧没有改作者算法来再次优化；只补缺失的可选打包入口。完整任务质量不退化、复杂任务均值至少快2倍、9/12配对更快、各族及p95不劣、可见文字token目标减半等主门保持。缺usage就保持相应门未验；不将未知换算成节省费用。E1主要收益通过后才推进E2。

证据为`llm_entry_functional_evidence.zip`及内部MANIFEST：revision_003原件、三个独立报告/探针、打包脚本/日志/wheel。打包首次TEMP权限、缺build backend、Windows长路径失败均保留，最后用隔离构建依赖的标准PEP517后端离线构建成功。wheel SHA256 `9ac643495bc2dd7448200641d9eb80613e32479d39aed417d56befb19d3cf0da`；它绑定当时源码与README，不冒称后续文档也已包含。机器决定见[验收JSON](radical_acceptance_llm_entry_functional.json)。
