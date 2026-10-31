# 有限任务间隙原生取景合同

`9.7.2+20261031.task.gap.r1` / `7a88d58d` 已通过SDK与固定入口MCP验收并安装；用户GUI仍未验收。旧消费者明确拒绝V2、新消费者接受旧V1，源身份错配会拒绝。外层readonly协议和八字段能力保持，新局部计划使用显式 `native-task-gap-plan-v2`，不能将旧消费者视为支持V2。旧V1公共规划/渲染/动作路径保持。

只有旧计划为overview_sufficient、焦点和参考为严格外向8顶点12三角形轴对齐闭盒、恰好一轴正分离且另两轴重叠至少4倍gap，才考虑任务局部图。最佳正交间隙须<1个全景像素，局部gap>=32px、zoom为2..4096；局部span=max(4gap,overview_span/4096)。不处理1–12px中等特征、斜面、任意复杂网格、penetration/touching或两轴对角分离。

原overview的视向和像素保留。gapZ的detail使用XZ，gapX/Y使用XY；中心是重叠区中心与gap中点。V2公开reference、axis、SI gap、两个几何端点、三sample、原view投影和新view/像素机会。旧feature仍描述物体轮廓，不偷换成gap。相机在binary32中不能把局部中心定位到span*.005以内时保留V1；原实际RNA/frustum门仍逐帧执行。

两body内部样本朝eye射线要求各自表面first，gap样本前方不得有表面，样本后方背景允许。三sample仅验证这些采样，不证明整ROI/对象完整可见；共面/近退化/近tie保守拒绝。producer与独立consumer各三ray，共享6F<=4096三角形工作上界（F<=682），scene V<=4096。所有原几何保留参加渲染和完整深度，不以删遮挡、Xray或增budget获得通过。

每call最多2张384²、294912px、同原readonly截止，不发动作权限、不续期原预算、不重试未知写入。消费者从原生快照独立重算边界/方向/中心/像素与共享工作量；V2坐标按局部gap尺度及ULP检查，不复用大绝对坐标的宽松相对误差。任何失败保持原准入/恢复/隔离语义，不能临时改投影图冒充原生成功。

验收要求实际ray-AABB像素真值与PNG间隙可辨，图数不足以验收；物理毫米来自已导出网格的结构化量测，图片提供局部视觉佐证。5个新输入同old/new对照真实通过，额外3detail几何投影均96px，连续PNG核心为94/95/94px（抗锯齿边界另计）；普通与全遮挡不加图，五overview像素exact。正式模型任务收益仍未测，新增细节图确有渲染/视觉输入成本。[证据](../verification/fixes/20261031_v21_task_gap/REPORT.md)。
