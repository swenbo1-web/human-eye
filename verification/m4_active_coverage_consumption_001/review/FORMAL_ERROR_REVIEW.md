# 正式六槽错误与终态复核

固定序列完成六槽，4 槽通过严格验收，N1、N3 失败。六份原始最终回答均已保存，质量由根独立评分。原验收状态完整保留。

N1 第 3 次 Python 工具响应发生 SyntaxError。N3 第 2 次也有普通 Python 错误响应。两次请求参数与全部正文分别完全相等，owner 的 `isError=true` 对应 CLI 工具的 `status=failed`。CLI result 省略 `isError` 并增加 `structured_content=null`。成功专用兼容函数拒绝该错误包络转换，登记 `CLI_result_differs_from_owner`。

N3 另外出现真实 CLI 顶层错误 `Reconnecting... 1/5`，内容指向流断开与响应正文解码错误。冻结验收器保留该错误，因此未来单独修复错误包络仍不足以使 N3 满足本批严格验收。原始最终回答与退出证据继续保留。

六槽的 CLI、actor 和 STARTED 后绑定的实际 thin runtime 均已确认退出并关闭持有句柄。全部来源回读一致，共同图片及运行故障为零。固定序列按原策略继续，控制器没有补样或重跑。N3 的 CLI 自动重连观测单独保留，provider 内部请求数及中断流 usage 覆盖保持未知。

仅第 2 对两路均通过正式验收，本批不满足预登记的完整三配对收益条件。后续应同时报告六槽质量及全部实际消耗，由根管理员判定解释范围。

完整原件链接、逐文件 SHA、两次错误包络及每槽终态见 [JSON 复核](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_coverage_consumption_001/review/FORMAL_ERROR_REVIEW.json)。先前 N1 证据继续保存在 [单次错误复核](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_coverage_consumption_001/review/ERROR_RESPONSE_REVIEW.json)。
