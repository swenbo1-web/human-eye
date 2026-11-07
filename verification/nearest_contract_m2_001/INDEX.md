# NEAREST-CONTRACT-M2-001 索引

状态：静态核查 READY，完整表面来源保证仍有条件；不是产品准入。

- `REPORT.md`：唯一结论、证据表、版本链、四例边界及一个后续建议。
- `LOCAL_SOURCE_AUDIT.json`：固定基线和 131 源逐文件核验；本轮零产品执行。
- `OFFICIAL_TAG.json`：官方 tag API 的原始 JSON 回执。
- `OFFICIAL_SOURCE_PROBE.json`、`OFFICIAL_SOURCE_CHAIN_PROBE.json`：官方 tag 的 8 文件内容摘要与符号行段，不保存外部代码全文。
- `OFFICIAL_SOURCE_INDEX.json`：8 文件在固定 commit 再读，全部与 tag 内容相同；本地 binary/build commit 对应仍未证。
- `STATIC_RESULTS.json`：四个标准库逻辑例子的真实结果。
- `source_probe.py`、`local_audit.py`、`static_examples.py`：本轮自编文本读取/哈希/条件推演脚本，不导入产品或下载执行外部代码。
- `DELIVERY_MANIFEST.json`：除自身外交付文件 SHA256 和字节数。

离线重放只需标准库（使用 Python 的 `-I -S -B`）：

```text
python -I -S -B verification/nearest_contract_m2_001/static_examples.py
```

`local_audit.py` 检查原固定基线 3f1d9d9 为当前祖先，并核其 131 文件摘要；仅新增证据的交付提交仍可重放。`source_probe.py` 默认读取官方 tag；`--followup` 读取链路其余四文件；`--pinned` 读取不可变 commit 并与前两份摘要比较。源探测只用于本轮证据复核，不是产品新增网络功能或性能验收。

范围遵守：0 Blender、产品运行、性能、消费者、安装和默认变更；不修改旧原件或根 STATE。四个逻辑例子不主张任何新增实际 bpy 行为覆盖。
