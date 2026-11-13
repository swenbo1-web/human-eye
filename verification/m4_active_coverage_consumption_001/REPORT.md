# M4 主动覆盖真实消费 001

## 本轮判定

唯一正式批已完成，六个 fresh Pro 会话、六个用户轮次，次序为 N1、P1、P2、N2、N3、P3。原始执行保持 4 completed、2 failed、0 not_run。

六份答案的目标发现、完整观察、真实像素及有限相机池内的未覆盖原因均正确。作者与独立审查分别核验了全部本轮图像与原始数组，84 个明确像素标量、18 个明确遮挡对象声明全部匹配。每份答案均找到六个目标，为五个目标给出有效证据，并将第六个目标的未知范围限定于当前相机池。

冻结的完整验收为 N 1/3、P 3/3，只有 N2/P2 同时通过。三对完整质量门尚未满足，主配对比值、中位数和性能胜负保持未判定。全部失败槽耗时与消耗保留在总账。

## 固定版本与范围

准备 Git 为 `28105d629416cbfe8e15e7414ea008a08e74a269`。FROZEN 的 SHA256 为 `e9c7fe18cd047c3c2a3f0d94905efaa48d8e8d6b3f2c3fb88fa2535c2f645f83`，176 项执行来源在正式批前后保持一致。准备清单覆盖 224 项原件，SHA256 为 `4c2f7b1d2fc548e0852d5cdce1f0493b7d5d78ed02c48f7175a2d4a57b647a12`。

本批新增内容位于独立 verification 目录。共用既有固定产品的 138 项源码、001 几何 core 和 adapter，以及003完整几何与六相机。产品默认安装与原资产保持原版本。

两路共用完整几何、相机、NumPy/Fraction、持久 Python、scratch、批量渲染、同一次调用附图、原始 RGB/owner/depth 和每视角缓存。P 增加在线主动覆盖入口，首次计算索引、按实际像素反馈推进。模型自主选择使用方法。N 三次均选择六视图及数组计算，CLI 收图为0；P 三次均由冻结链生成两图，CLI 每次实收两图。评分接受任意正确视图组合。

每槽原绝对期限450秒，最多12次工具、六次独立视角光栅尝试。CLI0.152.1，请求 gpt-6.1-sol、medium、default，使用原ChatGPT登录。原始 fallback 警告保留，服务端实际 resolved model 与 effort 仍未暴露。

## 六槽原始结果

| 槽位 | 完整验收 | 工具 | 光栅 | CLI收图 | 完整耗时秒 | input | cached input | output |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| N1 | 失败 | 5 | 6 | 0 | 117.837713 | 87227 | 69376 | 4030 |
| P1 | 通过 | 1 | 2 | 2 | 27.800320 | 13032 | 5760 | 630 |
| P2 | 通过 | 1 | 2 | 2 | 32.576324 | 13033 | 5760 | 528 |
| N2 | 通过 | 3 | 6 | 0 | 74.171378 | 43475 | 19072 | 2362 |
| N3 | 失败 | 4 | 6 | 0 | 116.009873 | 58578 | 44672 | 2685 |
| P3 | 通过 | 1 | 2 | 2 | 30.399516 | 13032 | 5760 | 542 |

完整槽位时间覆盖启动前检查、actor与CLI启动、实际工具执行、已持有的stdio运行时退出、CLI/actor退出、原件归档、结果回读和发布。每槽都在原450秒内结束。六槽顺序函数窗口为398.802719秒。准备marker至正式启动marker的已标记墙钟为1188.2133543秒，其中至PREPARATION中间checkpoint为1031.0724541秒。marker之前的编辑与上下文处理未测。controller初始导入、首次全源检查的独立耗时，以及实现和审查模型用量继续保留未测。

## 两个失败的原因

N1第3次工具调用产生原生代码 SyntaxError，模型随后恢复。owner 保留 isError=true 及951字节错误正文，CLI 使用 item.status=failed、error=null，result 包含相同 content 与 structured_content=null。成功响应专用兼容函数拒绝这一错误包络，造成业务原件绑定失败。正文逐项一致。

N3第2次调用的 ValueError 发生同一包络问题，错误正文1201字节保持一致。该槽还实际出现一次顶层流断开、响应体解码错误和 CLI 自动重连记录。后续最终回答已保存，严格失败状态保留。只修包络仍不足以让该槽满足原准入。

准备检查遗漏了实际 CLI 错误响应投影这一边界。本轮源码与评分保持冻结，作者未重跑、替换或追溯提升失败槽。六个会话以外新增正式会话为0。CLI 内部观察到一次自动重连，provider内部请求次数及中断前usage覆盖范围保留未知。

## 准备修正和生命周期

49项本地检查通过，覆盖单调图片构造账本、当前成功门、错误分类、两种实际Windows stdio生命周期、共享渲染和评分控制。四次准备新光栅的PNG、数组及像素计数与冻结基线一致。一次离线核对命令因旧bootstrap不接收stdin目标而在导入评分器前失败，修正命令后核对完成，该次新增光栅和模型调用为0。

六个真实stdio运行时均在首次可读STARTED后绑定一次只读句柄，核对实际base镜像SHA、创建时间及到持有CLI句柄的有界父链。全部CLI、actor与stdio实际退出并关闭持有句柄。六个stdio EXIT文件均缺失，EOF与退出触发原因继续记unknown。OS实际退出已获证据，实际运行终态unknown为0。原始stdout字节流与解析事件分别保留，627项ZIP原件成员已重新核验。

## 消耗总账

N三个槽实际占用308.018964秒、12次工具、18次光栅，CLI回报 input+output 合计198357。P三个槽实际占用90.776159秒、3次工具、6次光栅，CLI回报 input+output 合计40797。这些原始总量包含全部失败槽，正式比较门继续保持未通过。

正式构造、服务器发送和CLI接收均为6个图片块，20850字节PNG、27804个base64字符。准备阶段另有8个图片构造，其中4个来自既有PNG故障控制，4个来自新渲染。准备网络发送图片为0。本批合计14次图片构造，交付口径与光栅口径分别计数。

正式光栅24次，加准备4次，本批28次，分别满足36、6与42上限。旧002/003的64次保留独立历史账本。新增Blender运行与付费API路线调用为0，Pro用量按实际CLI回报保留。数组载荷与RSS、模型图片输入分别记录。

已记录的owner工具跨度约0.21至0.68秒，CLI启动至最终回答约21.45至111.66秒。最大观测损失窗口位于CLI和模型交互链的工具跨度之外。该窗口同时含客户端、网络和provider处理，细分耗时尚未暴露。几何计算的局部耗时已单列，完整任务耗时覆盖上述窗口。

现金费用、图像token、provider内部轮数、resolved模型与effort、N3中断用量覆盖、controller初始bootstrap和实现审查工作成本保留未测。

## 管理员复核入口

作者与独立质量、成本和错误包络报告分别保存。最终交付清单由CONTENT_MANIFEST固定。管理员重点核验冻结门下的失败判定、错误响应内容与投影、N3重连用量范围以及同版完整计量。后续任务由管理员依据本批原件决定。

独立成本复核1944项通过。作者与独立核对的六份评分、分组完整时间、工具与光栅、usage、stdio/TCP及raw stdout总量一致。

[独立质量审查](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_coverage_consumption_001/review/QUALITY_REVIEW.md)

[独立成本复核](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_coverage_consumption_001/review/COST_INDEPENDENT.md)

[错误响应与终态复核](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_coverage_consumption_001/review/FORMAL_ERROR_REVIEW.md)

[作者最终原件检查](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_coverage_consumption_001/FINAL_AUDIT.json)

