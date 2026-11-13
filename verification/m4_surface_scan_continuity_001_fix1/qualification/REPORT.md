# FIX1 来源接口与真实 owner 回归

2026-11-13。本目录将来源修复接入唯一活动 verify_c_turn。最终 16 个离线方法通过，零 failure、零 error。原 C BASE 的真实 INITIAL、FINAL、工具返回、audit 和 capture 均经过新工程 runner 实际调用的 verify_business 入口，再进入同一资格函数。新增 Blender、模型和 API 调用为零。

## 一个适配函数与一套活动资格入口

verify_continuity.py 复用原资格实现。旧整包 bind_snapshot 调用替换为 bind_source_snapshot，返回 source_report，随后核对同次实际捕获。活动文件只定义一次 verify_c_turn，原冻结文件及历史候选保持原件。

owner 简版合同要求准确的 unit_scale_m 与 objects 两个顶层字段，全部 24 个对象名称有序且唯一，每个对象准确包含 name、vertices_local、faces、matrix_world。单位、顶点坐标和矩阵必须为有限 float，顶点及矩阵维数固定，面索引必须为合法 int。全部本地顶点、三角面和完整世界矩阵与对应冻结 BASE/EDIT 逐项规范编码一致，保留类型和 signed zero 的区别。

rich 输入继续经过原完整来源合同，同时执行上述完整几何检查。简版返回 rich_source_metadata_verified=false，并列出缺少的 rich 顶层与对象字段。缺失字段没有从参考包复制到观测包中。

## 实际 capture 的对应

verify_c_turn 新增必需 keyword capture。runner 通过 read_capture(native_workspace, host_event) 从当前业务的实际 WIRE 请求和返回读取捕获。执行代码 SHA 必须对应同次 worker script_sha256，wire 的请求及返回尺寸、完整发送状态和唯一捕获信封也要对应。

重复或姿态变更捕获通常只传资源引用，resources 可以为空。read_capture 只从同一 worker 先前真实捕获的资源交付中恢复引用所需的 id/revision，记录每份原 wire 摘要及资源来源序号。它不从资格参考构造资源，缺少实际历史资源即拒绝。历史捕获必须保持相同 document_epoch 和固定 host source，同一资源 revision 的字节不能发生变化。

当前捕获的 24 个对象 coverage、mesh/resource 引用、完整矩阵、单位、frame、document 与 directory binding 对应到任务返回。资源顶点和面与实际 owner 完整几何逐项一致。普通请求、原阈值、全部 276 对处置、距离、kernel、图片和宿主保护检查沿用原条件。

source_status=supported 继续作为固定宿主静态来源检查的声明，报告将其与独立 rich 逐字段采集分开。未记录的动画、parent、约束及其他 rich 元数据仍保留未证。

## 真实失败数据与离线反例

原 C BASE 的完整输入经旧 binder 可精确复现 actual geometry or source fields differ from qualified state。新 runner 的 verify_business 对实际 INITIAL 与 FINAL 分别调用后，均通过 71 匹配、112 新 kernel、一次捕获及原真值检查。ACTUAL_OWNER_REGRESSION.json 保存完整报告、实际入口源码摘要和来源清单。原 C episode 的 passed=false、1 attempted、1 failed、2 not_run 保持，旧 368 份文件在回归前后摘要一致。

离线测试包含原失配、真实 owner 正例、rich 正例及 rich parent 变化拒绝，覆盖简版单位、重复或缺失对象、字段、顶点、面、矩阵的类型、形状、有限值和逐值篡改。实际捕获还覆盖错误事件、脚本、frame、单位、document、directory、host source、coverage、source_status、mesh、资源、矩阵及 live resource 集合。缺失历史资源与跨文档历史分别按预期拒绝。

原请求、trace、kernel、来源绑定、宿主保护、零图像和 N 内存标记反例继续保留。旧五观察的 BASE/EDIT 真实 default 与原实际 wire 用于回归。REPEAT 单元夹具复用历史 brief 的完整事实并只合成缺省请求标志，N 包也属于合成合同数据；这些记录分别注明其范围。

首次 15 方法通过，补充历史资源拒绝后 16 方法通过。最终 16 方法仍通过，全部三份 OFFLINE_CHECK 日志保留。本子任务没有失败重跑。

## 供工程 runner 使用

```python
capture = qualification.read_capture(folder / 'owner/native', host_events[0])
report = qualification.verify_c_turn(
    body, audit_rows, host_events, source_snapshot, turn, request,
    capture=capture,
)
```

资格返回保留原 sequence 所需字段，增加 source_report 和 capture_report。新的真实 C BASE→REPEAT→EDIT 资格仍由主 runner 在准备冻结后执行。本目录离线结果不证明模型续接、模型记忆或多轮实际收益。

AL 本轮 context_bound=false、host_epoch=5，未借用其他会话句柄。仅在本 qualification 目录新增文件，产品、actor、worker、stdio 和旧证据均为固定来源。
