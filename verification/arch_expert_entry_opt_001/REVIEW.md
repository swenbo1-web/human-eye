# 选择修复和副本优化独立审查

独立审查 `/root/expert_opt_review` 结论为 PASS，无待修产品或证据口径阻断。本轮仅用 Git、文件读取和自写 stdlib 解析现有证据，没有写文件、导入或执行产品/测试、启动 Blender、发送 RPC 或查询 PID；实际旧新配对期间暂停重 IO。

最终 1,769 个成功 ck 谓词由来源 693、报告/native 选择 748、原始返回链 214、独立 LBS/native 配对 46、五份交付文档 68 组成。每次 ck 调用计一项，数组聚合谓词算一项；这是只读数据审计，不能加入 27 个产品测试、旧 521 次执行或主线 16 个行为方法分母。

## 两份产品差异

产品仅 6 行插入、4 行删除。host 在成功 bind 后同步一位 default-indices 来源标志，仅旧 bound 原请求也省略时删除派生 indices 比较。既有 type-exact 递归保留，bind 失败不更新旧绑定/标志，没有新增请求深拷贝、默认并集计算或验证器。两方向 402↔384、两类暖重复、调用者隔离及旧 bool/float 回归均有实质测试。

来源文件仅增加 capture 私有关键字参数（默认 True）、返回静态副本的门控、analyze 传 False 三处。用 stdlib AST 精确逆转这三处后，整个模块与 27785b3 相等，未改变数值、异常、读取或 prepare 流程。公共 capture 默认隔离契约保持；新增测试修改六类深字段后内部缓存、prepared 和结果均不受污染。

新 7 个测试和四个实际 harness 均经过静态实审。CPU 组精确为 7 新增 +14 相关入口 +6 相关来源共 27 个不同方法，一次通过，无失败/错误/跳过；未扩为旧 165 方法矩阵。旧新内部副本 [1,0,1,1]→[0,0,0,0]，工作与报告一致，unknown 三条真实来源/编解码路径共 6 次进程内工具调用正常恢复。

## 运行来源

逐字节核对新 136 个磁盘来源与固定 fa096c1 Git、旧 136 个导出来源与 27785b3 Git 及 manifest。独立 canonical 重算分别为新 `46ee6672b23a9df9b2bdd13dde5edb6f2e8eb9f65aab2cc77209f8577b8ca24e`、旧 `239cc00a3cf09e9c18874cf0071e811e3244695c93590f806048fab97129b3b9`。实际前后四份 identity 和 CPU 前后两份新 identity 一致；仅 blender_host/arm_twist_source 两个 SHA 改变。四份实际执行 harness 快照与当前文件同字节。

owned 实际默认 worker 的 136 manifest、loader pin、末句 guard.exec_path 吻合，无 worker_path override。shared 三个真实 execute_code 的首包六份冻结来源解压 SHA 符合 manifest，后两包不再带来源。既有私有模块别名和冻结来源执行路径保留。

## 实际选择与模型对照

首轮 19 次工具全部正常成功：18 estimated、1 unknown，0 工具失败。441 个区域的严重度、flag、截面号、原始 ID 与直接原生 RNA 输入的同模型 oracle 完全相同，最大严重度差 0。

19 条 selection_key 均由原请求补默认 sorted union 后独立 canonical 重算，与 source 相符。owned/shared 的 1602→1536→1602 选择和 key 正确改变并在切回时恢复；所有 native packet 的 ID、sections、triangles 域及 weights 归一化合法。五次 repeat 均无 static read/prepare 且保持 bound/prepared。

old/new first、repeat、static、load 的完整 native packet 相等，去掉 source/trace 的报告相等；三个进程各仅一个 oracle 默认模型 identity。recovered load 的 packet 恢复 first。独立 Gauss-Jordan 逆与 LBS 重算 30,240 个当前点，最大坐标误差 `1.3859213698896866e-7 m`，与 source 披露的 `1.3859213709999096e-7 m` 在 `1e-12 m` 内相符。

累计 capture 工作和入口各 19，predict_prepared 入口 19，其中 unknown 提前返回，没有 MLP 严重度评分。static read/prepare 各 14，rest/weight 各 22,296 行、current 30,240 行、rest bones 28、pose bones 38、topology 14。old 四配对副本为 [1,0,1,1]，new 四配对为 [0,0,0,0]，work_delta 完全相同；全部 15 个新工具调用的静态交付副本为 0。

实际 unknown 是正常 isError=false 报告，reason 为 bone_twist_branch_unknown，regions 为空，未给出 max_severity；随后 load 恢复 estimated，epoch 增长并重新 prepare 一次。该恢复不作为暖 prepared 复用证明。

## 原始返回链和计时

47 对 stdio 请求/响应、19 次工具的原始 isError/JSON 与 RESULTS/event 链一致；42 对 owned bridge 包和 3 对 shared execute_code 包一致。19 工具 stdio TX/RX 为 338,561/238,895 B；整个 stdio 会话 old 为 78,743/235,974 B、new 为 214,086/595,500 B、shared 为 47,995/63,195 B。

owned 工具后的下一独立请求才进行 inspect，shared 的三次 inspect 也是独立控制。四个 harness 没有 setprofile 调用，客户端、stdio、Blender 三侧 getprofile 为 None，产品方法时间不超过 dispatch 或完整 RTT。25 控制为 19 inspect、2 static、3 load、1 unknown，单列于 19 次工具之外。轻量 wrapper/wire 复制仍在时间内，后置 oracle 和大 JSON 写入不在时间内。

repeat 的新产品方法增加 0.2430 ms、完整 RTT 增加 0.4225 ms，均如实保留。static/load 产品方法分别减少 7.0325/6.7279 ms，只是旧组先运行、每阶段一个样本的观察。没有将旧有 profiler 的 82–87 ms 残差归因于复制，也没有承诺每次更快。

## 最终文档与限制

REPORT、RESULTS、ACTUAL_QA_REPORT、ACTUAL_COSTS、PROCESS_CLEANUP 五份文档对齐。68 项文档谓词核对逐 19 成本字段及表格、27=7+14+6、19=18+1、copy/work、fixture SHA、原文账本字节、退出与 cleanup 副本。账本原文为 `b'opaque ledger unchanged in expert opt QA\n'`，含 LF 共 41 B，前后同字节。

三个已知 Blender PID 29420/6496/28636 已结束；stdio 返回 0，shared fixture 受控 terminate/wait 返回 1。stdio 客户端数值 PID 未单列，已披露正常退出原件与任务命令行检查的证明范围。没有启动新的 fixture creator。

审计探索脚本曾将 Blender 启动数字误当 dict、将实际 list 的 guard manifest 当 dict、将 cost section_count 当输入截面数（实际为返回 regions 数，unknown 为 0），以及对派生 delta 用浮点全等而未容许显示舍入。修正这些审计假设后最终上述谓词通过，均非产品、CPU 或实际 QA 失败。审查消息还曾把账本长度转录为 40 B，已更正为 41 B；逐字节断言始终使用完整原文。没有重建或修改原始证据。

同模型 oracle 仅证明来源与接线一致，不能证明模型准确性；BMesh 全 mesh C 层成本保持；单组固定顺序不能支持统计速度保证；实际 unknown 恢复使用 load 重准备。旧 task/nearest、M5 和历史矩阵只引用。本轮没有发现需要扩大执行的影响。
