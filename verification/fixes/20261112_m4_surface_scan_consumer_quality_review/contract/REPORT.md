# 六格全场扫描消费：冻结合同与适配公平性独立复核

2026-11-12。本子审没有读取六份答案，也没有读取匿名映射、实际耗时或 usage；不参与分组推断。**未发现阻塞匿名评分的合同或适配公平性问题。两项运行前修正均符合根冻结题面和工具语义。**

父任务 `b4f1454a-12a3-4736-adfd-783ab2f4e7b0`，本代理使用自身 assignment，未写父任务。实施树只读，未修改 Git；输出限本 `contract/` 目录。新增 Blender、消费者、产品调用和 API 均为 0。

## 固定证据与检查结果

- 根计划 `D:/hefe/docs/M4_SURFACE_SCAN_CONSUMPTION_001_PLAN.md` SHA256 `8c2baa7394f12d003291dbc643aa1c5ed6aba38e6215240d4e1f0148943f1989`；实施 `ROOT_PLAN.md` 与之逐字相同，题面等于根引文加换行。
- 准备提交 `bedcc827ec548e3afab816c0986db0c99eb42bb8`；交付提交 `e5c8afafbcd7cf55307be9e640a3e2ad61e25fd3`。25 个精选计划、合同、运行框架、声明文件均核对准备提交、交付提交和当前磁盘三者字节一致。
- 最终 `PLAN.json` SHA256 `7e3567f1ea8b528c13d36078abe2a659ba7ff74d02342cca86c1bff3dfedcb3f`，GO 与 FREEZE 都绑定此摘要。准备提交是交付祖先，且当时树中没有实际 cells、STARTED、RUN_RESULT 或 FORMAL_PROCESS。完整预登记预算、六格顺序、模型请求设置未变。
- 独立脚本 `check_contract.py` **100 项检查通过**；见 `CHECKS.json`、`RESULTS.json`、`SOURCES.json`。本脚本只读取明确选择的公共合同及源码，没有打开私有映射文件；PLAN 中只核匿名映射摘要，不解析其实际内容。

上述 Git 顺序、冻结记录和源码先核输入后启动的顺序足以确认最后评分合同不是交付时替换的文本。本子审不读取实际调用时刻，因此“所有真实启动均晚于准备 commit”的墙钟核对仍由根来源复核负责，不把作者自述 0 次运行直接当独立测量。

## 1. surface_scan 默认不请求图片

固定产品 `human_eye_plugin/live_spatial_mcp.py:877` 在普通 observe 的 surface_scan 分支执行 `args.setdefault('include_image', False)`；传输遥测在 `:822` 使用 `args.get('include_image', not scan)`。

本批 actor `runtime/actor.py:172` 的预算 guard 与产品采用相同 effective default。它允许省略 include_image 的正常 scan 请求，随后 `self.peer.call(req,...)` 原样透传，没有替模型插入参数、改 query、填答案或替消费者决定工具。显式 true 仍违反本批共同零图片预算。

因此这项修正消除了测试夹具对正常产品请求的错误拒绝；不是为某组放松图片预算。`test_bridge_contract.py:259` 的合成反例核省略字段原样传入，本子审没有重跑作者测试或把作者通过数计入自己的 100 项。

## 2. 毫米、精度与引用的质量合同

原根题面已经要求“距离以毫米表示，至少保留小数点后三位；确为零可写 0”。最终合同据此区分：

- 数值、对象集合或确定性完整性声明错误：incorrect。
- 数值正确但只给 m/cm，或非零展示精度不足：presentation_incomplete，并归 incomplete；不假装是几何数值错误。
- 等价科学记数法可以满足毫米 0.001 的有效展示精度；真零可直接写 0。
- 明确引用模型可见的完整毫米清单可以纳入最终答案；只引用原始 distance_m 清单不会自动满足毫米展示要求。

旧合同、旧评分 helper 与旧 PLAN 保留。CONTRACT_CORRECTION 的修改目标是展示合同；输入、精确 276 对真值、71 匹配分母、容差 `0.000500001 mm`、完整性优先规则和证据规则均保持。旧 PLAN 到最终 PLAN 顶层只变 `quality_materials` 和 `dispatch_input_sha256`：合同摘要刷新及 freeze 阶段新增绑定，没有改题面、样本、预算、顺序、产品或工具声明。

**根评分应坚持按表达实质人工裁决。** `score_answer.py` 是合成回归辅助，不能让正则未解析、JSON 数值丢失尾零或上下文单位识别不足自动决定正式答案输赢。展示不足应和几何事实正确率分栏；错误完整性声明不能降为普通不完整。此建议在本代理未读任何正式答案时提出，非依据结果调整口径。

引用规则没有给工具或组别特权：必须有明确的引用关系，且实际可见清单本身满足集合、毫米和精度要求。无需强制把已完整展示的 71 行机械复制进 final；同样不能仅凭工具存在正确原件就替没有提供或引用该结果的最终答案补齐。

## 3. 对照可用能力和提示公平性

公共原生声明由历史 `native_plugin_complex_003/actor.py` 的 NATIVE 字面量直接核对：双方都可使用普通只读 bpy/Python、NumPy、mathutils BVH、三角读取、自编计算和本格变量缓存。actor 两组使用同一 NativeSession 和原样 code，没有强制算法或对 N 的单独精度限制。

P 唯一新增声明是固定 OPT1 早期真实 TOOLS.json 中的完整 ordinary observe，逐字核对旧 Git。N 工具数组恰为公共 native；P 恰为相同 native 加完整 observe。产品说明中的 scan 用法属于已有完整产品声明，没有在公共题面加入工具攻略，也没有把声明缩成扫描专用版本。

`consumer_transport.py` 的 settings、safe_environment、wait_bridge_closed、kill_owned_tree 与既有凹槽消费框架 AST 相同。共同 prompt 直接写入 stdin，未拼接策略或完成规则；忽略用户配置和规则、fresh ephemeral、关闭 Hook/记忆/额外工具的隔离设置沿用。公共题面不含目标名、目标数、真匹配数或求解算法。

N 分支仅启原生所需进程，普通产品初始化位于非 N 分支。P 的私有初始化仅 initialize/list/ping 元数据，不调用几何业务。实际冷态缓存状态由根来源审查核对，本子审只确认设计没有隐藏 warmup。

## 边界与根裁决

本轮未发现需重跑消费者、修改评分门或补充新模型调用的问题。可按最终冻结合同进行六格独立匿名评分，封存后再解成本。

本子审没有验证每次真实调用、实际模型解析版本、退出状态、完整成本或匿名投影；这些属于其他子审/后续阶段。源码和准备材料证明预定流程，不替代运行原件。

探索过程有一次对不存在的候选文件名 rg 返回路径不存在，随后用实际文件列表定位到 `live_spatial_mcp.py`；没有运行失败检查、改变测试输入或接触用户资产。最早仅列出文件名的目录搜索意外包含 cells/private 路径名，没有读取其内容；后续全部按明确白名单读取，本报告不使用这些名字推断分组或行为。
