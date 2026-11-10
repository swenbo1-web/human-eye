# COMPLEX-005 包装差异预检复核

结论：**GO（本次有限代码复核无阻断项）**。根核对来源、冻结及预检合同后，可发布绑定现有 PLAN/FREEZE 的执行 GO。此意见本身没有启动消费者，也未创建 GO。

固定提交：`52f583098b81cc4ee647dcaa71b88eb706f6b946`；检查时工作树干净，GO、STARTED、正式 cells 均不存在。仅对比004与005 actor/driver/consumer_transport，阅读已有7项fake与预检原件；未执行测试、模型、Blender或产品，未修改实施文件。

| 重点 | 直接检查结果 |
| --- | --- |
| H/C真实目录 | driver.py:47–52 分别读取 H/C 自己的 tools/list；actor.py:94–103 与实际私有 serve 目录精确相等后，仅追加各自 scene_observe/status。独立读取六份 PUBLIC_TOOLS.json：N仅共同native，H/C各三工具；H/C保留工具逐对象等于各自原目录，未套用C schema到H。 |
| 原请求/结果透传 | actor.py:121–129 将原req交给peer，取原result返回；仅在scene缺失/true include_image时按共同0图预算拒绝，不改写为false。status不要求图片参数。没有添加答案、补mode或改错误。 |
| status预算与日志 | actor.py:113在分派前增加同一attempt，116同一32次限制，127–140同一1MiB响应账本和finally日志。四条插件预检链中，status均单独留下bytes、wall与成功记录；其失败同样进入finally。consumer_transport.py:12/20–23将status纳入同轮已批准工具，并保持相同观测日志。 |
| native一致 | actor仍继承003的base.NATIVE和accepted_native；只改变私有导入标签，无原生求解或接口改动。六份实际公开目录的native对象精确相同。 |
| 生命周期 | Peer与Owner.close代码无变更。actor.py:145–160即使终态快照失败也继续关闭peer，再finally关闭native；consumer_transport.py:181–204保留计时器结束、进程回收、读取线程和桥清理、最终记录。LIFECYCLE_REUSE_REVIEW明确五个例程AST等同004，既有测试只记历史复用。 |
| 绝对预算 | driver.py:55保留worker原570秒deadline，consumer_transport.py:90/111/177–179保留原450秒绝对deadline、计时器与完成时刻判断；工具timeout30秒、32次、1MiB不变。总生命周期仍于driver.py:211完整记录，不将每次调用当成重置总期限。 |
| 防重复run | driver.py:195–200要求005任务授权、精确PLAN/FREEZE hash并逐文件核冻结；在消费者启动前以STARTED.open('x')独占创建，二次run失败。每格目录exist_ok=False、消费者工作目录必须为空；失败不替补，其余not_run保留原18格。 |
| 预检与消费隔离 | H的overview→真实ID→原exact_pairs/top1只在product_preflight管理路径；run直接送原题干/session rules，不传预检模板或结果。H两项blocked作为原版限制保留，不包装成任务完成；预检只证明direct TCP/产品stdio，未冒称已验正式public thin stdio。 |

已有测试证据：ADAPTER_TESTS.json记录7/7通过、0失败/错误/跳过，actor摘要与当前文件一致；覆盖各版目录、N无status、status透传/预算、零图拒绝、写工具拒绝。此次只读检查，没有重跑或把历史004生命周期测试算成005新增测试。六条无模型预检共22次attempt全部留账，包含6次预设错误和2次H原版blocked。

固定摘要：

- actor.py：`42086c72a30500e86298f1e61802daf19979e58dcdbb4a1fdf482a4a70f48eda`
- driver.py：`29452013a631924d10a9096e3962bfb1244ab95fa4ae5a4976c7136606c75d93`
- consumer_transport.py：`3bd85eca9589e28fe0fa8c266a74bb5d6394065b5b679d7527ec1d750c55c9f1`
- PLAN：`8a6a81fdfd4102ace53ddfdf9491c3434ad13b4e0fcac8659fe4b53c7857ed16`
- FREEZE：`bd2133aba2c53ef7260c621b2af8c87fad63873ed48da7cb3807f3f69aef4d67`

本报告只覆盖包装差异与指定守卫；实际模型结果、正式public帧、质量和费用仍待本轮执行与独立评分，未预判收益。

Reviewed UTC: 2026-11-10T12:18:40.136801+00:00
