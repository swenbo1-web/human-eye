# 真实宿主受阻与 N/V 离线准备验收

2026-11-06，主审026。**ACCEPT_OFFLINE_PREPARATION_HOST_BLOCKED**。接受原生对照N与视觉评分V的可执行准备，当前不提升为已具备真实原生/模型资格的模块。025已验收入口及17个内核保持；完整E1收益、E2放行均未通过。

**证据封存后的执行更新**：用户已在主聊天明确回复“授权这两次测试”。根侧已通知原实施聊天按下述新版冻结计划、经正常自动审批执行；不扩大外发内容、模型或样本。51文件归档保留的是授权前的审查快照，旧拒绝不改。此授权不代表模型已经运行或通过验收。

## 实际阻塞与已准备命令

自动审批在进程创建前拒绝原pilot启动命令。记录明确：缺少将本地合成任务、工具回包和图片发送到现有ChatGPT账号连接的OpenAI托管Codex服务的具体授权，并指出原命令带`--approve-for-me`。实际为0 Blender、0 Codex模型上下文、0试点外发。未重试、未换入口绕过，拒绝原文和当时runner保存在`launch_denied_001/`。

新版取消`--approve-for-me`，使用`--sandbox read-only`，保留管理规则与正常审批；这项执行方法取代025协议中可选自动审批模式。两个consumer放在已授权visualization workspace下独立空目录，不属于Git checkout。两次离线临时目录问题分别保存在`prepare_failed_001/002`：首次嵌套Temp权限错误，其后Windows工具沙箱AC/Temp路径不持久。旧2d8c039清单没有被冒称当前计划。

当前可审查计划为`artifacts/llm_entry/host_pilot_001/run_001/manifest.json`，SHA256 `22445e963fb685d73611b5670a2504d132ec00ec6cb8fdc9ed5f201158ad879b`；33源ZIP SHA256 `06ceeab2c1230c32d38aebe07efd7a86f9d429ffc6242edb807947b16401fe69`；runner SHA256 `b425db06a6e63821ab9d1fefb7a9886cc3009d7308bb758d11302571595918fc`。没有launch marker。未来命令仍须用户明确授权外发并经正常自动审批后执行：

```powershell
& 'D:/human eye/venv/Scripts/python.exe' -B artifacts/llm_entry/host_pilot_001/run_pilot.py launch
```

上限为1个自有factory GUI worker、2个真实模型上下文、各180秒。公开任务分别缩隙到0.000600m及0.000750m，容差8e-9m；第二题随同一次`eye_run`请求SECTION图，模型依据实际图描述面板、可见颜色/位置或遮挡。拟外发两条合成提示、公开工具schema、精简实测回包及一张合成图。未主动注入repo源码、评分真值、独立RNA快照或私有夹具答案；不修改HOME/CODEX_HOME、读取复制凭证或默认MCP。

只读CLI沙箱加“仅使用本工具”的提示并非对所有本地文件读取的绝对技术禁止。实际非任务工具访问仍须按记录审查，不能仅凭提示宣称隔离成功。通过本pilot只证明该CLI的有限消费资格，不替代桌面默认注册、正式四V或任务收益。

## N：合理原生对照准备可以收口

新runtime仅依赖标准库、NumPy、bpy和自身；不导入HE内核、recipe或评分器。采用中位AABB树、同拓扑refit、best-first节点对搜索；每叶最多8×8三角配对，用向量化vertex-face、vertex-edge、edge-edge和edge-through-face窄相。全三角对支持枚举/SVD评分oracle仅存在于小规模测试，不作为正式性能基线。

主干独立复跑最终8项CPU检查通过，核对两次原8/8日志和最终7源ZIP。cpu_001与cpu_002源版本不同，不能累计成最终16项。原128×128剪枝夹具实际仅进入64个窄相配对，说明剪枝生效，不是实际Blender时延或收益。没有需立即重写的主要算法缺陷，不继续优化N。

世界米setter、借用evaluated mesh、同责RNA采集和I/N共享SetterTrace有可执行接线。真实父变换/单位、borrowed mesh刷新、实际setter与双方trace仍未运行，不能用RNA double代替；任意其他脚本写入仍须结合实际派发代码和before/after复核。N宿主dispatch和终态渲染还待接入。之后可一次限定background资格核D02/D03/T01/C02，并在同批核实际I/N写入审计；本审没有启动此批次。

## V：同源取证与评分准备可以收口

collector保存实际float32绘制几何、同次VG PNG和相机/切面/单位/对象身份；标准MCP图片按原字节对应。评分只读归档数字和PNG，以实际GPU view-projection逆变换求射线，对实际保留几何求命中，再核像素色标。SECTION只用于witness面板；五点至少三票同标签，unknown保留分母，HUD及不确定深度/切面不冒充可见。

作者10项合成检查通过；主干独立内存检查复核自然visible/occluded、SECTION cut_away、像素冲突、HUD遮挡及synthetic不进入实际覆盖。未发现主要绑定或算法退化，无需扩展测试矩阵。实际V01–V04同源渲染、I/N等价观察条件和正负标签仍缺；当前pilot_worker没有接入这一新collector，README接线示例不是运行证据。后续仍需一次统一真实资格，当前不预填标签PASS。

## 身份、归档与推进

联合delivery manifest SHA256 `d8e2ef4d743397d881f1d0a5f4976faa052194307f8d994d1491355b6f3f6fd0`。主干独立核对14源、14引用证据、33pilot源ZIP与当前文件，17内核保持；新consumer存在、为空且不属于checkout。独立报告/探针与作者43文件原件归档于`llm_host_preparation_evidence.zip`，机器决定为`radical_acceptance_llm_host_preparation.json`。

证据封存时授权问题已在主聊天提出，模型尚未启动；用户随后授权，执行更新见文首。N/V离线准备到此收口，不再因更换聊天重复优化；实际原生资格、真实模型消费/usage和完整收益保持未测。原实施聊天执行已登记pilot，作者完成或真实阻塞主动唤醒主干，随后独立验收。
