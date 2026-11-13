# 连续全场扫描002：接口修复后的正式对照

2026-11-13。cycle **M4-SURFACE-SCAN-CONTINUOUS-CONSUMPTION-002**。在b51dc02eb4f25966f983033b42dad3c9cfec9393接口修复经根独立复核通过后执行。直接完成新正式批，不再增加单独工程准备交付。

## 固定基线与本次差异

完整实验合同继续采用[001冻结计划](M4_SURFACE_SCAN_CONTINUOUS_CONSUMPTION_001_PLAN.md)，根提交ee1e11117d31708c2298893da7273f8345aa210f、文件SHA256 95a334c39672a72ac771beba0f02e6c17735771a5e0f8411203d46e2769feba5。本文件只改变批次身份、实际消费器接线和明确共享harness故障的停止行为；题面、场景、模型设置、预算、评分与收益门不变。如有冲突，仅上述三个差异以本文件为准。

原001交付11f944e71bc530822e8741384732529003efc29f及质量seal 7f90243826c1a113d0365282517899902cc9aa2f1b163b67c43d6c644d2a51c6继续封存：6首轮内容正确，但执行6failed、12not_run、resume0。不回改，不拼接旧首轮与新后两轮。旧失败成本账本单列，不算作002新增消耗，也不从项目总投入中删除。

产品仍为452b44d2dcf231d6675bef54e568db0431a29261、138源4067c864c3db1ba586cd7179e6430db5acc4d71675b5295416d471632851a9f6、隔离9.7.2+m4.surface.scan.compact.r1。CLI仍0.152.1及SHA256 01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6。请求gpt-6.1-sol／medium／default tier，同一Pro接点；不切其他provider，不改工具描述或产品输出。

新批实际使用已审接口修复的runtime/episode.py、runtime/consumer_transport.py和compatibility.py，分别固定SHA256：

- episode：e3bef0c338e6f6078e74a64a2b3fd5fc6ea92de0f34ade94410d7b9a10768757。
- transport：675d0d855635a3586fd60f90c73a70d0bf0968e2b8bf193d2446e77fc5849a5f。
- compatibility：ad41521eccb2be5e61ca24d37e7e985128267cf959d818a1dd87cd84545d30c4。

保留旧exact回执匹配与既有工具错误处理；仅在两表示原不相等时用新增成功兼容。不得在002临时放宽其他字段、删除错误或修改已审谓词。旧FIX1 actor、worker、原始consumer循环及协调器通过已审globals绑定复用，实际正式入口必须指向新wrapper，不能测试新函数后仍执行旧路径。

## 六个全新episode，最多十八轮

固定串行顺序 **N1、C1、C2、N2、N3、C3**，N/C按数字配对。新建六个模型线程、owned实例和工作目录；不要复用001或工程实例。每个episode内部的BASE／REPEAT／EDIT维持同一个实际模型UUID、工作目录、原生宿主脚本/缓存；C另保留产品session/runtime。原生批量计算、NumPy/BVH、缓存与C原生回退均照常可用，不预置解答、不清N缓存。

沿同一BASE资产7f6452d1…5ad66、BASE/EDIT真值a0f14b1a…656c7／ccbc66e4…b1e91。T1题面SHA256 6a78e38a474647c0c0c49558be215864cb672932273b3e15ca6ba7f9fa02b4fc；T2与T3同用435字节重查题面1556e86013d52b1ca222237f6e5df33d389d33e95c8e3df3bd218edb4e5549d6。不给变化提示。第二轮不改场景，第三轮前由原actor单次执行登记Obj_008 Z−0.00075 m及回读。零图像，其他隔离配置沿001。

每episode原绝对590秒，从输入检查和owner启动前到关闭、后验、完整原件归档及结果写关；每轮450秒截到原episode期限。启动40秒、工具30秒、episode累计32工具尝试／128宿主非close请求／1 MiB正文响应，单执行代码256 KiB。不得按轮重新发放累计预算。错误、自纠及回退计入实际记录；不延时、替补或加样本。

## 最小接线与停止

新材料放verification/m4_surface_scan_continuous_consumption_002/，采用全新短运行根（例如.m4cc2），不复用或覆盖.m4cc1。沿001外层driver、匿名投影与源绑定，改当前批次常量、输入/输出位置、匿名映射和已审coordinator/transport引用；修正前后字节摘要冻结。归档复用已审幂等Windows路径处理，不重新复制深目录导致路径超长。

根已发现一个必须在本次接线处理的明确模块接口差异：新episode wrapper只导出run_episode等字段，没有pack；旧driver在结束归档时使用coordinator.pack.capture_cell。002应显式复用coordinator.legacy.pack这一同字节既有packer，不能只替换模块路径。无需改已冻修复，也无需新归档层。

把已审review/stop_recommendation.py的窄条件接入外层现有stop_reasons：出现请求／结果绑定故障，且原owner明确成功、CLI也明确成功时，记shared_success_binding_fault；完成当前sole finish与原件收口后，现有run_batch将余下未启动episode列not_run并结束。原始错误、各槽和已有回答保留。该条件不能由正文答错、普通tool error或仅error=null触发，也不能重跑当前格。

现有权限／额度／服务不可用、关闭不明、执行状态未知等停止条件保留。普通内容答错与正常工具错误按原合同运行，不泛化成整批停止。一次错误的结束不代表整个用户项目被取消，实施者交回根复核具体缺口。

正式前只需必要离线检查：实际002入口加载上述三个固定文件和对应函数globals；当前目录及Git准备字段正确；同一绝对时界和实际新运行根；在新driver的真实run_one路径用无provider／无Blender依赖替身走过finish、postclose、outer archive和publish，并证明pack引用正确、完整归档及结果发布完成。此项加载实际wrapper，只替换会启动外部进程的依赖，不能再用虚构pack属性的假coordinator遮住模块接口。再用真实run_batch调度替身证明共享成功绑定故障会在唯一收尾后停止剩余槽，正常tool error控制不会走该全批停止分支。不能只验内coordinator或纯stop函数表。复用已经通过的14成功、3真实错误和进程循环证据，无变更部分不重复全矩阵，不启动模型或Blender预试。

离线接线通过后提交冻结全部执行源码、配置、题面、依赖和匿名映射，再按本派单直接启动六个正式episode，不另交“准备就绪”等待批准。真实resume首次运行属于正式样本；若失败保留，不换新上下文补考。

## 质量、usage与收益

仍先匿名质量后成本解封。十八槽固定，每轮276对真值，匹配71／71／72；完整列表、毫米精度0.000500001容差、当前状态依据和执行有效性分别评分。明确引用或完整delta只记原合同的上下文重建辅助分。实际问题已由当前版本／依赖核对支持时可以复用缓存，不强制固定工具次数。

真实模型线程续接、前轮内容保留和当前状态查证由原始事件证明，合成fixture不算。每轮保存真实usage字段；只有证据明确本轮或累计范围时才求不重叠总量。未确认则保留原值、aggregation null、token门未测；不可盲加累计终值，不为计量另开模型探测。实际费用和Pro扣账不可见继续unknown。

正式门保持：双方各3/3完整有效episode、9/9完整正确且依据充分的轮次，配对完整episode耗时中位比C/N≤0.70，C可确认input+output总量不高于N。任一条件缺失就不通过；不从更少工作或未运行轮次推算收益。总episode、逐轮及REPEAT＋EDIT分段分别报告，BASE优势不能被归因于跨轮暂留。所有准备、归档、失败和共享成本按原账本范围保留，未测不记0。

## 回报

完成或遇到明确停止条件后，提交全部原件与匿名六episode×三槽质量包，成本保持封存。主动回报root local/01a1971f-eef5-7a23-a1b1-2352beb80a77，标记 **M4-SURFACE-SCAN-CONTINUOUS-CONSUMPTION-002_QUALITY_READY**，附准备/交付commit、包和来源SHA、完成/失败/未运行分母、实际resume及停止原因。随后结束等独立复核，不自行解封成本或再开试验。

本轮仍不改默认、原资产、共享GUI、竞争分支或产品；Google/key/503/付费暂停。若无新缺陷，通过本批后结束连续题的准备和格式调优，按实际结果选择数据交付优化或进入真正的主动扫视能力任务。
