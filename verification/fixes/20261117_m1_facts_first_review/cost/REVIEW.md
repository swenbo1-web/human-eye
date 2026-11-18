# M1-FACTS-FIRST001 身份与完整成本独立复核

2026-11-17。固定作者提交544cf4f123c35fbca24b8f425acc30fd3308b178。独立保存字节检查通过4962项，失败检查0项。原九门验收0/3、每例8/9的记录继续保留。内容评分与题面单位义务的裁定由根的质量复核负责。

本轮运行自己的 recompute.py，读取固定Git、wheel、安装与原始RPC、时钟、模型公开事件及归档原件。作者checker和产品执行次数均为0。新增Blender、MCP、raster、PNG／NPZ编码、模型与付费调用均为0。作者目录、安装、原资产和runtime按只读处理，独立输出仅写本cost目录。

## 固定身份和完整原件

- namespace包含1010个Git路径，其中1009项列入CONTENT_MANIFEST，另1项为manifest本身。完整基线到作者提交差分为1011个路径，另含human_eye_plugin/live_spatial_mcp.py这一产品文件。逐件比较清单长度、SHA、当前字节和固定Git blob。
- OLD、A、B均为143份源。OLD到A、A到B的源清单差异都仅为live_spatial_mcp.py。A为be28a9cbc1311580e75c3c8d7f0f084967f0207c／e24e116434b814efb2f6e75adf098eeaadb16bb648b7a3d48c5cd16dd724e2ea，B为08a5f3b29283270c97b6d9d6e217bbee6ca7bfc1／0d75c8f7f3522c4c7f2a5807f51f86fc4f2bec49efa9a215bf090775787ab91b。
- OLD、A、B的安装143源均与各自Git及完整聚合清单匹配。A／B完整wheel RECORD逐项通过，wheel中的源与各自安装字节一致。B到最终作者提交的产品差分为0。原5项直接绑定均重新哈希匹配。
- runtime实际集合恰为913份原件，合计26,826,163B。913份共享副本全部逐字节一致，投影文件数0。ZIP成员清单、长度和摘要逐件匹配。三个消费者ZIP还逐成员匹配当前对应原始文件，公开工具、原图、usage和最终回答均保持原件身份。
- 原始stdout先扫描事件类型，私有reasoning／analysis正文按词法跳过并仅生成哈希。三个实际模型流观察到的私有事件数为0，正文解码和输出为0。PNG解码只核原字节、SHA和512×512尺寸，图片编码0。
- CACHE_CLEANUP的deleted为空，runtime_files_deleted为0。独立复核删除文件0个。

## 运行冻结与三消费者身份

FROZEN在消费者启动前固定363个直接输入。14个声明执行源全部明确属于该集合，当前长度／SHA与冻结一致。三个实际ADAPTER_PROOF的14项执行源列表均与冻结相同。原run_slot在导入adapter前逐项重新哈希direct_inputs。产品A／B源、原题面、原工具说明、三份原九门评分材料及可执行文件均保持对应冻结身份。

CLI固定0.152.1，每个argv均为fresh ephemeral exec，expected_thread_id为null，三个实际thread_id互异。请求gpt-6.1-sol、medium、default，实际工具RPC的_meta也记录相同model、medium与对应thread。provider内部最终解析后的服务字段继续未暴露。

三例按原S1、S2、S3串行运行，各1次read_observation与1幅原生PNG，完成状态均为completed。实际owner回包、MCP内容与CLI完成事件均等于冻结投影，错误与unexpected_tool_deviations均为空。每例全部CLI工具完成数为1，处于原4次上限。新三例的空discovery实际调用数为0。

实交文本分别为9964、9991、9987B，合计29,942B。实际PNG合计28,510B，逐例与历史DISPLAY原字节一致。新旧几何事实和图片沿原采集身份引用，消费对象为历史观测的新投影。当前宿主采集与完整任务仍需相应验收。

原450秒任务期限及600秒生命周期均由各自slot开始时刻形成，CLI、读取器、结果与发布携带同一原期限。三答、关闭、结果和发布时戳均在450秒内。三答封存后才进入作者评分的单调时钟窗口，评分文件继续绑定原封存与原规则。

## A／B成本原件与计量单位

基准合同先于实际基准开始，预登记每例5对，每窗口20次，顺序AB、BA、AB、BA、AB。独立重读63份RPC的TX、RX、响应与receipt，核对原ID、原时钟、长度和SHA。实际安装formatter返回的源摘要和import_path分别匹配OLD、A、B安装。

每对原响应的文本与native_images一致，A／B默认export完整content一致，OLD／A／B的full export完整content一致。输入未修改的运行字段保留。每个计时窗口的elapsed_ns为20次_tool_result调用区间的累计，window_elapsed_ns另包含循环比较等工作。独立核每对原值及中位数如下。

| 输入 | A的20次窗口中位数 毫秒 | B的20次窗口中位数 毫秒 | 格式化区间减少 |
| --- | ---: | ---: | ---: |
| S1 | 101.4426 | 10.1387 | 90.0054809% |
| S2 | 97.5376 | 8.6502 | 91.1314201% |
| S3 | 96.5967 | 8.7449 | 90.9469992% |

三例的五个B窗口均快于配对A窗口。表格的统计单位为20次调用累计窗口，单次调用分布未单独记录。该区间覆盖实际formatter及其原PNG读取、校验、base64和JSON处理。worker启动、stdio传输、等价性检查及guard另计入完整基准窗口。

639次实际formatter调用的分类如下。

| 分类 | formatter次数 |
| --- | ---: |
| 定时窗口 | 600 |
| 预热 | 12 |
| 默认export | 6 |
| OLD／A／B full export | 9 |
| profile单独探查 | 6 |
| memory单独探查 | 6 |
| 合计 | 639 |

30个定时RPC构成3×5×2个窗口。全部639次调用的formatter区间合计1.8033185秒，其中600次计时调用合计1.6073747秒。实际完整基准至三个worker关闭后发布时戳为4.5528778秒。上述区间为嵌套口径。

## 复制与内存的测量范围

profile调用单独替换formatter局部mcp.copy和mcp.json入口。计数器记录进入该入口的顶层deepcopy调用，以及这些参数的JSON UTF-8总量。std_copy.deepcopy内部递归对象复制由原标准库完成。定时窗口的profile计数器为0且tracemalloc未启动。

| 输入 | A顶层deepcopy | B顶层deepcopy | A参数JSON B | B参数JSON B | formatter JSON编码 A／B |
| --- | ---: | ---: | ---: | ---: | ---: |
| S1 | 37 | 1 | 185811 | 9964 | 1／1 |
| S2 | 37 | 1 | 185831 | 9991 | 1／1 |
| S3 | 37 | 1 | 185843 | 9987 | 1／1 |

参数JSON字节度量调用参数体积，重复或重叠参数也按实际入口累计。Python物理分配量及完整进程RSS另有测量范围。单次memory探查的tracemalloc当前／峰值原件已与原RPC逐项比较。

| 输入 | A 当前／峰值 B | B 当前／峰值 B |
| --- | ---: | ---: |
| S1 | 65146／861472 | 51282／119805 |
| S2 | 34721／860904 | 20801／50960 |
| S3 | 34697／860904 | 20777／50960 |

memory为每例每候选一次独立探查，完整任务内存和宿主进程峰值仍待测。639次formatter调用的原图片构造、PNG／NPZ编码与raster均为0，worker中相应入口绑定了失败哨兵，原响应均成功。

## 实际进程退出与原unknown

| 输入 | CLI PID／退出码 | 读取器PID／保留句柄退出码 |
| --- | --- | --- |
| S1 | 31224／0 | 23124／1 |
| S2 | 23840／0 | 21268／1 |
| S3 | 28296／0 | 19900／1 |

三个CLI均reaped，reader线程停止，管道和进程句柄关闭，kill_requested为false。实际读取器具有创建时间与父进程绑定，并由保留句柄确认exit1、关闭。三个normal EXIT收据依然缺失，其confirmed=null、receipt_status=unknown及缺失数1原样保留，exit1原因未观测。

三个基准formatter worker均确认退出0，reader、管道及句柄关闭，forced_kill为false。另核5个纯协议进程的原关闭文件与报告。4个正常检查退出0，1个预登记的过期期限控制退出1，response_count=0、normal_exit=false、closure.confirmed=false，reader、管道及句柄均关闭。该预期错误及原EOF字段继续保留。

源码与隔离B各9项回归的保存报告及日志SHA匹配，失败／错误数组为空，PNG／NPZ编码、求解与raster guard计数为0。本轮只核原件，新增回归运行0次。

## 三次消费与准备的完整成本

| 输入 | slot开始至closed 秒 | 含发布时戳 秒 | 提交题面至最终答 秒 |
| --- | ---: | ---: | ---: |
| S1 | 48.1081297 | 48.1104678 | 39.6884545 |
| S2 | 39.9294881 | 39.9323469 | 35.4687357 |
| S3 | 39.5091932 | 39.5118148 | 35.0346146 |
| 合计 | 127.5468110 | 127.5546295 | 110.1918048 |

原报告127.554630秒由三个slot开始至各自SLOT_PUBLICATION.published_ns求和得到。外层slot closed窗口合计127.5468110秒，后续结果保存至发布时戳共7.8185毫秒。最后一份发布文件自身写入完成没有单独端点。

consumer的cleanup_end窗口合计126.7286677秒，延长至CONSUMER记录关闭合计126.7316245秒，后者对应作者runtime审核的full_consumer口径。两者均位于slot窗口内。

| 记录窗口 | 秒 |
| --- | ---: |
| 总准备 | 840.6745890 |
| 其中build A | 4.9052256 |
| 其中build B | 4.4545976 |
| 其中协议预检 | 1.2421574 |
| 其中客户端预算重建 | 0.0369823 |
| 其中基准含关闭发布 | 4.5528778 |
| 其中源码回归 | 0.0961529 |
| 其中安装回归 | 0.1356539 |
| 准备开始至final audit端点 | 1698.9177140 |
| 其中closeout envelope | 354.9605575 |
| 其中最终seal审计 | 5.5531583 |

准备总窗包含实现期间墙钟与各个子阶段。最终1698.917714秒的范围覆盖准备、三消费者、阶段间隔及收口。354.960558秒是其中的closeout窗口。各项具有嵌套关系，RESULT按原范围分别保存。

作者评分脚本的已测窗口为0.0019064秒，范围覆盖已有判断的报告构造过程，结束时戳位于评分文件写入之前。人工评分阅读／判断工时、独立内容审核耗时、准备记录前的计划阅读、人工编写独立工作量、final manifest写入与Git验证／发布、管理员复核成本均缺完整分段计量。当前复核新增模型协调成本也未暴露。

原始turn.completed合计input 42,661、cached input 9,728、cache write 0、output 4,213、reasoning output 0。全部匹配原stdout公开事件及CONSUMER记录。reasoning数值字段单列。图像token、费用、provider请求次数、provider内部实际输入／视觉消费与最终effort仍未测。

本轮A／B约90%收益适用于已登记formatter窗口。历史旧批的未交付／事实遗漏与新批的题面单位门限具有各自质量结果，完整任务时间收益仍需相同质量条件的对应实验。

## 独立复核过程与覆盖

首次元数据探索假设RPC目录存在REQUEST.json，实际该schema使用TX.bin，产生FileNotFoundError。原错误保存在READER_ATTEMPT_001.json，后续reader读取并验证原TX／RX。首个完整checker通过4874项，补充协议控制、独立内存原件及消费者ZIP成员核查后最终通过4962项。完整checker未出现失败判据，私有正文输出0次。

复核沿自身AL上下文恢复。历史assignment仍为current=false／write740，父当前任务985fb28e-857e-4221-9af6-ae5645c1d873、rev1／write751可见。本轮按本次明确委派范围执行，父任务写入0次。发布版省略会话句柄。

本轮通过项为保存证据的身份、原分母、计数、窗口算术与已记录退出。产品内容保真和任务质量由根的其他独立复核接续裁定。原九门0/3、协议过期控制exit1及三个正常EXIT未知保持原证据状态。
