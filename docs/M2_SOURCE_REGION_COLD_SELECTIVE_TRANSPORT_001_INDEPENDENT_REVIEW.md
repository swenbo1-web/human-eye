# 冷启动选区传输批独立复核

远端证据 f75b9454 与提交树一致，本机封存 ZIP 的 803 项逐件复验。固定 e8006670、隔离候选 a383f953。三种封存资产的六组量测与原距离、方向、实际点对和源面对应等价。安装版走本机回环 TCP 重放封存几何，完整到选区响应分别为装配 72,469→3,879 B、Yanyite 3,318,954→26,830 B、轨道 27,054→2,828 B。Yanyite 仍需展开和扫目标与参照的 53,276 三角，私有包实际只发 313 个。 [原报告及证据](https://github.com/swenbo1-web/human-eye/blob/f75b945498793ebeacfb242ada4635c6e12b0804/verification/m2_source_region_cold_selective_transport_001/REPORT.md)

回环的私有请求先执行，包含约 106 KB 驻留源码初始化，后执行的完整捕获请求均为 1,137 B。响应字节已可直接核对。完整双向冷连接成本还需在两边相同起点上测量。 [回环线包索引](https://github.com/swenbo1-web/human-eye/blob/f75b945498793ebeacfb242ada4635c6e12b0804/verification/m2_source_region_cold_selective_transport_001/RESULT.json)

现场四格原判全部失败，均正常关闭，零量测用宿主 TCP。A 两格在派发前拒绝，B 两格各一次私有派发，错包参数拒绝。控制器把冻结记录 `{query, include_image}` 再当成 `query` 包了一次，评分器也把线包内层与冻结外层比较。启动预飞只走故意非法请求及目录恢复，遗漏成功序列的真实派发。已证实的回环收益与待实测的 Blender 展开、冷/热线包、实际耗时分别留账。 [原判与失败线包](https://github.com/swenbo1-web/human-eye/blob/f75b945498793ebeacfb242ada4635c6e12b0804/verification/m2_source_region_cold_selective_transport_001/RESULT.json)
