# 离线复算解析记录

首次执行在主场景中位数字段处停止，报错为 `ValueError: raw arm medians`。

原始 RESULTS.json 把两个中位数保存为 numerator、denominator、value 三字段字典。首版复算器按标量比较。复算器随后改为与已有配对比值相同的精确有理数检查，原始证据和验收规则保持原字节。

本次失败发生在离线 JSON 解析适配，没有启动实验进程或新增渲染。

第二次执行在旧 002 的未运行条目处遇到 `KeyError: 'output_directory'`。旧记录对未启动条目省略输出目录，复算器加入明确的 not_run 检查后跳过其不存在的 TRACE，所有已启动条目继续计入尝试总账。

资格的两个时界分别保留。RESULTS.timing 的汇总发布前窗口为 3.1530992 秒，FINAL_TIMING 的含 RESULTS 写关窗口为 3.1551422 秒。两项来自各自原始边界。

第三次执行在资格原件哈希表处遇到 `FileNotFoundError: AUDIT.json`。该表使用相对各自 output_directory 的文件名，复算器随后明确按各资格目录解析。原件没有缺失。

第四次执行在预期非零异常的 STATE 字段处遇到 `KeyError: 'marker_actions'`。该异常状态保留异常正文，未附带正常状态的动作计数字段。复算器保留字段缺失事实，独立读取 marker_written 事件与 MARKER.json 是否存在，再核对资格行的动作计数，没有为缺失状态补造数值。
