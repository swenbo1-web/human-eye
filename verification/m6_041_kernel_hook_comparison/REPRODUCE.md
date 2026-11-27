# M6-041 复核方式

## 从本分支重算

在本目录运行以下命令。Python 3.10 以上的标准库即可。程序读取随分支提供的压缩业务回执，校验摘要、四臂外部安装身份与预期槽位，重新计算七组收益、交互项和三类暖读取的退化门。整份 Blender 模型和专用安装均留在本机。

```text
python replay_public.py
```

[压缩包内容与计数](WIRE_INDEX.json) · [原始分组和门槛](PLAN.json) · [实验报告](REPORT.md)

## 在原 Windows 实验机查证

完整证据目录为 `D:/HumanEye/runs/M6-041-KERNEL-HOOK`。各文件的字节数和 SHA-256 见 [EVIDENCE.json](EVIDENCE.json)。原 032 和 R3 的 Git 对象以及 Hook 修复的逐文件对应可在 [安装复核表](review/GIT_WHEEL_INSTALL.json) 查看。G60、D48、G508、B02、Yanyite 的固定资产、读取参数和独立答案见 [宿主计划](s1/PLAN.json)。

下面是本轮实际使用的主要实验入口。命令中的 Python 为 `D:/he_m3_bvh032_private_654c1f69/venv/Scripts/python.exe`，各脚本依赖本机留存的历史夹具和原版 Blender 插件。重演时应在新的实验副本中绑定新输出目录。原有槽使用独占创建，以便保留首次数据。Windows 系统文件缓存随机器运行自然变化。

```text
python -I -B install/build_installed.py
python -I -B s0/historical_replay.py 032 --installed --credit-boundaries
python -I -B s0/historical_replay.py r3 --installed --credit-boundaries
python -I -B s0/consumer_controls.py 032 --installed
python -I -B s0/consumer_controls.py r3 --installed
python -I -B s1/s1.py prepare
python -I -B s1/s1.py run --window s1/WINDOW.json
python -I -B s2/run_s2.py formal --window-receipt s2/OWNER_WINDOW.json
python -I -B s3/workflow.py freeze
python -I -B s3/workflow.py run preflight preflight01
python -I -B s3/workflow.py run screen screen01
python -I -B s3/workflow.py run resource resource01
python -I -B s3/review.py screen01 resource01
```

S1 的收据字段及落盘时序恢复分别保留原始计划、修订计划和先行失败记录。补充暖读的原始和恢复批均在本机，合并评分时只接纳原先缺失的 14 份暖扫描。S2 的退出、超时和取消控制单列。对应的脚本和门槛见 [暖读取计划](s1/warm_diagnostic/PLAN.json) 和 [错误出口计划](s2/error_control/PLAN.json)。
