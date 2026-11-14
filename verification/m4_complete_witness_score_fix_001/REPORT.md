# 完整见证离线评分修复

## 结果

同一批保存证据已完成补充自动评分，原33项内容检查全部通过。最终答案正确，产品事实正确，纯直接采用为false，存在原生补核。21项离线回归控制及1项输出保护辅助检查全部通过，未出现意外失败。

| 判定来源 | 同一原样本的结果 |
| --- | --- |
| 历史首轮自动评分 | 失败0/1，终态字段KeyError |
| 管理员独立语义复核 | 正确1/1 |
| 本次派生补充自动评分 | 正确1/1，direct-only=false，原生补核=true |

这三项是同一原样本的不同判定记录。本批新增模型、产品观察、Blender和raster调用均为0，评分与回归中的网络执行为0。

## 固定来源

基线交付为 `8baad59ac6da01f14e1eb87c3e1f4f0687eb2b7d`。本批准备提交为 `8d69825a259bddd7c341f49e1941bc7ce3e889ec`，执行前2524个输入路径已冻结，摘要为 `ab5be82225ef57fcd47ef337399658417f4a59b08eb8d1c79593983323b992af`。

新材料全部位于 `verification/m4_complete_witness_score_fix_001/`。原产品仍对应d12c7ab2及141源d8ad7003…9f02，评分输入采用原 `D:/he_complete_witness_001/` 数据和原归一化答案。

| 实际生产者原件 | 字节数 | SHA256 |
| --- | ---: | --- |
| RUN_RESULT.json | 26763 | `b55da6f3f2dd40a2917db3690be66f63992c6999f5ca6a131d5d44f7e6fabe9a` |
| CONSUMER.json | 98609 | `6d920559013d6174a201b51ad01a75f89cf90826cb9dfd60a9ca564da55bcab8` |

`fixtures/`保存这两份实际原字节及来源记录，可供相同producer reader进行后续纯离线接口回归。更换生产者或包装时，应先读取实际样例核对接口，再启动昂贵消费者。

## 最小派生改动

原评分器误读逐槽记录中的execution_state。实际 `complete-witness-single-formal-v1` 生产者将该字段放在顶层，post_route_checks失败时顶层state还可能是completed。

新增小型 `terminal_reader.py`，同时核对当前schema、唯一P1/P记录、planned_routes/actual_routes/actual_CLI_processes均为1、outer_retries为0、顶层completed、launcher_succeeded为true、terminal_errors为空，以及原row和consumer有效性、来源绑定与持有退出确认。

非法结构在进入内容判定前返回精确failed_fields。计数字段采用整数类型校验，已保存正例中的真实exit_code=1和confirmed持有句柄证明可正常通过。

派生 `score_saved.py`继续依赖原固定helpers、TRUTH、NORMALIZED和原语义规则。输出增加派生版本、源码及reader身份，限定在新目录内exclusive写入。新源码为 `b444ffa6f3528ca1e775ccd6fb617b808b47ae2cf326f8ebcdb9863655f99600`，reader源码为 `b6e095a866c7fa498f700bf856d04d75aed5701c8cf44d31d4eef9c5b1f2afde`。

`DERIVED_SCORER.diff`记录完整文本差异。静态复核对注册的终态读取、提前拒绝、路径隔离和身份元数据差异做逆变后，原score/main/load的保留部分逐节点AST一致。完整性、像素、引用、覆盖、unknown及采用判据均沿原规则。

## 实际离线验收

根先通过真正的main入口对原RUN_RESULT、CONSUMER、NORMALIZED及原保存图像数组完成一次评分，使用网络、进程和产品执行审计保护，blocked_side_effects为空。随后运行固定回归矩阵。

| 注册组 | 分母 | 实际结果 |
| --- | ---: | --- |
| 同真实原件正例回归 | 1 | 通过 |
| 终态负例 | 18 | 全部按精确字段拒绝 |
| 完整性与引用负例 | 2 | 全部按精确判据拒绝 |
| 主矩阵 | 21 | 21/21通过 |
| 输出保护辅助 | 1 | FileExistsError且sentinel摘要前后相同 |

终态控制覆盖state缺失/failed、schema错误、launcher失败、postcheck错误、records缺失/多条/错slot或group、计数与retry错误，以及原row、consumer、来源绑定或退出确认失败。completed与postcheck错误并存的控制仍被拒绝。

实际SCENE负例使用原图的37917个目标像素和924个对比边界像素，其readable=true、complete=false。派生评分明确报告target_actual_complete_view和target_index_frame_consistency失败。不存在引用控制保留原TOP计数和身份，仅替换目标ref，按同一完整见证与索引绑定规则拒绝。每项检查都核对了精确错误集合，另有实际帧与阈值前提核验。

独立真实补充评分1次、主矩阵21次、输出保护1次，共23次离线评分入口。主矩阵另有21次reader直接预检，这些调用不是额外模型样本或独立三维场景。

## 原件与采用判定

回归保护的原namespace及运行目录共338个文件，执行前、执行后及收尾摘要全部相同。原首轮QUALITY、原NORMALIZED、质量seal、图像数组、模型最终答案及请求原件均有独立哈希核对。执行前2524项冻结输入亦全部匹配。

原生几何读取和全幅像素重算继续计入补核。补充评分得到target_selected_public_witness=true、product_current_facts_correct=true、correct_with_supplement_or_recomputation=true、direct_product_adoption=false。该结果沿原来的三次实际工具轨迹计算。

原首轮失败摘要仍为 `272f925f1f46b4140b7483fbeceb1ff0a2b58285d3b5c9cab6c417cbb6cb3a87`，原质量seal仍为 `93b0dde406a185bdb60c7921eb1f7d3f697e45e493763130d304828fdfdd30d9`。本次补充结果另存 `SUPPLEMENTARY_QUALITY.json`，摘要为 `f3475509ee2118a3d86187627bdf19ab22f46a88ab0abd32d0cfbff475f2babe`。

## 独立复核与边界

静态审查16项、回归作者的19项结果核验、跨作者的21项执行后复核分别通过，彼此存在重叠。原评分器作者参与了跨作者复核，作者关系在对应报告中披露。

本批关闭当前producer的离线评分接口缺陷。它支持原保存样本的补充正确性判定，模型能力、纯直接消费和性能提升分别沿各自实验流程判断。

主要证据为 `FROZEN.json`、`STATIC_REVIEW.json`、`POSITIVE_RUN.json`、`SUPPLEMENTARY_QUALITY.json`、`REGISTRY.json`、`regression_01/RESULT.json`、`REGRESSION_REPORT.json`及`POSTRUN_REVIEW.json`。输入输出和提交内容由 `FINAL_AUDIT.json`与`CONTENT_MANIFEST.json`绑定。
