# M1 目标观察首包路径 Windows 修补独立复核

2026-11-21。接受工程候选 `95fd44bb8c4b6b992d8849f38ffbe5d778b0ac5a`。相对 `a9183d02` 只有一处路径比较修改。目标观察按严格解析后的原生字符串比较，旧源区沿用旧行为。原候选 0/1 和原失败线包留在原批。[原验收报告](https://github.com/swenbo1-web/human-eye/blob/0cc8afa5082f27a3aff607bebf7793d0d4072bc9/verification/m1_target_observation_first_image_path_windows_001/REPORT.md)

- 独立读取正常、旧别名及新别名 MCP 字节，正常新版与旧正常回复逐字节相同。8,726 B 正文、16,456 B 线包，只有 LEFT 有路径。Windows 真实文件复查确认原 PNG 为 2,526 B，摘要 `4a69c9a0c955be1527564d9df02db9fbfcdbad95bfd836deb7fd6afd04c75157`。
- 新 `SLOTS` 别名回复仍是成功工具结果，省略路径列，与同输入无路径基线逐字节一致。8,478 B 正文、16,204 B 线包。两张原 PNG 和其它事实保留。独立提取实际新比较逻辑，对同两条本机路径得到原路与空值。
- 143 运行源在 Git、wheel、隔离安装逐件同字节。冻结回放正例 1/1、反例 12/12、兼容 6/6、固定 CLI 六配置 6/6。60 对热文件系统中，路径投影中位 0.346 ms，完整序列化相对同候选禁用路径中位另增 0.351 ms。此次工程回放无模型或 Blender。自然模型最终引用和实际调用数留待下批。[字节证据](https://github.com/swenbo1-web/human-eye/blob/0cc8afa5082f27a3aff607bebf7793d0d4072bc9/verification/m1_target_observation_first_image_path_windows_001/checks/BYTE_CONTROLS.json)

## PERF050-TARGET-OBSERVATION-FIRST-IMAGE-P2

1. 沿用原异装配 `f74703cb` 的 350 B 原题面、`f5469ae8` 新只读副本、相同 CLI 0.152.1、原 gpt-6.1-sol／medium／default 请求、普通工具、12 业务／12 构图与 450／600 秒。固定 `95fd44bb`，运行源 `eaccba2ec88abc035c62841a765f99ecae5f50e34dd8e7867b09dc17cb6d9dc9`，wheel `e0f603f2279df4d9e08c844ad3b191449b69799c54737f2b0c178f6ef22f4fbe`。预检复放合法目标作用域、原失败拼写、普通和插件两层转发及关闭。只新增一个冷态 P2，沿用既有 Pro 授权。原 N1 5/5、P1 4/5 和实际分母保留，产品变更／构建、额外资格、替补、Google/API／新增费用均为 0。
2. 模型自行选择工具和视角。按原标准核 M09 图像、M09→M03 两整件距离及方向，同时分开查首个实际目标简报是否含合格原图路径、是否另取同一 PNG、最终原始答复是否明确引用原图，以及闭槽后是否能按同槽原图摘要打开。原生等价证明照常评分，候选字段使用单列。原冻结全场评分器的作用域误拒原样保留，新槽按实际入口、调用和帧动态配对，并以当前完整装配独立核遮挡、真源和像素。验收展示与真人点击各自留证。
3. 记录实际首包、图片块、整件范围、原答和所有新旧成本。若不触发候选入口，或最终仍漏引用，按实际记录。一次后收口，无同题补跑。结束向 `local/01a1971f-eef5-7a23-a1b1-2352beb80a77` 发 `PERF050-TARGET-OBSERVATION-FIRST-IMAGE-P2_READY`，附原始证据及完整分母。
