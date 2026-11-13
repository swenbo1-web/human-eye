# 接口原件回放验收

本批离线回放通过 381 项检查。实际调用冻结 FIX1 的 `archive_turn` 和新批 adapter 的 `archive_turn`，保留两端生成的原件副本、归档回执及 raw ZIP。模型、Blender、产品和 API 新增调用均为零。

## 实际原件

| 输入 | 旧 archive 绑定 | 新 archive 绑定 | 新成功谓词 |
| --- | --- | --- | --- |
| 本次连续消费 14 份真实成功工具回执 | 14 份均复现 `CLI_result_differs_from_owner` | 14 份全部通过 | 14 份均为 true |
| 同冻结 CLI 的 3 份历史真实工具错误 | 3 份全部失败 | 3 份全部失败 | 3 份均为 false |

14 份成功直接取自旧批 `ORIGINALS.zip`，每份绑定旧交付清单、私有质量绑定、外层 ZIP、成员清单、原始 REQUEST/RESPONSE、完整 events 文件和对应原行。逐项核对公共业务投影的来源 SHA、请求工具名及参数，以及根 interface 报告的正文 SHA。旧私有质量绑定和完整外层 ZIP 均保留摘要链。

3 份历史错误按根 interface 的明确索引读取，核对 REQUEST、RESPONSE、events 文件和事件原行 SHA。历史 PLAN 和运行前 driver 的摘要与根报告一致，冻结 CLI 字节 SHA 为 `01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6`。

`run_01/SOURCE_INDEX.json` 列出全部 17 份真实输入定位及摘要，`INPUT_HASHES.json` 和 `UNCHANGED.json` 保留所有读取文件的前后摘要。全部来源前后相同。旧正式执行仍为 6 轮失败、12 轮未运行。

## 定向边界

25 个定向变体分别检查请求参数和工具名改变、原始 REQUEST 缺失、文本改变和正文块移除、content 缺失或类型错误、isError 的 true/0/空字符串/缺失、CLI failed 或 error 非空/0/缺失、RPC error、非空结构化数据及未知字段。

正常控制覆盖同表示成功、业务 content 内嵌同名 `isError` 与 `structured_content` 字段及 JSON 字符串。嵌套业务载荷逐值保留，嵌套 false 改成 0 的篡改被拒绝。两端同值的非空结构化数据仍按本批支持范围退出。

同表示错误控制明确保留旧策略。owner 的 `isError=true`、CLI 的 `status=failed`、两端 result 完全一致时，旧和新 archive 都能忠实绑定回执，新成功谓词保持 false。每个结果分别记录 `matched` 和 `success_predicate`。

## 证据交付

- `run_01/RESULTS.json` 汇总真实回放和变体结果。
- `run_01/CHECKS.json` 保留 381 项逐条检查。
- `RUN_01_ORIGINALS.zip` 封存全部 818 个回放文件，原目录继续保留。
- `RUN_01_MANIFEST.json` 绑定 ZIP 和每个成员的字节数、SHA256。

Git 可跟踪源码、报告、run_01 浅层结果、来源索引及完整 ZIP/成员清单。深层病例原件可经 ZIP 重放和逐文件核对。

## 复现入口

使用既定隔离 Python 执行以下参数，输出必须选本批 `replay` 内的新目录。

```text
-I -B -X utf8 verification/m4_surface_scan_continuous_interface_fix_001/replay/run_replay.py --output verification/m4_surface_scan_continuous_interface_fix_001/replay/root_recheck_01
```

本报告覆盖原件绑定和回执比较。实际 consumer 进程循环及三轮协调接线由同批 integration 单独验收。真实模型 resume 留待新正式合同验证，旧 thin EXIT 六项继续 unknown。Git 提交来源由固定计划和旧交付清单声明，本脚本通过读取与 SHA 核验建立来源链。
