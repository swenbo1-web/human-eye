# 28 对象装配对照独立复核

固定 e8006670 证据端及 91129d2e 只读资产，同题原生与插件各一个冷 Blender 和现有 Pro，两个实际槽正常完成。远端证据 4bc6b7d6 与 963 件本机 ZIP 逐件核对。N19→N14 的选区间隙为 44.500014 mm、+X，N25→N07 为 414.366994 mm、斜向 +Y/+Z。两组点对的当轮表面与等距条件、350 mm 阈值、四张最终原图和同帧像素均成立。插件两次自然请求有图 full，都直接采用首包量测、原图路径与像素，无其他工具、重测、补读或重传。构图双方均为 2，业务 5→2。 [验收报告](https://github.com/swenbo1-web/human-eye/blob/4bc6b7d6da32a4204f57465f4311723e0836faff/verification/m4_assembly_cross_asset_product_native_001/REPORT.md)

完整窗口 88.211→49.242 s（−44.18%），首图 57.794→11.605 s，累计工具间等待 45.797 s→0.519 ms。原始 CLI 输入加输出 59,576→24,440（−58.98%），扣缓存 16,568→17,272（+4.25%）。对外正文 14,437→26,205 B，图 5,519→5,888 B。与同版 Yanyite 的另一同题配对相比，两资产各有一对同质量结果，完整窗下降 42.62% 至 44.18%，原始 token 下降 51.13% 至 58.98%，扣缓存后的方向不同。模型内部时钟和账单未观测。 [原始成本及证据索引](https://github.com/swenbo1-web/human-eye/blob/4bc6b7d6da32a4204f57465f4311723e0836faff/verification/m4_assembly_cross_asset_product_native_001/RESULT.json) · [Yanyite 对照](M4_YANYITE_OPPOSITE_DIRECTION_PRODUCT_NATIVE_001_INDEPENDENT_REVIEW.md)

原冻结评分器给 N1 7/17，另 10 项访问了旧资产字段 `matrix64_regions`。P1 将已校验的字符串路径交给需要 `Path` 的加载器，退出且无正式分数。只在原件闭槽后修复这两处适配并重评，双方均为 17/17，旧通过项保留，错方向、错图路径和错像素三类反例各臂仍拒绝。无 Blender 或模型重跑。下一轮在零模型条件下，通过同一正式评分入口复现旧故障、修复并回放两个资产，补足冻结前只测过真值和局部输入的缺口。
