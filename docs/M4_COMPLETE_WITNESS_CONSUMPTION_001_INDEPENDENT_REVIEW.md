# M4-COMPLETE-WITNESS-CONSUMPTION-001 独立复核

结论分开记录：新案例真实成立，产品事实正确，正式最终答案正确；当前产品事实被实际采用，但纯直接消费未通过，因为模型又读取了原生几何并全幅重算像素。原自动评分器在内容判断前发生字段层级错误，原自动失败0/1和direct adoption=null继续保留。下一项仅修离线评分读取，不重跑模型。

固定作者交付 `8baad59ac6da01f14e1eb87c3e1f4f0687eb2b7d`，起点 `a9dd9490d1817630e090975362591ce232d881ae`。产品仍为 `d12c7ab248452ff253452007d0635f2d662f0191`，141源摘要 `d8ad7003397d0c0611f54d128c0d0ad3433865b8d9f69b8b0519123752fe9f02`，隔离安装 `D:/he_view_reuse_001/product`。原运行根 `D:/he_complete_witness_001`。

根独立证据在 `D:/hefe/verification/fixes/20261115_m4_witness_001_review/`。三个只读子复核分别重算几何/像素和答案、核来源/成本、诊断评分器；根阅读实际scorer、launcher生产字段、正式final及首次brief-v4，并据此限定修复。没有新产品、模型、Blender或raster调用。

## 案例与模型答案

独立语义检查132项通过。由原始Fraction坐标投影可得：Panel_B在SCENE对Panel_A的影子为[-1,1]平方，遮挡面积4，A面积16；其他五方向没有正面积交集。全部角点入框条件、正面方向和正深度另行核对，没有用产品complete字段当作独立几何真值。

资格与正式的四份PNG/NPZ逐一核对，八条像素事实重新计算。两阶段结果相同：

| 实际视图/对象 | 表面像素 | 对比边界像素 | 可读 | 完整 |
|---|---:|---:|---|---|
| SCENE / A | 37,917 | 924 | 是 | 否 |
| SCENE / B | 12,639 | 0 | 否 | 是 |
| TOP / A | 70,756 | 1,060 | 是 | 是 |
| TOP / B | 17,689 | 528 | 是 | 是 |

A第一条可读行0确实不能证明完整，公开完整见证索引2正确指向TOP；B索引3也正确。整个支持集恰为A/B两面，remaining及unsupported均为0。正式final引用TOP/index2/当前ref，正确报告A中心、70756/1060像素和owned point(155,155)，同时完整列出B和有限六相机范围，没有误把SCENE部分图当作完整见证。

这是两矩形的定向语义反例，不能称复杂资产性能样本，也不能从一次通过推导任意任务泛化。

## 产品采用与额外工作

正式三次工具依次为active_observation、execute_python、execute_python。第二次实际解析公开JSON，随后打印完整geometry/cameras并读取TOP缓存；第三次归并raw源面、全幅重算表面/对比边界像素，并查询RGB相邻点和计算法向。TOP命中已有帧，新增raster为0，复用功能在本次真实消费中生效。

首次brief-v4已经提供题面必需字段：来源/ROI/对象身份，center/u/v/front，complete_witness_pixel_index，当前view/ref，surface/boundary counts与owned anchor，以及完整覆盖/剩余/支持域/有限池。没有识别到必须通过这次原生重算才能补齐的字段。额外源面索引、RGB相邻点和数值色差属于消费者自选的补核。

因此，本例记录为“最终正确、实际采用产品事实、附加原生核对、纯直接消费未通过”。没有产品事实被纠正的证据；也不能仅凭补核行为推断模型心理上的不信任。它对耗时/token的增量没有消融测量，不事后从实测成本中扣除。

## 评分器缺陷与修复边界

原 `score_saved.py` 先取 `RUN_RESULT.records[0]`，却读该行的execution_state。本次launcher复用原始route，该字段只在顶层；旧Routed批次曾额外包装逐槽记录，准备时把旧包装的字段归属误套到当前生产者。这是验收工具接线错误，不是模型答案错误。原QUALITY SHA `272f925f1f46b4140b7483fbeceb1ff0a2b58285d3b5c9cab6c417cbb6cb3a87`不变。

独立诊断只在内存中修正整对象保留及state读取位置，使用完全相同保存材料运行原内容路径，33项检查通过，得到quality=true、direct=false、correct_with_supplement=true，没有继续出现字段KeyError。该结果只是有明确派生代码的诊断，不替代原正式评分，也不是重新独立构造的像素oracle。

根还确认仅改一处取值仍不充分：launcher的execution_state只取决于route.outer_valid_completion；post_route_checks失败时它仍可为completed，而launcher_succeeded=false且terminal_errors非空。派生reader必须同时读取当前schema、单P1/P记录、顶层成功和错误列表，并保留原row/consumer有效性、来源绑定及持有退出确认。18个独立终态控制（含实际正例）支持这个边界。

这类接口问题本可由准备阶段对实际生产者记录进行一次离线读取发现；源码里出现同名字段不能替代接口验收。修复使用一个小reader/谓词和真实原件回归，不增加产品运行时检查层、通用schema框架或模型预热。

新派生评分写独立目录与版本；原scorer、NORMALIZED、真值、题面、阈值、QUALITY和seal不改。完整见证及来源/采用逻辑保持原规则，尤其不能把两次原生补核重分类为direct=true。另用SCENE真实部分可读行作负例，证明像素门槛达到也不能通过完整性检查。

## 来源、运行分母与成本

独立身份核对202个新增路径及Git blob、2216冻结路径、191项质量seal、141产品源/安装和136个运行原件/副本，共1,572,334字节。只有一次产品资格、一个fresh正式P，资格和正式各2次实际raster，总4次，没有替换样本或重跑。

| 计量 | 本轮原始重算 |
|---|---:|
| 资格入口窗口 | 2.7234349秒 |
| 正式route窗口 | 62.8451825秒 |
| 正式启动入口窗口 | 64.5498345秒 |
| 正式业务调用 / CLI图片块 | 3 / 2 |
| 累计PNG交付 | 5,127 B |
| CLI原始input / output | 42,627 / 1,331 |
| 原始input+output | 43,958 |

启动入口窗口含正式前后来源/资格检查与结果持久化，解释器导入在外；原始route没有旧Routed额外slot_timing，仍为null。嵌套窗口不相加。cached input28,160与reasoning20分别为input/output子集，没有重加。无N对照，不计算加速百分比；provider请求数、图像token和现金仍未测。

资格actor、正式actor和CLI均有已退出及关闭句柄证据。thin持有句柄确认exit1并关闭，其自身EXIT回执缺失仍为unknown；不把持有句柄证明换写成正常EXIT回执。

## 本轮复核自身的修正

评分诊断的输入日志收尾曾把Python尝试读取但不存在的pyc路径当成已有输入文件，报错后仅修正日志收集范围，正文诊断结果和原件未变，错误另记。身份/成本审计首轮去掉raw事件行的LF后再比脱敏字节数，导致一项差1字节的误报；R1保留，后续依据原transport的含LF定义核对，不能normalize任意内容差异。

这些审核工具修正与原冻结scorer的真实缺陷分开记录，不把任何一项失败抹掉，也不为此重新运行消费者。

身份/成本补充检查还曾将TCP的MCP结果整个封装与CLI结果整个封装比较，三项不等；两边content的逐项比较和封装差异须分别呈现。wire含`isError:false`，CLI含`structured_content:null`，不能把不同封装说成逐字节相同，更不能改写原文件消除差异。该读法修正仅影响复核口径，不影响按各自原字节累计的传输成本。

身份/成本复核分批为3148/3149、32/35及内容相等3/3，均有重叠，不能合称大量独立功能场景。原四项审计失败保留并由补充证据解释。其首版FINAL汇总曾在收口中改写，随后依原生成逻辑恢复并另存INITIAL，最终解释写到R2；这次审核产物恢复另有记录，不影响作者原件，不能把恢复件描述成始终未改动。

## 出口

本例产品完整性与最终答案有独立证据支持；原自动验收尚待修复，纯直接消费仍未达成。仅派发 `M4-COMPLETE-WITNESS-SCORE-FIX-001`，对同一保存证据补充评分并保留原失败。详细计划见 `M4_COMPLETE_WITNESS_SCORE_FIX_001_PLAN.md`。本批不再增加模型样本，不改默认部署、产品能力、Google/API或专家线。
