# FIX2 实际 runner 的阶段集成回归

2026-11-13。末版 runner 摘要为 e48be8fbc14f7a3a6c8d75e77b411af2d2a82b1456092c9cb2bf2910631d465d。最终8个方法通过，零failure、零error。新增Blender、provider、模型与API调用均为零。

## 实际协调路径

测试调用新run_episode完整入口，Popen、管理通道和thin请求用本地内存替身。实际新的verify_business、原FIX1的WIRE reader、唯一verify_c_turn和verify_c_sequence均执行。每次finish前，虚拟owner路径下的WIRE在read_bytes、open、exists和is_file处不可用；唯一finish后才映射到冻结原件。

正常用例依次记录BASE收集、REPEAT收集、在线登记EDIT和回读、EDIT收集、finish、BASE验收、REPEAT验收、EDIT验收、sequence验收。finish恰好一次，登记EDIT也恰好一次，任何WIRE读取均发生在finish之后。BASE和REPEAT使用原始INITIAL几何投影，EDIT使用登记回读，真实资格函数逐项核验冻结事实，得到71/71/72匹配和112/0/10新kernel。

## 固定输入和小范围

按SHA引用原compact_facts_001五观察工程中的BASE default、base_brief及EDIT default、对应snapshot、audit和WIRE。REPEAT只将历史brief请求标志合成为缺省，原响应、资源及历史均保持。WIRE仍是该历史实例的完整终态归档，各轮事实读取按目标sequence前缀进行。这些引用用于阶段集成，不构成新实机样本。

运行输出由真实runner的save接口记录到内存，再只发布调用顺序、状态分母、原时间窗口、错误及输入摘要。没有复制旧几何矩阵或整套消费者fixture。保存的空actor stdout/stderr是实际runner打开文件的最小副作用，不对应真实进程。

替身时钟将每轮收集窗口与被引用历史事件对齐。发布的窗口均保留原采样值。阶段故障发生后，测试逐轮比较started_ns、ended_ns，确保它们没有被关闭或后验时间覆盖。suite的0.984884秒是实际Python离线测试耗时，合成episode时界不能当作引擎性能结果。

## 同一套中的拒绝分支

| 分支 | 三轮执行 | 资格结果 | 最终判定 |
| --- | --- | --- | --- |
| 正常 | 3次成功返回 | 3通过，sequence通过 | 通过 |
| finish未确认 | 3次成功返回 | 3未核验，未读WIRE | 失败 |
| 关闭后WIRE缺失 | 3次成功返回 | 3未核验 | 失败 |
| REPEAT后验异常 | 3次成功返回 | 2通过、1失败 | 失败 |
| host事件越过原业务窗口尾部 | 3次成功返回 | 2通过、1失败 | 失败 |
| finish后原deadline已耗尽 | 3次成功返回 | 3未核验 | 失败 |
| sequence实际抛错 | 3次成功返回 | 行资格3通过，sequence为failed | 失败 |
| 计时发布回执异常 | 3次成功返回 | 行资格3通过 | 磁盘等价FINAL_TIMING重写false，错误回执保留原分母 |

宿主事件没有新增ended_ns字段。越尾反例的起点仍在原窗口内，但started_ns+elapsed_ns越过窗口尾部，被真实verify_business按具体守卫拒绝。后验错误没有改写执行状态或未运行分母。

## 记录与边界

首轮6方法通过；runner补入sequence和发布终态保护后，最终同套8方法通过。两份结果和原unittest输出分别保留在offline/attempt_01及attempt_02。本阶段没有自身测试失败。末版读取35份输入，来源、字节和摘要见SOURCE_BINDINGS.json和最终RESULT.json。

本回归证明准备协调路径的阶段和记账，实际新C三轮仍由主runner在提交冻结后运行。旧N、旧C两批失败及未运行均没有被改变。真实模型线程续接、上下文、usage语义和完整任务收益仍待正式消费阶段。
