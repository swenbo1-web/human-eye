# CONSUMPTION-COLLAB-METER-001 独立复核

接受固定提交 `d2ecb396f0729d467cd8ba198ff06283c6666e8f` 为下一轮实验的计量候选。没有新增真实消费者或部署；旧 RUN004 的协作成本缺口保持未知。

根核查：15 个新增 Git 文件与磁盘逐字节一致，14 个封存成员共 67,430 字节全部核对通过；父提交 `cde74da09d0f0c1fd06fb20ff16688d617f4e79b`，没有修改旧文件，工作树干净。runner SHA 为 `08c5d10003c203c0cdc2c6fde2033ae8ada616bdc392ec4ef3479b691309094b`。移除三处新增的 67、1、2 行后，逐字节还原固定 RUN004 runner（32,616 字节，SHA `d893ff8bdd96fdd693c2159bcc486f6af194ee75aeb989f45778eb42ab422b27`）；未统一换行或只比较规范化文本。原模型设置、主 usage、动作计数、期限、预算、清理及重试逻辑没有改变。

独立语义复核由根与 `/root/approval_gaps` 分工完成。协作记录使用专用投影，只保存已知事件阶段、调用 ID、工具枚举、参与者 ID 和状态；不复制 prompt、message、arguments、result/error 或隐藏正文。事件数、当前 consume 内按 item.id 去重的调用数、无 ID 事件及观察到的线程 ID 分开记录。重复事件不重复计调用，冲突终态保留。观察到的 ID 包含发送者，不作为新建或成功 agent 数。额外 usage/参与者总数为 null，accounting_complete 为 false，不与主 usage 相加。

作者执行记录：5 组合成离线检查通过，0 失败、错误、跳过。前四组覆盖生命周期、重复与冲突、未知结构、正文排除；第五组使用模拟 stdout 调用真实 consume 并核对落盘、主 usage、原动作数与模拟 budget 记账保持一致。候选和测试均有固定源字节编译记录。它验证 collector 接线，不证明真实 CLI 二进制 schema 或实际 bridge/RPC。首次静态恢复脚本因换行假设错误断言失败，修正比较后通过；原记录保留，未改候选。实施者管理回合 995,183ms，与离线测试耗时分开；AL 未同步限制保留。

本轮独立执行：Git/封存/差异/原字节还原核查通过；不重复运行作者测试。新增真实 CLI、模型、Blender、MCP、RPC、API 均为 0。独立结果见 COLLAB_METER_RECOUNT.json；作者日志与独立核查不合并计数。

后续只有一个明确用途：待 M1 同次名称查询候选独立验收后，将两项固定到 RUN005。准备时必须重新固定候选源身份与运行常量，不能直接运行本离线副本。旧 discarded 计数仍保留，新的成本账本另读 collaboration；不能因计量补丁存在便宣称总 token/费用可测。公开字段没给出的 usage 继续未测，不补零，不追索私有内容。M1 当前唯一 QA 窗口保持，不新增任务或重复优化。
