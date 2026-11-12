# M3-SUFFICIENT-SEPARATION-001 独立成本与分母复核

复核者 `/root/discovery_scope_review`，2026-11-12。**冻结的有限工程成本门通过，保存数据中未发现阻断性差异。** 本结论不是模型消费、原生agent对照或生产性能结论。

证据提交 `189ecdb84185d96c3ed0d75ca268bc16d6d4999b`；产品 `e836e03f4b3821f869c72ac3e50df5204f28b50f`；137源摘要 `2c453e56f3abf83a49f9c8ef37a3a77728dd8f05168db4fd5217d3bad465c390`。本复核独立读取固定Git blob，与实施树630文件逐字节比较，核对INDEX的623文件；最终 **8383项保存数据检查通过**。这些检查包括数据一致性和逐顶点证明复算，不应与产品230个测试方法相加。

没有调用作者verify脚本、产品、Blender、模型或新增计时。自己的AL句柄有效但assignment过期、父任务只读，未借句柄、未修改父任务。数学见证面成员与算法整体正确性由根的另外两路复核承担。

## 六十份原始样本与共同事实

按冻结TIMING_SEQUENCE逐条核60份单独JSON与PAYLOAD.bin，对原始字节长度/SHA、完整result/diagnostics、请求事实、顺序、iteration、时间锚点及最终总表做交叉检查。实际为六输入×两臂×五次，严格交替，无缺样、替补、重试、异常或超时。每次重新创建输入mesh、holder及diagnostics，无跨次memo。两源码命名空间只在同一解释器内各加载一次，故“冷”指函数输入/准备生命周期，不是冷进程或冷硬件缓存。

两臂每格均5/5返回有效关系、表面距离和measured见证。分离控制距离1m；穿入为penetrating且距离0；包含为penetrating且表面距离1.5m。包含的正表面距离没有被错当成实体分离。G508距离逐份落在冻结独立区间±1e-6m内。精确三元平方rank按有理数与二进制指数独立解析，两臂每次三候选唯一最近均为Peer_000，4mm判断均为不满足/满足/满足。

对候选所有20份充分分离样本，额外独立以原始被引用顶点复算：公开最近点B−A的精确二进制差、primitive方向、完整引用集合、整数frame、两端支持极值及其source index。严格支持不等式和2V+3收费逐份一致，closed未执行。该复算没有执行候选核心；公开见证是否位于实际三角内的完整独立几何审查仍由根算法分工承担。

| 输入 | 参考中位 ms | 候选中位 ms | 候选增量 ms | 允许增量 ms |
|---|---:|---:|---:|---:|
| G508 Peer | 4782.1386 | 1844.8568 | −2937.2818 | 0 |
| G508 Competing | 831.8532 | 218.3106 | −613.5426 | 0 |
| G508 Near | 1315.0454 | 262.3883 | −1052.6571 | 0 |
| 简单分离盒 | 12.5841 | 10.5677 | −2.0164 | 1 |
| 穿入bars | 3.1694 | 2.2380 | −0.9314 | 2 |
| 完整包含 | 13.9729 | 13.8984 | −0.0745 | 2 |

G508三个中位数之和为 **6929.0372→2325.5557ms，下降66.4375%**，超过20%门且逐对不退。简单控制与两个fallback各自通过，没有把fallback混入aggregate抵消退步。全部60值、各阶段及范围在本目录RESULTS.json。简单控制候选范围10.4866–13.2614ms、参考12.4476–12.7508ms，说明通过的是预登记中位门，不能追加“每次都更快”或尾部改善结论。

参考仍是fac9b437私有诊断版本，只有冻结三项数量门覆盖，保留旧叶算法/AABB/位宽/期限。它额外计算embedded闭壳资格；候选充分路径证明引用三角集合凸包分离，省略该资格。**这里比较共同间隙/最近业务答案的成本，不是同一完整闭壳保证的加速。** 旧批完整闭壳失败继续成立；也不能以本次新算法较旧诊断参考的收益，否认前批Competing同surface阶段+21.31%与昂贵叶+26.34%的事实。

## 主计时边界、非计时观察和测试

静态审查实际run_sixty.py：它只复用前批loader的source/load_kernel，未调用work_spy，也无setprofile/patch等包装；checkpoint仅读perf_counter并核期限，没有计数字典。实际产品计数仍保留。每次最早started在输入创建之前，deadline=started+30秒，只设置一次；输入、query holder准备、求解及完整JSON编码结束后均核同一期限，保存ended也全部早于deadline。不能把本次数据与前批插桩计时直接拼接。

input_preparation、query_preparation、solving、serialization和residual逐条加总一致。query_preparation是holder/事实列表/选项等轻量构造；整数几何准备仍包含在solving中，并非独立准备耗时。完整payload与产品计数都真实序列化，没有只编码摘要来减时间；独立证书检查与磁盘写样本在此窗口外。

批次计时46,740.5771ms，60个完整调用合计46,584.6050ms，源码加载与输入绑定总57.7497ms（两臂源加载24.8294/27.6312ms为其子项），60份证据发布59.9125ms，其余批次协调38.3099ms。该batch从main内开始，排除解释器启动、参数解析与最终总表发布，不能称完整用户端耗时。不得把总加载窗口与两个子窗口重复相加。

非计时工作观察明确为候选独有6次、performance_samples=0，不混入60个计时样本。原始spy记录显示分离四输入的closed分类、自交验证、closed候选树和cone均为真实0调用；surface、admit、整数frame、支持与方向入口各一次。被引用点512/288/288/16，收费1027/579/579/35，符合2V+3。世界距离树仍实际构建，不能称“所有树均0”。穿入和包含各回退closed一次且复用整数准备。未执行closed时的空work对象不代表已检查闭壳资格。

从executed方法ID、RESULTS及原始TESTS日志核得 **213原回归+8核心定向+9接线=230方法**，同源、无skip、failure或error。它们包含多个子例，不是230个独立场景。另有作者侧1290项保存验证，本复核未执行或借它作为独立答案。

## 普通MCP、缓存和真实退出

从实际stdio和host TX/RX核对：**8条stdio请求/7条响应**，其中元数据4条/3响应（notification无响应），元数据host RPC=0。业务4次严格为目录→新装配→旧v1装配→新控制；另QA与close各1，共 **6 host RPC**。唯一FORMAL marker与run_01，未见重放。

新装配三pair的spatial、surface和结果memo均未命中，closed计数0、支持计数与非计时观察相同。旧v1未复用新语义memo，仍执行原closed并三对work_budget unknown，间隙unknown、nearest完整性false。旧请求宿主RX为5916B，低于新请求70247B，属于已有几何驻留后的传输；不能因此称整个旧请求完全冷态，也不能把新旧MCP两列时间当同事实性能AB。

| 实际业务 | 外层耗时 ms | 模型可见文本 B |
|---|---:|---:|
| 目录 | 53.4671 | 6448 |
| 新空间装配 | 2353.4085 | 7987 |
| 旧v1装配 | 3357.6478 | 6523 |
| 新控制 | 36.7750 | 3350 |

业务总5801.2984ms，owned总7785.8193ms，外层进程7891.1035ms。阶段之外79.1439ms保留未分配；业务、startup、QA、binding与cleanup均已包含在owned中。QA快照和已有owned worker的前后全场raw mesh指纹是额外验证工作，不能将MCP窗口视为纯内核。

Host TX96,629B/RX214,278B，合计310,907B；stdio TX2,286B/RX52,917B，合计55,203B。两层链路以及模型可见文本是不同口径。源建立包含在首目录；完整源码/几何桥字节不等于模型输入token。

实际initialize及全部公开body绑定候选源；实际evaluated快照与前批固定原件逐字节一致。raw close、拥有者Popen reap、WORKER_CLOSED与保留的runtime Windows句柄共同确认Blender和真实Python runtime exit0、handle_closed，初末几何指纹一致。没有仅凭launcher exit0替代真实runtime退出。完整安装源码/wheel核验另由根来源审查承担。

## 模型消费准备：哪些内容直接帮助答题

新装配实际文本 **7987B**，旧v1 **6523B**，新多1464B（约22.44%）；旧结果没有完成共同业务答案，不能因此作同质量传输胜负判断。

按真实文本substring提取三份support_evidence，值分别436/430/441B，合计 **1307B，占16.3641%**；连字段名和冒号为455/449/460B，合计 **1364B，占17.0778%**，此口径不含外围逗号。新控制对应223B值/242B字段，占6.66%/7.22%。不是用重新缩排后的字节估计。

模型直接回答当前问题可使用：binding.objects的名字与ID映射、每对spatial_relation的measured/separated、certificate与geometry_scope、separation_gap或surface distance、summary完整性与nearest IDs；需要解释位置时用nearest_witness。4mm阈值来自任务，数值比较即可；不能把proof中的整数投影差当米距离。

origin有理数、factor、大整数primitive_direction、支持极值及source indices用于机器独立复核，对这道间隙/最近问答没有直接贡献，是明确的证明展开成本；但它们不是无价值证据。当前未测这些字段是否使模型更慢、更准确或更不信任。没有删除字段、修改回包或新增消费者实验。

建议下一步按当前版本进入固定N/P消费者对照，保留范围说明、状态完整性和原始回包；把证明展开是否干扰消费作为观察项。无需为17%的文本比例先开启另一轮格式/内核优化。这里的G508是反复使用的工程熟悉样本，应明确记录，不能声称未见任务泛化。模型token、费用、完整调用轮次和最终回答质量仍未测。

## 失败历史

旧M3失败、Competing退步及准备时间勘误保持。作者保存排名脚本曾把三元exact-rank误作二元Fraction，TypeError、旧脚本和失败记录保留；更正只重读已保存数据，没有替换60个性能样本。

本复核RUN01在末尾读取FORMAL_PROCESS时误沿用上一批elapsed_ms字段，当前原件实际使用elapsed_ns；该解析器错误和原日志保留，按原件单位修正后RUN02全部通过。没有重跑产品取更好的结果。独立产物见同目录audit_saved.py、RESULTS.json、CHECKS.json、SOURCES.json、RUN02.txt。
