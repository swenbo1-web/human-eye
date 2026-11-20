# M4 导轨遮挡对照资格独立复核

2026-11-20。原资格失败与六个正式槽未运行的判定保留。证据 `69c48d35f581b72ef8762ccf5cdae545adaaf882`，原冻结摘要 `2162f98f38568f9510db6db6aa11e8cb720556e9915fbe93d30f83d4272d2fce`。两个 Blender 槽都正常执行并关闭。原审核器在匹配原始请求、回复、ID 和计量后，访问客户端收据中不存在的 `TX_sha256`，两次抛出 `KeyError`。该收据本来只发布 `TX_bytes`、`RX_bytes` 和 `RX_sha256`。对照客户端、转发层和宿主的原始字节一致，从封存 `TX.bin` 派生 SHA256 后，其他冻结条件均可从已有原件恢复验证。[原判定](https://github.com/swenbo1-web/human-eye/blob/69c48d35f581b72ef8762ccf5cdae545adaaf882/verification/m4_rail_blocker_consumption_001/QUALIFICATION.json) · [离线复验](https://github.com/swenbo1-web/human-eye/blob/69c48d35f581b72ef8762ccf5cdae545adaaf882/verification/m4_rail_blocker_consumption_001/qualification/OFFLINE_RECHECK.json)

## 实际现场证据

两臂同一 21 对象、148 点、184 三角装配，初末原生和求值来源相同。四个端面逐项通过。两根导轨 +X 都有当前局部 SCENE 原图，M17 为 **91,559／542**、M18 为 **91,559／271** 个表面／达标边界像素。两根的 −X 端仅 LEFT 前向，有正面积遮挡。A 用普通读算独立得到有效挡物，B 在首包直接交付两条 `M12[10]`，精确目标面交叠分别为 `1/4` 和 `2/11 m²`。真实正面积即可作为所问证据，其他有效三角也被允许。三帧不同的作用域和身份均能解析，三个 PNG/NPZ 跨臂逐字节相同。 [真值](https://github.com/swenbo1-web/human-eye/blob/69c48d35f581b72ef8762ccf5cdae545adaaf882/verification/m4_rail_blocker_consumption_001/truth/CURRENT_TRUTH.json) · [原件证据](https://github.com/swenbo1-web/human-eye/blob/69c48d35f581b72ef8762ccf5cdae545adaaf882/verification/m4_rail_blocker_consumption_001/truth/QUALIFICATION_ORIGINALS_REVIEW.json)

从原现场请求计算的两条 SHA256 在 QA／QB 一致。资格首包正文 **7,333／7,667 B**，各三张原图合计 10,283 B，固定 CLI 两阶段重放均完整保留。在这两次单槽中，首包实测 stdio 往返 778.053／755.537 ms，完整窗口 3,586.6／3,522.3 ms。仅有两资格、四业务、六构图、零模型。357 件运行原件归档 SHA256 `57520912bef199a0b89514f92eff6deacce502f65f68c2a575226b9db4093086`。模型采用、补查和完整任务收益未测。 [分段时钟](https://github.com/swenbo1-web/human-eye/blob/69c48d35f581b72ef8762ccf5cdae545adaaf882/verification/m4_rail_blocker_consumption_001/RUNTIME_REVIEW.json)

原启动脚本会重新开启 QA/QB，并只读同目录旧判断。后续使用[正式对照的独立冻结与派生准入](M4_RAIL_BLOCKER_CONSUMPTION_FORMAL_001_PLAN.md)，引用已有资格原件，保留两条原失败记录。用实际回执验证读取逻辑后再启正式槽。
