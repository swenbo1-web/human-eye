# M4-OBSERVATION-BASELINE-001：FORMAL_QUALITY_READY

已按独立 GO 执行固定运行器一次，启动且收尾全部六个新消费者，没有试答、替补、第七格或未运行尾部，controller stop 为 null。此报告只交付原始执行与匿名材料的完整性，不评分、不报告分组正确率、耗时/token 对比或收益。

准备提交为 `1c110f2b`，产品仍为 `107641ec`、137 源、canonical `7a3d108bc5658508d76d98fe24b8f3dee4feac2d50856202b2ea7395c3dc9cc1`。PLAN、原准备 FREEZE、全部 37 派发摘要和原 380 个准备索引材料字节保持。GO 从根记录原字节复制，来源及摘要见 `GO_PROVENANCE.json`。原 FREEZE 是准备快照，不为本次执行改写。

匿名公共材料位于 `quality_handoff/handoff_01/public`：同一个共同题文和原 PNG、六个冻结 opaque ID 排序的原答案及必要工具事实。公共 INDEX SHA 为 `e950da63c0b61ddf2b3938b92a7ac443ead08524797330ced86f7e876be861cf`。完整私有原件、组别映射和原始成本记录位于 sibling private 及原 cells，公共包没有新增分组成本比较或排行；原事实和代码仍可能透露路线，不声称完美盲法。不要在质量封存前用私有材料作分组评价。

固定打包器 `afa802bdb085ad9e174f04c4ba91ff05bdacdbc7b0bb892162a7b7e14d580cbc` 只执行一次。两项独立只读完整性复核分别为 148/0、218/0：六份 final 原字节及 producer 绑定、28 个公开文件、六份私有 ZIP 的全部 475 个原件均匹配。实际 owner result/error、公开工具事件、代码、原生输出和嵌套 JSON 文本没有递归清洗，管理删除限已知信封位置。此批未实际出现重复/缺响应/错误尝试；这些异常保留能力仍由此前合成测试证明，不能冒称本正式批触发过。

六个独立 CLI 线程及原答案记录齐全。六个消费者进程退出/回收、owner/native/product 关闭凭据均有各自记录。只读查询的 33 个试验 PID 均已不存在；没有终止或修改任何进程，PID 缺席不代替正常退出证明。六个 thin client 缺少 EXIT，继续记为 unknown，未晋升为已正常退出。完整状态见 `formal_run/private/EXECUTION_STATE.json` 和 `PID_QUERY.json`。

六格的初图都通过真实 `--image` 参数指向同一冻结 PNG，记录前后字节未变。provider 接收和模型认知使用没有独立回执，保持 unknown；不从线程启动、答案内容或 token 数猜测图片已被理解。新增图片只在原 helper 工作目录 PNG 扫描/render hooks 范围内未观察到，不声称任意 Python 的全域安全证明。

原资产、初图、任务、真值、语义评分、收益门槛、匿名映射、六格顺序、预算、产品和消费运行器均未改变。nearest 的来源域及决定 A 保持；实际工具选择、拒绝和回退记录照存，等待匿名质量封存后再归因。没有重做安装、几何预检或旧 27 格；仅使用获准的既有 Pro 登录通道，未启用 Google、API-key 或其他 provider，未改共享 GUI 或默认配置。

全部原始 timing、usage、调用和失败字段都在私有原件中保留，当前未汇总分组成本。看不到的 provider 请求次数、费用、图片 token 分量和精确模型版本仍为未知。下一步只由根核匿名包并独立评分封存，之后才揭盲，不能用运行器成功代替质量通过。
