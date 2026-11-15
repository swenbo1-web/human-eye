# 相机可靠性固定入口与来源记录

本批最多10次 owned Blender 启动、36次 raster。资产 builder占1次启动，旧新两版乘3个输入占6次，余下3次仅用于恢复。所有真实启动由根执行，准备代理只进行文件和语法检查。

固定基线是 `03eb4e2971891dfe0160972cbcf974e3dcf1a21c`。旧安装仍为 `D:/he_m4_target_001/A/product`，原作者树、安装、失败和清理拒绝历史均保留。新运行根为 `D:/he_m4_camera_001`。

## 冻结资产

fixtures/INPUT_PLAN.json 固定反例与probe源码的SHA、局部顶点、完整矩阵、两面绕序、共同原点、旧外围负例、公共期限及四步请求。camera_reachable.json没有独立faces字段，绕序取固定probe中的字面量 `[[0,2,1],[0,3,2]]`。

一个独占 builder先创建extreme，逐值读回evaluated局部点、矩阵和三角面。随后用实际读回数据按原宿主scalar forward次序取得量化后的world点，减共同原点，将这些差值存入origin的binary32局部点。保存前后检查量化尺寸保持，未替换成理想0.0001。与旧离线world的差异单独记录。

peripheral从关闭的旧运行根字节复制，SHA及已绑定geometry文件沿原件核对。它继续是遮挡负例。原文件不打开或另存。

## 每槽固定四步

每槽fresh owned Blender、fresh MCP。OLD与NEW使用同一资产和请求参数。

1. `active_observation`单目标，include_image=true，response_detail=full。
2. ping，检验主结果之后通道可用。
3. task单目标aabb，include_image=false，实际读取同宿主world网格。
4. ping，检验读回之后通道可用。

公共request_budget与Blender timeout固定为30秒，来源配置及SHA写入INPUT_PLAN。owned lifecycle最多600秒，公共请求期限持续保持原值。

主业务窗口仅为第一条请求完整读到至原stdout flush完成。完整会话包括启动、全部四步、预算结算和持有进程清理。后续task读取、两个ping及事后静态核验单列计时，嵌套子段不相加。本批不执行效能准入矩阵。

## 真实来源读回

普通安装的LiveSpatialService和标准MCPserver沿既有输入输出流接线执行。capture、相机和renderer均使用安装实现。I/O审计转发原输出文本，只记时界、原文本编码口径与预算，不替换算法。

NativeSession保存原TCP源码载荷、请求与回包。postrun静态展开真实resource和变换，先核同槽对象实例、固定local/矩阵/面序，再作资产owner对应。主目标的实际返回捕获保存为MAIN_CAPTURE，后续task捕获保存为READBACK_CAPTURE，均记录原命令和wire摘要。

numeric提前失败时，MAIN_CAPTURE可以缺失。此时保留实际错误及之后的READBACK_CAPTURE，后者只证明后来同宿主求值，不能改写成失败时已交付的geometry。实际source_frame、resource revision与实例分别保留。

## Producer图片与NPZ回执

第一次主观察直接选择现有full交付，原MCP文本中的frames包含producer生成时的arrays_sha256、图片摘要、frame_identity、host_binding_sha256、owner/patch身份及字节数。原回复、PUBLIC文本和本次文件分别保存，读取时逐字节核producer摘要。没有第二次observe或重栅格化来凑回执。

full投影没有frame.pose及完整数组metadata。pose继续从同次真实capture的camera_plan核对，并与candidate/camera身份绑定。上一批brief缺少producer NPZ摘要的限制保持原状态。

I/O输出审计明确使用RX_text_UTF8_LF字段。Windows stdout可能将末尾LF转换为CRLF，实际wire长度和摘要取原始StdioClient RX.bin与RECEIPT。输入TX读取原字节。

## 数值不足与持久预算

精确受信token为 `active_observation_target_camera_numeric_insufficient`。NEW extreme返回status=unknown、observation_status=numeric_insufficient、observation_mode=active_observation及isError=true时，记录预期unknown，保留原error合同。它与恢复为完整见证分开。普通origin及旧遮挡控制收到该异常时仍由质量验收判定退化。

每个图像请求最多预留6次。成功或已结束的raster失败按原render-attempt事件结算。对camera提前失败，先钉实际安装host源码，检查该token的字面量均位于host camera构造函数，再结合完整精确typed错误回包和零render-attempt事件，可确认实际构造为0。证据不足时保留预留上界。预留量、已确认actual与未知upper分别记录，构造后失败不退回次数。

预算的启动与结算采用本批独立claim/settlement目录。旧A01附加runtime退出证明继续unknown，新实例无法补证旧进程。旧缓存删除被平台拒绝的事实保留，没有替代删除。新批复制只取源文件，旧缓存不作为依赖。

## 资格边界

三类输入是extreme、同量化origin及原peripheral，旧新各执行一次。独立数值、相机求值与像素验收由质量模块处理。harness的passed仅指来源、期望结果分类、传输和生命周期检查完成，完整目标覆盖仍需独立检查。

本批只有一项相机正确性修复，无B选择性采集实现。模型及付费调用为0。微测与完整MCP成本保持各自口径，完整见证恢复、数值不足和普通控制结果分别报告。
