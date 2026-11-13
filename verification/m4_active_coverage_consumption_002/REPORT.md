# 主动覆盖真实消费002

## 本轮判定

修正结果绑定后的唯一新批完成，六个fresh Pro会话、六个用户轮次，原次序N1、P1、P2、N2、N3、P3。六槽均完成，失败0、未运行0。作者和独立质量评分均为N 3/3、P 3/3，72个显式像素标量、18个遮挡对象声明全部正确。

固定三配对的完整耗时P/N中位数为 **0.3813707433**，对应下降 **61.8629%**。CLI回报input+output总量从N的 **183789** 到P的 **40733**，下降 **77.8371%**。同质量下，时间与公开模型用量满足预登记双指标收益条件。

结论适用于本固定六视角矩形覆盖任务的三配对小样本。实际费用、服务端内部调用数、图像token和resolved模型/effort未测，统计总体与其他资产效果继续需要各自证据。

## 相同任务和能力

geometry、CAMERAS、prompt、公共工具定义、Python/原始RGB-owner-depth数组、批量生成和同次Python附图能力、缓存、空间核心与质量规则沿用001。prompt SHA256保持a063914f32409ef33015c50751ea96a5d7646a672d5570d5eb5c725154c62583。两路使用同一完整场景和精度，P增加已验证的在线主动覆盖入口。

N自主编写空间/像素求解代码，三槽工具数为4、4、3，均生成六视角并使用数组，CLI收图0。P三槽各调用主动入口一次，在线build_index、选择视角、同一渲染器出图、真实像素反馈和状态提交，每槽两图并实际交付CLI。模型可以使用任意正确视图组合，评分没有把两图最优设为条件。

每份答案均发现六个目标，为五个提供本会话完整且可读的证据，并正确说明另一个在有限相机池内未覆盖。隐藏表面的状态仍为unknown。

## 六槽完整结果

| 槽 | 完整资格 | 工具 | 光栅 | CLI图 | 完整秒 | input | cached input | output |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| N1 | 通过 | 4 | 6 | 0 | 115.7564682 | 62123 | 46976 | 2601 |
| P1 | 通过 | 1 | 2 | 2 | 37.3657842 | 13034 | 5760 | 542 |
| P2 | 通过 | 1 | 2 | 2 | 37.0473564 | 13035 | 5760 | 536 |
| N2 | 通过 | 4 | 6 | 0 | 97.1426284 | 69453 | 51712 | 2511 |
| N3 | 通过 | 3 | 6 | 0 | 85.7759895 | 44707 | 30464 | 2394 |
| P3 | 通过 | 1 | 2 | 2 | 36.7222160 | 13034 | 0 | 552 |

| 配对 | N完整秒 | P完整秒 | P/N |
| --- | --- | --- | --- |
| 1 | 115.7564682 | 37.3657842 | 0.3227965122 |
| 2 | 97.1426284 | 37.0473564 | 0.3813707433 |
| 3 | 85.7759895 | 36.7222160 | 0.4281176611 |

P/N配对中位数按三个原始比值计算。N完整时间中位数为97.1426284秒，P为37.0473564秒，两路中位数之比另列于完整账本。全部六槽进入质量和消耗分母。

每槽主时间覆盖启动前检查、actor与CLI启动、实际工具执行、CLI/actor/已持有stdio的实际退出、归档、结果回读和发布。450秒原期限保持同一绝对终点。顺序批次为409.8171413秒，启动器main至LAUNCH_RESULT关闭为410.9664747秒，解释器启动位于该窗口之外。

准备登记marker至FORMAL_STARTED为1029.4155778秒。启动器正式标记前0.7839486秒与该准备窗口重叠。登记前编辑、上下文处理及实现审查模型用量未完整计量。这些阶段与旧001真实消费账本分别保留。

## 来源与准备检查

基线Git为cb5c33a158a9dea06c8151248cc42d2b87c5697b，准备Git为bad18a465300eba102120b1544dd698d655d61d6。新FROZEN固定188项，包含旧176依赖、候选consumer/driver/result_contract三文件、新启动器/plan/fake及新评分入口与真值，SHA256为1f9527f844b58a3e9719a2c0130c1cd1ad19c05a815bb39b975fb256b2a6680e。

新启动器明确使用新002/r，调用已验候选run_batch，前后13项指针检查一致。旧HERE/check_frozen作为只读依赖来源，候选三文件和新入口另有显式覆盖。新评分main私有globals绑定newadmin/newbatch，评分规则与真值原字节保持，模型未读取旧答案、真值或其他会话。

准备只做N/P各一次实际fake CLI接线。两路均通过自编ValueError→打印42→已知failed/null与成功投影→新archive/common检查→正常EOF。四次本地工具、渲染0、图片构造0、Pro0，独立只读复核876项通过。47项旧协议矩阵与49项旧准备矩阵没有重跑。

本轮正式14个结果均为success，tool_error为0。业务错误恢复证据来自上述两路本地链及已独立复核的旧真实错误包络重放，各自记录范围明确。

## 原件、回收与消耗

正式共14次工具、24次光栅，准备光栅0，符合36上限。正式构造、服务器发送、CLI接收均6图片块，20850字节PNG、27804个base64字符。P6光栅与N18光栅均按实际生成计数。数组载荷与进程RSS、模型输入分别记录。

N三槽累计298.6750861秒，input176283、cached129152、output7506、reasoning269。P三槽累计111.1353566秒，input39103、cached11520、output1630、reasoning0。主用量为原回报input+output之和，cached及reasoning字段另存。现金费用和细分image tokens保持未测。

六个CLI与actor均exit0，六个已绑定stdio持有句柄确认实际exit1并关闭。六份正式EXIT/EOF回执仍为unknown，实际进程退出已获证据。两路本地则有正常EOF、exit0、kill_requested=false的实际记录。六个fresh线程、原stdout字节与完整MCP/TCP均保留，16份ZIP的784个成员经回读核验。

正式CLI顶层错误、可见重连和外层重跑均为0。服务端内部请求范围继续未知。CLI0.152.1请求gpt-6.1-sol/medium/default，原fallback model metadata警告保留，实际服务端resolved设置未暴露。

旧消费001的4completed/2failed、旧N3流断开及usage覆盖unknown保持原账本。旧消费001含准备的28次光栅与更早002/003的64次分别列示，本批24次独立统计。

## 准备说明更正

准备期我误判了旧run_batch是否提供actual_CLI_processes。该字段实际一直存在。新启动器已删去冗余复制引用，新RUN_RESULT和原PID记录明确确认6个CLI。原准备记录保留，PREPARATION_NOTE_CORRECTION给出来源行与更正；运行源码、题目及实际结果保持正式前冻结版本。

## 复核与收口

独立质量确认六槽完整合格，独立成本2047项检查与作者账本一致，协议/生命周期核对确认14条内容绑定和全部实际退出。本批只执行一次固定正式分母，未补样。当前有限任务验收收口，后续能力范围由管理员按证据决定。

[独立质量](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_coverage_consumption_002/review/QUALITY_REVIEW.md)

[独立成本](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_coverage_consumption_002/review/COST_INDEPENDENT.md)

[协议与生命周期](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_coverage_consumption_002/review/PROTOCOL_LIFECYCLE_REVIEW.md)

[本地错误恢复链](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_coverage_consumption_002/review/LOCAL_INDEPENDENT.md)

[作者原件核验](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_coverage_consumption_002/FINAL_AUDIT.json)
