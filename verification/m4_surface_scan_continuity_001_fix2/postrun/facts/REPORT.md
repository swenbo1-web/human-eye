# FIX2 实际三轮事实与缓存复核

2026-11-13。固定准备提交1511af696b564a0b261b70d5f0562325daa1f2a7。只读实际新C的原件，1719项检查通过，读取38份输入。新增Blender、产品、模型、provider及API调用为零。

## 完整事实和来源

实际BASE、REPEAT、EDIT三轮分别使用原INITIAL、原INITIAL、登记EDIT回读。全部24对象、530顶点、978面以及单位逐项绑定冻结真值，本地顶点和拓扑保持，只有Obj_008完整世界矩阵改变。登记Z值为−0.000750000006519258米。

每轮保留的owner REQUEST/RESPONSE与runner原行一致，工具原文本逐字绑定body。原started_ns、ended_ns与逐轮文件相同，实际捕获事件的started_ns和started_ns+elapsed_ns完整落在各自原业务窗口内。每轮恰好一次捕获。后验资格时间独立记录，并晚于后台关闭。

复用固定独立有理真值资格函数，重读实际原始返回、audit、捕获和对应状态快照，三份重算报告均与存储报告逐字段、类型一致。每轮276对处置全部核验，FP=0、FN=0、重复匹配为0。该复核复用了既有独立真值核验器，没有新增几何求解实验。

| 轮次 | 界限排除 | 匹配 | 测得非匹配 | unknown/deferred | 新kernel | pair调用 | pair缓存命中 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BASE | 164 | 71 | 41 | 0/0 | 112 | 112 | 0 |
| REPEAT | 164 | 71 | 41 | 0/0 | 0 | 0 | 0 |
| EDIT | 162 | 72 | 42 | 0/0 | 10 | 114 | 104 |

BASE与REPEAT的完整binding相同，匹配成员及原始米值位模式相同。EDIT改变scene_revision、scene_fingerprint、directory_sha256，document_epoch、host和runtime来源保持同一代际。展示对象表均为22个匹配端点，全场24对象的分母由独立capture coverage核定。

## 真实WIRE前缀和资源

捕获序号依次为2、3、7。复核在实际原WIRE reader调用期间硬拒绝读取大于目标序号的任何payload，三轮未来payload读取次数均为零。

| 轮次 | 实际捕获历史前缀 | 本次发送资源 | 解析资源数 | 资源实际首次交付序号 |
| --- | --- | --- | --- | --- |
| BASE | 2 | 24 | 24 | 2 |
| REPEAT | 2、3 | 0 | 24 | 2 |
| EDIT | 2、3、7 | 0 | 24 | 2 |

REPEAT与EDIT引用同worker先前交付的资源，当前pose矩阵分别核对初态和登记回读。没有使用后续capture的资源证明过去状态。原完整几何投影的rich_source_metadata_verified保持false，缺少的rich逐字段来源记录继续未证，固定host静态来源检查声明单独保留。

## 实际匹配变化

EDIT新增1个匹配，退出0个匹配。

| 对象对 | BASE处置 | EDIT处置及毫米距离 |
| --- | --- | --- |
| Obj_002—Obj_008 | 界限排除，未进行精测 | 新匹配，1.4999989653006196 |
| Obj_003—Obj_008 | 界限排除，未进行精测 | 新进入窄相后非匹配，28.444248998134317 |

原匹配Obj_008—Obj_013及Obj_008—Obj_014各从0.49999915063381195毫米变为0。其他匹配成员及距离不变。不含Obj_008的253个对象对，其完整disposition逐字段保持一致。

## 缓存与实际工作量

REPEAT的result_cache_hit=true、scan_cache_hits增量为1，pair_calls和新kernel均为0。measurement_hits累计仍为0，属于完整扫描结果复用路径。

EDIT保留114个候选，104次pair缓存命中、10次新kernel。measurement_entries从112增到122，measurement_hits从0增到104，measurement_misses及computations从112增到122。条目保留不同依赖版本的结果，不能把122解释成当前窄相候选数。

| 工作量 | BASE | REPEAT | EDIT |
| --- | --- | --- | --- |
| resource_builds | 24 | 0 | 0 |
| resource_vertices_read / resource_faces_read | 530 / 978 | 0 / 0 | 0 / 0 |
| world_transforms | 24 | 0 | 1 |
| world_vertices_transformed | 530 | 0 | 8 |
| source_qualification_vertices / faces | 530 / 978 | 0 / 0 | 0 / 0 |
| source_qualification_cache_hits | 0 | 0 | 24 |
| scan_bound_tests | 276 | 0 | 276 |

完整几何仍在缓存与引擎侧，模型工具正文仍逐轮为完整紧凑表，字节数7911、7911、7912。内部少传、少读和少算分别由上述不同字段证明。

## 成本字段及边界

| 实际区间或span，毫秒 | BASE | REPEAT | EDIT |
| --- | --- | --- | --- |
| thin生命周期 | 1887.2804 | 150.8656 | 268.1085 |
| host.capture | 118.9309 | 37.0465 | 51.8699 |
| observation.surface_scan | 1646.1583 | 1.1078 | 101.8475 |

这些字段来自同一次owned工程的原始时界和嵌套trace，分别保留其范围。缓存估计estimated_compute_ms_avoided为1562.3001000130898，按原计算耗时构造，估计范围排除了lookup overhead。该诊断值独立于实际完整episode墙钟。

本批证明实际跨thin边界的三轮事实、依赖失效和内部复用，模型/provider调用为零。真实模型记忆保持、usage语义、同任务端到端质量和现金费用仍待正式连续消费对照。

verify_facts.py只读取原件并写本目录派生RESULTS.json。逐文件字节、SHA256、1719项标签、三个重建报告所用的来源、实际匹配变化和原trace字段见RESULTS.json。
