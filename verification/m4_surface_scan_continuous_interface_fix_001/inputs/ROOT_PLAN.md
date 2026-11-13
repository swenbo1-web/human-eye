# 连续消费接口兼容修复：唯一下一项

2026-11-13，cycle **M4-SURFACE-SCAN-CONTINUOUS-INTERFACE-FIX-001**。固定失败交付11f944e71bc530822e8741384732529003efc29f，准备a02c4230651b8134539fb4d96595998d8146c75a。只修测试消费者的CLI／owner回执比较，不改引擎、题面、几何或模型。

## 已定位的问题

六个首轮共14次工具调用，请求与业务content一致，owner为isError=false，真实CLI为status=completed、error=null，省略isError并添加structured_content=null。FIX1 archive_turn却要求整个result编码一致，全部标为CLI_result_differs_from_owner，阻断后续12轮。

fake_cli把owner.result直接复制成CLI.result，未模拟真实CLI转换，因此此前合成贯通不能覆盖这一边界。旧冷态审查已有两端包装不同的记录，未转成连续适配器的回归输入，是实施和根审核共同漏项。旧六个执行失败不得回改；离线修复回放不等于原正式批次成功或真正resume。

## 最小实现

在新命名空间verification/m4_surface_scan_continuous_interface_fix_001/实现最小差异，封存的旧源码和证据不改。沿现有消费链调用一处明确的回执比较函数，移除跨表示的整对象字节相等假设，不新建通用归一化框架。

成功兼容只针对已证明的实际形状：

- owner的RPC没有error，result.content存在，isError为明确false；CLI工具item为completed、error为null，content结构、顺序、文本逐值对应。请求的工具名及参数仍逐值绑定。
- 允许CLI省略owner的isError=false，并增加structured_content=null。也允许已核同表示完全对应的成功控制；类型必须准确，0、空字符串不能当false。
- 不忽略任意额外字段，不删除业务中的同名字段，不解析或重写content里的JSON字符串。非空structuredContent/structured_content只有明确对应且完整保真才可支持；本批未实现的形状直接标不兼容，不凭正文相同通过。
- owner isError=true、RPC error、CLI failed/error、缺失正文或请求/正文篡改均不能被这条成功兼容规则变成成功。保留原错误、final与真实动作状态，不增重试，不将回执失败改写成动作未执行。

使用已有14份真实成功原件、同一固定CLI字节的3份历史真实工具错误原件作为回放输入。具体输入索引见本次根interface报告。历史错误中owner isError=true、CLI status=failed、error=null且正文相同，必须保留失败；只比content会错误放行这个反例。

## 验收和运行范围

新增Blender、产品、模型/provider/API调用为0。用现有原件即可复现，不开provider预试，也不重新跑六个正式episode。

1. 原比较在14份实际成功上复现旧错误；新比较对这14份成功通过，请求、正文和来源绑定保持。输出明确为离线兼容回放，原正式状态不变。
2. 3份同CLI真实工具错误仍失败。补少量直接相关变体：改参数或文本、删一块正文、翻转错误位、CLI failed/error、RPC错误、非空或被篡改结构数据、字段类型不符，均保持原错误或明确不兼容。正常内容内嵌isError/structured_content等字符串不得被删改。
3. 一次现有consumer真实进程循环的零provider回放使用实际CLI形状，证明修复函数确实接入archive_turn，并且三轮协调可继续；错误回放沿原失败及后续处理规则保留三槽，不修改自纠或重试政策。可以复用既有fake进程但它必须按已录CLI结构输出，不能再次原样回显owner冒充CLI。该项只证明协调接线，不能宣称真实模型resume已测。

旧缺失thin EXIT六项继续unknown，本批不扩修生命周期或重跑宿主。固定UUID、原期限、单次finish、原件归档和分母复用已核逻辑；只对本次实际改动做定向验收，不机械重跑全部安全/安装矩阵。

下一正式批应复用现有stop_reason：出现明确的共享harness绑定／协议接线故障时结束本批，保留已运行并将剩余标not_run；答题内容错误继续既定样本。先记录一个最小分支建议及离线可复现行为，供根在新正式合同中冻结，不追溯改变001执行策略，不增加新调度层。

## 历史成本与交付

根质量seal后允许为失败001整理同原件成本账本：列六首轮实际耗时、工具尝试、可确认的原始usage及共享准备/打包成本，不给连续收益胜负，不将未运行两轮补成估算值。没有resume，不证明累计usage语义；实际费用与不可见开销继续未测。此项是同次失败的账目收口，不启动新的成本实验。

交付最小源码diff、14成功＋3真实失败的来源索引与回放、定向变体及消费循环接线结果、旧失败未修改证明、失败成本账本和准备/交付commit。主动回报root local/01a1971f-eef5-7a23-a1b1-2352beb80a77，标记 **M4-SURFACE-SCAN-CONTINUOUS-INTERFACE-FIX-001_READY**，随后结束等根独立审核。通过后根再冻结新正式连续批，不拼接001首轮与未来后两轮。

Google/key/503/付费仍暂停；默认、原资产、共享GUI、竞争分支和产品452b44d2/4067均不改。可恢复离线错误同轮修正留档，不以本计划增添其他模块。
