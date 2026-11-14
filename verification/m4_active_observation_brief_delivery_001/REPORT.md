# M4-ACTIVE-OBSERVATION-BRIEF-DELIVERY-001

## 交付状态

active 观察的默认输出与显式 `response_detail=brief` 已接入版本化公共事实投影，显式 `full` 保留完整诊断。本轮固定候选通过 33 项定向单测和一次已安装服务的历史传输回放，等待管理员独立复核。

实施基线为 `32a1c6eb47cfa84133d92199387339d407a33cb5`，准备提交为 `cd72d23b847456b64c24143ef2abcfbac1edbebd`，分支为 `codex/architecture-arm-correction`。上一批 Host 功能已验，brief 未生效的 P2 在本轮处理。

## 表示与语义

公共 schema 为 `active-observation-brief-v1`。完整对象映射只表达一次，ROI、无支持范围和像素事实通过零基表索引引用。列名使用完整可读字段名，宿主 ID、实例 ID、ROI ID、来源摘要、图片引用和 SHA 均保留完整值。

每个矩形样本包含全部 28 个对象、6 个 ROI、22 个无支持 ROI 的 unknown 对象、两幅实际观察图及完整 12 行 ROI/view 像素事实。可读和不可读、零表面像素和零对比边界事实均保留。16/4/24 准则在像素规则中共享，covered、unresolved、有限池未覆盖范围及原因保持。空 ROI 返回 unknown。

保留来源 revision、文档 epoch、capture 实例/epoch/revision、binding/source-binding/geometry/camera/runtime 摘要、单位、坐标与完整 capture 范围，以及 loaded generation、disk not checked 和来源检查范围。帧与事实里的重复身份别名在一致性校验后去重。

相机政策、binding schema 名、选择器缓存摘要、工作树、阶段时钟、数组及本机文件路径纳入 full 诊断。独立语义合同列明任务事实集合及这些诊断字段。完整 full 值经登记的 PNG 读取位置逆映后逐字段比较，数组路径保留原值。

版本合同明确空表和空覆盖集合的省略含义。默认投影对完整像素网格、整数索引、来源必需字段、重复、悬空及冲突引用进行检查。无法满足该表示合同时交付完整值，并在审计中记录投影状态。

## 冻结与来源

首次候选执行前已冻结公共合同、独立解码器、五份历史实际 RX、八份历史 PNG 副本、单测、回放源和运行依赖。冻结含 1223 个文件摘要，SHA256 为 `fac63d76e41d4c1778fc8302f9009e38497fc74c5cf39a7e41b4848f5b278a4e`。冻结时产品、解码器及测试函数执行次数为 0。

本轮产品只修改 `human_eye_plugin/live_spatial_mcp.py`。141 个运行源码的整体摘要为 `2a478a6290943c0daff2f9aa0b53a57a563ca61ef7a1f8d558e756c606a82688`，候选发行版本为 `9.7.2+m4.active.brief.delivery.r1`，wheel SHA256 为 `67aaa5acfa8b7009d9d3f83bab743328c7d5686208458207fd453cc57f517334`。已安装副本位于 `D:/he_brief_001/product`。

历史输入通过上一批 EXTERNAL_ARCHIVE 映射获取，输入清单 SHA256 为 `7255e98afc968e0802bf66c8bf4166014e6364cacd813cc046967b540ead5453`。独立解码器 SHA256 为 `8638ed2ea41968fd68b4e39bd5eb632dd6c7df62c80192059bdab967e7b8266c`。

## 固定数据结果

字节数按实际公共 text 的 UTF-8 统计。

| 历史案例 | 原文本 | 新 default / brief | 新 full | 默认预算 |
| --- | ---: | ---: | ---: | ---: |
| ordinary | 24549 | 6457 | 23977 | 8192 |
| same_source_repeat | 23266 | 6457 | 22734 | 8192 |
| recovery_rename_baseline | 24547 | 6457 | 24039 | 8192 |
| renamed_source | 24588 | 6468 | 24040 | 8192 |
| nonplanar_source | 4874 | 1906 | 4874 | 2048 |
| 合计 | 101824 | 27745 | 99664 | 原总量的 35% |

五例默认文本减少 74079 字节，约 72.75%，剩余比例约 27.25%。各例和合计预算均通过，质量比较先于字节判定。full 文本长度受登记的本机 PNG 读取位置搬迁影响，所有完整字段经逆映后相等。

五例属于上一批固定场景的历史响应，其中包含同源复用、更名与非平面情况。它们没有增加独立资产覆盖。

## 实际 stdio 路径

从仓库外 cwd 启动新进程，经已有源守卫加载正常已安装 MCP server、dispatcher、投影、PNG 验证、base64 与 serializer。验收目录中的 service stub 仅按固定序列注入历史完整结果，并映射登记的 image_path。

一次序列为 initialize、tools/list，随后每个案例依次 default、brief、full，共 17 次协议请求、15 次工具请求。五例 default 与显式 brief 相同，十份短表示均通过独立语义展开，五份 full 通过完整诊断比较。

24 个原生图片块逐字节等于历史块，消费者实际解码 PNG。MCP 的 consumer_read_status 继续记录 unconfirmed，消费者读取证据单独保存。历史图片合计读取和重编码 83400 字节、base64 111216 字符。17 请求 TX 为 3832 字节、RX 为 311634 字节。

响应中的历史 runtime_source_sha256 及 work/new_raster_attempts 描述原来源。回放 service 回执另列本轮实际 capture、prepare、raster、新图构造均为 0。本轮没有启动 Blender 或执行几何核心。

## 成本与进程

外层回放进程全过程为 1.3086655 s，内层控制器至清理回读为 1.2374282 s。十次投影原调用累计 1.8001 ms、十五次内容构造 32.0574 ms、十七次协议编码 11.7916 ms。投影嵌套在内容构造中，阶段不得相加为整任务耗时。透明侧录的写入费用进入外层墙钟。

各案例 default/brief/full 至消费者读完的时长已分别保存在 RESULT_SUMMARY。首个 default 为 72.1947 ms，其余矩形请求约 16.48–20.54 ms，非平面约 11.14–13.80 ms。这些时序包含首次加载、缓存与侧录影响，未进行配对性能比较。

环境准备为 10.2810632 s，build/install 整体为 3.1916929 s，33 项定向测试为 1.1665958 s。单测使用常量合成 PNG，真实 raster 和 Blender 启动均被禁止；现有 CLI help 回归产生一个 Python 子进程并退出 0。

回放 held launcher 退出 0，未强制终止，读线程、三条管道及句柄清理确认。内层 Python server 单独保留 START/FINISH、源校验及 EOF 证据。两者 PID 分列。

本轮新增正式模型实验、CLI 推理、Google/API、Blender、capture、prepare 与 raster 均为 0。模型 tokens、现金费用、视觉理解与真实任务收益仍待验证。进程 RSS 未测。

## 准备修正与证据

冻结前静态复审补齐了缺失负面行、布尔索引和来源字段缺失时的 full 出口，并收紧 PNG 路径逆映。一次 schema 默认值旧读件误判在核对当前源码后更正。工具路径通配符与尚未发布文件的读取错误保留在准备记录中。正式单测和 stdio 回放均首轮通过，单测包含预期注入的图片编码失败。

EXTERNAL_ARCHIVE 索引 183 份外部原件，共 2156934 字节。使用短文件名及逐文件原路径映射，保留全部历史输入、实际 TX/RX/stdout、投影和编码阶段、语义还原、图片、审计和清理记录。

examples/BRIEF.json 为实际普通默认 text，6457 字节。examples/REQUEST.json 保留对应请求，REFERENCES.json 指向实际两图及消费者读取记录。独立复核结果在 review，完整交付由 CONTENT_MANIFEST 固定。

## 收口范围

本轮验证了已冻结历史输入上的任务事实完整性、默认短表示、完整诊断兼容和已安装 stdio 传输。真实当前 Host 的新采集验收、模型实际消费及更广复杂资产能力需由后续批次验证。管理员依据本轮证据决定下一项。

## 终审补充

独立来源与成本审计通过 827 项核对。独立语义与传输审计对十五份既有实际工具响应各复核一次，十份短表示和五份完整诊断通过，另以五份内存副本验证缺负像素、重复图片、错误块位置、缺来源字段和悬空区域的拒绝。

语义审计曾以随更名变化的 host_id 联结名称对照，改为稳定 instance_id 后收口。另一处审计断言预期了不同错误字符串，实际缺 disk_status 已因 required_fields_missing 被正确拒绝。两个审计假设修正、原异常和细分计时缺项均写入原审计 JSON，十五份实际响应未重复解码。本轮产品及正式回放均首轮通过。

十七次 serializer 返回字符串共 311617 UTF-8 字节，Windows stdio 的十七个额外 CR 使实际 RX 为 311634 字节。全部公共文本共 155154 字节，原生图片 JSON 块共 112512 字节，PNG/base64/JSON/RPC 层分别记录。
