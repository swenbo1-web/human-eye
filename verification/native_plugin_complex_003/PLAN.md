# NATIVE-PLUGIN-COMPLEX-003

固定既有assembly.initial：scene.blend SHA a1a593fc1591365bbbff0c62c535af90ab8b1cdd2dc5ce560d3922252c4e1fcb。4网格72顶点132三角面，小规模、空间关系复杂，不称大型高面数资产。旋转带孔凹闭体、3相关候选、全部AABB重叠但关系不同；判断全体关系、分离间隙、穿插集合、最近分离件并解释包围盒局限。旧数据源及非零误差界证书沿用，实际初态对local/matrix/有向面逐值核对。只initial，不作跨状态缓存试验。选题检索发现密集曲管需要新oracle；按管理员最终选题复核不扩新资产，保留前期检索耗时，不移作模型成本。

N=普通原生execute_blender_code与Python；A=a3a72b9，B=d01d49b，复用上轮真实隔离venv/wheel。A/B保留完全相同原生工具并额外提供实际安装LiveSpatialMCPServer(spatial_task_only=True)→human_eye_spatial_relations。事实不由桥求解。A/B空间路径同字节，唯一产品差异在三骨执行，不能预设空间算法差异。

9个fresh consumer，Latin NAB/ABN/BNA。gpt-6.1-sol requested medium，既有ChatGPT Pro登录，固定CLI0.152.1及相同neutral prompt/完成规则。自然选择工具，允许NumPy、BVH、原始三角读取和自编计算，证据足够即可答，不强制插件消费或少调用。只读同一.blend副本，不读管理/真值/旧答案，不保存或编辑。无Google/外部API，正式配置/原资产/竞争分支不动。

共同预算：模型450秒、每格全流程最多570秒（含startup/终态清理余量），工具32次、结果wire总1MiB、每次native/插件请求30秒、code256KiB、physical RPC128、图片0、自动consumer重试0。冷启动、插件import、CLI输入到最终答案/退出、owner终态/close分别计时，全部失败/原生回退计入9分母。provider request/费用/resolved effort未暴露就未知。多步NativeSession由CLI外parent持原Popen，薄stdio客户端无backend关闭权；终答后parent回读、close ACK、WORKER_CLOSED和wait/reap均核验，不能第一工具后关场景。

预注册语义评分：完整三个候选及关系；两个分离距离满足abs(answer-d0)+原E<=1e-6；穿插集合；最近分离件；解释旋转/孔洞/AABB局限及当前几何证据；不把穿插表面距离当脱离量/深度；只读、证据/来源与完成合同。unknown保留安全语义但不自动算完成，遗漏不补答。原文去组别后盲评，质量先于成本结论。9样本仅探索，不按结果加样、调提示词/阈值/算法。所有原始文本、代码、fallback、usage/cache与公开字节均保存。

一个实施者执行；检索代理仅只读，无实现/模型/Blender动作。一次无模型A连通预检已确认相同Native协议和实际安装HE入口，初终态与旧证书对应，parent正常回收。冻结后直接运行9格，不重建审计平台。
