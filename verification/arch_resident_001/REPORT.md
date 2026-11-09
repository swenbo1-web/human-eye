# ARCH-RESIDENT-001：常驻宿主与变化采集首版

产品基线：`bd1c2e4ed3be550cde8e096a9970ebc5e592463d`；分支：`codex/architecture-resident-state`。旧实验分支保持。此交付是宿主侧可运行首版，交管理员深审，不代表整个新架构或正式收益门限已通过。

最终运行源：132 个文件，`f0d5d0e4c3392d4a2185c03bbda3e23032dad47d3d8bcab5fff0434eca8c6c78`。五个变更产品文件的实际 SHA 保存在 `run_04/result.json`；测试前后源码一致。

## 已实现

- MCP 构造时冻结宿主与小型 helper 源码，首次发送压缩快照并建立常驻 host；暖请求只查找已加载实例，移除逐次文件读取、源码哈希、源码编译和 host 重建。升级来源使用新的 tag；来源不符的旧连接不会静默复用另一版本。
- 宿主保留局部顶点、三角形、边及各自资源版本，姿态单独更新。无变化不调用 `to_mesh` 或三角化；纯平移复用局部资源，网格事件仅重建受影响资源。无通知能力的旧 host／测试替身仍走新鲜采集，不提供可复用 token。
- `capture_state={instance_id,epoch,revision,selection_key}` 覆盖几何、求值姿态、目录／名称、单位、帧及查询选择。撤销、重做、加载和场景切换使旧代失效。撤销销毁 Scene RNA 后，默认 host 重新绑定当前 scene/view layer；显式失效引用准确拒绝。
- MCP 和 owned worker 使用同一私有资源 delta。连接端持有明确的资源 baseline 并重建原有完整逻辑 capture；最近候选 token 位于 `packet.capture`。旧 public 方法保留。增加 owned 的 task／nearest 接线，保留原进程生命周期和错误路径。
- 资源与 dirty 状态清理已删除对象；资源总量保持原有限工作集约束。旧 native evidence／写入内部仍使用原新鲜采集，不使用只读缓存。同步已有 example worker 镜像，更新必要的临时依赖 fixture／manifest。

## 最终验证

`final/unit.json` 和 `final/unit.log`：**95 项，零失败、零错误**。覆盖原宿主、MCP、process／worker、依赖加载，以及新增 delta、实例替换、求值姿态事件、共享 mesh 数据事件、失效代际和正常旧归一化→零变换写入口。执行前后产品源码相同。

`run_04/result.json`：**真实 Blender 5.2 后台链路通过，23 条记录**。使用独立构造并保存的十对象三角网格测试副本，未连接用户 GUI。MCP 通过隔离的 addon 兼容 TCP 测试服务执行真实 Blender Python；owned 走正式 `BlenderProcessHost`／固定 worker。不能把这项称作已安装 Codex 会话中的 MCP 工具验收。

| 实际调用 | 完整调用耗时 ms | 新发送局部资源 | 累计 to_mesh／三角化 |
|---|---:|---:|---:|
| MCP task 冷请求 | 35.252 | 2 | 2／2 |
| MCP task 重复 | 1.705 | 0 | 2／2 |
| 单对象纯平移后 | 1.771 | 0 | 2／2 |
| 单对象网格编辑后 | 1.767 | 1 | 3／3 |
| MCP nearest 首次 | 8.105 | 0，复用已访问资源 | 11／11 |
| MCP nearest 重复 | 2.010 | 0 | 11／11 |
| owned task 首次／重复 | 3.971／0.815 | 私有 delta 回放正确 | — |
| owned nearest 首次／重复 | 3.733／1.286 | 私有 delta 回放正确 | — |

后台测试服务启动 825.386 ms；正式 owned worker 启动 827.202 ms，分别记账，没有混入暖调用耗时。MCP task 冷／暖请求字节为 57,378／1,393，响应为 3,962／2,349。以上是小型功能场景的单次工程观察，不是统计门限、旧 E／F 的公平新对照或复杂资产收益证明。

量测独立核对最初 4 mm 间隙、平移后 6 mm、局部顶点编辑后 5 mm；指定采集、完整采集、最近候选的相关几何一致。还验证改名、删除、同名替换、单位、帧、**真实 `bpy.ops.ed.undo()`**、场景切换、重新打开测试文件和连接重建。测试文件 hash 在 owned 运行前后相同。几何控制只改隔离测试进程内对象。

## 保留的失败与修复

- `run_01/result.json`：真实撤销后旧 Scene RNA 被销毁，触发 `ReferenceError`。已修默认宿主重新绑定；最终 run04 通过同一入口。
- `run_02/result.json`：测试服务的新 scene 使用全局已存在的对象名，被 Blender 自动加 `.001`，预期名称找不到。修正测试构造时的名称冲突；这次是 fixture 缺陷，没有通过修改产品的名称匹配掩盖。
- 旧 worker 镜像和旧临时 bundle 起初遗漏新依赖，已同步镜像／补 manifest。旧“每次编译”和“执行后续磁盘内容”的断言改为常驻一次加载与执行原冻结快照，依赖缺失、未列入来源合同和篡改的拒绝反例仍保留。
- 最早使用 `-S` 跑需要 NumPy 的旧测试导致环境缺依赖；最终用既有 venv 正常 site 运行。此项不记作产品算法失败。

## 下一项真实缺口

首版暖路径仍有完整 scene 的深拷贝，连接端 decoder 也仍按局部资源重新计算世界顶点。不能声称已消除全部 O(N) 数据遍历。接下来应在管理员深审后，优先按资源版本＋矩阵＋单位复用解码后的世界数组，分离名称／颜色／ordinal 等元数据与真实几何姿态失效，再评估 `foreach_get` 批量读取的实际收益。

另一条实施线的常驻只读服务上下文尚未在本分支合并；这里未宣称减少服务归一化或整个模型任务耗时。整体服务集成、已安装 Codex 入口和正式多规模收益验收由管理员统一推进。

本会话 Agent Learning 查询为未绑定、`rebind_required=true`、epoch 5，未借用管理员句柄，未伪报任务同步。没有更改模型／Google API／全局配置。

复跑：使用已有 Python venv，`-I -B -X utf8 verification/arch_resident_001/run_unit.py <输出目录>`；真实后台验证用 `-I -S -B -X utf8 verification/arch_resident_001/run_blender.py <新输出目录>`。脚本中的 Blender 路径为本机既有 `D:/Tools/blender5.2/blender.exe`。
