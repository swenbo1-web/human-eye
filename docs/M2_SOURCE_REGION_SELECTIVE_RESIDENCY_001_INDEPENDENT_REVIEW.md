# 无图选区同代复用独立复核

远端候选 ff0105db 和证据 709d7274 提交与树一致，本机封存 1,145 项逐件复验。4/4 真实 Blender 槽完成，12/12 量测成功。六对原距离、方向、实际点对、两个当前原源面均相等。两次候选同盒经当前宿主确认，零展开、三角化、世界变换、闭盒筛选及几何重传。候选保留原精确求解。 [实测报告](https://github.com/swenbo1-web/human-eye/blob/709d727410e929a69b9b0c6bcfc2870dad6e1d09/verification/m2_source_region_selective_residency_001/REPORT.md)

Yanyite 同盒双向 29,712→4,886 B、业务 582.759→341.792 ms。同对象换盒免重展并保留 53,264 个目标原面筛选，业务 581.050→353.671 ms、双向 17,486→19,813 B。装配换对象对确实新展开 24 个点、44 三角。两个资产冷首包几何量相等，冷双向分别多 4,578/4,621 B，首次引导源码增加 2,284 B 只是其中一段。 [分段计量](https://github.com/swenbo1-web/human-eye/blob/709d727410e929a69b9b0c6bcfc2870dad6e1d09/verification/m2_source_region_selective_residency_001/METRICS.json)

完整槽装配 2.737→2.213 s，Yanyite 5.980→6.000 s。Yanyite 三请求合计实际少 486.111 ms，业务外多 505.868 ms。其最后采样的 Blender 整进程工作集增约 11.9 MB，差值包含缓存外分配。每资产只有一对，不能从业务段推出整题收益。正式默认保持原样。下一轮验证这条无图量测能力在真实 MCP 入口的显式可选交付。
