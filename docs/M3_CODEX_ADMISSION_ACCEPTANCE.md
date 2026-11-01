# M3-A2b：Codex受信任务入口与审查消费（实现前合同）

2026-11-02，排期仅见PRODUCT_ROADMAP。用户要求连续完成M3，只有真实阻塞才中断。本阶段先核对宿主，不把后续未实现模块或条件项标为完成。

本机codex-cli为0.152.1，实际导出的App Server schema包含mcpServer/elicitation/request和对应accept/decline/cancel应答。当前聊天仅连接正式22fb的四个旧工具；旧Hook携带的prompt/session/turn或permission_mode均不作为具体三维任务批准。官方文档说明了Hook数据与App Server elicitation分别的功能：[Hooks](https://learn.chatgpt.com/docs/hooks)、[App Server](https://learn.chatgpt.com/docs/app-server)。这只是可行性证据，不证明当前插件已接入真实批准UI。

采用独立显式owned MCP入口，复用现有两只读工具/TrustedTaskEntry/OwnedGoalScheduler；新入口不提供旧transform/segment旁路，默认live四工具及原共享GUI路径不改。操作对象仅为受信本机配置指定的独占Blender副本，模型参数只能提议既有有限ClearanceTaskSpec，不能指定文件/可执行程序、批准身份或权限。真实动作前通过已协商的MCP elicitation向宿主提交具体目标、原预算、进程/来源摘要，请求明确批准；只接受对应随机server request id的accept与approve=true，decline/cancel/超时/无能力均零写。外部客户端是此传输的信任边界，不声称抵御同账户任意Python/伪造宿主。

协商仅支持已实现版本的form elicitation；旧2025-03-26客户端仍可用旧四工具，新目标调用拒绝，不偷用prompt/stdout作为批准。所有接收、审批和登记等待消耗原固定窗口，不为批准重新计时。请求单飞、同连接call id不重跑；断开、取消和输入故障先使当前任务停止资格失效，已提交动作仍回读/计量，不撤回已发生写入或重试unknown。原子提交与保存确认语义沿用原代码，不引入异步提前报成功。

审批返回只是TaskAuthority的真实输入来源，随后仍核对原场景/源/配置/对象/原三角、claim和原预算；完成/异常结果通过同一MCP工具回执交还Codex。结果构造或写到stdout不等于客户端已消费，不提供恰好一次通知或重启恢复能力。

先验：JSON批准注入/错id/重复id/过期/无协商/取消/EOF/异常均不能派发；独占真实Blender的accept4→1mm、decline零写、审批期间变更、原期限到期、在途取消、断开及unknown不重跑。协议测试用显式脚本客户端，不能冒称真实人类批准或当前Codex UI消费。最后必须把固定候选加载到实际Codex，收到真实表单应答并读取实际终态；缺少热加载/重启或真实UI答复时保留pending并报告具体外部阻塞。不得通过另起用户聊天、伪造审批或付费模型调用补造验收。

M3-A3/A4/B/C/D仍按主计划各自的数据、几何与修改域验收；新MCP入口不赋予顶点修改或通用修复权限，不改变旧M2/成本门、正式安装或模型试次0。

## 2026-11-02交付与阻塞

源码候选`v21-codex-owned-admission-candidate-20261102`，91源，build `554b5028867732bd64ec131d8a75c3b800c128f939650970ccd02f98bc7844df`；隔离发行`9.7.2+20261102.codex.owned.rc2`，wheel98文件，SHA256 `60ac759b5b60dc3aa6c0ea168145ca27786da6d349e5b45a539a45e98b1b2f4e`。固定bootstrap校验所有源及实际导入位置；独立wrapper额外核验相邻固定bootstrap字节，不接受模型指定模块或源码目录。

17项新单测通过，覆盖协商/无form能力/旧协议/写旁路、JSON权限注入、精确scope与原接收窗口、拒绝/取消/数字1/错id、重复、到期/未来或非有限起点、配置变更、execute边界异常、EOF/坏输入及id类型。默认live协议仍2025-03-26，新独立入口只实现2025-06-18 form wire协议；支持更高客户端协商降至该已实现版本，无form能力拒绝目标调用，不假装支持新stateless协议。模型提议最长30秒，审批、排队和本地执行共享原固定窗口；实际父预算不续期。

最终26项（13场景×2独立worker）使用真实stdio与明确脚本客户端，尚无真实人类表单应答：

| 场景 | 结果 |
| --- | --- |
| accept，随后同call id重发 | 每次4setter完成4→1mm，重复不弹新表单/不重跑 |
| decline、cancel、数字1、错应答id | 零setter，未交付live执行能力 |
| 旧协议、模型参数注入批准 | 目标调用在elicitation前拒绝，零setter |
| 审批期间原期限到期、配置变化 | 零setter，原窗口与配置不重绑 |
| 首个真实apply后发送取消通知或关闭stdin | 先保留真实回读/对账，准确1setter；EOF测试保留stdout仅用于检查最终回执，不冒称双向socket硬断开 |
| 真实apply后注入回执丢失 | 实际1setter，调用结果unknown，不误报0或重发 |
| 完成保存后注入ACK丢失 | 4setter/解析终态成立，物理成功但保存确认unknown |

验证端独立读取原生顶点计算盒体间隙；参考对象、焦点局部网格、世界XY和旋转保持，输入blend未保存，全部进程退出。脚本记录不作为真实Codex用户批准或模型消费。公共113模块1868项，本机1865通过/3跳过；干净导出1855通过/13跳过，额外10项仍是未公开历史基线依赖，不是GitHub Actions证据。

早期夹具两次失败是公开context_text未解析与Path拼接错误，原数据和脚本均保留。rc1正常协议24项通过后，负例抓到数值1可与True相等的问题；rc2严格检查`is True`，增加数值拒绝并重跑26项。rc1不作为最终候选，24项不与26项累加成当前覆盖。

已新增项目MCP命名空间human_eye_owned和新的4mm独占副本，CLI get返回enabled；固定wrapper只读初始化/form协商/三工具列表通过，零动作。该修改**只追加一个独立MCP配置**，默认human_eye_live正式22fb、全部原有配置内容、Hook及原连接配置保持；因此项目config.toml哈希预期变化，不宣称整个保护三元组未改。本轮不会将旧M2/成本失败版本替换为正式版。

真实阻塞：当前聊天工具表仍只提供旧human_eye_live四工具，未加载human_eye_owned；可用工具无该自定义MCP的热重连接口，CLI管理命令也没有reload。因此需要宿主重新连接/重启后，实际调用新工具、展示具体表单、取得真实accept/decline及终态读取，才能通过M3-A2b。此处按用户“遇真实阻塞才中断”的条件保存状态，不将整个M3标为完成，不新增用户聊天或付费模型绕过验收。A3/A4/B/C/D保持未完成。

本机原始证据在`verification/fixes/20261102_m3_codex_admission/`（rc1及协议/失败记录）和同级`20261102_m3_codex_admission_rc2/`；最终协议组为后者`owned/RESULT.json`。准备好的独占配置在`.human-eye/owned-admission-20261102/connector.json`，只在新独立进程处理该测试副本。
