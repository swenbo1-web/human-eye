# BOUND-SOURCE-FIX-001：来源校验修复与唯一候选验收

**BOUND_SOURCE_FIX_001_COMPLETE。** 已关闭本轮复现的异常来源排除缺口，并把保留对象的面索引校验移到原生展开之前。固定候选五态实测为**两种正常成功、三种指定来源拒绝**。本轮完成来源修复，不代表完整 nearest 接线、M3资格或发布准入完成，也没有性能收益结论。

## 唯一产品变更

基线 `d6fdf2a1381c541a54c8326e73b011e9ca80720f`。唯一候选提交 `f34db5c79f7bb27148bf95710eabfa7762e5cfcb`，只在 `human_eye_plugin/blender_host.py` 新增共享 helper 与 acquisition 调用点，共48新增行。131源摘要为 `ae3bd4a30908d104165e0ca5e24d764f72544f49a0f2d54341335a27e0df7769`，host SHA256 `20ab9cf8157dac963fa9eba873342814e9163b02c07fb4445acefab86622c3ce`。

`_acquisition_validate_triangles`（288起）先检查所有面的 `loop_total==3`、`loop_start` 范围及各角顶点索引，再进行引用坐标读取。拟排除对象使用每对象临时 bytearray 去重，核引用坐标有限性；保留对象只核结构和索引，坐标有限性沿用原 `_capture`。不是抽样、总角数代替逐面、或遇错改为保留后继续三角化。

调用在去向循环1032处、`_capture`1039之前；因此完整 selected 列表进入任何 `to_mesh()/calc_loop_triangles()` 前已通过索引校验。错误为带对象ID的 `BlenderHostError`：`acquisition_invalid_triangle_structure`、`acquisition_invalid_triangle_indices` 或 `acquisition_nonfinite_referenced_vertex`。正常有限共线/重复面未新增来源拒绝，M3资格另判。

原期限在入口、每256面、每256标记槽及出口检查；没有延长期限或吞掉期限错误。原目录全场景500000顶点/1000000面限制保持。没有 `mesh.validate`、min/max重算、世界数组、临时mesh认证、新缓存/代际/权限层或生产遥测。

`POST_SOURCE_CHECK.json` 证明：仅host相对原131源变化，其他130文件相同；旧 `_capture` 函数正文逐字相同。`runtime_identity.py`、M3、MCP、公共packet schema和旧capture行为未修改。未安装、重载共享插件或切换默认入口。根后续统一整合版本常量。

## 离线结果与保留的失败

| 组别 | 结果 | 范围 |
|---|---:|---|
| 新定向测试 | 16项通过 | excluded/普通retained/focal/seed后续坏索引；to_mesh及三角化双哨兵；NaN、不同面长但总loops相同、坏范围、先索引后坐标、去重、孤点、retained坐标复用、退化、期限/数量 |
| 旧M4及九点对，原fake不改 | 17项中记录2 failure、19 error子项 | fake缺真实RNA面布局/loop索引；原始失败保留，不称原套件原样全绿 |
| 初版fake适配 | 1 failure | generated-wire重新加载host模块，初适配只包本地helper，未覆盖该独立模块；保留原报告 |
| 完整fake接口适配后旧M4/九点对 | 17项通过 | 新runner在fake创建及本地校验前仅补缺失RNA字段；不覆盖显式非法值、不跳过真实helper、不改产品放宽校验 |
| host/selected/identity/deadline | 71项通过 | 独立运行通过；适配修正后没有无理由重跑该组 |

原失败在 `LEGACY_RAW.txt`、`REGRESSIONS_INITIAL.json`、`LEGACY_RNA_ADAPTED_INITIAL.txt`，最终见 `REGRESSIONS.json`。新用例直接调用真实helper/入口，不经旧fake适配回退。两个工程子代理分别完成新用例和只读复审，没有启动额外Blender。原生展开哨兵对四种坏索引角色均为零调用；不是靠最终错误文本猜测顺序。

启动前一次 Git whitespace 检查把 unittest 原始进度行末空格当成错误，未启动会话。已在 `PREP_STAGE_CHECK_ERROR.json` 保留，改为检查自编源/文档/JSON；原始日志字节未裁剪。此准备问题未改变唯一产品候选。

## 新增工作与内存

`WORK_COUNTS.json` 在实际helper属性读取上计数，不含旧首面见证和原 `_capture`，不记录性能样本。

| 数据/去向 | 新增索引读取 | 新增唯一坐标读取 | 标记payload |
|---|---:|---:|---:|
| 6顶点2面，有效excluded | 6 | 6 | 6 B |
| 同数据retained | 6 | 0 | 0 |
| 后续NaN excluded | 6 | 4后拒绝 | 6 B |
| 后续首角越界excluded | 4后拒绝 | 0 | 6 B |
| 400面共享3顶点 | 1200 | 3 | 6 B |
| 原数量上限500000顶点，仅3点被引用 | 6 | 3 | 500000 B |

上限例 bytearray 在离线Python的 `sys.getsizeof` 实测500057 B；这是该标记对象及开销，**不是整个helper/Blender进程峰值内存认证**。逐对象局部对象在处理后释放，没有新增持久缓存。未引用槽仍需遍历以找标记，按原步长检查期限；不能把“仅3坐标读取”说成O(1)总工作。保留对象不多读坐标；原首面见证仍有原本三点读取，不能宣传整个入口每点只读一次。

## 唯一真实批次

启动前固定源码/测试/controller/五份实际脚本、资产、binary及既有NativeSession helper。`run_01/FREEZE.json` SHA256 `0f9ba710aa78e8a80e0e05808d6275357d82af113d1bd15a5047801bd380e586`。后续没有改候选或重试状态，离线分析一次通过。实际TX code、worker编译code摘要及冻结脚本完全一致；worker磁盘SCRIPT因平台换行产生的字节另原样保留。

复用原 `far_second_degenerate.blend`，旧SHA `9a7671bb202720b09311f313363bc0e5267017f2af155a9167fff4cf2d96d1b6`。前四态与旧QA同构；第5把同一个原Far对象选为实际 `focal_id`，仅改变查询角色，未为了其后续面新建/替换mesh。原名M4_Focal只有一面，这个角色选择已预登记。

| 状态 | 实际结果 | 与旧证据的关系 |
|---|---|---|
| 1 baseline | 成功；远对象严格排除，展开2对象 | geometry字段与旧成功态相同；不比较旧epoch/耗时 |
| 2 正常后续点更新 | 成功；Far保留，展开3对象 | 完整geometry字段与旧成功态相同 |
| 3 后续引用NaN | `acquisition_nonfinite_referenced_vertex:<Far ID>` | 正常RNA仍保留NaN；此次受控拒绝，没有成功排除packet |
| 4 后续索引13/6顶点 | `acquisition_invalid_triangle_indices:<Far ID>` | 正常RNA仍保留非法索引；校验拒绝，未进入_capture |
| 5 同坏数据作为focal | 同类指定对象索引错误 | 实际focal角色；错误栈为去向循环→helper，先于任何原生展开 |

所有状态均正常收到RPC回执；应用层3次拒绝是预登记正确结果。五状态各一次产品capture。完整native oracle仅用于QA，前后 graph `1969197047968`、帧、单位、对象/data身份和明确NaN标签后的数据一致，最终各自恢复。新脚本标签化比较NaN；旧QA的原始false与close事件unknown仍在历史目录，未改写。本批仍先经oracle读取bounds，不是冷getter性能/正确性对照。

本机一次 build 仍为 `5.2.1 LTS`、`9e2066aef7ef`、`blender-v5.2-release`，与既有官方tag前缀对应；binary SHA `284f4041f98e113f3dc10654a7193ffaaa9bfdfec8b87fa116620a48b5f6d4cb`。没有新增可复现构建声明。

窗口 `SOURCE-FIX-001-ONLY`：**1 NativeSession、5状态RPC＋1close共6RPC**，发送尝试=完成143902 B，接收61928 B。controller整个作业2.1680661秒；owner close内部约.1467224秒。它们是生命周期记录，不是完整聊天turn或正式性能比较，不能与旧四态作业作速度对照。费用/token未测。

PID31240由持有Popen的owner wait回收，退出码0；worker未poisoned，最终指纹等于初始。旧原件和新私有input.blend的SHA相同，helper SHA仍 `5bc1152aeafab89220c93edeec51cbe32ace458cc07d3e7d0507b6412b816fb3`。没有保存blend、操作共享GUI/默认端口、第二会话、builder、重试、模型消费者、外部付费API、安装或默认启用。

## 交付边界

源码与测试已经固定，原异常反例保留；只在本分支提交修复及证据。下一步交根与独立M3精确排名候选做同版本整合和nearest接线验收。当前仍 `acquisition_only_not_nearest_result`、`M3_qualification_performed=false`、`execution_authority=false`，不把本轮来源拒绝修复包装成完整产品发布。
