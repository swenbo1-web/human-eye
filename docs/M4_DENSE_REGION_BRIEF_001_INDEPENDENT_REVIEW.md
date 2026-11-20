# M4 密集区域简报 v2 独立复核

2026-11-20。接受隔离工程候选 `278fd3003758299379f6d87b7e9174c577f5bb88`，直接承接 `3cbf240562b61cff18c2818c6d134904259b36b7`，唯一改动 `live_spatial_mcp.py`。固定 143 源 `6e8663feb57b630048fe919141cfcabbae4ae2365df1f80da693382c360b65e8`，wheel `46664941fbd83be143ae4866486d1a76593c82c7331a4c9926a600189c8ee347`。冻结 `b5af3f8ed7c9e2839035df65dd6d8cf7b313c472`，归档 `ea74b940dd78f3e467856659b197acdbe9710f6d`。原 v1 首包失败继续列在原分母。本次同资产、同请求的单独 QP 通过；作为[后续正式对照](M4_DENSE_PANEL_SWEEP_FORMAL_001_PLAN.md)的插件资格。[作者报告](https://github.com/swenbo1-web/human-eye/blob/ea74b940dd78f3e467856659b197acdbe9710f6d/verification/m4_dense_region_brief_001/REPORT.md)

## 交付与兼容

同一固定资产的实际 MCP 正文 **72,253→8,242 B**，少 88.59%；实际完整 RX **81,685→16,366 B**。独立从线包恢复 13 个区域的对象、中心、精确源三角和空间形状，11 条见证、两个几何遮挡解释。10 个侧板共享 LEFT，顶板引用 SCENE。两张原 PNG 为 3,456／2,077 B，PNG 和对应 NPZ 均与旧现场原件逐字节一致。v2 的真实帧行与 MCP 块位分开，同名视角由作用域和帧身份区分，未交付的真实帧块位置为空。原像素短证据与其门槛顺序可核。固定 CLI 三个工具头的两个处理阶段保留全部正文和两张原图，最长工具头下总文本 8,277 B，历史近似用量 2,070 token。[实际首包](https://github.com/swenbo1-web/human-eye/blob/ea74b940dd78f3e467856659b197acdbe9710f6d/verification/m4_dense_region_brief_001/public/BRIEF.json) · [原线包验收](https://github.com/swenbo1-web/human-eye/blob/ea74b940dd78f3e467856659b197acdbe9710f6d/verification/m4_dense_region_brief_001/checks/LIVE_REVIEW.json)

共享当前绑定和对象身份，完整源三角使用原顺序的零基含端点区间。有图成功简报直接生成 v2；无图预测也使用该形状，保留零实际观察。显式 `full` 仍按现有来源验证输出完整证据，普通观察、`source_region` 和错误路径在已封存的对照中保持原字节。作者的 31 个生产者实例、5 个损坏回包已过，含组合量测、非连续源、错误绑定和有图无块两类场景。21、28 对象原件的新简报分别 6,997、7,707 B；后者 N10 的 8,835／0 像素不足证据仍与局部 TOP 对应。[回归证据](https://github.com/swenbo1-web/human-eye/blob/ea74b940dd78f3e467856659b197acdbe9710f6d/verification/m4_dense_region_brief_001/checks/OFFLINE_CONTROLS.json)

## 现场成本与适用范围

一次 Blender 独占、一次业务、两次构图，零原生资格、模型、重建或付费。冷 RPC 2,036.039 ms，生产服务 1,987.989 ms，内含宿主采集 170.302 ms、索引 365.046 ms、两图发布 410.243／390.557 ms。文本格式化 7.084 ms，完整独占窗 4,393.786 ms。仅为同资产前后各一次工程槽，时间波动不作算法收益结论。当前证明的是可用客户端交付，真实供应商输入、模型理解、补查、完整耗时和 token 仍待测。93 件运行原件 ZIP SHA256 `0afc0e820eaef19efcf5c2c4c502191c3d69e0852d9f6d732da04312713deb42`。[原件索引](https://github.com/swenbo1-web/human-eye/blob/ea74b940dd78f3e467856659b197acdbe9710f6d/verification/m4_dense_region_brief_001/RUNTIME_INDEX.json)
