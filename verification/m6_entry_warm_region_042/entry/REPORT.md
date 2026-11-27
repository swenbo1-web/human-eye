# 042 E：实际 Codex 入口预检

**注册与发现已通过；新定义仍未获本人信任。自动派发、上下文交付、入口计时和实际宿主取消均未运行。** 没有模型回合、付费 API、Blender 启动或观察，也没有写入任何 Hook 信任。

041 的原 R3 安装已复核：143 个实际源文件逐项匹配冻结清单，启动器与安装绑定匹配。源摘要为 `ebd8068712ae70af74d4cfacc6fd8e05f5056e6047334c91c6487f1cd18dff0e`。041 S2 的手工收益作为历史事实保留，未计入本轮自动入口结果。

| 实际客户端进程 | 版本 | 有效元数据探针 | 结果 |
| --- | --- | --- | --- |
| 桌面包内二进制，独立 app-server 模式 | `0.171.0-alpha.13.2` | H0、H1 各一次 | 精确注册被发现，启用但 `untrusted` |
| PATH 独立二进制，app-server 模式 | `0.152.1` | H0、H1 各一次 | 与上一行使用同一份对应注册，启用但 `untrusted` |

两端的 H0 定义哈希均为 `sha256:b7dfee95f2bac321441aadca52c378289ec43e3724507db6d04844440973dbf8`；H1 均为 `sha256:8a8ec381081543163782e6203760adf30dd6fb850f64d2a24be0beaf2605b643`。四次正常交换只有 `initialize`、`initialized`、`hooks/list`；没有创建回合、发送提示或触发 Hook。四次 Job 所属进程均已退出，管道读取结束。这里的“桌面包内”只描述二进制来源，**不等于实际桌面 GUI 已派发事件**。交互式 CLI、`codex exec` 也未测试自动派发。

原始启动警告另外确认：新 workspace 的项目 `.codex/` 配置、Hook 和执行策略在项目获信任前被禁用；用户级独立配置仍可被发现。`untrusted` 是实际宿主库存结果；本轮没有发送提示，所以没有把它冒称为一次已观察的“事件触发后被跳过”。原件保留在各探针的 `STDERR.bin`、`HOOKS_LIST.json` 和 TX/RX 中。

## 已准备的精确范围与最短合法动作

H0 的工作区为：

`D:/HumanEye/runs/M6-042-ENTRY-WARM-REGION/entry/trust_H0_desktop_002/workspace`

H1 的工作区为：

`D:/HumanEye/runs/M6-042-ENTRY-WARM-REGION/entry/trust_H1_desktop_002/workspace`

每个工作区的项目注册是 `.codex/hooks.json`；相应用户级隔离注册在旁边的 `codex_home/hooks.json`。受控 Human Eye 配置分别是对应案例根目录的 `connector.json`，完整命令、H0 解码前的逻辑参数、安装绑定均记录在该案例 `RESULT.json`。H0 加 PowerShell 包装，H1 直启同一个 R3 启动器。

桌面正常路径是打开对应工作区，按宿主正常流程确认该项目，再在输入框的 **Review hooks** 或 **Settings > Hooks** 审阅该项目注册。必须重新核对实际显示的项目来源、精确命令与当前哈希。用户级 app-server 的库存键不能当作桌面项目 Hook 已获批准。本轮没有验证当前桌面 GUI 的点击流程。

CLI 的精确隔离路径如下；由本人打开交互式宿主后输入 `/hooks`，审阅对应的 `UserPromptSubmit` 定义。若要求登录，使用现有 Pro 正常登录；不要复制认证文件。以下命令未由本轮执行：

```powershell
$env:CODEX_HOME = 'D:/HumanEye/runs/M6-042-ENTRY-WARM-REGION/entry/trust_H0_desktop_002/codex_home'
& 'C:/Program Files/WindowsApps/OpenAI.Codex_26.1120.6357.0_x64__2p2nqsd0c76g0/app/resources/codex.exe' --cd 'D:/HumanEye/runs/M6-042-ENTRY-WARM-REGION/entry/trust_H0_desktop_002/workspace'
```

H1 使用同样命令，将两个路径中的 `H0` 改成 `H1`。使用此 CLI 隔离路径时，每个案例只批准该 CODEX_HOME 的用户级定义，项目副本保留未信任状态。这些是已准备的轻事件预检定义；配置端口为未使用的 `9`，不是正式 G60 观察配置。后续 G60 连接及新增 `PostToolUse` 定义仍须另行冻结并按实际定义审阅，不能由本次信任自动推定。

[OpenAI 的 Hook 文档](https://learn.chatgpt.com/docs/hooks)要求非托管 Hook 在精确定义获审阅后执行，并给出 `/hooks` 及桌面的审阅入口。本机两套生成协议均有 `hooks/list` 和通用配置写入，没有独立的“本人批准 Hook”请求。[原生 TUI 的实现](https://github.com/openai/codex/blob/main/codex-rs/tui/src/hooks_rpc.rs)在审阅后将当前哈希通过 `config/batchWrite` 写入 `hooks.state`；该配置写接口本身不能代替本人动作。本轮没有调用它，也没有复用旧信任、创建托管策略或使用信任绕过参数。

## 失败、分母和未测项

| 案次 | 原始情况 | 处理 |
| --- | --- | --- |
| `trust_metadata_001` | Job 辅助模块导入失败，app-server 尚未启动 | 保留失败和执行源码，未计有效探针 |
| `trust_metadata_002` | 初步 H1 用户级注册发现 | 单列诊断，未计最终四格 |
| `trust_H0_desktop_001` | 安装描述覆盖了 arm 变量，实际注册为直启 | 原件保留，H0 标签无效，排除比较 |
| `trust_H1_desktop_001` | 同一变量问题，arm 类型错误 | 原件保留，排除比较 |
| `trust_H0_standalone_001` | 复用检查因 arm 类型不符而在启动前拒绝 | 保留失败，未启动宿主 |
| `trust_H1_standalone_001` | 同上 | 保留失败，未启动宿主 |
| 四个 `*_002` | 修复标签后，真实注册与哈希交叉核对通过 | 最终有效元数据分母为四格 |

无关提示的三组轮换、G60 三个 H0/H1 配对、同回合只读工具交付及实际宿主取消，尝试与有效结果均为零，状态均为 `NOT_RUN`。不报告 Hook 耗时收益、模型响应收益、自动去重或取消回收资格。预检的进程关闭只证明元数据探针自身清理，不能代替在途 Hook 取消。

四格隔离配置均未复制认证或密钥文件，凭据环境变量已从子进程环境过滤，隔离 HOME 中没有认证／密钥文件。公开索引不含配置正文、编码命令、会话内容或凭据；原件只保存在本机原始目录。未改动 D:/hefe 的配置、041 安装或原证据。

[可复算索引](INDEX.json) · [只读复核程序](verify_index.py)。复核命令为 `python -I -B verification/m6_entry_warm_region_042/entry/verify_index.py`；它不启动 Codex、模型或 Blender。
