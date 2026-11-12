# M2-TIGHT-DIRECTORY-001 独立源码与正确性复核

固定审查实施 `c0134088796d47a982edfc838aa6704c8e052d57`，产品 `fac9b4373575d653cc96f39f1dcb225300cd5977`。本复核未发现需要阻止工程候选交付的数值、缓存或来源合同缺陷。此判断不代表模型消费收益或默认启用验收。

## 本轮实际执行

1. 读取七个产品文件相对 `de35ceda` 的 diff，以及原计划、实施报告。独立脚本 `audit.py` 从作者保存的 17 次实际目录响应及其 RNA 输入重算 153 个对象的 1377 个 bounds/center 坐标。使用 Fraction 仿射计算，不调用作者 oracle 或新目录实现作为真值。实际最大坐标误差为 `1.734723475976807e-18 m`，满足独立 16-epsilon 算术上界；发布 center 与发布 bbox 的精确有理中点正确舍入一致。
2. 独立重算 17 份目录摘要；核对象 ID、name、instance、frame/subframe、完整覆盖计数、无执行权限以及无完整 scene/delta 字段。实际旋转非盒反例的八角外包中心与紧致范围中心不同，候选采用后者。
3. 独立检查存档真实变化记录的 capture_state 更新、冷暖同代命中和重连事实。目录摘要被当作完整 delta 基底提交时，实际响应为 `status=full, base=null` 的完整网格重同步，确有 vertices/faces/edges，未接受目录为完整几何基底。
4. 精确读取并 compile 实际 `blender_host.py` 字节（SHA `e3cdbbf1c8a3775dfbad8e1c0aecfa147279f4ab178b152df3f2d81792813f19`），对 `_bounds_midpoint` 做 65536 个固定端点组合，含极大、极小、正负和固定随机二进制数；全部与 Fraction 的正确舍入一致。
5. 使用实际宿主源码及既有 bpy doubles 独立执行：同名同世界几何替换保持目录事实相同，但实例身份、目录摘要、capture_state 更新且不命中旧缓存；几何通知使目录失效；完整 capture 与目录缓存/wire 分离。真实 Blender 的同世界几何替换仍未由本轮运行。

共 67079 个机械检查通过。这不是 67079 个场景；分母如上。脚本、输入文件 SHA 与实际结果在 `RESULTS.json`。

## 源码判断

- `blender_host.py:1134–1227` 使用真实 evaluated 顶点，按既有 world forward 公式聚合，所有对象成功才发布 complete。不是八角近似。
- 目录使用独立 captures key；`SceneResidency.sync/reset` 统一失效。返回经 `_capture_state` 深拷贝，服务随后补 provenance，不污染宿主缓存。
- `live_service.py:1286–1376` 独立目录协议校验和来源绑定；没有 activate 完整 ReadContext、记录完整 scene_memory 或产生旧动作基底。`blender_mcp_host.py` 与 typed worker 的 directory 均绕过完整 capture delta decoder。
- 新入口只在显式 directory 分支，无图且不接受 pair、goal、delta、自然语言求解；旧 overview/task/nearest 几何流程未被改写。完整 JSON Schema 与运行校验的一致性由根另核，本子任务未重复测试。

## 一个可优化点，当前不是错误

`blender_host.py:1168–1190` 在目录未命中时，总是逐对象 `evaluated.to_mesh()` 并重做顶点 forward，即使同代完整资源已驻留。独立 fake-host 的“先完整 capture，后首次 directory”观察确认重复读取。现状通过只读正确性，且计划只是允许复用资源；不能把此点描述为数据错误。

若总成本审查证明该情况值得优化，下一候选可以只研究复用**同对象资源 stamp 与 pose 均匹配**的已有世界顶点，避免重取和重变换，不新增缓存系统。是否减少真实主要成本须由保存的阶段记录决定，不能仅以这项代码机会就启动微调。

## 保留的失败与未运行

独立脚本首次误要求“仅连接端重连必须更换 resident 代”，失败记录见 `ATTEMPT1.txt`，原脚本保留为 `audit_attempt1.py`。同一活 Blender 宿主的重连允许保持实例与代；修正的是复核期望，没有改产品。

本轮没有运行 Blender、模型、隔离安装、完整旧单测集或实机性能矩阵。作者的 21 次观察、进程退出与安装结果属于已保存证据，不能算成本轮实际执行。完整 JSON Schema 引擎、模型质量/token/费用和真实同世界几何替换不由此报告认证。只在本复核子目录写脚本、记录与报告，没有修改产品。
