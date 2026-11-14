# 固定路由任务完整成本与预登记判定

六槽全部完成并通过已封存质量审核，N/P各3/3，P实际事实采用3/3。本固定任务达到预登记的有用正信号。

| 配对 | N完整外层秒 | P完整外层秒 | P/N |
| --- | ---: | ---: | ---: |
| N1/P1 | 192.1434770 | 107.0212609 | 0.556986 |
| N2/P2 | 218.5544347 | 106.3112278 | 0.486429 |
| N3/P3 | 202.3410581 | 101.4070276 | 0.501169 |

配对P/N中位数为0.501169，门限为0.90。3/3对P更快，逆向配对为0。最慢N槽为N2，最慢P槽为P1。每槽均使用检查前至SLOT_RESULT写入、fsync及关闭的同一独立wrapper，SLOT_TIMING自身发布在时界外。

| CLI原始usage合计 | N | P |
| --- | ---: | ---: |
| input_tokens | 645207 | 303608 |
| cached_input_tokens | 553728 | 242560 |
| output_tokens | 16089 | 6397 |
| reasoning_output_tokens | 2599 | 753 |
| cache_write_input_tokens | 0 | 0 |
| input+output | 661296 | 310005 |

P/N原始input+output为0.468784。六槽均为同CLI schema、fresh进程、单用户轮次，原始usage与summary逐项一致。turn/session聚合范围仍未确认，此处按预登记作同源CLI消费的有限判断。cached属于input、reasoning属于output，没有再加一次。现金、图像token和provider请求数未测。

六槽独立outer合计927.7784861秒。batch为929.4499304秒，额外协调及共同发布1.6714443秒。父周期929.5219420秒。route、consumer及工具阶段嵌套保留，不叠加，也没有总周期除以6。

实际49次业务工具、0 guard拒绝、29次raster，包含产品9次和原生20次。28个PNG块实际构造、发送并进入CLI。P1多构造的SCENE没有附图，P2重复SCENE附图，P3无重复。产品调用、prepare、index与重放各3次，Blender采集和进程均为0。

P1的独立组件发现、P2的产品region引导全网格映射及两次重复SCENE全部计入。P3只查询、派生及保存JSON。三个N槽缺少shapely的错误、N3错误断言恢复和尾部表格重印全部保留。没有将这些成本从结果中扣除，也没有把P补查描述为六池遮挡重算。

每个P公开v4 JSON为44,873字节，直接绑定原字符串。COST.json保留产品index/prepare、scope_and_facts、图片反馈及定位、MCP投影与序列化包容阶段、图片read/validate/base64、PNG/NPZ联合发布、每次工具和原始数组字节。独立JSON解析CPU、PNG编码CPU、峰值内存和完整缓存占用未测。

1796冻结来源、24质量文件和869份外部原件/副本已逐SHA复核。准备只有一次无图普通Python读取，模型、产品观察和光栅均0。安装复用既有隔离候选，前期研发、安装、人工协调与审计未完整计量。

此结果支持当前固定题、显式路由和同源CLI消费口径下的工程判断。三对样本没有统计显著性或普遍性能保证。所有readable行恰好完整，partial-readable与新场景仍未验收。provider内部、namespace独立dump仍未知。thin持有句柄确认exit1及关闭，EXIT回执缺失保持未知，actor/CLI/launcher均exit0。没有引用旧239秒或前批141秒作分母，没有增补同题样本或修改门限。
