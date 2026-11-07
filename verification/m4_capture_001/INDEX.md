# M2-M4-CAPTURE-001 文件索引

唯一报告是 RESULTS.md。最终产品源摘要为 776485105a0616b9aa19b4a7385e6fd01a15ef32bf535d9487444855b1a193e5。

| 文件 | 用途 |
|---|---|
| human_eye_plugin/blender_host.py | 数值帮助函数、单宿主读取方法、复用展开上下文 |
| human_eye_plugin/blender_mcp_host.py | 唯一新内部运输命令及期限/回执绑定 |
| verification/test_m4_capture_001.py | 预登记 12 类离线用例；包含独立 Fraction oracle 与宿主/运输桩 |
| PREREGISTRATION.md | 离线边界和未来真实 QA 预登记 |
| offline_qualification_03.json | **最终**固定产品源码的 128 项原始验收回执 |
| offline_qualification_01/02.json | 中间源码的历史通过记录，非最终验收，不叠加覆盖 |
| candidate_runtime_identity.json | 实际 import 的最终源摘要、131 源清单和模块路径 |
| baseline_audit.json | 独立读取 82ef6eb 的 131 个 Git blob，重建 fb5a 并确认仅两个产品文件改变 |
| run_offline.py | 可复放的有界验收记录器，不覆盖已有回执 |
| real_qa.py / blender_assets.py | 待根授权独占窗口后运行的真实 QA；本轮仅语法/CLI 检查 |
| qa_preparation_check.json | 最终 QA 脚本的 AST/hash 与未执行状态 |

需要复放时用已存在的解释器，指定新的回执名，不覆盖既有证据。

```powershell
& 'D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe' -B 'C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_capture_001/run_offline.py' --out 'C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_capture_001/root_review_replay.json'
```

未来真实 QA 命令模板如下。本轮未执行；BASELINE_ROOT 须由根提供只读的固定宿主导出目录，ROOT 取本工作树。输出目录必须新建且位于本工作树内。

```powershell
& 'D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe' -B 'C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_capture_001/real_qa.py' --run --baseline-root '<BASELINE_ROOT>' --expected-source-sha256 776485105a0616b9aa19b4a7385e6fd01a15ef32bf535d9487444855b1a193e5 --out 'C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_capture_001/real_run_01'
```

任务书与上一轮根审证据在 D:/hefe/verification/fixes/20261107_m4_acquisition，本工作树没有改写。Git 提交号与报告 SHA256 由唯一回报附送。managed worktree 当前仍为后续复核所需，不回收。
