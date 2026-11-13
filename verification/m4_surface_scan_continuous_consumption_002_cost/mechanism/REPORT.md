# 002 工具、传输与复用机制账目

离线复算 6 集、18 轮，396 项一致性检查通过。312 个读取输入均记录绝对路径及 SHA256，并核对结束时字节。质量依据为已固定的根 QUALITY_SEAL，SHA256 为 `ccea554353a6f0607263124d2170ef3b2094a07e222c86276f522184b7f5316c`。新增模型、Blender、产品及 API 调用均为 0。

## 实际字节与工具

| 本批合计 | N | C |
| --- | ---: | ---: |
| 工具尝试 | 19 native | 9 observe |
| 工具错误 | 0 | 0 |
| owner 编码响应字节 | 63,239 | 77,820 |
| CLI 可见业务 text UTF8 字节 | 60,398 | 71,202 |
| 业务 host 请求字节 | 37,856 | 301,215 |
| 业务 host 响应字节 | 60,417 | 1,036,542 |
| 最终答案 UTF8 字节 | 27,350 | 26,828 |

C 的 native 回退尝试为 0。十八轮输入图像、工具图像及其解码字节均为 0。host 字节取实际 REQUEST.bin/RESPONSE.bin，业务请求按实际 owner 尝试时界分配。每集另有 6 个行政 host 请求，完整保留快照、登记 EDIT 与 close 的字节。

CLI 正文计量取真实完成事件中的 text 字段，与 owner content 逐值对应。provider 最终序列化输入字节、协议额外开销继续 unknown。host stdout 单列原返回 UTF8 字节，包含实际注册 framing。C 的 scene-delta JSON 和资源数组另列。N 的进程内网格采集内存字节未测。

## 本次 C 的实际机制

C1、C2、C3 的本批 audit、逐 pair 缓存记录、WIRE 和 worker 观测均给出下表。

| 每集每轮 | BASE | REPEAT | EDIT |
| --- | ---: | ---: | ---: |
| 新 kernel 调用 | 112 | 0 | 10 |
| 结果整表缓存命中 | false | true | false |
| 单 pair 缓存命中 | 0 | 0 | 104 |
| 新建局部资源 | 24 | 0 | 0 |
| world transform 更新 | 24 | 0 | 1 |
| 更新的世界顶点 | 530 | 0 | 8 |
| 传输局部资源数组个数 | 24 | 0 | 0 |

每集自身的 resident instance 和 24 个 live resource ID 跨三轮保持对应，revision 为 1、1、2。EDIT 的 114 个候选中，104 个保留同一依赖并命中缓存，8 个既有 pair 的依赖改变，另有 2 个新增候选，合计发生 10 次新计算。改变或新增的这 10 个 pair 均涉及登记对象 Obj_008。数值均由 002 原件重新取得。

缓存内部 `accounted_bytes` 为 181,984、181,984、198,307，口径是不可变载荷与条目额度核算。实际几何缓存 RAM、临时内存和完整服务成本继续 unknown。trace 的 process-lifetime peak RSS 保留原口径。缓存自报的 avoided-compute 估计保持其原字段含义，完整任务收益由总账另判。

## N 的实际复用路径

N1 后续调用已有 `triangle_surface_distance`，N2 调用 `surface_distance`，N3 调用 `tri_pair_distances`。六个后续轮的实际成功脚本均重新获取当前 evaluated 网格、当前三角形和世界坐标，再执行距离计算路径。N1 使用 `evaluated_get` 后的 `.data`，N2/N3 使用 `to_mesh`。原生底层动态 kernel 次数没有计数器，保持 unknown。AST 指标标明为语法调用位置。

## 复算与保留项

`MECHANISM.json` 同时提供 `episodes` 和十八个带 `cell/turn_index` 的 `turns`，可直接连接总账。所有读取输入见其中 `inputs_sha256`。

```text
-I -B -X utf8 verification/m4_surface_scan_continuous_consumption_002_cost/mechanism/build_mechanism.py --output verification/m4_surface_scan_continuous_consumption_002_cost/mechanism/ROOT_RECHECK.json
```

输出使用新文件名。早期检查曾直接解析带 framing 的 stdout，后已按明确协议前缀读取。初稿把 N1 的当前采集摘要限定为 to_mesh，复查实际 `.data` 路径后已修正，初稿源码、395 项结果及问题记录保存在 `attempts/01/`。旧原件摘要始终保持。十八 thin EXIT 未知继续沿根 seal 保留。
