# PLUGIN-VERSION-LLM-AB-001 冻结短计划

比较两个真正隔离安装的插件版本，A=a3a72b9，B=d01d49b；不是插件对原生模型。各自wheel、独立venv和相同NumPy/Pillow。模型走现有ChatGPT/Pro登录CLI，不启用外部API；固定gpt-6.1-sol、requested medium，resolved effort没有实际证据就记未测。正式配置、原资产、竞争分支和Google不动。

12个新consumer：round_120可达（mesh/rig共同Rz35°和平移1.25,-.75,.5）、balanced_120无需修正、unreachable_120不可达；每任务两个独立A/B配对、初态每格重建，AB/BA顺序平衡。精确顺序、夹具、阈值和提示词见PLAN.json、TASKS.json、PROMPT.txt，由PLAN_FREEZE.json绑定。三类任务均必须取得实际执行回执，不能只测无变化的observe接口。每格全新会话，最多360秒；不看成绩追加样本。

使用两版字节完全相同的薄MCP桥describe_task/run_arm_goal，转发到实际安装的ArmAxialTaskSpec→scheduler.run；桥不解算、不生成答案、不写候选。初始化只设置起始姿态，产品setter与QA分别计数。MCP initialize启动owned场景，保留独立初终态，模型不执行亦可核验。该桥属于测试适配，未正式发布MCP功能。桥和runner在首consumer前另冻结源码SHA。

提示词、工具schema、完成规则、模型和effort完全一致；不告知版本优劣、旧性能结论或预期状态。读取描述不足以完成，必须取得实际产品回执再输出最终JSON；未知动作不得重试或伪造成功。模型仍自行选择工具调用和最终答案。

评分两栏：正文按实际调用、状态/目标、数值、写入计数、保守声明与适用范围六项；几何另按独立native重算目标、完整端姿/保护点/静态/sentinel。exit0不能代替通过。失败/未运行保留在12格分母；部分结构字段缺失不自动补成正确答案。

保存从提示词提交到最终出答、CLI结束、setup/启动/cleanup各时界，内部source/prepare/ledger/state/RPC，真实工具/写入/采集次数，原始stdout/stderr、公开text/image字节、实际usage与可得cache token。未知美元费用不从Pro token推算。六对逐对B/A、每任务及总体中位/范围只作小样本描述，不宣称稳定提速或泛化3D收益。安装或适配可恢复错误保留并修复，产品版本不改；真实权限/额度/未知执行状态如实阻塞。

最终在我方分支提交完整证据并回报管理员复核；只清理本轮确证owned临时进程和目录，不删旧证据。
