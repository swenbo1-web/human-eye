# M4 局部像素不足证据 001 独立复核

2026-11-20。接受隔离工程候选 `3aa1d1fb43ae9a8207acd17bdab8d2861720c5a6`，实际验收归档 `58920560404544bfc973463761bcd2db55acc5ff`。产品直接承接 `21e608db565cf20d21fca735f913ae780e231470`，只改 `live_spatial_mcp.py`。独立复核了 143 个 Git、wheel、安装源码字节和实际工具定义。运行源 `b06f5e85a5d7b2519a09df2d7e5aa92ec2c915e860e58979837545c2851ded0a`，wheel `a4098cb0206971d18788a884e8a35cc97301eb7359df93247a389d2bc4b24985`。产品与证据均已核对远端头。[现场报告](https://github.com/swenbo1-web/human-eye/blob/58920560404544bfc973463761bcd2db55acc5ff/verification/m4_cross_scale_pixel_evidence_001/REPORT.md)

## 证据、交付和边界

用封存 PNG 的 RGB 与 NPZ 的所有者、源面和区域三角映射分别复算四邻边界，得到 N10 全场 TOP **5,026／0**，局部 TOP **8,835／0**，两者单位均为表面像素／达到门槛的边界像素。简报只发表同一当前局部拍摄的一条结果，最少 16／4 像素、RGB 门槛 24，图像交付为 false、块索引为空。N11 全场 TOP 有 6,244／13，正面积遮挡仍阻止完整见证。N22 SCENE 1,489／546，实际唯一交付的原 PNG 为 8,514 B，逐字节吻合。三个构图的 PNG 与 NPZ 均对应现有绑定。

投影仅在有图观察的简报里附加短证据，对应当前来源、ROI、作用域、帧、视角和对象。原件经候选 formatter 重放复现公开简报 10,570 B。旧简报 10,277 B，增量 293 B，固定 CLI 预算重建保存正文和原 PNG。实际同代无图 `full` 仍为 393,750 B，命中全场索引，零新增构图和观察见证。离线有图 `full`、无图 `full`、无图简报均未引入短证据。作者记录的 10 组重放和 28 项正负控制通过。本轮独立核对原 ZIP 的 106 项与 Git 索引和现场原件逐字节一致，ZIP SHA256 `583456c1838a6fd200104fcfaf72dfa279beaf928901a5b42164b99f60415bae`。[公开简报](https://github.com/swenbo1-web/human-eye/blob/58920560404544bfc973463761bcd2db55acc5ff/verification/m4_cross_scale_pixel_evidence_001/public/BRIEF.json) · [原件索引](https://github.com/swenbo1-web/human-eye/blob/58920560404544bfc973463761bcd2db55acc5ff/verification/m4_cross_scale_pixel_evidence_001/RUNTIME_INDEX.json)

## 分段成本和下一项

唯一实际槽有两次业务、三次构图、零模型。原计时边界为启动至就绪 1.853 s，独占窗口 4.053 s，冷简报 RPC 1,715.028 ms，内含生产服务 1,658.263 ms，冷全场索引 922.574 ms。后续显式无图全量 RPC 97.397 ms，内含服务 56.610 ms。独立 formatter 九次重放的无图全量中位为约 7.15 ms。大回包的实际问题是正文超出固定 CLI 回放预算，模型端采用、复查轮次、token、服务商输入和现金费用均未测。旧正式 8/9 与错误分量计数沿原账本保留。[现场时钟](https://github.com/swenbo1-web/human-eye/blob/58920560404544bfc973463761bcd2db55acc5ff/verification/m4_cross_scale_pixel_evidence_001/checks/REVIEW_TIMING.json)

独立读取候选的封存终态数组，28 对象、416 点、744 三角、188 个支持区域。旧路径 118,143 次检查中有 109,045 次排除无正面积的屏幕包围盒交叠。一个线性临时空间的精确端点整数秩试算在现行装配终态的纯覆盖构建中位为 891.847→650.424 ms，约少 27.1%。历史同资产终态为 908.750→656.399 ms，21 对象对照为 144.709→101.511 ms。各三对交错试算的完整覆盖索引、首遮挡者和进入精确深度分支的计数完全一致。上述数值来自一次只读归因和内存试算，实际 Blender 配对尚未运行。选择[投影盒筛选](M4_CROSS_SCALE_PROJECTED_BOUNDS_001_PLAN.md)做一次独立候选，随后转向完整任务验证。
