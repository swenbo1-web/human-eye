# TOOL-AFFORDANCE-001

唯一实施者W-ENTRY，起点clean `bfcde7e739d61049271cc715e448fe849b10ef3e`，产品c08d882b/131源ec3ac8。先读根COMPLEX001_REVIEW.md；本批只做一个公共工具说明候选，≤25分钟完整turn，0真实模型/Blender/MCP现场/RPC/性能样本。不再改几何算法或重复性能测量。保持本分支，不向竞争分支提交。

已证事实：正式原题两initial均未确认终答；P没有调用HE。原生实际求解均不足1秒，但模型在150秒内没有完整交付。根双匿名评分确认工具计算事实充分。不能由此声称模型不信任或未看见HE；有效模型schema实际暴露仍未证。可修的明确问题位于 `human_eye_plugin/live_spatial_mcp.py` 公共observe说明：开头唯一完整例子是surface_nearest单对象，紧接Use exactly one…；原题需要的closed_solid_relation只在后段一句，query.description仍以nearest/top1为主，没有实体关系与表面间隙联合请求的完整例子。

单变量候选范围严格限定为现有工具schema的description字符串：observe总说明、query说明、objects/requested_facts等相关字段说明。允许在同一个现有源码文件内改这些文字，新增验收证据仅 `verification/tool_affordance_001/`。不得增删工具名/字段/enum/type/required/allOf/default/返回结构，不能改变分派、算法、数值域、unknown、执行授权、校验或缓存。递归去掉description后新旧实际schema必须完全相同。

重写成模型按任务能直接使用的简短说明：清楚区分“两个指定对象的真实分离/接触/穿插及表面间隙”与“一个对象的全局最近表面”。给一个通用且可直接解析的task请求例，使用两个通用名称selector和requested_facts=[closed_solid_relation,surface_proximity]；说明更多候选按对应对象对查询。只用通用A/B占位，不出现本fixture对象名、形状、几何数值或真值。明确单对象限制只属于surface_nearest，每个selector的name/id互斥与pair两对象不能混说。

必要事实用普通词表达：闭壳实体关系、非负表面距离、状态绑定、测不出/有歧义时的unknown原因。完整且当前的测量事实可以用来回答；缺项或unknown再补证据。不要写强制信任、不许原生核查、总能正确/最快等无证承诺。保留其他已支持查询模式的准确使用说明，用短字段说明承载；消除重复声明，不加新的防御段落。整个observe schema及完整公共catalogue的UTF8编码字节不得增加；以实际新旧公开schema生成结果比较，不拿Python源码字符数作收益。

验证：固定一个候选提交，给完整131manifest与新摘要；逐字节证明仅description变化、去description结构一致、通用例子符合现有JSONSchema及已有纯请求解析路径。适量利用已有离线入口检查，不新增镜像实现测试、不跑Blender、不声称模型已采用/节省token。给新旧说明/UTF8字节及具体歧义解决对照，正常多模式说明不误导；旧来源/失败原件保留。

停止规则：最多这一个候选，不反复设计许多文案筛选最短。根独立复核后才会选择一次有限消费验证；若后续仍无采用/完整收益，不继续同题改词刷分。WACQ同时只修公开诊断记录，无资源竞争，不向其分支写代码。完成后固定源码和证据提交并回报cycle_id到根 `local/01a1971f-eef5-7a23-a1b1-2352beb80a77`，结束该批等审。Google/API/key/503、默认部署、原资产和共享GUI均不动。
