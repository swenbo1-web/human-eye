# COMPLEX-004 preflight ready

2026-11-10。仅完成准备与无模型预检，正式18格由根审实际FREEZE后另发GO；不向用户重复请求审批。

- 固定两题×N/O/C×三轮，共18个fresh会话。顺序为PLAN_DRAFT的Latin轮换并交替题序，PLAN.json为机器版本。模型gpt-6.1-sol/medium，450s模型/570s整格/32工具尝试/1MiB工具响应/30s单工具/256KiB代码/128 worker RPC/0图/0consumer补跑。
- 两题正文分别保持003原1217字节及指定discovery1231字节。统一SESSION_RULES205字节加一个换行，实际模型输入assembly1423字节SHA1ffb175653bdc11423e62e177915639f4fc10ee5a22871dc41259c8032097358；discovery1437字节SHAddcf37206d68bb5abfebccaabe4699b1681a4470d4d22799d8b405df26f09571。共同原生定义完整原字节，ordinary scene_observe schema原样，不改图像参数；缺失/true图片请求明确拒绝并计次。
- O/C实际controlled release使用同一dependency Python及同模板serve子进程，actor转发真实普通MCP。SOURCE_PREFLIGHT核对Git/source/wheel/actual137及参考venv，唯一runtime差异为已接受4行；不采用003 spatial_task_only，也不在桥里求解。N同depPython与同owned Blender/公共native能力。
- 六链无模型预检全部通过。两题初终态/冻结local网格+矩阵+有向faces对应，四次真实插件查询按已有真值/区间核对正确，commonNative全六组相同，普通read schema四插件链相同；16工具尝试含6次刻意原生错误均记账，34 worker events含QA/close。无模型调用，预检成本单列。
- 当前新Owner.close无论final snapshot是否失败，都finally尝试MCP close/wait，再native close/wait；失败不能被清理绿化。9个pure fake测试全部通过，覆盖终态失败、peer关闭失败/组合失败、正常顺序、native异常/未知工具/三类零图拒绝和满响应预算留痕。
- 每次模型工具尝试都在finally保存REQUEST、ATTEMPT、elapsed、异常、响应/bytes、TOOLS聚合。Peer保留真实MCP TX/RX与握手/status/catalogue成本。TOOLS的wire bytes是拟交付MCP响应的精确序列化并保守计预算；实际stdio交付依据原thin client的TX/RX。内部peer接收统计指匹配完整帧，未知/晚到数据不冒称已交付模型。
- 消费者工作目录仅新建空目录；不把真值/评分/计划/生成器/历史答案提供到模型上下文或公共工具。普通Blender Python不是恶意代码文件系统安全沙箱；预注册代码审计和污染判定，不能将协议隔离说成OS不可读保证。最终匿名答案原文打乱后先交根语义评分，不含组标签、顺序或成本；保留术语可能泄漏路线的局限。
- CLI0.152.1/哈希01b0fd…6ee6和ChatGPT登录模式已以无模型命令核对；不读key/auth正文，不改配置/信任，help不证明远程额度或最终resolved effort。仅既有Pro路线，不运行Google/API/Key/付费试验。AL本连接仍unbound/host_epoch5/rebind_required，未借根任务514或其他句柄写状态。
- 两个准备脚本错误均在任何Blender/model启动前：schema probe取错envelope，随后碰到保留的空输出目录。清除空目录的命令被执行策略拒绝，未删除；改为新目录preflight_attempt_02并完整保留先前记录。六条真实预检没有重跑或覆盖旧数据。

源码差异仅新verification/native_plugin_complex_004的actor/driver/transport及证据适配；产品、默认配置、真实GUI、原资产与竞争分支未动。Root需审核READY/FREEZE后发GO；当前不存在GO.json或STARTED.json，不能启动模型。
