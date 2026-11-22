# M3 斜面精确来源兼容恢复独立复核

2026-11-22。接受隔离修复 `cee6fe78a65c1534361228641743aa83d6d72b61`。唯一产品文件差分是共享 `_publish_points` 默认恢复显示点，距离见证显式获取显示点与精确点。实际已安装内核重现原穿透样本，与 `5c77f71a` 同交单点 `[1.0,0.4375,0.25]`。两远端提交已核。原 `ae14344e` 的兼容拒收保留。 [修复差分](https://github.com/swenbo1-web/human-eye/commit/cee6fe78a65c1534361228641743aa83d6d72b61)

独立逐件核对 `241d10f75c52074bb7f072ab5fdb9f6d243fc17a` 的 Git ZIP 1,817 个成员、3,979,384 B、全成员 SHA、长度和 CRC，摘要 `5357d79f36d4eaf374534616b33db565b3d5a0cc4b518516e24d102c2a52b74b`。从原线包直接解出候选标准／隔离证据两端 20 条冷暖结果。除 `trace_id` 和 `binding.runtime_source_sha256`，与旧版 20/20 正文稳定字节和字段顺序相同。16 个正向包共 20 处定位字段恢复为原单点，实际为 `penetrating`／`transverse_boundary_interiors`、三角 6/4，另四个分离结果均无定位。原缺陷版同 16 包的 20 处重复点均可复查。 [正式原包矩阵](https://github.com/swenbo1-web/human-eye/blob/241d10f75c52074bb7f072ab5fdb9f6d243fc17a/verification/m3_whole_object_rounded_witness_compat_001/evidence/RELATION_MATRIX.json)

复验批量 210/210，对应原严格 202 和新精确 8，距离、方向、显示点、来源与搜索计数保持。四个场景 8/8 真实量测回包独立解析。斜面与 BVH 回包有精确来源，普通标准距离无可选来源，严格来源继续用原字段。同代热读结果相同，未重算。合计 14/14 独占进程、28/28 次实际读、168/168 固定 CLI 回放。两项新增定向回归通过。源码、wheel 与实装按证据所报的哈希固定。 [工程报告和集成证据](https://github.com/swenbo1-web/human-eye/blob/241d10f75c52074bb7f072ab5fdb9f6d243fc17a/verification/m3_whole_object_rounded_witness_compat_001/REPORT.md)

关系标准的冷／热回放 10.975／5.930→10.944／6.295 ms，关系证据端 11.143／6.008→12.856／7.062 ms，四份量测历史异窗 17.061／9.359→23.514／9.716 ms。局部时钟留作诊断，未得稳定时延变化。下一项只做[两组实际 BVH 位姿的真实模型留出](M3_WHOLE_OBJECT_ROUNDED_WITNESS_CONSUMPTION_001_PLAN.md)。
