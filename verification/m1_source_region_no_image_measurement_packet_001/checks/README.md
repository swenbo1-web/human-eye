# 独立选区量测与 CLI 验收

使用固定解释器，从工作树执行。三个 case 分别是 `holdout_A1`、`holdout_B1`、`independent_P1`。

### 复核原全文

`D:/he_anchor_001/venv/Scripts/python.exe -IB verification/m1_source_region_no_image_measurement_packet_001/checks/score.py --case holdout_A1 --mode full`

### 验收实际回放

`D:/he_anchor_001/venv/Scripts/python.exe -IB verification/m1_source_region_no_image_measurement_packet_001/checks/score.py --case holdout_A1 --mode compact --request <TX.bin> --response <RX.bin> --producer <PRODUCER.json> --output <new-receipt.json>`

标准端点改用 `--mode full`，核完整当前源三角、逐点映射和量测证据，并单独记录固定 CLI 的实际遗漏。候选隔离端点的 compact 验收要求正文最多 10,800 B，三种工具头各在两阶段保持正文完整。已有历史 A1/B1 简报可省略回放路径直接核验。P1 原简报的参考换成了 Obj_08，请给出同一 Obj_05 请求的实际回放。

验证器读入初末 native 与 evaluated 数据、producer、线包、CLI 事件和原答，并用两个独立解析下界和有理数三角形点归属复核最短距离。全量公开正文与简报语义分别核验。进程关闭、实验分母和标准端点的成对字节一致性由主回放收据提供。
