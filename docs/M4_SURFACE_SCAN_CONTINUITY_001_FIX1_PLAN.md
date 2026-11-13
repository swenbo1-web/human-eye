# CONTINUITY-001 FIX1：修复准备接口，完成消费者接线

2026-11-13。承接交付a206a96e51ca6293ea555f17960b964ba02f0606。原准备1c96846cbbf948b80860a5366f5442407e1cbabd及其工程失败全部保留。本批只完成同一连续观察准备中的接口与接线缺口，产品、场景、题面和算法不变。

## 固定事实和目的

原N三轮成功；原C BASE工具成功返回，但后置资格核验失败，REPEAT/EDIT未运行。四次薄客户端都有实际退出，两个owned实例已关闭，没有待确认的动作需要恢复。原分母3通过/1失败/2未运行不改。

失败来自owner完整几何投影与旧rich资格整包比较；CLI的argv/parser虽然有离线测试，实际consume循环仍未连接。FIX1要使真实准备路径从runner输入、资格接口到三轮消费者归档连续工作，不能只增加分别正确的辅助函数。

保持C产品452b44d2dcf231d6675bef54e568db0431a29261、138源4067c864c3db1ba586cd7179e6430db5acc4d71675b5295416d471632851a9f6、既有隔离安装和原BASE/EDIT真值。旧N结果仅作为未变actor/thin/backend的工程证据复用，不拼成新的性能对照。root原计划9e8adc0eac4dea5ce5d1afd40c8e484a72d79ab99564cbc5f81af80d58e8d4bc中的其他条件继续有效。

## 一处来源接口修复

接受明确的owner完整几何投影合同：unit_scale_m以及全部24对象的name、vertices_local、faces和完整matrix_world必须与固定BASE/EDIT相等。类型、单位、重复/缺失对象和数据非有限或改变均不能通过。已有rich输入仍按原完整合同核查。

只保留一个bind_source_snapshot适配函数和一套活动verify_c_turn；在新准备版本中替换旧binder调用即可，不长期并列维护候选复制的整套验收器。历史冻结文件留原样。返回明确schema及已验证字段，缺失的rich元数据仍标未记录，不从参考包补造。

本固定任务的几何真值不要求再次导出完整rich包。把同次实际capture的资源、matrix、单位和绑定对应到几何投影，复用固定宿主源中的静态来源检查。source_status及源码检查与独立原始rich逐字段记录分开陈述，不把前者写成后者。不得改变被测产品准入或放宽事实/距离条件。

离线回归必须包含原C BASE的真实INITIAL、FINAL、工具返回、audit及capture组合，通过未来runner实际调用的同一个资格函数；至少覆盖原失配反例、实际正例、旧rich正例和已有几何/来源篡改拒绝。禁止继续只用rich fixture替代owner接口。

## 把真实consume循环接上，而不另建框架

在新准备目录复用旧consumer_transport的事件/进程循环，最小参数化逐轮输出目录、episode共享workdir、expected_thread_id和原绝对期限，接已有argv_for_turn/summarize_turn。每轮有自己的final/events/归档；共享工作目录在首轮初始化，此后保留。首轮persist，后两轮显式续接首轮实际UUID；失败不能改为新上下文。

每轮期限不得晚于episode原期限；计时包括正常消费者启动、stdin、事件、退出与清理。完成单轮只清理该CLI/薄客户端，不关闭外层owner、Blender和产品。episode统一finish一次。继续保存原始usage事件，尚不求和/差分，不把合成计量当模型真实usage。

把原业务请求/响应归档与三轮信封实际接通。模型consumer未启动开关保持关闭；正式样本量、顺序、预算和收益门在根复核后另冻。

零模型端到端测试必须真正调用上述consumer循环及episode协调入口，可用本地fake CLI/进程替身输出合成事件。验证三轮共享work/endpoint、独立输出目录、显式UUID、原期限、失败保留及not_run、单轮清理不finish后台、真实归档信封连接。不要只断言argv文本或分别调用parser。stub结果明确为合成，不声称真实模型记忆、模型续接或token范围已验证。该测试不接provider、无新Blender实例。

## 新冻结后，只运行一次C工程episode

新目录为verification/m4_surface_scan_continuity_001_fix1/。离线接口与完整接线测试完成后，先提交冻结本批源码、来源、复用组件和执行配置，再从新隔离实例运行一次C的BASE→REPEAT→EDIT。不得继续原已关闭C，亦不得只补原未运行轮次。

actor、stdio_attach、worker及被测产品继续固定原字节，不为本批更换生命周期实现。原N三轮因此可复用，新增N工程episode为0。若修复实际必须改变这些共享运行组件，先报告具体差异，本计划不自动扩大live数量。

唯一新C：绝对590秒、每工具30秒、三个业务调用，真实薄客户端逐轮启动/EOF/退出；普通default surface_scan，固定2mm阈值，零图像。同owner/backend/product/session跨三轮保持；原登记Obj_008 Z位移仅在REPEAT后、EDIT前由外层实施一次。匹配71/71/72、新kernel112/0/10、每轮一次捕获，原真值全276对象对按每轮对应状态核查。BASE与REPEAT绑定相同，EDIT失效，不变pair复用。

启动、状态QA、注册编辑/回读、清理和发布分别记录，完整C时界都计入。一次live失败保留并结束，不能同批追加样本；准备期可恢复离线错误修正留档。成功响应后核验失败不代表动作没发生，仍按原回读/关闭证据处理。新工程实例结束后丢弃，未来消费者从新实例起步。

## 交付与出口

交付固定准备和最终commit、最小diff、真实owner回归、consumer完整接线的离线证据、唯一新C三轮原件、实际输入/结果/关闭/成本，以及已测与未测。原001失败、两not_run及后验事实报告保持可追溯。

本批新增模型/API调用0，不读取Google key、不恢复503/付费，不改默认、原资产、共享GUI、竞争分支，不增加产品模块。不要回到报告格式、距离算法或已封顶冷态题。

完成向root local/01a1971f-eef5-7a23-a1b1-2352beb80a77主动回报 **M4-SURFACE-SCAN-CONTINUITY-001_FIX1_READY**，随后结束等复核。如果真实C资格与完整接线通过，下一出口是冻结公平N/C连续模型消费，不再安排第三轮无新缺口的准备检查。
