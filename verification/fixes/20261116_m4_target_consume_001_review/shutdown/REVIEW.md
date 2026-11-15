# M4任务消费001的薄客户端收尾独立复核

2026-11-16。固定作者最终提交bc177d231329dac630b4d02a161076b2b9fb50e3，实际薄客户端源为 `verification/native_plugin_complex_003/reused/stdio_attach.py`，SHA256为 `210539d6a728fd63cc8f8b3925bb866e1929dce4a8e5db85a7ceece7c183cb00`。本轮独立脚本为review_shutdown.py，180项检查通过。

## 判定

六槽的任务完成和实际进程退出证据成立，允许按原safe_to_continue合同进入M5。六个薄进程的exit1和缺EXIT回执继续作为非优雅收尾事实保存。新增本地对照支持宿主直接终止子进程这一解释，原正式记录中终止发起者仍未知。

全部29个业务工具调用均有当前薄客户端的完整TX/RX，ID类型和值一致。六槽的最终答案、唯一usage事件、CLI输出文件一致性、CLI退出、薄客户端退出观察及完整槽发布时序均成立。没有发现丢失工具结果或未关闭的已绑定进程证据。终态误报、业务重试和效果质量由根的其他复核分工判定。

## 六槽实际证据

- 各槽恰有一个STARTED，PID、Python映像字节、创建时间及祖先链绑定保留句柄。六个薄进程均被该原句柄确认exited、exit_code=1、handle_closed=true，等待无错误。
- CLI主进程各自exit0、reaped、原始句柄和管道关闭，kill_requested=false，deadline_timer_fired=false，读线程均已停止。独立consume_turn异常列表为空。
- 每个含ID的薄客户端TX都有对应RX，初始化通知没有响应的行为匹配原合同。原工具错误回复也在这些RX中，未被当作无响应。
- 六槽final_received与turn.completed均在CLI退出之前，薄进程保留句柄退出观察在其后，全部发生在完整槽SLOT_PUBLICATION之前。因此现有完整成本包括这段等待与关闭。
- 六槽owned actor/listener关闭无错误，Blender退出0并reap。三个P槽的产品MCP stdio及保留句柄分别确认退出0。

原事件没有记录谁调用了进程终止，也没有薄客户端自己的finally执行回执。保留句柄能证明实际退出，不能单独证明异常发起者。

## 同字节客户端的四个本地对照

独立脚本直接启动原固定字节适配器，提供本地伪端点与管道。没有启动CLI、Blender、渲染器或模型。每种情况只执行一次，所有输入、stdout、stderr、STARTED、EXIT和结果保存在local_*目录。

| 输入与关闭方式 | 实际退出码 | EXIT回执 | stderr |
| --- | --- | --- | --- |
| 直接EOF | 0 | normal_exit=true | 空 |
| 单次本地假broker RPC，收到回复后EOF | 0 | normal_exit=true，1请求 | 空 |
| 无效JSON后EOF | 1 | normal_exit=false | JSONDecodeError |
| STARTED后Windows terminate | 1 | 缺失 | 空 |

源码finally在普通Python异常或正常EOF时都会写EXIT。强制结束不会执行Python finally，其实际签名与六个正式薄进程相符。这个对照说明该现象可由宿主终止产生，同时保留正式终止发起者未知这一边界。CLI主进程与薄适配器是两个实际进程，分别读取自己的退出证据。

## 最小后续处理

原记录已同时保留真实exit1、缺EXIT、原句柄退出和安全继续范围，当前无需改产品或增加关闭进程。后续M5继续沿现有实际进程退出观察和独立owned关闭路径，报告可标注receipt缺失与实际退出分别成立。后续若出现工具响应未完成、已绑定进程未退出或具体finally写入错误，再依据那一条原件修复。

本轮没有修改作者源、原正式数据或产品。独立脚本首版误读取不存在的slot.clocks.slot_completed_ns，在启动任何本地子进程前失败。原版和ERROR_R0.md保留，最终改为实际SLOT_PUBLICATION.json/slot_result_published_ns后完整通过。四个本地Python子进程均由本脚本自己的Popen wait收回。

本轮新增模型、Blender、raster、API和付费调用均为0。
