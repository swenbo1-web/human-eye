# M4 可消费观察001：独立成本、终态与优化出口

结论：作者披露的核心成本和终态可从原始记录复算。本审计163/163项通过，新增产品、模型、Blender、raster、benchmark执行均为0。应保留本批既定“不得重复已有视图”条件失败，同时结束以零重复为唯一目标的单题微调，转入有界、公平的完整任务对照。现有证据不足以支持为约0.246秒的重复构造再增加缓存API或刷一次真实槽。

固定作者交付 `a7632563fa8631176816100ff4bef778bdbce318`，文件根 `verification/m4_consumable_observation_001/`，原始运行根 `D:/he_consume_001/formal/P1/`。本审计只运行自写标准库离线脚本 `audit.py`，读取原始时钟、CLI事件、MCP请求响应、NPZ/PNG、账本和相关源码；未执行作者成本脚本或产品。根和其他审查者负责全量来源/安装和任务质量。

## 时间、额度与usage

|独立复算范围|秒|
|---|---:|
|父进程调用至launcher返回|141.1133463|
|launcher自身|141.0454885|
|原route|138.4381683|
|consumer|137.1918579|
|launcher包容route调用|138.4388121|
|prompt至首个产品结果到达CLI|23.0662642|
|首产品结果至最终答到达|111.1803916|
|全部工具服务|4.7090710|

四层生命周期嵌套，不相加。launcher的route包容时钟比原route多643800纳秒，分别保留。父时钟在父收据/stdout发布前关闭；launcher时钟不含自身最终timing文件发布，原route/consumer时钟覆盖其声明的结果发布。原450秒期限没有延长，真实完成在期限内。

七个工具全部进入业务，顺序是active_observation、execute_python、execute_python、render_views、execute_python、execute_python、execute_python。第五个工具保留Fraction字符串直接转float的ValueError，第六个工具同轮恢复。没有guard拒绝、额外fresh会话或外层重试。

四份durable raster intent连续为1至4，都是formal：产品SCENE/BACK/LEFT三帧、原生重复SCENE一帧。实际捕获重放1次，Blender采集0。全部四张PNG实际送到CLI，不能把第四张说成缓存命中。

原stdout仅一条turn.completed usage：input144766、cached input118528、output2616、reasoning output213、cache write0。input+output为147382；cached属于input，reasoning属于output，不能再相加。单个usage事件不等于一次provider请求，turn/session聚合语义未被证明。现金、图像token、provider请求数及实际后端配置保持未测。

## 重复与后续复核的实际成本

|事件|服务秒数|
|---|---:|
|tool2解析公开JSON并打印|0.0012327|
|tool3查询已有JSON|0.0010555|
|tool4重复SCENE构造和交付|0.2461134|
|其中真实raster调用|0.1965573|
|tool5失败的源面归属转换|0.0013779|
|tool6恢复后按产品region匹配全网格|0.0571725|
|tool7全幅SCENE像素/边界及账表|0.0206188|

tool4的服务时间占父周期约0.1744%；tool5至7合计0.0791692秒。两部分合计0.3252826秒，占父周期约0.2305%。这些比例仅说明已测服务开销的量级，不能作为删除这些操作后整体任务收益的预测。

tool2包含解析、查询、打印与调用处理，不能称纯json.loads CPU。产品scope_and_facts为2.8039毫秒；MCP投影、序列化及图片处理包容阶段12.9916毫秒，独立各项CPU未测。

首包后的111秒还包含后续模型服务、传输、客户端处理和最终回答形成。我们没有不执行tool4至7的同配置反事实，因此不能把该区间或相邻请求间隔全部算成“可以省掉的推理”。反过来，也不能据服务开销很小断言省去模型回合没有价值；它需要完整任务对照。

## 字节与缓存语义

实际v4公开text为44873 UTF8字节。上轮同场景真实v3原包独立读得42049字节，当前作者同状态离线记录也是42049，增加2824字节，约6.72%。本子审计没有重新运行旧projector；同状态投影兼容由产品审查负责。

四PNG共13109字节，实际CLI base64共17480字符。生成NPZ共123621字节。逐NPZ解包NPY头、dtype/shape与payload，累计数组20010424字节，其中四主缓冲19922944字节、三个产品映射元数据87480字节。当前产品几何数组127548字节单列。stdio TX11687字节、RX109618字节。这些是不同层或嵌套表示，不相加为独立网络传输或峰值内存。

原生重复SCENE与产品SCENE的pose、PNG、RGB、depth和object-owner相同；但产品保存的是patch_owners及patch→ROI映射，原生缓冲提供raw triangle_ids。两种owner含义不能互换。

当前公共render_views的工具说明与实现明确规定每个请求都fresh构造，包括重复请求。active_observation把已产图片登记到by_ref/by_view，但没有填入原生buffers；原生render_views无缓存分支，显式再次走raster。模型公开说要“verify the queried pixel and retain source-face evidence”，随后用已有产品regions定位各源面，再核SCENE像素。没有重新发现全部region或重算六相机遮挡。

因此，不能把现有fresh调用悄悄改成cached、将patch_owners冒作triangle_ids，或只改成本标签来满足旧验收。真正新增现有帧读取/patch拾取需要独立、明确的接口语义；当前业务只要验证既有anchor即可，不足以证明现在必须做该扩展。

## 终态与证据限制

parent、CLI、actor退出0，launcher结果成功，末端结果与时间均已发布，terminal/publication错误为空。thin由持有句柄证明exit1且handle关闭，正常EXIT回执仍缺失，EOF为unknown。不能将持有句柄退出改写为正常EOF。

同字符串桥接的独立namespace dump/hash和独立赋值CPU未测；本次实际解析和后续查询可观察，但不扩大成provider内部输入可见。fallback model metadata警告保留，不能单凭警告认定模型切换或重试。

## 建议的唯一下一项与停止标准

保持本批质量与消费采用通过、criterion3失败的原记录，不更换历史标准。阶段选择可以以净收益为目标：冻结当前候选，预登记一次有界的原生/插件完整任务对照，检验质量、实际采用、总调用、总时间和真实usage；重复视图继续列为诊断指标，不再为了一个零重复数字无限微调。

对照应给双方对称的任务契约和合理第一步：P可以明确使用其观察入口，N使用本组已有原生读取/计算入口；双方均可复用自己的证据和使用同一普通原生能力。若使用显式入口指令，结论限定“已配置入口后的能力”，不混为自发采用率。题目、来源、完成规则、模型请求设置、预算、评分先固定，样本次序平衡，失败和未知都进入分母，不中途改题或补样。

不要以旧失败239秒或历史不同配置的原生槽作为本轮成功任务收益分母。先固定这一批的停止数和质量/成本门槛；若结果没有可复核净收益，保留当前可用候选并依据真正失败决定下一项，而不是回到同题零重复循环。

本审计没有修改源码、夹具、正式部署、资产或专家线，也没有开展新的对照。输入摘要、逐项检查及所有复算值在RESULTS.json与CHECKS.json。
