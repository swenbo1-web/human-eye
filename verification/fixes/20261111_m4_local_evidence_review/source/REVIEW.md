独立源码审查结论：**未发现需要阻断本候选的实质缺陷。** 三个产品文件的改动符合已确认的最小计划，没有把表面定位点改成共同体积内部点，也没有增加场景采集或再次几何求解。

固定范围：证据 HEAD `e6a620cd68e23b87dc60387eb28a9d70411e6ec8`，产品提交 `e077fce38b5951efff8166b3b688d05ffa2ebf04`，对照 `107641ec19919d56aa843c1949261590fc338148`。候选记录137源、canonical `53db41976085ce5f361d026196f4da5faf80d639af33dfced35ba58e328ef732`；本子项核实三个改动文件及所用 `surface_proximity.py` 与产品 Git 字节相等，未重复全137源安装矩阵。产品 diff 为三个文件、38行新增、6行删除。

核查所得

- **最终穿越对绑定正确。** [surface_geometry.py:482](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/surface_geometry.py:482) 只在当前横向穿越成立后，将当前 `i,j` 和本次中点交给证据函数。没有使用较早的 `prepared_holder['boundary_contact']`。[_closed_transverse:338](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/surface_geometry.py:338) 仍执行原有两片严格相对内部判定，中点只在判定成功后保留；每次先清空 holder，失败不泄漏上次中点。
- **单位、有限值与位置误差处理一致。** [证据函数:348](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/surface_geometry.py:348) 按现有有序 records/faces 取捕获世界米顶点；它们已经经过 `_integer_frame` 的有限 binary64 输入验证。精确中点沿同一 origin/factor 还原，复用 [_publish_points:429](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/surface_proximity.py:429) 的有限值和1e-9米坐标误差检查。成功明确标 approximate，超限/算术发布失败仅使 point 为 unknown，保留三角片和已经成立的闭体关系；未放宽闭体零容差。
- **点语义正确。** 输出的 `point_scope` 表示边界交叉定位，三角片作用域明确是本次捕获、target→candidate、非原始 polygon ID。[精简输出说明:615](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/live_spatial_mcp.py:615) 明确“精确中点也在双方边界上，不在共同体积内部”。新增证据没有替换已有 surface nearest witness。
- **缓存和两条输出路径一致。** [task_query.py:251](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/task_query.py:251) 将闭体缓存键升级为 `task-closed-solid-exact-local-evidence-v2`，有序网格与参数绑定沿用原机制。[第265行](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/task_query.py:265) 将同一结果字典投影进事实；普通输出保留该字段，精简投影第613行仅搬走公共合同字段，不重算或删去证据。缓存本身以完整JSON编码/解码结果，不增加新缓存层。
- **没有新增采集/求解。** 改动没有宿主、RPC或重新取网格调用。原相交、点在三角形内、点在实体内、闭壳验证的判定路径保持原样。新增工作为每次成功结果复制两片三角形、发布一个已算出的中点以及序列化；这是常数规模输出成本，不能说它零成本。非横向分支没有新增证据。

本轮实际执行的独立检查

[check_publication.py](D:/hefe/verification/fixes/20261111_m4_local_evidence_review/source/check_publication.py) 先核固定 Git 字节，只加载纯数学模块和三个 AST 提取的闭体辅助函数。没有导入作者测试/fixture/oracle，没有启动产品服务、Blender或模型。自行构造两片有理数解析三角形，其交线中点为 `(1, 11/6, 0)`；六项全部通过：

1. 非binary64精确可表示中点，输出位置与独立有理数答案的误差在合同内。
2. 交换双方三角片，顺序和世界坐标保持对应。
3. 非零参考原点与 factor=256，世界米坐标恢复正确。
4. 平移至 `2**40` 后，独立误差超过1e-9米，定位点明确 unknown，三角片仍正确、有限。
5. 点接触返回false且清空已有 holder。
6. 平行接触返回false且清空已有 holder。

前四项另使用非零三角片序号及诱饵第0片，确认输出使用传入的当前片序号。所有结果可通过拒绝NaN/Infinity的JSON编码。

原始结果：[PUBLICATION_PROBE.json](D:/hefe/verification/fixes/20261111_m4_local_evidence_review/source/PUBLICATION_PROBE.json)，SHA-256 `909f7eaf55d0042c4419e28413c38a0824c74cddb4b17f9d6ae9ba23600d57e0`。

验收局限

六项是辅助函数定向验证，不冒充本子项独立重跑了完整闭壳、缓存、隔离安装或Blender入口。作者测试代码已只读检查，其日志不是本轮执行结果。完整入口、次数与性能证据由主复核的其他项汇总。该证据是否减少原生补读仍未在模型消费中验证；本轮不据此宣称调用数、token或完整时间收益，也不建议提前扩写更多证据分支。
