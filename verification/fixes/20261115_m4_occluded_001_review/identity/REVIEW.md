# 根独立来源、入口与生命周期复核

本轮对作者最终提交 1f3db153d4a46363ed3e64103d495bbc5ee65864 离线复核，未发现影响该批比较结论的来源、变量控制或进程终态缺陷。新增产品、模型、Blender、raster 调用均为 0；没有执行作者验收或成本生成器。

独立脚本 check_identity.py 最终 10,381 项来源与合同断言通过；这些不是功能测试数。4,326 个不同文件只读取哈希一次，去重核查：1,125 个新命名空间路径及实际 Git blob；2,369 冻结项；128 资格封存项；4,312 质量封存项；1,026 原运行文件及其归档字节；141 产品源安装字节与产品 Git。旧保护清单也一致。结果见 RESULT.json。

当前工作树为 detached HEAD=1f3db153，干净。远端 origin 的 codex/architecture-arm-correction 已通过实际 ls-remote 确认为该最终提交；本地同名分支仍为 6e1e65c6，被旧 m4-single-pass-acquisition 工作树持有。这与显式推送 HEAD 相容，不是提交丢失。后续不能按本地分支名误取旧版本，也无需切换冻结树。

六槽按 N1/P1/P2/N2/N3/P3 运行，六个不同 CLI thread；资格只有 QN/QP 两个目录，0 模型、9 次 raster。全部构造意图序号为 1–39，前9资格、后30正式，无额外正式目录或替代槽。冻结时间早于资格，资格封存早于正式入口。各槽原始450秒期限、12次业务、6次构造、正式36与全批48配置一致。18个 owner/CLI/thin 的保存句柄终态确认成立；thin 自身 EXIT 缺失和实际退出码1继续保留，未伪装成退出码0。

实际 CLI argv 的共同配置完全一致：同模型/medium/default请求、相同登录入口、关闭 hooks/rules/记忆/附加skills，只有当前四公共工具，P多 active_observation。四公共工具 schema 逐字节等价；共享依赖、缓存和工具许可一致。已阅 bootstrap 的同份共享依赖加载及核验路径；Shapely2.1.2包字节在冻结中，三次N的实际工具代码均成功导入Shapely，旧缺库失败未重现。resolved_effort仍null，不能把请求值当提供方已证实执行值。

题面均由各自冻结前缀加同字节公共任务组成。N自主选择首入口、P指定active_observation是事前登记差异，因此该批是既定入口比较，不能声明自然选工具收益。没有要求N输出产品ROI。资格/oracle私有路径受审计隔离；六槽保存代码未引用TRUTH、PIXEL_TRUTH、QUALIFICATION、oracle或SOURCES，实际私有读写/产品未公开调用计数为0。这里只确认本批记录未显示答案泄漏，不宣称Python审计构成通用对抗沙箱证明。

已读真实launcher及原routed run_slot：复用原代码对象，slot时钟从目录/来源检查前到消费者、进程关闭、归档、来源回查和SLOT_RESULT落盘关闭；六槽原始时间字段与此合同一致。新增事实核对发生在slot时钟之后，已归入batch协调，不混进单槽。准备修复发生在有图冻结前，未见评分后修改正式答案或冻结执行字节。

首版独立检查器 R0 用浅层字典合并分别解析的 TOML -c 参数，覆盖已有features字段，报KeyError: hooks。原脚本保留为check_identity_R0.py，事件见REVIEW_EVENTS.json；改为递归合并后通过。此错误属于本轮检查器，作者及正式运行文件未修改。

下一产品修复的来源约束：FROZEN固定当前作者树的产品源码绝对路径，live_spatial_mcp.py、active_observation_host.py、live_service.py均在其中。新增候选必须使用新的隔离工作区和安装，不能在当前树改这些文件再声称旧封存不变。
