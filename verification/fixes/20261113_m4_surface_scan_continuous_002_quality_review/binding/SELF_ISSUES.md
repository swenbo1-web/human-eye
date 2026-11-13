# 本审查自身错误留存

1. 主脚本第一次：10 项记录中，错误把旧准备的 168 内容文件再加清单计为 169，并用不存在的源码文本 `validate_preparation(frozen)` 定位 main，触发 ValueError。保留 ATTEMPT_01_SCRIPT.py / ATTEMPT_01.json / ATTEMPT_01_CHECKS.json。实际原准备有 168 内容文件，168 个 Git blob 均另行读取并对 SHA；main 实际使用 `preparation = validate_preparation(read(...))`。
2. 主脚本第二次：10 项记录中，误以为 FORMAL_STARTED.preparation 带 head，触发 KeyError。保留 ATTEMPT_02 三文件。实际回执只含 preparation_path/files/external_files/committed_verified，已核原字段、原 PLAN SHA、固定 Git 字节和 main 顺序，不补造不存在字段。第三次最终 372 项通过。
3. 补充期限脚本第一次：3 项记录中，误在磁盘 EPISODE_RESULT 取 `business_receipts_closed_ns`，触发 KeyError。保留 BUDGET_ATTEMPT_01 三文件。原代码先写 EPISODE_RESULT，后取得 closed 时间并返回含派生字段的 coordinator；改为绑定原 c/FINAL_TIMING 与 outer 内 coordinator 返回值，再核绝对时界。第二次最终 49 项通过。
4. 定向源码搜索曾尝试不存在的 `human_eye_plugin/owned_blender.py`；随后从实际 actor 导入关系找到固定 `verification/native_plugin_complex_003/reused/accepted_native.py`，只读审其计数及 code 保存逻辑。该路径猜测不是作者缺陷。

以上均为独立读法/脚本假设错误，不是产品或实验运行失败。原件未改、没有新增运行。最终检查数不能与保留的失败尝试相加作为实验样本或成功率。
