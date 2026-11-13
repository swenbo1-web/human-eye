# FIX1 实际工程失败的生命周期复核

2026-11-13。只读原件复核通过，共 4008 项检查，绑定 1997 份输入。FIX1 原工程资格仍未通过。新增 Blender、产品、模型、API 和 Git 操作为零。

## 实际分母和关闭

纠正准备 e06597f92d1193b40e9a62b78919a3125e4e346d 后，只实际启动一次 C episode。BASE 的业务请求成功返回，真实薄客户端正常 EOF 退出，随后资格失败。原分母为计划 3、实际 1、资格完成 0、资格失败 1、未运行 2。REPEAT、EDIT 没有启动。新增 N episode 为零。

8000b52f 的第一次准备守卫在预留及实例启动之前失败，记录 ENGINEERING_STARTED=false、episodes_directory=false、新 live=0。它与 e065 的一次实际工程分母分别保留。

实际 owner、Blender、产品 launcher/runtime、session 与薄客户端逐项绑定，原始 stdio 和 owner 请求/返回一致。单业务在 30 秒内完成。完整 episode 为 4.1995286 秒，结果关闭及最终计时发布均在原绝对 590 秒内。两个 metadata RPC、一个通知及一个业务分别保留。

BASE 已 end_turn，active_turn 为空。C 没有尝试登记 EDIT，初末几何及 worker initial/accepted/final fingerprint 相同。owner、产品和 Blender 的实际关闭及回收均确认。通用 worker close 事件的 status=unknown 与这些实际关闭证明分别记录。

## 实际结果和失效阶段

产品实际返回 complete、71 匹配、24 对象及 276 对完整覆盖，unknown/deferred 为零。私有工作量记录首次 kernel 112，测量条目从 0 到 112。此次业务恰好一次真实宿主捕获，捕获及图片保护检查完成，零新图像。上述是原件中的业务事实，原工程验收失败保留。

失败栈发生在 runner.verify_business 调用 qualification.read_capture 的 WIRE/INDEX.json 读取处，尚未进入 verify_c_turn。业务成功、thin 退出和 end_turn 都早于这次 FileNotFoundError。清理的最终快照发生在错误之后。

冻结 worker 把 WireSocket 请求/返回先留在进程内 RECORDS。wire_meter.flush 才创建 WIRE 目录和汇总 INDEX。源码中该 flush 只有一处调用，位于 worker 服务循环结束之后、WORKER_CLOSED 发布之前。因此关闭后离线归档可读，不代表同一材料在在线资格时已经发布。

关闭后的实际 INDEX 现有四条原帧，依次为初始 QA、业务捕获、最终 QA 和 close，长度及 sendall 回执逐项一致。业务捕获的资源 delta 保留 24 resources/24 meshes。原 FileNotFoundError 及原 failed 不因关闭后文件存在而升级。

单次运行材料的时机不同。worker 每次先写 call_N/SCRIPT.py、stdout.txt、stderr.txt，再发布完成事件，随后发送成功响应。实际 call_2 的代码与 script_sha256、stdout 与实际响应及字节计数一致，保存文本的 Windows 换行转换单独处理。因此既有单次输出可以供在线资格绑定；后续修复应在此材料与原宿主事件、资源历史之间接线，并继续把关闭后 WIRE 汇总作为完整归档。本复核没有替换读入口或重新执行业务。

## 字节保护与边界

1,190 份准备文件、362 份外部输入以及旧 001 的 367 份内容文件保持原字节。原 actor、stdio、worker 和产品组件的固定摘要继续成立。

本复核建立记录、来源和清理的一致性，未补跑 C2/C3，也未运行任何模型/provider。C 的三轮缓存复用、EDIT 失效以及真实模型续接仍未测。完整原异常、证据时间顺序和逐文件摘要见 RESULTS.json。
