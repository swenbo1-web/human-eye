# 消费循环接线定向回放

定稿 a04 的四项测试全部通过，主命令退出码为 0。它们使用真实本地 Python
进程、stdio 薄客户端、读取线程和原协调循环。新增模型、provider、Blender、
产品及 API 调用均为 0。该回放范围限于接口接线，实际模型 resume 尚未验证。

## 最小代码变化

新 transport 加载原 FIX1 transport，替换它的 `archive_turn` 全局引用，并导出
原 `consume_turn`。新 episode 加载原协调器并绑定新 transport。原文件保持。

`ARCHIVE_TURN_DIFF.txt` 的逐函数对比证明，仅回执比较条件发生变化。原整包
相等仍保持原回执绑定行为，原整包不等时调用根提供的窄成功兼容谓词。请求、
次数、顺序、源文件复制和 ZIP 发布继续使用原实现。

新 fake CLI 复用原进程 fixture，在 stdout 事件发出前产生已录 CLI 结构。
成功使用 `status=completed,error=null` 及 `content/structured_content=null`。
错误使用 `status=failed,error=null`。正文原值保留，未解析其中的 JSON 字符串。

## 定稿四项与分母

- N 正常流程完成三轮，实际相同线程 UUID、固定 work、三次独立 fake CLI
  进程、单次 finish、注册 EDIT、读取线程及逐文件归档断言通过。
- C 正常流程完成同一组三轮断言，公开工具路径保持相应条件。
- 跨表示错误流程的第二轮使用批准历史原件 `P1/owner/tool_03/RESPONSE.json`
  的完整 result，SHA256 为
  `ed7236af2a3ef5080b2de78eb30a746f0d8652efc2fd8c339c4a6a08bfe13ef1`。
  正文一致，owner `isError=true` 与 CLI `status=failed` 原样保留，窄成功谓词
  返回 false。原绑定策略判第二轮失败，保留 final，第三轮为 not_run。
- 同表示错误控制保留 owner `isError=true` 和 CLI `status=failed`。原整包相等
  保持回执绑定，窄成功谓词仍为 false，原协调策略继续第三轮。

四个 fixture episode 共十二槽，状态为十 completed、一 failed、一 not_run。
这些状态属于模拟执行记录。四项 unittest 均按各自预期通过。定稿启动十一
fake CLI 进程、十一 stdio 薄客户端进程及四个本地 socket owner 实例。相关
消费者、读取线程和薄客户端的清理回执均确认完成。

## 准备尝试记录

`RESULTS.json` 绑定各次原件和具体原因。

- a01 完成四项接线测试，记录结束时的源码摘要。
- a02 增加运行前后源码摘要，两端一致，四项测试通过。
- a03 增加 `SOURCES.zip` 和完整外层封包。四项测试通过，封包发布时重复添加
  Windows extended-path 前缀，产生 FileNotFoundError，原主命令退出码为 1。
  该失败单列在 `offline/a03_ARCHIVE_FAILURE.json`，原目录保留。
- a04 将路径 helper 改为幂等，分配编号时只统计数字目录。四项测试、源码
  前后摘要及自动封包均通过。此后停止新增进程循环。

a01 至 a03 使用修正后的只读归档 helper 补封，未重放其消费过程。a04 自动
封存。每次均有完整 ZIP、成员清单和浅层结果副本，raw 目录保留。a03、a04
另有当次源文件快照。四次准备合计十六 fixture case、四十四 fake CLI 进程和
四十四 stdio 薄客户端进程，共八十八 fixture 进程，正式样本为零。

原正式 001 的六个执行失败、十二个未运行槽和六项 thin EXIT unknown 保持。

## 固定命令与分配

```powershell
& 'D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe' -I -B -X utf8 'verification/m4_surface_scan_continuous_interface_fix_001/integration/test_process_loop.py'
```

runner 在 `integration/offline` 下取最大数字目录编号加一，并以排他 mkdir
创建 `aNN`。ZIP、`aNN_MANIFEST.json` 和 `aNN_RESULT.json` 位于该目录旁，
分配过程排除这些浅层文件。该命令持续使用 provider-disabled 配置和显式本地
fixture，只运行上述四项定向 case。
